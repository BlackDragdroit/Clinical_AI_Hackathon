"""Speech -> text. GPU: Qwen3-ASR-1.7B (German + English, language detection) behind vLLM's OpenAI-compatible
/v1/audio/transcriptions. The prompt carries domain words (known lab names, test names) as a vocabulary hint.
CPU fallback: Parakeet TDT 0.6B v3 via onnx-asr, if installed (`uv sync --group cpu-asr`).

Audio is processed in memory and never written to disk; only its SHA-256 and duration go to the audit log.
"""
from __future__ import annotations

import hashlib
import io
import time
from dataclasses import dataclass

import httpx

from engine.config import settings

VOCAB = ("Gerinnung, INR, aPTT, Thrombozyten, Fibrinogen, Blutbild, Entlassungsbericht, Reha, Labor, Befund, "
         "Kreatinin, CRP, Patientin, geboren, punkt, at, minus, coagulation, discharge report")


@dataclass
class AsrResult:
    text: str | None
    model: str
    ms: int
    sha256: str
    language: str | None = None
    error: str | None = None


def transcribe(audio: bytes, filename: str = "voice.ogg", language: str | None = None, vocab: str = VOCAB) -> AsrResult:
    sha = hashlib.sha256(audio).hexdigest()
    t0 = time.perf_counter()
    if settings.asr_url:
        data = {"model": settings.asr_model, "prompt": f"Vocabulary: {vocab}", "response_format": "json", "temperature": "0"}
        if language:
            data["language"] = language
        try:
            r = httpx.post(f"{settings.asr_url.rstrip('/')}/audio/transcriptions", data=data,
                           files={"file": (filename, audio)}, timeout=max(settings.timeout_s, 60))
            r.raise_for_status()
            j = r.json()
            return AsrResult(j.get("text", "").strip(), settings.asr_model, int((time.perf_counter() - t0) * 1000), sha,
                             j.get("language"))
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
    else:
        err = "no ASR model configured"
    try:  # CPU fallback
        import onnx_asr  # type: ignore
        import soundfile  # type: ignore
        wav, sr = soundfile.read(io.BytesIO(audio), dtype="float32")
        if getattr(wav, "ndim", 1) > 1:
            wav = wav.mean(axis=1)
        model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", quantization="int8")
        text = model.recognize(wav, sample_rate=sr)
        return AsrResult(str(text).strip(), "parakeet-tdt-0.6b-v3 int8 (CPU)", int((time.perf_counter() - t0) * 1000), sha)
    except Exception as e:  # not installed or unreadable audio
        return AsrResult(None, "", int((time.perf_counter() - t0) * 1000), sha, error=f"{err}; cpu: {type(e).__name__}: {e}"[:300])
