"""Checks on an answer before it is filed: did they send what was asked, is it recent, are the values plausible?

All deterministic. They never change a value and never block filing on their own: they add lines to Dr. Hofer's
message ("4/4 angefragte Parameter · Probe vom 22.10.2026 · Werte plausibel") and flags for the review.
"""
from __future__ import annotations

from datetime import datetime

from engine._core import KNOWN, ParsedDoc, parse_datetime, resolve
from engine.config import settings
from engine.lexicon import plausible

SAMPLE_KEYS = ("Sample taken", "Collected", "Abnahme", "Entnahme", "Probenentnahme", "Abnahmedatum", "Probe")
DOC_LABEL = {"lab": "Laborbefund", "report": "Bericht"}


def _sample_time(doc: ParsedDoc) -> datetime | None:
    for k, v in doc.fields.items():
        if any(k.lower().startswith(s.lower()) for s in SAMPLE_KEYS):
            t = parse_datetime(v)
            if t:
                return t
    return None


def _name(code: str) -> str:
    syns = KNOWN.get(code, ("", []))[1]
    return syns[0].upper() if syns and len(syns[0]) <= 5 else (syns[0].capitalize() if syns else code)


def run(doc: ParsedDoc, requested_loinc: list[str] | None = None, requested_at: datetime | None = None,
        requested_doc_type: str | None = None) -> dict:
    out: dict = {"doc_type": None, "completeness": None, "recency": None, "sanity": [], "lines_de": [], "flags": []}
    lines, flags = out["lines_de"], out["flags"]

    if requested_doc_type and doc.kind in ("lab", "report") and doc.kind != requested_doc_type:
        out["doc_type"] = {"requested": requested_doc_type, "received": doc.kind}
        flags.append(f"Angefragt: {DOC_LABEL[requested_doc_type]}, erhalten: {DOC_LABEL[doc.kind]}")

    codes = []
    for r in doc.rows:
        lc = resolve(r.loinc, r.test)
        codes.append(lc.code)
        problem = plausible(lc.code, r.value, r.unit)
        if problem:
            what = f"Einheit „{r.unit or '–'}“ passt nicht zu {r.test}" if problem == "unit" else f"{r.test} {r.raw_value} {r.unit} unplausibel"
            out["sanity"].append({"test": r.test, "value": r.raw_value, "unit": r.unit, "loinc": lc.code, "problem": problem})
            flags.append(what)
    if doc.rows:
        lines.append("Werte plausibel" if not out["sanity"] else f"⚠️ {len(out['sanity'])} Wert(e) prüfen")

    if requested_loinc:
        got = [c for c in requested_loinc if c in codes]
        missing = [c for c in requested_loinc if c not in codes]
        out["completeness"] = {"requested": requested_loinc, "delivered": got, "missing": missing}
        line = f"{len(got)}/{len(requested_loinc)} angefragte Parameter"
        if missing:
            line += " (fehlt: " + ", ".join(_name(c) for c in missing) + ")"
            flags.append("Unvollständig: " + line)
        lines.append(line)

    t = _sample_time(doc)
    if t and requested_at:
        ref = requested_at.replace(tzinfo=None)
        age = (ref.date() - t.date()).days
        out["recency"] = {"sample": t.isoformat(), "requested_at": ref.isoformat(timespec="seconds"), "age_days": age}
        line = f"Probe vom {t:%d.%m.%Y}"
        if age < -1:
            flags.append(f"Probendatum {t:%d.%m.%Y} liegt nach der Anfrage")
        elif doc.kind == "lab" and age > settings.lab_max_age_days:
            line += f" – {age} Tage vor der Anfrage"
            flags.append(f"Befund ist {age} Tage alt (Grenze {settings.lab_max_age_days})")
        lines.append(line)
    return out
