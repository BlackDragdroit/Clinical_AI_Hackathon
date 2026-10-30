"""Public-facing portal routes. Owner: SWE 2.

Routes exposed here are reachable by outside senders (patients, family members). They handle the
link-open → eID → answer → receipt flow plus the simulated SMS inbox and health check.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app import audit, db, engine_client, i18n, intake_service, misdelivery, notify, tokens
from app.config import settings
from app.identity import eid_mock, policy
from app.security import sign, unsign

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
i18n.install(templates)
SESSION = "bb_session"
COOKIE_SECURE = settings.base_url.startswith("https://")
NEUTRAL = f"{settings.clinic_name} hat eine sichere Dokumentenanfrage an Sie gerichtet."
MAX_UPLOAD_BYTES = 10 * 2**20
MAX_TEXT_BYTES = 1 * 2**20
log = logging.getLogger("befundbruecke.portal")


def _tr(request: Request, key: str, **kw) -> str:
    return i18n.t(key, i18n.resolve_lang(request), clinic=settings.clinic_name, **kw)


def _page(request: Request, name: str, status: int = 200, **ctx) -> HTMLResponse:
    lang, other = i18n.resolve_lang(request), i18n.other_lang(i18n.resolve_lang(request))
    keep = {"state": request.query_params["state"]} if "state" in request.query_params else {}

    def t(key: str, page_lang: str | None = None, **kw) -> str:
        kw.setdefault("clinic", settings.clinic_name)
        return i18n.t(key, page_lang or lang, **kw)

    base = {"clinic": settings.clinic_name, "lang": lang, "other_lang": other, "t": t,
            "switch_href": f"{request.url.path}?{urlencode({**keep, 'lang': other})}"}
    resp = templates.TemplateResponse(request, name, {**base, **ctx}, status_code=status)
    if "lang" in request.query_params:
        i18n.remember(resp, lang, secure=COOKIE_SECURE)
    return resp


def _invalid(request: Request) -> HTMLResponse:
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


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.get("/r/{raw}", response_class=HTMLResponse)
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


@router.get("/eid/authorize", response_class=HTMLResponse)
def eid_page(request: Request, state: str):
    return _page(request, "eid_mock.html", state=state, citizens=eid_mock.TEST_CITIZENS)


@router.post("/eid/authorize")
def eid_login(state: str = Form(...), citizen: str = Form(...)):
    return RedirectResponse(f"/r/{state}/callback?assertion={eid_mock.issue(citizen, link_token=state)}", status_code=303)


@router.get("/r/{raw}/callback", response_class=HTMLResponse)
def eid_callback(request: Request, raw: str, assertion: str):
    tok = tokens.resolve(raw)
    who = eid_mock.verify(assertion, link_token=raw)
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
        if attempts == 1:
            notify.doctor(f"⚠️ Identitätsprüfung fehlgeschlagen (1. Versuch von {settings.max_identity_attempts}): "
                          f"verifiziert {who.full_name} ≠ {req['expected_name']}. Nichts offengelegt.", req["id"])
        if attempts >= settings.max_identity_attempts:
            _block(req, actor)
            return _invalid(request)
        return _page(request, "identity_failed.html", 403)
    audit.log("identity_checked", req["id"], actor, {"result": "OK", "method": "eid-mock", "loa": who.loa})
    db.update("requests", "id", req["id"], status="identified")
    resp = RedirectResponse(f"/r/{raw}/answer", status_code=303)
    cookie = sign({"th": tokens.token_hash(raw), "name": who.full_name, "pseud": who.pseudonym,
                   "method": policy.identity_method_text(who)}, "portal", 3600)
    resp.set_cookie(SESSION, cookie, httponly=True, samesite="lax", max_age=3600, secure=COOKIE_SECURE)
    return resp


@router.get("/r/{raw}/answer", response_class=HTMLResponse)
def answer_form(request: Request, raw: str):
    tok, sess = tokens.resolve(raw), _session(request, raw)
    if not tok or not sess:
        return _invalid(request)
    req = db.get("requests", "id", tok["request_id"])
    audit.log("patient_revealed", req["id"], f"eid:{sess['pseud']} {sess['name']}", {"after": "identity_checked OK"})
    return _page(request, "answer.html", raw=raw, req=req, doc_label=_tr(request, f"doc.{req['doc_type']}"),
                 doctor=settings.doctor_name, sender=sess["name"])


@router.post("/r/{raw}/answer", response_class=HTMLResponse)
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
    try:
        eng = await run_in_threadpool(engine_client.document, data, filename, ctype,
                                      json.loads(req.get("panel_loinc") or "[]"),
                                      datetime.fromisoformat(req["created_at"]), req["doc_type"])
    except Exception:
        log.exception("engine failed on request %s", req["id"])
        return form_error(_tr(request, "portal.err_tech"), 503)
    if not eng["ok"]:
        return form_error(_tr(request, "portal.err_unreadable"))
    if eng["needs_readback"]:
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
    if not tokens.claim(raw):
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
    if filed:
        notify.doctor(f"⚠️ Antwort zu Anfrage {req['id']} abgelegt, danach technischer Fehler ({type(e).__name__}). "
                      f"Bitte Task und Ressourcen auf dem FHIR-Server prüfen.", req["id"])
        return _page(request, "receipt.html", ok=True, receipt=req["id"], message=_tr(request, "portal.done_review"))
    tokens.reopen(raw)
    db.update("requests", "id", req["id"], status="identified")
    notify.doctor(f"⚠️ Antwort zu Anfrage {req['id']} konnte nicht verarbeitet werden (technischer Fehler: "
                  f"{type(e).__name__}). Nichts abgelegt. Der Link bleibt gültig, der Absender kann erneut senden.", req["id"])
    return _form_error(request, raw, req, sess, _tr(request, "portal.err_tech"), 503)


@router.post("/r/{raw}/readback", response_class=HTMLResponse)
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
    return await run_in_threadpool(_finish, request, raw, req, sess, rb["typed_name"], rb["typed_dob"], rb["filename"], markdown,
                   json.loads(rb["engine_json"]), len(markdown.encode()), corrected=len(changed))


@router.get("/sms", response_class=HTMLResponse)
def sms_inbox(request: Request):
    return _page(request, "sms_inbox.html", messages=db.query("SELECT * FROM sms_outbox ORDER BY id DESC"))
