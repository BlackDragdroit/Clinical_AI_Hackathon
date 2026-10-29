"""Closed vocabularies (German + English): document types, test panels, units and plausible ranges.

Every LOINC code here comes from core/loinc.py's verified seed table (check digits are tested). Panels say which
tests a request expects, so the answer can be checked for completeness. Ranges are *physically plausible* bounds
(to catch a misread digit or a wrong unit), not reference ranges, and the engine never changes a value with them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Panel:
    key: str
    label_de: str
    label_en: str
    loinc: tuple[str, ...]
    pattern: str


PANELS = (
    Panel("coagulation", "Gerinnung", "coagulation", ("6301-6", "14979-9", "777-3", "3255-7"),
          r"gerinnung\w*|coagulation|clotting(?: tests?)?"),
    Panel("cbc", "Blutbild", "blood count", ("718-7", "4544-3", "789-8", "6690-2", "777-3"),
          r"(?:kleines |großes |grosses )?blutbild|(?:complete )?blood count|cbc"),
    Panel("kidney", "Nierenwerte", "kidney function", ("2160-0", "3094-0", "2823-3", "2951-2"),
          r"nierenwert\w*|nierenfunktion\w*|retentionswert\w*|kidney (?:function|values|panel)|renal (?:function|panel)"),
    Panel("liver", "Leberwerte", "liver function", ("1742-6", "1920-8"),
          r"leberwert\w*|leberfunktion\w*|transaminasen|liver (?:function|values|panel|enzymes)"),
    Panel("electrolytes", "Elektrolyte", "electrolytes", ("2951-2", "2823-3"), r"elektrolyt\w*|electrolytes?"),
    Panel("inflammation", "Entzündungswerte", "inflammation markers", ("1988-5",),
          r"entzündungs(?:wert|parameter|marker)\w*|inflammat\w+ markers?"),
    Panel("lipids", "Blutfette", "lipids", ("2093-3",), r"blutfett\w*|lipid\w*|cholesterin\w*|cholesterol"),
    Panel("glucose", "Blutzucker", "blood glucose", ("2345-7",), r"blutzucker\w*|glukose|glucose"),
)
PANEL_RE = re.compile(r"\b(?:" + "|".join(f"(?P<{p.key}>{p.pattern})" for p in PANELS) + r")\b", re.I)

# document type: strong words decide alone, weak words only when nothing strong is there
REPORT_STRONG = re.compile(r"\b(?:entlassungs\w*|entlass\w*|discharge(?: report| summary| letter)?|arztbrief\w*|"
                           r"reha-?bericht\w*|rehabericht\w*|rehab(?:ilitation)? report)\b", re.I)
LAB_WORDS = re.compile(r"\b(?:labor\w*|lab(?:oratory)?(?: results?| report| values)?|blutwert\w*|blood (?:tests?|results?|values)|"
                       r"befund(?:e|s)?|werte|results?|inr|aptt|ptt|crp|hb|hämoglobin|kreatinin)\b", re.I)
REPORT_WEAK = re.compile(r"\b(?:bericht\w*|report|summary|brief)\b", re.I)


def _unit_key(u: str) -> str:
    u = (u or "").strip().replace("µ", "u").replace("μ", "u").replace(" ", "").replace("x10", "10").replace("*", "^")
    return u.lower()


def units(*us: str) -> frozenset[str]:
    return frozenset(_unit_key(u) for u in us)


G_PER_L = units("10^9/L", "10^9/l", "G/l", "G/L", "/nl", "/nL", "10*9/L", "10^3/ul", "x10^9/L", "Tsd/ul")
# code -> [(allowed units, low, high)]; a value is plausible if it fits one of the unit groups
PLAUSIBLE: dict[str, list[tuple[frozenset[str], float, float]]] = {
    "6301-6": [(units("", "ratio", "{INR}", "1", "INR"), 0.5, 15)],
    "5902-2": [(units("s", "sec"), 5, 200), (units("%"), 3, 200)],
    "14979-9": [(units("s", "sec"), 10, 250)],
    "777-3": [(G_PER_L, 0, 3000)],
    "3255-7": [(units("g/L", "g/l"), 0.1, 15), (units("mg/dL", "mg/dl"), 10, 1500)],
    "718-7": [(units("g/dL", "g/dl"), 2, 25), (units("g/L", "g/l"), 20, 250), (units("mmol/L", "mmol/l"), 1, 16)],
    "4544-3": [(units("%"), 5, 80), (units("L/L", "l/l"), 0.05, 0.8)],
    "789-8": [(units("10^12/L", "10^12/l", "T/l", "T/L", "/pl", "10^6/ul"), 0.5, 10)],
    "6690-2": [(G_PER_L, 0, 500)],
    "2160-0": [(units("mg/dL", "mg/dl"), 0.05, 30), (units("umol/L", "umol/l"), 5, 2500)],
    "2345-7": [(units("mg/dL", "mg/dl"), 10, 2000), (units("mmol/L", "mmol/l"), 0.5, 110)],
    "2951-2": [(units("mmol/L", "mmol/l", "mEq/L"), 90, 200)],
    "2823-3": [(units("mmol/L", "mmol/l", "mEq/L"), 1, 12)],
    "1742-6": [(units("U/L", "U/l", "IU/L"), 0, 20000), (units("ukat/L", "ukat/l"), 0, 350)],
    "1920-8": [(units("U/L", "U/l", "IU/L"), 0, 20000), (units("ukat/L", "ukat/l"), 0, 350)],
    "1988-5": [(units("mg/L", "mg/l"), 0, 1000), (units("mg/dL", "mg/dl"), 0, 100)],
    "2093-3": [(units("mg/dL", "mg/dl"), 20, 1500), (units("mmol/L", "mmol/l"), 0.5, 40)],
    "3094-0": [(units("mg/dL", "mg/dl"), 1, 300), (units("mmol/L", "mmol/l"), 0.5, 100)],
}


def plausible(code: str | None, value: float | None, unit: str) -> str | None:
    """None if fine or unknown; otherwise 'unit' or 'range'."""
    if not code or code not in PLAUSIBLE or value is None:
        return None
    groups = PLAUSIBLE[code]
    fitting = [g for g in groups if _unit_key(unit) in g[0]]
    if not fitting:
        return "unit"
    return None if any(lo <= value <= hi for _, lo, hi in fitting) else "range"
