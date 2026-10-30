"""Engine settings from the environment. Every model sits behind an OpenAI-compatible URL (vLLM on the GPU box);
an empty URL switches that stage to its CPU fallback (rules / tiny models), so the engine always answers."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class EngineSettings:
    # text -> JSON (request job + document fallback)
    llm_url: str = _env("ENGINE_LLM_URL", "")                         # e.g. http://gpu:8001/v1 ; "" = rules only
    llm_model: str = _env("ENGINE_LLM_MODEL", "numind/NuExtract3")
    llm_mode: str = _env("ENGINE_LLM_MODE", "nuextract")               # nuextract | json_schema
    llm_fields: str = _env("ENGINE_LLM_FIELDS", "all")                 # all | core (4 fields, -22 % time on CPU; request_job.CORE)
    llm_api_key: str = _env("ENGINE_LLM_API_KEY", "")                  # "" = no Authorization header (local servers)
    # speech -> text
    asr_url: str = _env("ENGINE_ASR_URL", "")                          # e.g. http://gpu:8002/v1
    asr_model: str = _env("ENGINE_ASR_MODEL", "Qwen/Qwen3-ASR-1.7B")
    # image -> text (scans, phone photos, image-only PDFs)
    ocr_url: str = _env("ENGINE_OCR_URL", "")                          # e.g. http://gpu:8003/v1
    ocr_model: str = _env("ENGINE_OCR_MODEL", "PaddlePaddle/PaddleOCR-VL-1.6")
    tesseract_cmd: str = _env("ENGINE_TESSERACT", "tesseract")         # classic OCR, the independent second reader
    # patient directory (the clinic's FHIR server); "" = no lookup, only explicit Patient/<id>
    hapi_url: str = _env("ENGINE_HAPI_URL", _env("HAPI_URL", ""))
    timeout_s: float = float(_env("ENGINE_TIMEOUT_S", "30"))
    lab_max_age_days: int = int(_env("ENGINE_LAB_MAX_AGE_DAYS", "14"))  # recency check for lab results


settings = EngineSettings()
