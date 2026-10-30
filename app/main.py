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
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app import audit, bot, dashboard, db, engine_client, i18n, intake_service, misdelivery, notify, tokens
from app.config import settings
from app.identity import eid_mock, policy
from app.security import sign, unsign

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
i18n.install(templates)
SESSION = "bb_session"
COOKIE_SECURE = settings.base_url.startswith("https://")
NEUTRAL = f"{settings.clinic_name} hat eine sichere Dokumentenanfrage an Sie gerichtet."
MAX_UPLOAD_BYTES = 10 * 2**20     # PDF, photo, scan
MAX_TEXT_BYTES = 1 * 2**20        # .md / .txt / pasted text: a real report is a few kB
log = logging.getLogger("befundbruecke.portal")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    task = asyncio.create_task(bot.start())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="BefundBrücke", lifespan=lifespan)
app.include_router(dashboard.router)


def _tr(request: Request, key: str, **kw) -> str:
    return i18n.t(key, i18n.resolve_lang(request), clinic=settings.clinic_name, **kw)


def _page(request: Request, name: str, status: int = 200, **ctx) -> HTMLResponse:
    lang, other = i18n.resolve_lang(request), i18n.other_lang(i18n.resolve_lang(request))
    # the toggle keeps only the eID page's `state`; never echo a signed assertion (callback) into a link
    keep = {"state": request.query_params["state"]} if "state" in request.query_params else {}

    def t(key: str, page_lang: str | None = None, **kw) -> str:   # portal: t(key); audit pages: t(key, lang)
        kw.setdefault("clinic", settings.clinic_name)
        return i18n.t(key, page_lang or lang, **kw)

    base = {"clinic": settings.clinic_name, "lang": lang, "other_lang": other, "t": t,
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
    typed_dob = _norm_dob(typed_dob)
    if upload is not None and upload.filename:
        data, filename, ctype = await upload.read(MAX_UPLOAD_BYTES + 1), upload.filename, upload.content_type
    else:
        data, filename, ctype = text.encode("utf-8"), "formular.md", "text/markdown"

    def form_error(msg: str, status: int = 400) -> HTMLResponse:
        return _form_error(request, raw, req, sess, msg, status)
    if not data.strip():
        return form_error(_tr(request, "portal.err_empty"))
    is_text = ctype.startswith("text/") or filename.lower().endswith((".md", ".txt"))
    if len(data) > (MAX_TEXT_BYTES if is_text else MAX_UPLOAD_BYTES):
        return form_error(_tr(request, "portal.err_too_big", mb=(MAX_TEXT_BYTES if is_text else MAX_UPLOAD_BYTES) // 2**20))
    try:   # parsing / OCR is slow: off the event loop, so one upload never stalls the portal for everyone
        eng = await run_in_threadpool(engine_client.document, data, filename, ctype,
                                      json.loads(req.get("panel_loinc") or "[]"),
                                      datetime.fromisoformat(req["created_at"]), req["doc_type"])
    except Exception:
        log.exception("engine failed on request %s", req["id"])
        return form_error(_tr(request, "portal.err_tech"), 503)
    if not eng["ok"]:
        return form_error(_tr(request, "portal.err_unreadable"))
    if eng["needs_readback"]:          # scan/photo: the sender confirms what we read before anything is processed
        rb_id = db.new_id()
        db.insert("readbacks", {"id": rb_id, "request_id": req["id"], "created_at": db.now(), "typed_name": typed_name,
                                "typed_dob": typed_dob, "filename": filename, "markdown": eng["canonical_markdown"],
                                "items": eng["readback"],
                                "engine_json": {k: eng[k] for k in ("path", "models", "flags", "check_lines_de", "input")}})
        audit.log("readback_shown", req["id"], f"eid:{sess['pseud']} {sess['name']}",
                  {"items": len(eng["readback"]), "models": eng["models"],
                   "disagree": sum(1 for i in eng["readback"] if i["agree"] is False)})
        return _page(request, "readback.html", raw=raw, rb_id=rb_id, items=eng["readback"])
    return await run_in_threadpool(_finish, request, raw, req, sess, typed_name, typed_dob, filename,
                                   eng["canonical_markdown"], eng, len(data))


def _norm_dob(s: str) -> str:
    """Phone number pads have no dot: '12031961' -> '12.03.1961'; German decimal pads give '12,03,1961'."""
    s = s.strip().replace(",", ".")
    return f"{s[:2]}.{s[2:4]}.{s[4:]}" if len(s) == 8 and s.isdigit() else s


def _form_error(request: Request, raw: str, req: dict, sess: dict, msg: str, status: int = 400) -> HTMLResponse:
    return _page(request, "answer.html", status, raw=raw, req=req, doc_label=_tr(request, f"doc.{req['doc_type']}"),
                 doctor=settings.doctor_name, sender=sess["name"], error=msg)


def _finish(request: Request, raw: str, req: dict, sess: dict, typed_name: str, typed_dob: str, filename: str,
            markdown: str, eng: dict, n_bytes: int, corrected: int | None = None) -> HTMLResponse:
    if not tokens.claim(raw):            # a second, concurrent submit of the same link
        return _invalid(request)
    actor = f"eid:{sess['pseud']} {sess['name']}"
    db.update("requests", "id", req["id"], status="answered")
    audit.log("answer_sent", req["id"], actor, {"filename": filename, "bytes": n_bytes, "read_by": eng.get("path"),
                                               "sha256": (eng.get("input") or {}).get("sha256")})
    method = sess["method"]
    notes = list(eng.get("check_lines_de") or []) + [f"⚠️ {f}" for f in eng.get("flags") or []]
    if corrected is not None:
        method += "; Werte vom Absender per Read-back bestätigt"
        notes.append(f"Scan/Foto gelesen ({(eng.get('models') or {}).get('ocr_vlm') or 'OCR'}), Werte vom Absender bestätigt"
                     + (f", {corrected} korrigiert" if corrected else ""))
    try:
        out = intake_service.process_answer(req, verified_name=sess["name"], identity_method=method, actor=actor,
                                            typed_name=typed_name, typed_dob=typed_dob, filename=filename,
                                            content=markdown, engine_notes=notes,
                                            doc_type_mismatch=(eng.get("checks") or {}).get("doc_type"))
    except Exception as e:
        return _processing_failed(request, raw, req, sess, e)
    return _page(request, "receipt.html", ok=out["decision"] != "reject", receipt=out["answer_id"],
                 message=_tr(request, f"portal.done_{out['decision']}"))


def _processing_failed(request: Request, raw: str, req: dict, sess: dict, e: Exception) -> HTMLResponse:
    """E.g. HAPI down. If nothing was filed, give the link back so the sender can simply send again."""
    log.exception("processing answer for request %s failed", req["id"])
    filed = db.query("SELECT 1 FROM answers WHERE request_id = ? AND filed_refs != '[]'", (req["id"],))
    if filed:   # resources are on HAPI, a later step failed: never offer a second filing
        notify.doctor(f"⚠️ Antwort zu Anfrage {req['id']} abgelegt, danach technischer Fehler ({type(e).__name__}). "
                      f"Bitte Task und Ressourcen auf dem FHIR-Server prüfen.", req["id"])
        return _page(request, "receipt.html", ok=True, receipt=req["id"], message=_tr(request, "portal.done_review"))
    tokens.reopen(raw)
    db.update("requests", "id", req["id"], status="identified")
    notify.doctor(f"⚠️ Antwort zu Anfrage {req['id']} konnte nicht verarbeitet werden (technischer Fehler: "
                  f"{type(e).__name__}). Nichts abgelegt. Der Link bleibt gültig, der Absender kann erneut senden.", req["id"])
    return _form_error(request, raw, req, sess, _tr(request, "portal.err_tech"), 503)


@app.post("/r/{raw}/readback", response_class=HTMLResponse)
async def readback_confirm(request: Request, raw: str):
    tok, sess = tokens.resolve(raw), _session(request, raw)
    form = await request.form()
    rb = db.get("readbacks", "id", str(form.get("rb_id", "")))
    if not tok or not sess or not rb or rb["request_id"] != tok["request_id"]:
        return _invalid(request)
    req = db.get("requests", "id", tok["request_id"])
    items = json.loads(rb["items"])
    confirmed = {i["key"]: str(form.get(f"v:{i['key']}", i["value"] or "")).strip() for i in items}
    changed = [i["key"] for i in items if confirmed[i["key"]] != (i["value"] or "")]
    audit.log("readback_confirmed", req["id"], f"eid:{sess['pseud']} {sess['name']}", {"items": len(items), "changed": changed})
    markdown = engine_client.apply_readback(rb["markdown"], confirmed)
    return await run_in_threadpool(_finish,request, raw, req, sess, rb["typed_name"], rb["typed_dob"], rb["filename"], markdown,
                   json.loads(rb["engine_json"]), len(markdown.encode()), corrected=len(changed))


@app.get("/sms", response_class=HTMLResponse)
def sms_inbox(request: Request):
    return _page(request, "sms_inbox.html", messages=db.query("SELECT * FROM sms_outbox ORDER BY id DESC"))


@app.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, request_id: str | None = None):
    # clinic-internal: in production this sits behind the clinic login (footer says so)
    lang = i18n.resolve_lang(request)
    resp = _page(request, "audit.html", v=audit.view(request_id, lang), lang=lang, other_lang=i18n.other_lang)   # audit templates call other_lang(lang)
    if request.query_params.get("lang"):
        i18n.remember(resp, lang)
    return resp


@app.get("/audit/apple", response_class=HTMLResponse)
def audit_page_apple(request: Request, request_id: str | None = None):
    # same data and query params as /audit, second look (formal audit record) for side-by-side review
    lang = i18n.resolve_lang(request)
    resp = _page(request, "audit_apple.html", v=audit.view(request_id, lang, base="/audit/apple"), lang=lang, other_lang=i18n.other_lang)
    if request.query_params.get("lang"):
        i18n.remember(resp, lang)
    return resp


@app.get("/audit.json")
def audit_json(request_id: str | None = None):
    v = audit.view(request_id)
    return JSONResponse({"chain_ok": v["chain_ok"], "coverage": v["coverage"], "entries": audit.entries(request_id),
                         "first_broken": v["first_broken"], "entry_count": v["entry_count"], "last_hash": v["head"],
                         "request_id": v["request_id"],
                         "requests": [{k: r[k] for k in ("id", "status", "patient_ref", "expected_name", "contact",
                                                         "covered", "misdelivery")} for r in v["requests"]],
                         "misdelivery": {code: [{"request_id": m["request_id"], "seq": m["seq"]} for m in found]
                                         for code, found in v["misdelivery"].items()}})
