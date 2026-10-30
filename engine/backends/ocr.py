"""Image -> text, two independent readers.

  vlm        a document VLM on vLLM (default PaddleOCR-VL-1.6) that writes Markdown with tables.
  tesseract  classic OCR (deu+eng) on the CPU. It barely "corrects" text, which is why it is the second reader:
             a value from the VLM counts as agreed only if Tesseract read the same characters.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass

import httpx

from engine.config import settings

PROMPT = os.environ.get("ENGINE_OCR_PROMPT", "Convert this document page to Markdown. Keep every table as a Markdown "
                        "table. Copy all characters exactly, including digits, units and umlauts. Do not correct anything.")


@dataclass
class OcrResult:
    text: str | None
    model: str
    ms: int
    error: str | None = None


def _html_tables_to_md(s: str) -> str:
    """Some OCR models emit <table> HTML; turn it into pipe tables."""
    def conv(m: re.Match) -> str:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S | re.I)
        cells = [[re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S | re.I)] for r in rows]
        cells = [c for c in cells if c]
        if not cells:
            return ""
        md = ["| " + " | ".join(cells[0]) + " |", "|" + "---|" * len(cells[0])]
        return "\n".join(md + ["| " + " | ".join(c) + " |" for c in cells[1:]])
    return re.sub(r"<table.*?</table>", conv, s, flags=re.S | re.I)


def vlm(png: bytes) -> OcrResult:
    if not settings.ocr_url:
        return OcrResult(None, "", 0, "no OCR model configured")
    t0 = time.perf_counter()
    body = {"model": settings.ocr_model, "temperature": 0, "max_tokens": 4096,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}},
                {"type": "text", "text": PROMPT}]}]}
    try:
        r = httpx.post(f"{settings.ocr_url.rstrip('/')}/chat/completions", json=body, timeout=max(settings.timeout_s, 60))
        r.raise_for_status()
        text = _html_tables_to_md(r.json()["choices"][0]["message"]["content"])
        return OcrResult(text, settings.ocr_model, int((time.perf_counter() - t0) * 1000))
    except Exception as e:
        return OcrResult(None, settings.ocr_model, int((time.perf_counter() - t0) * 1000), f"{type(e).__name__}: {e}"[:200])


def tesseract(png: bytes) -> OcrResult:
    exe = shutil.which(settings.tesseract_cmd)
    if not exe:
        return OcrResult(None, "", 0, "tesseract not installed")
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "page.png")
        with open(p, "wb") as fh:
            fh.write(png)
        try:
            out = subprocess.run([exe, p, "stdout", "-l", "deu+eng", "--psm", "6"], capture_output=True, timeout=60)
            text = out.stdout.decode("utf-8", errors="replace")
            return OcrResult(text, "tesseract-5 deu+eng", int((time.perf_counter() - t0) * 1000),
                             None if out.returncode == 0 else out.stderr.decode(errors="replace")[:200])
        except Exception as e:
            return OcrResult(None, "tesseract", int((time.perf_counter() - t0) * 1000), f"{type(e).__name__}: {e}"[:200])
