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
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import audit, bot, db, engine_client, intake_service, misdelivery, notify, tokens
from app.config import settings
from app.identity import eid_mock, policy
from app.security import sign, unsign

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
SESSION = "bb_session"
NEUTRAL = f"{settings.clinic_name} hat eine sichere Dokumentenanfrage an Sie gerichtet."
DOC_LABEL = {"lab": "Laborbefund", "report": "Entlassungsbericht"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    task = asyncio.create_task(bot.start())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="BefundBrücke", lifespan=lifespan)


def _page(request: Request, name: str, status: int = 200, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, {"clinic": settings.clinic_name, **ctx}, status_code=status)


def _invalid(request: Request) -> HTMLResponse:
    # same page for unknown / expired / used / blocked links: a guesser learns nothing
    return _page(request, "invalid.html", 404)


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
    return _page(request, "landing.html", neutral=NEUTRAL, raw=raw)


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
        return _page(request, "identity_failed.html", 403)
    audit.log("identity_checked", req["id"], actor, {"result": "OK", "method": "eid-mock", "loa": who.loa})
    db.update("requests", "id", req["id"], status="identified")
    resp = RedirectResponse(f"/r/{raw}/answer", status_code=303)
    cookie = sign({"th": tokens.token_hash(raw), "name": who.full_name, "pseud": who.pseudonym,
                   "method": policy.identity_method_text(who)}, "portal", 3600)
    resp.set_cookie(SESSION, cookie, httponly=True, samesite="lax", max_age=3600)   # TODO(SWE 2): secure=True behind HTTPS
    return resp


@app.get("/r/{raw}/answer", response_class=HTMLResponse)
def answer_form(request: Request, raw: str):
    tok, sess = tokens.resolve(raw), _session(request, raw)
    if not tok or not sess:
        return _invalid(request)
    req = db.get("requests", "id", tok["request_id"])
    audit.log("patient_revealed", req["id"], f"eid:{sess['pseud']} {sess['name']}", {"after": "identity_checked OK"})
    return _page(request, "answer.html", raw=raw, req=req, doc_label=DOC_LABEL[req["doc_type"]],
                 doctor=settings.doctor_name, sender=sess["name"])


@app.post("/r/{raw}/answer", response_class=HTMLResponse)
async def answer_submit(request: Request, raw: str, typed_name: str = Form(...), typed_dob: str = Form(...),
                        text: str = Form(""), upload: UploadFile | None = File(None)):
    tok, sess = tokens.resolve(raw), _session(request, raw)
    if not tok or not sess:
        return _invalid(request)
    req = db.get("requests", "id", tok["request_id"])
    if upload is not None and upload.filename:
        data, filename, ctype = await upload.read(), upload.filename, upload.content_type
    else:
        data, filename, ctype = text.encode("utf-8"), "formular.md", "text/markdown"

    def form_error(msg: str) -> HTMLResponse:
        return _page(request, "answer.html", 400, raw=raw, req=req, doc_label=DOC_LABEL[req["doc_type"]],
                     doctor=settings.doctor_name, sender=sess["name"], error=msg)
    if not data.strip():
        return form_error("Bitte Datei hochladen oder Text eingeben.")
    eng = engine_client.document(data, filename, ctype, json.loads(req.get("panel_loinc") or "[]"),
                                 datetime.fromisoformat(req["created_at"]), req["doc_type"])
    if not eng["ok"]:
        return form_error("Das Dokument konnte nicht sicher gelesen werden. Bitte als PDF/Text senden oder den Inhalt einfügen.")
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
    return _finish(request, raw, req, sess, typed_name, typed_dob, filename, eng["canonical_markdown"], eng, len(data))


def _finish(request: Request, raw: str, req: dict, sess: dict, typed_name: str, typed_dob: str, filename: str,
            markdown: str, eng: dict, n_bytes: int, corrected: int | None = None) -> HTMLResponse:
    tokens.mark_used(raw)
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
    out = intake_service.process_answer(req, verified_name=sess["name"], identity_method=method, actor=actor,
                                        typed_name=typed_name, typed_dob=typed_dob, filename=filename, content=markdown,
                                        engine_notes=notes)
    return _page(request, "receipt.html", message=out["sender_message_de"], receipt=out["answer_id"])


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
    return _finish(request, raw, req, sess, rb["typed_name"], rb["typed_dob"], rb["filename"], markdown,
                   json.loads(rb["engine_json"]), len(markdown.encode()), corrected=len(changed))


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
