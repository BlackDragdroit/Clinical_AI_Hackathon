"""Deterministic parser for the scenario's Markdown documents (lab report / discharge report).

Generic: works on any document in the same shape (title line, "Key: value" header lines,
a Markdown table with a LOINC column, ## sections). English and German labels.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from fs_matcher import parse_dob

_NUM = r"[-+]?\d+(?:[.,]\d+)?"


@dataclass
class LabRow:
    test: str
    raw_value: str
    value: Optional[float]
    unit: str
    ref_raw: str
    ref_low: Optional[float]
    ref_high: Optional[float]
    loinc: Optional[str]


@dataclass
class ParsedDoc:
    kind: str                                   # lab | report | unknown
    org: str
    title: str
    patient_name: str
    patient_dob_raw: str
    patient_dob: Optional[date]
    fields: dict[str, str] = field(default_factory=dict)
    rows: list[LabRow] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    raw: str = ""


def _num(s: str) -> Optional[float]:
    m = re.search(_NUM, s or "")
    return float(m.group(0).replace(",", ".")) if m else None


def parse_ref_range(s: str) -> tuple[Optional[float], Optional[float]]:
    s = (s or "").strip()
    m = re.search(rf"({_NUM})\s*(?:to|bis|-|–|—)\s*({_NUM})", s)
    if m:
        return _num(m.group(1)), _num(m.group(2))
    m = re.search(rf"[<≤]\s*({_NUM})", s)
    if m:
        return None, _num(m.group(1))
    m = re.search(rf"[>≥]\s*({_NUM})", s)
    if m:
        return _num(m.group(1)), None
    return None, None


def parse_datetime(s: str) -> Optional[datetime]:
    """'22 October 2026, 08:10' / '22.10.2026 08:10' / '2026-10-22T08:10' -> naive datetime (Vienna local)."""
    s = (s or "").strip()
    d = parse_dob(s)
    if not d:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", s)
    return datetime(d.year, d.month, d.day, int(m.group(1)) if m else 0, int(m.group(2)) if m else 0)


def parse_period(s: str) -> tuple[Optional[date], Optional[date]]:
    """'2 to 23 September 2026' / '02.09.2026 - 23.09.2026' -> (start, end)."""
    s = (s or "").strip()
    m = re.match(r"(\d{1,2})\.?\s*(?:to|bis|-|–)\s*(\d{1,2})\.?\s+([A-Za-zÄÖÜäöü]+)\s+(\d{4})", s)
    if m:
        return parse_dob(f"{m.group(1)} {m.group(3)} {m.group(4)}"), parse_dob(f"{m.group(2)} {m.group(3)} {m.group(4)}")
    parts = re.split(r"\s*(?:to|bis|-|–)\s*", s)
    if len(parts) == 2:
        return parse_dob(parts[0]), parse_dob(parts[1])
    return None, None


def _col(headers: list[str], *names: str) -> Optional[int]:
    for i, h in enumerate(headers):
        hl = h.lower()
        if any(n in hl for n in names):
            return i
    return None


def parse_markdown(text: str) -> ParsedDoc:
    lines = text.splitlines()
    org = title = ""
    fields: dict[str, str] = {}
    sections: dict[str, str] = {}
    rows: list[LabRow] = []
    patient_name, dob_raw = "", ""
    current = None
    table: list[list[str]] = []

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("# ") and not org:
            m = re.match(r"#\s*([^:]+):\s*(.+)", s)
            org, title = (m.group(1).strip(), m.group(2).strip()) if m else ("", s[2:].strip())
            continue
        if s.startswith("## "):
            current = s[3:].strip()
            sections[current] = ""
            continue
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells):
                continue
            table.append(cells)
            continue
        m = re.match(r"^(Patient(?:in)?|Patientin/Patient)\s*:\s*(.+)$", s, re.I)
        if m and not patient_name:
            rest = m.group(2)
            pm = re.match(r"(.+?)\s*,\s*(?:born|geb\.?|geboren(?: am)?)\s*(.+)$", rest, re.I)
            if pm:
                patient_name, dob_raw = pm.group(1).strip(), pm.group(2).strip()
            else:
                patient_name = rest.strip()
            continue
        m = re.match(r"^Geburtsdatum\s*:\s*(.+)$", s, re.I)
        if m and not dob_raw:
            dob_raw = m.group(1).strip()
            continue
        m = re.match(r"^([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß /\-]{1,40}):\s*(.+)$", s)
        if m and (current is None or re.search(r"(written|sent|validated|signed|reported|erstellt|gesendet|befundet|validiert|unterschrieben) ?(by|von)?$", m.group(1).strip(), re.I)):
            fields[m.group(1).strip()] = m.group(2).strip()
            continue
        if current is not None:
            sections[current] += (("\n" if sections[current] else "") + s)
        else:
            fields.setdefault("_text", "")
            fields["_text"] += s + "\n"

    if len(table) >= 2:
        hdr = table[0]
        ci_test = _col(hdr, "test", "parameter", "untersuchung", "analyt")
        ci_val = _col(hdr, "result", "ergebnis", "wert", "value")
        ci_unit = _col(hdr, "unit", "einheit")
        ci_ref = _col(hdr, "reference", "referenz", "normbereich", "norm")
        ci_loinc = _col(hdr, "loinc")
        for r in table[1:]:
            g = lambda i: r[i] if i is not None and i < len(r) else ""
            lo, hi = parse_ref_range(g(ci_ref))
            rows.append(LabRow(test=g(ci_test), raw_value=g(ci_val), value=_num(g(ci_val)), unit=g(ci_unit),
                               ref_raw=g(ci_ref), ref_low=lo, ref_high=hi, loinc=(g(ci_loinc).strip() or None)))

    kind = "lab" if rows else ("report" if re.search(r"discharge|entlass|report|bericht|befund", (title + " " + " ".join(sections)), re.I) else "unknown")
    return ParsedDoc(kind=kind, org=org, title=title, patient_name=patient_name, patient_dob_raw=dob_raw,
                     patient_dob=parse_dob(dob_raw), fields=fields, rows=rows, sections=sections, raw=text)


def interpret(value: Optional[float], low: Optional[float], high: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    if low is not None and value < low:
        return "L"
    if high is not None and value > high:
        return "H"
    if low is None and high is None:
        return None
    return "N"


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        d = parse_markdown(open(p, encoding="utf-8").read())
        print(f"{p}: kind={d.kind} org={d.org!r} title={d.title!r} patient={d.patient_name!r} dob={d.patient_dob}")
        print("  fields:", d.fields)
        for r in d.rows:
            print(f"  {r.test:24s} {r.value} {r.unit:8s} [{r.ref_low}, {r.ref_high}] LOINC={r.loinc} -> {interpret(r.value, r.ref_low, r.ref_high)}")
        for k, v in d.sections.items():
            print(f"  ## {k}: {v[:60]!r}...")
