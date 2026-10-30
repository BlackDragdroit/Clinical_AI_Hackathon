"""Grounding: every string the engine returns must be a slice of the input text.

`locate` finds a value in the text and returns the exact slice that is there, so a value from the model is
replaced by what the source actually says. Three levels, strictest first:
  exact            the value occurs as is
  case_space       same characters, case and whitespace may differ
  punct            same words, punctuation between them may differ ("Dr Eva Brandl" -> "Dr. Eva Brandl")
Anything else is ungrounded: the engine drops it and counts it (that count is a metric).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass
class Grounded:
    value: str            # the slice of the source text
    start: int
    end: int
    level: str            # exact | case_space | punct


def locate(value: str | None, text: str) -> Grounded | None:
    v = (value or "").strip()
    if not v:
        return None
    i = text.find(v)
    if i >= 0:
        return Grounded(v, i, i + len(v), "exact")
    words = v.split()
    m = re.search(r"\s+".join(map(re.escape, words)), text, re.I)
    if m:
        return Grounded(m.group(0), m.start(), m.end(), "case_space")
    toks = [t for t in re.split(r"[\s.,;:]+", v) if t]
    if toks:
        m = re.search(r"[\s.,;:]*".join(map(re.escape, toks)), text, re.I)
        if m:
            return Grounded(m.group(0), m.start(), m.end(), "punct")
    return None


def as_dict(g: Grounded | None) -> dict | None:
    return asdict(g) if g else None
