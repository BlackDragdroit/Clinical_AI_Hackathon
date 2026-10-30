"""Readable report page for Dr. Hofer: what was filed, from whom, and how it was checked. Owner: AI.

The chat's "Befund öffnen" opens this page instead of the raw FHIR resource (the FHIR links stay at the bottom).
It shows patient data, so it needs the signed key `k` that only the bot's message carries: purpose "befund",
bound to one request id.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from app import audit, db
from app.config import settings
from app.core_bridge import parse_markdown
from app.security import sign, unsign

PURPOSE = "befund"
KEY_TTL_S = 30 * 24 * 3600
TZ = ZoneInfo("Europe/Vienna")
DOC = {"de": {"lab": "Laborbefund", "report": "Entlassungsbericht"}, "en": {"lab": "Lab result", "report": "Discharge report"}}
READ_BY = {"de": {"markdown": "Text", "pdf-text": "PDF", "ocr": "Foto/Scan", "llm": "Text (KI-gelesen)"},
           "en": {"markdown": "text", "pdf-text": "PDF", "ocr": "photo/scan", "llm": "text (read by AI)"}}

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def url(request_id: str) -> str:
    return f"{settings.base_url}/befund/{request_id}?k={sign({'r': request_id}, PURPOSE, KEY_TTL_S)}"


def _when(ts: str) -> str:
    return datetime.fromisoformat(ts).astimezone(TZ).strftime("%d.%m.%Y, %H:%M")


def _flag(row) -> str:
    if row.value is None:
        return ""
    if row.ref_high is not None and row.value > row.ref_high:
        return "high"
    if row.ref_low is not None and row.value < row.ref_low:
        return "low"
    return ""


@router.get("/befund/{request_id}", response_class=HTMLResponse)
def page(request: Request, request_id: str, k: str = ""):
    claims, req = unsign(k, PURPOSE), db.get("requests", "id", request_id)
    answers = db.query("SELECT * FROM answers WHERE request_id = ? AND filed_refs != '[]' ORDER BY received_at DESC",
                       (request_id,)) if req else []
    if not claims or claims.get("r") != request_id or not answers:
        return PlainTextResponse("Not found", 404)
    ans, lang = answers[0], "en" if req.get("lang") == "en" else "de"
    doc = parse_markdown(ans["content"])
    events = audit.entries(request_id)
    sent = next((e for e in events if e["event"] == "answer_sent"), None)
    read_by = (sent or {}).get("details", {}).get("read_by") if sent else None
    ctx = {
        "lang": lang, "clinic": settings.clinic_name,
        "doc": DOC[lang].get(req["doc_type"], req["doc_type"]), "kind": req["doc_type"],
        "patient": req["patient_name"], "dob": datetime.fromisoformat(req["patient_dob"]).strftime("%d.%m.%Y"),
        "patient_ref": req["patient_ref"], "org": doc.org, "title": doc.title,
        "fields": {k: v for k, v in doc.fields.items() if not k.startswith("_")},
        "rows": [{"test": r.test, "value": r.raw_value, "unit": r.unit, "ref": r.ref_raw, "loinc": r.loinc or "",
                  "flag": _flag(r)} for r in doc.rows],
        "sections": doc.sections,
        "sender": ans["verified_name"], "method": ans["identity_method"], "received": _when(ans["received_at"]),
        "filename": ans["filename"], "read_by": READ_BY[lang].get(read_by or "", read_by or ""),
        "read_back": any(e["event"] == "readback_confirmed" for e in events),
        "notes": json.loads(ans["intake_json"]).get("notes") or [],
        "refs": [(r, f"{settings.hapi_public_url}/{r}") for r in json.loads(ans["filed_refs"])],
        "request_id": request_id,
    }
    return templates.TemplateResponse(request, "report.html", ctx)
