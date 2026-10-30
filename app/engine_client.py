"""The app's door to the engine. ENGINE_URL set -> HTTP to the engine service (the deployed setup);
unset -> the engine runs in-process (dev, tests), with patients looked up through app.fhir_client."""
from __future__ import annotations

import os
from datetime import datetime

import httpx

from app import fhir_client

ENGINE_URL = os.environ.get("ENGINE_URL", "")


class _AppDirectory:
    def read(self, ref: str) -> dict | None:
        try:
            p = fhir_client.read_patient(ref)
        except Exception:
            return None
        return {"ref": ref, "name": p["name"], "dob": p["dob"]}

    def search(self, family: str | None, birthdate: str | None) -> list[dict]:
        return fhir_client.search_patients(family, birthdate)


def _post(path: str, **kw) -> dict:
    r = httpx.post(f"{ENGINE_URL.rstrip('/')}{path}", timeout=120, **kw)
    r.raise_for_status()
    return r.json()


def _with_patient(res: dict) -> dict:
    if (res.get("patient") or {}).get("status") == "no_directory":
        from engine import request_job
        res = request_job.resolve_patient(res, _AppDirectory())
    return res


def request_text(text: str) -> dict:
    if ENGINE_URL:
        return _with_patient(_post("/v1/request", json={"text": text}))
    from engine import request_job
    return request_job.run(text, _AppDirectory())


def request_audio(audio: bytes, filename: str = "voice.ogg") -> dict:
    if ENGINE_URL:
        return _with_patient(_post("/v1/request/audio", files={"file": (filename, audio)}))
    from engine import request_job
    from engine.backends import asr
    r = asr.transcribe(audio, filename)
    asr_info = {"text": r.text, "model": r.model, "ms": r.ms, "audio_sha256": r.sha256, "error": r.error}
    if not r.text:
        return {"asr": asr_info, "ready": False, "ask_de": "Sprachnachricht konnte nicht transkribiert werden."}
    out = request_job.run(r.text, _AppDirectory())
    out["asr"] = asr_info
    return out


def document(data: bytes, filename: str, content_type: str | None, requested_loinc: list[str] | None,
             requested_at: datetime | None, requested_doc_type: str | None) -> dict:
    if ENGINE_URL:
        return _post("/v1/document", files={"file": (filename, data, content_type or "application/octet-stream")},
                     data={"requested_loinc": ",".join(requested_loinc or []),
                           "requested_at": requested_at.isoformat() if requested_at else "",
                           "requested_doc_type": requested_doc_type or ""})
    from engine import document_job
    return document_job.read(data, filename, content_type, requested_loinc, requested_at, requested_doc_type)


def apply_readback(markdown: str, confirmed: dict[str, str]) -> str:
    if ENGINE_URL:
        return _post("/v1/document/readback", json={"markdown": markdown, "confirmed": confirmed})["canonical_markdown"]
    from engine import document_job
    return document_job.apply_readback(markdown, confirmed)
