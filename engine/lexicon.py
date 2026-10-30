"""Closed vocabularies (German + English): document types, test panels, units and plausible ranges.

LOINC codes come from core/loinc.py's verified seed table and from ELGA_Laborparameter (Austrian terminology server,
v1.11.0+20260910, LOINC 2.83; compact extract in engine/data/elga_lab_loinc_de.csv, content unchanged, see
eval/REAL_DATA.md). Check digits of both are tested. Panels say which
tests a request expects, so the answer can be checked for completeness. Ranges are *physically plausible* bounds
(to catch a misread digit or a wrong unit), not reference ranges, and the engine never changes a value with them.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

# ELGA: code -> (German display, UCUM unit, panel). Austrian labs report with these codes.
_ELGA_CSV = Path(__file__).resolve().parent / "data" / "elga_lab_loinc_de.csv"
ELGA: dict[str, tuple[str, str, str]] = {}
if _ELGA_CSV.exists():
    with _ELGA_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("inactive", "false") != "true":
                ELGA[row["code"]] = (row["display_de"], row["unit"], row["panel"])

# the same measurement under different codes (US-style seed vs. ELGA, mass vs. molar unit, % Quick vs. seconds vs. INR)
EQUIV_GROUPS = [
    {"6690-2", "26464-8"},                                   # Leukozyten
    {"789-8", "26453-1"},                                    # Erythrozyten
    {"4544-3", "20570-8"},                                   # Hämatokrit
    {"6301-6", "5902-2", "5894-1", "52761-4", "52753-1"},    # Prothrombinzeit: INR, s, % Quick, Owren, Normotest
    {"2160-0", "14682-9"},                                   # Kreatinin mg/dl | µmol/l
    {"3094-0", "3091-6"},                                    # Harnstoff(-N)
    {"4548-4", "59261-8"},                                   # HbA1c % | mmol/mol
    {"2089-1", "13457-7"},                                   # LDL gemessen | berechnet
    {"17861-6", "2000-8"}, {"19123-9", "2601-3"}, {"2777-1", "14879-1"},   # Ca, Mg, Phosphat
    {"48065-7", "30240-6"}, {"67151-1", "6598-7"}, {"62292-8", "1989-3"},  # D-Dimer, Troponin T, Vitamin D
]
_EQUIV = {c: g for g in EQUIV_GROUPS for c in g}


def same_test(a: str | None, b: str | None) -> bool:
    return bool(a and b) and (a == b or b in _EQUIV.get(a, ()))


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
    Panel("hba1c", "HbA1c", "HbA1c", ("4548-4",), r"hba1c|langzeitzucker|glykiertes h[äa]moglobin"),
    Panel("thyroid", "Schilddrüsenwerte", "thyroid function", ("3016-3", "3024-7", "3051-0"),
          r"schilddr[üu]s\w*|tsh|thyroid(?: function| panel)?"),
    Panel("iron", "Eisenstatus", "iron status", ("2276-4", "2498-4", "3034-6", "2502-3"),
          r"eisenstatus|eisenwerte|ferritin|iron (?:status|studies|panel)"),
    Panel("cardiac", "Herzmarker", "cardiac markers", ("67151-1", "33762-6"),
          r"herzenzym\w*|herzmarker\w*|troponin|nt-?pro-?bnp|cardiac (?:markers|enzymes)"),
    Panel("pancreas", "Pankreaswerte", "pancreas", ("3040-3", "1798-8"), r"pankreas\w*|lipase|amylase"),
    Panel("ddimer", "D-Dimer", "D-dimer", ("48065-7",), r"d-?dimer\w*"),
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


# ELGA codes for the same measurement share its plausible ranges; Quick in % has its own
PLAUSIBLE.update({"26464-8": PLAUSIBLE["6690-2"], "26453-1": PLAUSIBLE["789-8"], "20570-8": PLAUSIBLE["4544-3"],
                  "14682-9": [(units("umol/L", "umol/l"), 5, 2500)], "5894-1": [(units("%"), 3, 200)],
                  "4548-4": [(units("%"), 2, 25)], "59261-8": [(units("mmol/mol"), 10, 250)],
                  "3016-3": [(units("mU/L", "mIU/L", "uIU/mL", "u[iU]/mL", "uU/ml", "mU/l"), 0, 500)]})


def plausible(code: str | None, value: float | None, unit: str) -> str | None:
    """None if fine or unknown; otherwise 'unit' or 'range'."""
    if not code or code not in PLAUSIBLE or value is None:
        return None
    groups = PLAUSIBLE[code]
    fitting = [g for g in groups if _unit_key(unit) in g[0]]
    if not fitting:
        return "unit"
    return None if any(lo <= value <= hi for _, lo, hi in fitting) else "range"
