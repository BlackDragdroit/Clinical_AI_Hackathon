"""FastAPI app: outside portal, mock eID, SMS inbox, audit page, bot task. Portal owner: SWE 2.

Outside flow (each step audited):
  GET  /r/{t}             link opened -> neutral page, "Mit ID Austria anmelden"
  GET  /eid/authorize     mock IdP: pick a test citizen
  POST /eid/authorize     -> redirect /r/{t}/callback?assertion=…
  GET  /r/{t}/callback    identity checked: eID name must match the expected person, else blocked
  GET  /r/{t}/answer      patient + request revealed (need-to-know), answer form
  POST /r/{t}/answer      answer sent -> intake_service (file / review / reject) -> receipt
"""
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import audit, bot, db, i18n, intake_service, misdelivery, notify, tokens
from app.config import settings
from app.identity import eid_mock, policy
from app.security import sign, unsign

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
SESSION = "bb_session"
COOKIE_SECURE = settings.base_url.startswith("https://")
NEUTRAL = f"{settings.clinic_name} hat eine sichere Dokumentenanfrage an Sie gerichtet."


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    task = asyncio.create_task(bot.start())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="BefundBrücke", lifespan=lifespan)


def _tr(request: Request, key: str, **kw) -> str:
    return i18n.t(key, i18n.resolve_lang(request), clinic=settings.clinic_name, **kw)


def _page(request: Request, name: str, status: int = 200, **ctx) -> HTMLResponse:
    lang, other = i18n.resolve_lang(request), i18n.other_lang(i18n.resolve_lang(request))
    # the toggle keeps only the eID page's `state`; never echo a signed assertion (callback) into a link
    keep = {"state": request.query_params["state"]} if "state" in request.query_params else {}
    base = {"clinic": settings.clinic_name, "lang": lang, "other_lang": other,
            "t": lambda key, **kw: i18n.t(key, lang, clinic=settings.clinic_name, **kw),
            "switch_href": f"{request.url.path}?{urlencode({**keep, 'lang': other})}"}
    resp = templates.TemplateResponse(request, name, {**base, **ctx}, status_code=status)
    if "lang" in request.query_params:
        i18n.remember(resp, lang, secure=COOKIE_SECURE)
    return resp


def _invalid(request: Request) -> HTMLResponse:
    # same page for unknown / expired / used / blocked links: a guesser learns nothing
    return _page(request, "invalid.html", 404)


def _block(req: dict, actor: str) -> None:
    """Identity attempts exhausted: block the request and alert Dr. Hofer exactly once."""
    if db.get("requests", "id", req["id"])["status"] == "blocked":
        return
    db.update("requests", "id", req["id"], status="blocked")
    audit.log("request_blocked", req["id"], actor,
              {"reason": "identity attempts exhausted", "attempts": settings.max_identity_attempts})
    notify.doctor(f"🔒 Anfrage {req['id']} gesperrt: {settings.max_identity_attempts} fehlgeschlagene "
                  f"Identitätsprüfungen. Der Link ist deaktiviert. Für einen neuen Versuch bitte eine neue Anfrage "
                  f"stellen (!anfrage …) und die Adresse prüfen.", req["id"])


def _who(request: Request) -> str:
    return f"link ip={request.client.host if request.client else '?'}"


def _session(request: Request, raw: str) -> dict | None:
    s = unsign(request.cookies.get(SESSION, ""), "portal")
    return s if s and s.get("th") == tokens.token_hash(raw) else None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/r/{raw}", response_class=HTMLResponse)
def open_link(request: Request, raw: str):
    tok = tokens.resolve(raw)
    if not tok:
        return _invalid(request)
    req = db.get("requests", "id", tok["request_id"])
    if req["status"] == "sent":
        db.update("requests", "id", req["id"], status="opened")
    audit.log("link_opened", req["id"], _who(request),
              {"user_agent": request.headers.get("user-agent", ""), "status": req["status"]})
    return _page(request, "landing.html", neutral=_tr(request, "portal.neutral"), raw=raw)


@app.get("/eid/authorize", response_class=HTMLResponse)
def eid_page(request: Request, state: str):
    return _page(request, "eid_mock.html", state=state, citizens=eid_mock.TEST_CITIZENS)


@app.post("/eid/authorize")
def eid_login(state: str = Form(...), citizen: str = Form(...)):
    return RedirectResponse(f"/r/{state}/callback?assertion={eid_mock.issue(citizen)}", status_code=303)


@app.get("/r/{raw}/callback", response_class=HTMLResponse)
def eid_callback(request: Request, raw: str, assertion: str):
    tok = tokens.resolve(raw)
    who = eid_mock.verify(assertion)
    if not tok or not who:
        return _invalid(request)
    req = db.get("requests", "id", tok["request_id"])
    actor = f"eid:{who.pseudonym} {who.full_name}"
    if not policy.names_match(req["expected_name"], who):
        attempts = tokens.count_failed_attempt(raw)
        label = misdelivery.classify_identity_failure(req)
        audit.log("identity_checked", req["id"], actor,
                  {"result": "FAILED", "method": "eid-mock", "loa": who.loa, "attempt": attempts})
        audit.log("misdelivery_caught", req["id"], actor,
                  {"type": label, "verified": who.full_name, "expected": req["expected_name"]})
        notify.doctor(f"⚠️ Fehlzustellung erkannt (Anfrage {req['id']}): verifiziert {who.full_name} ≠ "
                      f"{req['expected_name']}. Nichts offengelegt, nichts abgelegt.", req["id"])
        if attempts >= settings.max_identity_attempts:
            _block(req, actor)
            return _invalid(request)        # same neutral page as any dead link
        return _page(request, "identity_failed.html", 403)
    audit.log("identity_checked", req["id"], actor, {"result": "OK", "method": "eid-mock", "loa": who.loa})
    db.update("requests", "id", req["id"], status="identified")
    resp = RedirectResponse(f"/r/{raw}/answer", status_code=303)
    cookie = sign({"th": tokens.token_hash(raw), "name": who.full_name, "pseud": who.pseudonym,
                   "method": policy.identity_method_text(who)}, "portal", 3600)
    resp.set_cookie(SESSION, cookie, httponly=True, samesite="lax", max_age=3600, secure=COOKIE_SECURE)
    return resp


@app.get("/r/{raw}/answer", response_class=HTMLResponse)
def answer_form(request: Request, raw: str):
    tok, sess = tokens.resolve(raw), _session(request, raw)
    if not tok or not sess:
        return _invalid(request)
    req = db.get("requests", "id", tok["request_id"])
    audit.log("patient_revealed", req["id"], f"eid:{sess['pseud']} {sess['name']}", {"after": "identity_checked OK"})
    return _page(request, "answer.html", raw=raw, req=req, doc_label=_tr(request, f"doc.{req['doc_type']}"),
                 doctor=settings.doctor_name, sender=sess["name"])


@app.post("/r/{raw}/answer", response_class=HTMLResponse)
async def answer_submit(request: Request, raw: str, typed_name: str = Form(...), typed_dob: str = Form(...),
                        text: str = Form(""), upload: UploadFile | None = File(None)):
    tok, sess = tokens.resolve(raw), _session(request, raw)
    if not tok or not sess:
        return _invalid(request)
    req = db.get("requests", "id", tok["request_id"])
    if upload is not None and upload.filename:
        content, filename = (await upload.read()).decode("utf-8", errors="replace"), upload.filename
        # TODO(SWE 2 + MedEng): PDF upload -> text extraction, or store as attachment + review
    else:
        content, filename = text, "formular.md"
    if not content.strip():
        return _page(request, "answer.html", 400, raw=raw, req=req, doc_label=_tr(request, f"doc.{req['doc_type']}"),
                     doctor=settings.doctor_name, sender=sess["name"], error=_tr(request, "portal.err_empty"))
    tokens.mark_used(raw)
    actor = f"eid:{sess['pseud']} {sess['name']}"
    db.update("requests", "id", req["id"], status="answered")
    audit.log("answer_sent", req["id"], actor, {"filename": filename, "bytes": len(content.encode())})
    out = intake_service.process_answer(req, verified_name=sess["name"], identity_method=sess["method"], actor=actor,
                                        typed_name=typed_name, typed_dob=typed_dob, filename=filename, content=content)
    return _page(request, "receipt.html", message=out["sender_message_de"], receipt=out["answer_id"])


@app.get("/sms", response_class=HTMLResponse)
def sms_inbox(request: Request):
    return _page(request, "sms_inbox.html", messages=db.query("SELECT * FROM sms_outbox ORDER BY id DESC"))


@app.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, request_id: str | None = None):
    # TODO(MedEng): filter UI, coverage per request, chain status badge; protect behind clinic login in prod
    return _page(request, "audit.html", entries=audit.entries(request_id), chain_ok=audit.verify_chain(),
                 coverage=audit.coverage(request_id))


@app.get("/audit.json")
def audit_json(request_id: str | None = None):
    return JSONResponse({"chain_ok": audit.verify_chain(), "coverage": audit.coverage(request_id),
                         "entries": audit.entries(request_id)})
