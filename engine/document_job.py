"""Document job: whatever the outside person uploads -> Markdown in the scenario shape + checks.

  Markdown/text  core parser first (exact). Only if it cannot find patient + content does the model read it,
                 and then only values that occur verbatim in the text survive.
  PDF            text layer -> Markdown (exact characters), same as above; image-only PDF -> OCR.
  Scan/photo     two readers (document VLM + Tesseract). Never filed straight away: the sender confirms the
                 values on a read-back screen; values the two readers disagree on are highlighted there.

The output's `canonical_markdown` is what goes into core.intake.run_intake, so the patient check and the FHIR
build stay exactly the code the jury's Markdown documents go through.
"""
from __future__ import annotations

import hashlib
import io
import re
import time
from datetime import datetime

from engine import canonical, checks, pdf
from engine._core import ParsedDoc, parse_markdown
from engine.backends import llm, ocr
from engine.ground import locate

VERSION = "engine-0.1"
DOC_FIELDS = {
    "organisation": "string", "title": "string", "patient_name": "string", "patient_birth_date": "string",
    "sample_taken": "string", "reported": "string", "signed_by": "string",
    "rows": {"array": {"test": "string", "result": "string", "unit": "string", "reference_range": "string", "loinc": "string"}},
}
DOC_INSTRUCTIONS = (
    "You read a medical document (lab report or discharge report, German or English). Return JSON. Copy every "
    "string exactly as written in the document, character for character; never compute, convert or correct a "
    "value. Use null when the document does not contain it. rows = one entry per lab test in the results table."
)
NUMERIC = ("result", "reference_range", "loinc")


def sniff(data: bytes, filename: str = "", content_type: str | None = None) -> str:
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP") \
            or data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image"
    name = (filename or "").lower()
    if name.endswith((".md", ".markdown")) or (content_type or "").endswith("markdown"):
        return "markdown"
    try:
        data.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "unknown"


def parser_ok(doc: ParsedDoc) -> bool:
    return bool(doc.patient_name and doc.patient_dob and (doc.rows or doc.sections or doc.kind == "report"))


def summary(doc: ParsedDoc) -> dict:
    return {"kind": doc.kind, "org": doc.org, "title": doc.title, "patient_name": doc.patient_name,
            "patient_dob_raw": doc.patient_dob_raw, "patient_dob": doc.patient_dob.isoformat() if doc.patient_dob else None,
            "fields": {k: v for k, v in doc.fields.items() if k != "_text"},
            "rows": [{"test": r.test, "result": r.raw_value, "unit": r.unit, "reference_range": r.ref_raw, "loinc": r.loinc}
                     for r in doc.rows],
            "sections": list(doc.sections)}


def _model_read(text: str, flags: list[str], dropped: list[str]) -> tuple[str | None, llm.LlmResult]:
    """Model fallback with grounding. Returns canonical Markdown or None."""
    res = llm.extract(text, DOC_FIELDS, DOC_INSTRUCTIONS, max_tokens=2000)
    d = res.data or {}

    def g(key: str, value, numeric: bool = False) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        hit = locate(value, text)
        if not hit or (numeric and hit.level != "exact"):
            dropped.append(key)
            return None
        return hit.value

    f = {k: g(k, d.get(src), k == "patient_dob") for k, src in
         (("org", "organisation"), ("title", "title"), ("patient_name", "patient_name"), ("patient_dob", "patient_birth_date"),
          ("sample_taken", "sample_taken"), ("reported", "reported"), ("signed_by", "signed_by"))}
    rows = []
    for i, r in enumerate(d.get("rows") or []):
        if not isinstance(r, dict):
            continue
        row = {k: g(f"rows[{i}].{k}", r.get(k), k in NUMERIC) for k in ("test", "result", "unit", "reference_range", "loinc")}
        if row["test"] and row["result"]:
            rows.append(row)
        elif r.get("test") or r.get("result"):
            flags.append(f"Zeile {i + 1} nicht sicher lesbar, ausgelassen")
    if not (f["patient_name"] and f["patient_dob"]):
        return None, res
    f["rows"] = rows
    f["signed_label"] = "Validated by" if rows else "Written by"
    if not rows:
        f["body"] = text
    return canonical.render(f), res


def _to_png(data: bytes) -> bytes:
    from PIL import Image, ImageOps
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((2200, 2200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace(",", ".")).strip().lower()


def readback_items(doc: ParsedDoc, second_reader: str | None) -> list[dict]:
    """What the sender confirms. `agree` = the second reader saw the same characters (None = no second reader)."""
    other = _norm(second_reader) if second_reader else None

    def item(key: str, label: str, value: str) -> dict:
        return {"key": key, "label": label, "value": value,
                "agree": None if other is None else (_norm(value) in other if value else True)}
    out = [item("patient_name", "Patient/in", doc.patient_name), item("patient_dob", "Geburtsdatum", doc.patient_dob_raw)]
    for i, r in enumerate(doc.rows):
        out.append(item(f"rows.{i}.result", f"{r.test}", r.raw_value))
        out.append(item(f"rows.{i}.unit", f"{r.test} – Einheit", r.unit))
        out.append(item(f"rows.{i}.reference_range", f"{r.test} – Referenz", r.ref_raw))
    return out


def apply_readback(markdown: str, confirmed: dict[str, str]) -> str:
    """Rebuild the canonical Markdown with the sender's confirmed/corrected values (keys as in readback_items)."""
    doc = parse_markdown(markdown)
    f = {"org": doc.org, "title": doc.title, "patient_name": confirmed.get("patient_name", doc.patient_name),
         "patient_dob": confirmed.get("patient_dob", doc.patient_dob_raw),
         "sample_taken": doc.fields.get("Sample taken"), "reported": doc.fields.get("Reported"),
         "signed_label": "Validated by", "signed_by": doc.fields.get("Validated by") or doc.fields.get("Written by"),
         "rows": [{"test": r.test, "result": confirmed.get(f"rows.{i}.result", r.raw_value),
                   "unit": confirmed.get(f"rows.{i}.unit", r.unit),
                   "reference_range": confirmed.get(f"rows.{i}.reference_range", r.ref_raw), "loinc": r.loinc}
                  for i, r in enumerate(doc.rows)]}
    if not doc.rows:
        f["body"] = "\n\n".join(f"## {k}\n{v}" for k, v in doc.sections.items())
    return canonical.render(f)


def read(data: bytes, filename: str = "", content_type: str | None = None, requested_loinc: list[str] | None = None,
         requested_at: datetime | None = None, requested_doc_type: str | None = None, use_models: bool = True) -> dict:
    t0 = time.perf_counter()
    kind = sniff(data, filename, content_type)
    flags: list[str] = []
    dropped: list[str] = []
    models: dict = {}
    timings: dict = {}
    path, md, second = None, None, None

    def text_route(text: str, exact_path: str) -> tuple[str | None, str | None]:
        doc = parse_markdown(text)
        if parser_ok(doc):
            return text, exact_path
        if not use_models:
            return None, None
        out, res = _model_read(text, flags, dropped)
        models["llm"], timings["llm"] = res.model or None, res.ms
        if res.error:
            models["llm_error"] = res.error
        return (out, "model-fallback") if out else (None, None)

    if kind in ("markdown", "text"):
        md, path = text_route(data.decode("utf-8", errors="replace"), "markdown")
    elif kind == "pdf":
        t = time.perf_counter()
        layer, info = pdf.text_layer_markdown(data)
        timings["pdf_text"] = int((time.perf_counter() - t) * 1000)
        if layer:
            md, path = text_route(layer, "pdf-text")
        else:
            flags.append("PDF ohne Textebene – wird per OCR gelesen")
            kind = "pdf-image"
    if kind in ("image", "pdf-image"):
        pages = pdf.render_pages(data) if kind == "pdf-image" else [_to_png(data)]
        v_txt, t_txt = [], []
        for png in pages:
            v, t = (ocr.vlm(png), ocr.tesseract(png)) if use_models else (ocr.OcrResult(None, "", 0, "disabled"),) * 2
            timings["ocr_vlm"] = timings.get("ocr_vlm", 0) + v.ms
            timings["ocr_tesseract"] = timings.get("ocr_tesseract", 0) + t.ms
            models["ocr_vlm"], models["ocr_second"] = v.model or None, t.model or None
            for name, r in (("ocr_vlm_error", v), ("ocr_second_error", t)):
                if r.error:
                    models[name] = r.error
            if v.text:
                v_txt.append(v.text)
            if t.text:
                t_txt.append(t.text)
        second = "\n".join(t_txt) or None
        first = "\n\n".join(v_txt) or second
        if first:
            md, p = text_route(first, "ocr")
            path = "ocr" if md else None

    doc = parse_markdown(md) if md else None
    result = {
        "version": VERSION,
        "input": {"filename": filename, "content_type": content_type, "kind": kind, "bytes": len(data),
                  "sha256": hashlib.sha256(data).hexdigest()},
        "path": path,
        "ok": bool(md),
        "canonical_markdown": md,
        "parsed": summary(doc) if doc else None,
        "needs_readback": path == "ocr",
        "readback": readback_items(doc, second) if doc and path == "ocr" else [],
        "checks": None,
        "check_lines_de": [],
        "flags": flags,
        "dropped_ungrounded": dropped,
        "models": models,
    }
    if not md:
        flags.append("Dokument konnte nicht sicher gelesen werden – bitte als Text/Markdown senden oder Inhalt eintippen")
    if doc:
        c = checks.run(doc, requested_loinc, requested_at, requested_doc_type)
        result["checks"] = c
        result["check_lines_de"] = c["lines_de"]
        flags.extend(c["flags"])
    timings["total"] = int((time.perf_counter() - t0) * 1000)
    result["timings_ms"] = timings
    return result
