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
    # ELGA preferred codes folded in as aliases (P16) — same measurement, different unit or panel flavour
    {"10835-7", "43583-4"},                                  # Lipoprotein(a) g/L | nmol/L
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

# ── P16: ELGA preferred codes folded into lexicon (78 new codes from elga_lab_loinc_de.csv) ──────
# Coagulation
PLAUSIBLE.update({
    "3243-3":  [(units("s", "sec"), 5, 200)],          # Thrombinzeit
    "27811-9": [(units("%"), 40, 200)],                 # AT III Aktivität
})
# CBC differentials — absolute counts (10^9/L) and relative (%)
_ABS_DIFF = [(G_PER_L, 0, 50)]
_REL_DIFF = [(units("%"), 0, 100)]
PLAUSIBLE.update({
    "30428-7": [(units("fL", "fl"), 40, 150)],          # MCV
    "28539-5": [(units("pg"), 10, 50)],                 # MCH
    "28540-3": [(units("g/dL", "g/dl", "g/L", "g/l"), 20, 400)],  # MCHC
    "30385-9": [(units("%"), 5, 30)],                   # RDW-CV
    "32623-1": [(units("fL", "fl"), 2, 30)],            # MPV
    "26499-4": [*_ABS_DIFF],                            # Neutrophile Gran. abs.
    "26511-6": [*_REL_DIFF],                            # Neutrophile Gran. rel.
    "26474-7": [*_ABS_DIFF],                            # Lymphozyten abs.
    "26478-8": [*_REL_DIFF],                            # Lymphozyten rel.
    "26484-6": [*_ABS_DIFF],                            # Monozyten abs.
    "26485-3": [*_REL_DIFF],                            # Monozyten rel.
    "26449-9": [*_ABS_DIFF],                            # Eosinophile Gr. abs.
    "26450-7": [*_REL_DIFF],                            # Eosinophile Gr. rel.
    "26444-0": [*_ABS_DIFF],                            # Basophile Gr. abs.
    "30180-4": [*_REL_DIFF],                            # Basophile Gr. rel.
    "51584-1": [*_ABS_DIFF],                            # Unreife Gran. abs.
    "38518-7": [*_REL_DIFF],                            # Unreife Gran. rel.
    "14196-0": [*_ABS_DIFF],                            # Retikulozyten abs.
    "4679-7":  [*_REL_DIFF],                            # Retikulozyten rel.
    "30341-2": [(units("mm/h"), 0, 150)],               # Blutsenkung
})
# Kidney / electrolytes
PLAUSIBLE.update({
    "62238-1": [(units("mL/min/{1.73'm2}", "mL/min/1.73m2", "mL/min"), 5, 200)],  # GFR CKD-EPI
    "33914-3": [(units("mL/min/{1.73'm2}", "mL/min/1.73m2", "mL/min"), 5, 200)],  # GFR MDRD
    "98980-6": [(units("mL/min/{1.73'm2}", "mL/min/1.73m2", "mL/min"), 5, 200)],  # GFR Krea-Cys
    "3084-1":  [(units("mg/dL", "mg/dl"), 1, 20), (units("umol/L", "umol/l"), 60, 1200)],  # Harnsäure
    "33863-2": [(units("mg/L", "mg/l"), 0.1, 20)],     # Cystatin C
    "2075-0":  [(units("mmol/L", "mmol/l", "mEq/L"), 70, 130)],  # Chlorid
    "29265-6": [(units("mmol/L", "mmol/l"), 1, 4)],    # Calcium albuminkorr.
    "2692-2":  [(units("mosm/kg"), 200, 400)],          # Osmolalität
})
# Liver
PLAUSIBLE.update({
    "2324-2":  [(units("U/L", "U/l", "IU/L"), 0, 3000)],   # Gamma-GT
    "6768-6":  [(units("U/L", "U/l", "IU/L"), 0, 5000)],   # Alk. Phosphatase
    "1975-2":  [(units("mg/dL", "mg/dl"), 0.1, 50)],       # Bilirubin gesamt
    "1968-7":  [(units("mg/dL", "mg/dl"), 0, 30)],         # Bilirubin direkt
    "2532-0":  [(units("U/L", "U/l", "IU/L"), 0, 10000)],  # LDH
    "2098-2":  [(units("U/L", "U/l", "IU/L"), 0, 20000)],  # Cholinesterase
    "1751-7":  [(units("g/L", "g/l"), 10, 60)],            # Albumin
    "2885-2":  [(units("g/L", "g/l"), 30, 120)],           # Totalprotein
    "16362-6": [(units("umol/L", "umol/l"), 0, 300)],      # Ammoniak
})
# Pancreas / muscle
PLAUSIBLE.update({
    "2157-6":  [(units("U/L", "U/l", "IU/L"), 0, 100000)],  # CK
    "32673-6": [(units("U/L", "U/l", "IU/L"), 0, 5000)],    # CK-MB
    "2639-3":  [(units("ug/L", "µg/L", "ug/l"), 0, 5000)],  # Myoglobin
})
# Inflammation
PLAUSIBLE.update({
    "30522-7": [(units("mg/L", "mg/l"), 0, 1000)],          # CRP hs
    "33959-8": [(units("ng/mL", "ng/ml", "ug/L", "µg/L"), 0, 1000)],  # Procalcitonin
    "26881-3": [(units("pg/mL", "pg/ml"), 0, 100000)],      # IL-6
})
# Glucose / hormones
PLAUSIBLE.update({
    "1558-6":  [(units("mg/dL", "mg/dl"), 10, 2000)],       # Glucose nüchtern (oGTT)
    "20448-7": [(units("u[iU]/mL", "uIU/mL", "uU/ml", "µU/mL"), 0, 3000)],  # Insulin
    "1986-9":  [(units("ng/mL", "ng/ml"), 0, 50)],          # C-Peptid
})
# Lipids
PLAUSIBLE.update({
    "2571-8":  [(units("mg/dL", "mg/dl"), 10, 3000), (units("mmol/L", "mmol/l"), 0.1, 35)],  # Triglyceride
    "2085-9":  [(units("mg/dL", "mg/dl"), 5, 200), (units("mmol/L", "mmol/l"), 0.1, 5)],     # HDL-Cholesterin
    "43396-1": [(units("mg/dL", "mg/dl"), 10, 400)],        # Non HDL-Chol.
    "10835-7": [(units("g/L", "g/l"), 0, 10)],              # Lipoprotein(a) g/L
    "43583-4": [(units("nmol/L", "nmol/l"), 0, 500)],       # Lipoprotein(a) nmol/L
})
# Cardiac
PLAUSIBLE.update({
    "30934-4": [(units("ng/L", "ng/l", "pg/mL", "pg/ml"), 0, 100000)],  # BNP
})
# Iron
PLAUSIBLE.update({
    "4542-7":  [(units("g/L", "g/l"), 0.1, 4)],            # Haptoglobin
})
# Vitamins
PLAUSIBLE.update({
    "2132-9":  [(units("pg/mL", "pg/ml"), 50, 10000)],      # Vitamin B12
    "2284-8":  [(units("ng/mL", "ng/ml"), 1, 100)],         # Folsäure
})
# Tumor markers
PLAUSIBLE.update({
    "2857-1":  [(units("ug/L", "µg/L", "ug/l", "ng/mL", "ng/ml"), 0, 10000)],  # PSA
    "2039-6":  [(units("ug/L", "µg/L", "ug/l", "ng/mL", "ng/ml"), 0, 10000)],  # CEA
})
# Blood gas
PLAUSIBLE.update({
    "2744-1":  [(units("1", ""), 6.5, 8.0)],                # pH art.
    "2019-8":  [(units("mm[Hg]", "mmhg", "mm Hg"), 10, 120)],  # pCO2 art.
    "2703-7":  [(units("mm[Hg]", "mmhg", "mm Hg"), 10, 700)],  # pO2 art.
    "1960-4":  [(units("mmol/L", "mmol/l"), 5, 50)],        # Bikarbonat art.
    "2524-7":  [(units("mmol/L", "mmol/l"), 0.1, 30)],      # Laktat
})
# Urine
PLAUSIBLE.update({
    "5803-2":  [(units("1", ""), 4, 9)],                    # pH /U
    "20408-1": [(units("/uL", "/ul", "/µL"), 0, 500000)],   # Leuko /U
    "20409-9": [(units("/uL", "/ul", "/µL"), 0, 500000)],   # Ery. /U
    "2161-8":  [(units("mg/dL", "mg/dl"), 0, 5000)],        # Kreatinin /U
    "1754-1":  [(units("mg/L", "mg/l"), 0, 50000)],         # Albumin /U
    "9318-7":  [(units("mg/g{Krea}", "mg/g"), 0, 50000)],   # Alb./Kreat.-Ratio /U
})
# Other
PLAUSIBLE.update({
    "2143-6":  [(units("ug/dL", "µg/dL", "ug/dl"), 0, 300)],    # Cortisol
})


def plausible(code: str | None, value: float | None, unit: str) -> str | None:
    """None if fine or unknown; otherwise 'unit' or 'range'."""
    if not code or code not in PLAUSIBLE or value is None:
        return None
    groups = PLAUSIBLE[code]
    fitting = [g for g in groups if _unit_key(unit) in g[0]]
    if not fitting:
        return "unit"
    return None if any(lo <= value <= hi for _, lo, hi in fitting) else "range"
