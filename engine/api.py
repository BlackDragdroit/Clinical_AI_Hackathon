"""Engine HTTP service. Stateless: scale it by running more replicas; the models behind it batch on vLLM.

  POST /v1/request            {"text": "..."}                      -> checked request (card data)
  POST /v1/request/audio      multipart file (+ language)          -> transcript + checked request; audio not stored
  POST /v1/transcribe         multipart file                       -> transcript only
  POST /v1/document           multipart file (+ requested_loinc, requested_at, requested_doc_type)
                                                                    -> canonical Markdown, checks, read-back items
  POST /v1/document/readback  {"markdown": "...", "confirmed": {...}} -> canonical Markdown with confirmed values
  GET  /health                                                      -> which backends are configured

Run: uvicorn engine.api:app --port 8100
"""
from __future__ import annotations

import shutil
from datetime import datetime

from fastapi import FastAPI, File, Form, UploadFile
from pydantic import BaseModel

from engine import document_job, request_job
from engine.backends import asr
from engine.config import settings
from engine.patients import HapiDirectory

app = FastAPI(title="IRIS engine", version=request_job.VERSION)
_directory = HapiDirectory(settings.hapi_url) if settings.hapi_url else None


class RequestIn(BaseModel):
    text: str
    use_llm: bool = True


class ReadbackIn(BaseModel):
    markdown: str
    confirmed: dict[str, str]


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": request_job.VERSION,
            "backends": {"llm": settings.llm_model if settings.llm_url else None,
                         "asr": settings.asr_model if settings.asr_url else None,
                         "ocr": settings.ocr_model if settings.ocr_url else None,
                         "tesseract": bool(shutil.which(settings.tesseract_cmd)),
                         "patients": bool(_directory)}}


@app.post("/v1/request")
def request_text(body: RequestIn) -> dict:
    return request_job.run(body.text, _directory, use_llm=body.use_llm)


def _asr_dict(r: asr.AsrResult) -> dict:
    return {"text": r.text, "model": r.model, "ms": r.ms, "audio_sha256": r.sha256, "language": r.language, "error": r.error}


@app.post("/v1/transcribe")
async def transcribe(file: UploadFile = File(...), language: str | None = Form(None)) -> dict:
    return _asr_dict(asr.transcribe(await file.read(), file.filename or "voice.ogg", language))


@app.post("/v1/request/audio")
async def request_audio(file: UploadFile = File(...), language: str | None = Form(None)) -> dict:
    r = asr.transcribe(await file.read(), file.filename or "voice.ogg", language)
    if not r.text:
        return {"asr": _asr_dict(r), "ready": False, "ask_de": "Sprachnachricht konnte nicht transkribiert werden."}
    out = request_job.run(r.text, _directory)
    out["asr"] = _asr_dict(r)
    out["timings_ms"]["asr"] = r.ms
    return out


@app.post("/v1/document")
async def document(file: UploadFile = File(...), requested_loinc: str = Form(""), requested_at: str = Form(""),
                   requested_doc_type: str = Form("")) -> dict:
    return document_job.read(await file.read(), file.filename or "", file.content_type,
                             [c for c in requested_loinc.split(",") if c.strip()] or None,
                             datetime.fromisoformat(requested_at) if requested_at else None,
                             requested_doc_type or None)


@app.post("/v1/document/readback")
def readback(body: ReadbackIn) -> dict:
    return {"canonical_markdown": document_job.apply_readback(body.markdown, body.confirmed)}
