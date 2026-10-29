"""LOINC code verification (check digit + name/code consistency). No code is ever invented.

LOINC uses the Mod 10 check digit (published algorithm):
  digits of the number right-to-left; odd positions form a number, x2; even positions
  as digits; sum all digits; check digit = (next multiple of 10) - sum.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from fs_matcher import jaro_winkler, norm_tokens

# Small verified seed table: code -> (canonical name, synonyms). Extend from the official LOINC table if needed.
KNOWN: dict[str, tuple[str, list[str]]] = {
    "6301-6": ("INR in Platelet poor plasma by Coagulation assay", ["inr", "international normalized ratio", "prothrombin time inr", "inr prothrombin time"]),
    "5902-2": ("Prothrombin time (PT)", ["pt", "prothrombin time", "thromboplastinzeit", "quick"]),
    "14979-9": ("aPTT in Platelet poor plasma by Coagulation assay", ["aptt", "ptt", "activated partial thromboplastin time", "partielle thromboplastinzeit"]),
    "777-3": ("Platelets [#/volume] in Blood by Automated count", ["platelets", "platelet count", "thrombozyten", "thrombocytes"]),
    "3255-7": ("Fibrinogen [Mass/volume] in Platelet poor plasma by Coagulation assay", ["fibrinogen"]),
    "718-7": ("Hemoglobin [Mass/volume] in Blood", ["hemoglobin", "haemoglobin", "hämoglobin", "hb"]),
    "4544-3": ("Hematocrit [Volume Fraction] of Blood by Automated count", ["hematocrit", "hämatokrit", "hkt", "hct"]),
    "789-8": ("Erythrocytes [#/volume] in Blood by Automated count", ["erythrocytes", "erythrozyten", "red blood cells", "rbc"]),
    "6690-2": ("Leukocytes [#/volume] in Blood by Automated count", ["leukocytes", "leukozyten", "white blood cells", "wbc"]),
    "2160-0": ("Creatinine [Mass/volume] in Serum or Plasma", ["creatinine", "kreatinin"]),
    "2345-7": ("Glucose [Mass/volume] in Serum or Plasma", ["glucose", "glukose", "blutzucker"]),
    "2951-2": ("Sodium [Moles/volume] in Serum or Plasma", ["sodium", "natrium", "na"]),
    "2823-3": ("Potassium [Moles/volume] in Serum or Plasma", ["potassium", "kalium", "k"]),
    "1742-6": ("Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma", ["alt", "alat", "gpt", "alanine aminotransferase"]),
    "1920-8": ("Aspartate aminotransferase [Enzymatic activity/volume] in Serum or Plasma", ["ast", "asat", "got", "aspartate aminotransferase"]),
    "1988-5": ("C reactive protein [Mass/volume] in Serum or Plasma", ["crp", "c-reactive protein", "c reaktives protein"]),
    "2093-3": ("Cholesterol [Mass/volume] in Serum or Plasma", ["cholesterol", "cholesterin", "total cholesterol"]),
    "3094-0": ("Urea nitrogen [Mass/volume] in Serum or Plasma", ["bun", "urea nitrogen", "harnstoff-n"]),
    "11502-2": ("Laboratory report", ["laboratory report", "lab report", "laborbefund"]),
    "18842-5": ("Discharge summary", ["discharge summary", "discharge report", "entlassungsbrief", "entlassungsbericht", "arztbrief"]),
}


def check_digit(number: str) -> int:
    digits = [int(c) for c in number]
    rev = digits[::-1]
    odd = int("".join(str(d) for d in rev[0::2]) or "0") * 2
    total = sum(rev[1::2]) + sum(int(c) for c in str(odd))
    return (10 - total % 10) % 10


def is_valid(code: str | None) -> bool:
    if not code:
        return False
    m = re.fullmatch(r"\s*(\d{3,7})-(\d)\s*", code)
    return bool(m) and check_digit(m.group(1)) == int(m.group(2))


def name_matches(code: str, test_name: str) -> float:
    """Similarity (0..1) between the test name and the known synonyms of the code; 0.5 if code unknown to us."""
    if code not in KNOWN:
        return 0.5
    t = " ".join(norm_tokens(test_name))
    best = 0.0
    for syn in [KNOWN[code][0]] + KNOWN[code][1]:
        s = " ".join(norm_tokens(syn))
        best = max(best, jaro_winkler(t, s), 1.0 if (s and s in t) or (t and t in s) else 0.0)
    return best


def lookup_by_name(test_name: str) -> str | None:
    t = " ".join(norm_tokens(test_name))
    best, best_code = 0.0, None
    for code, (name, syns) in KNOWN.items():
        for syn in [name] + syns:
            s = " ".join(norm_tokens(syn))
            sim = 1.0 if (s and s == t) else jaro_winkler(t, s)
            if sim > best:
                best, best_code = sim, code
    return best_code if best >= 0.95 else None


@dataclass
class LoincCheck:
    code: str | None          # code to file (None -> file without coding, text only)
    status: str               # ok | ok_unknown | filled_from_name | invalid_check_digit | name_code_mismatch | missing
    note_de: str


def resolve(code: str | None, test_name: str) -> LoincCheck:
    code = (code or "").strip() or None
    if code is None:
        found = lookup_by_name(test_name)
        if found:
            return LoincCheck(found, "filled_from_name", f"LOINC fehlte; aus Testname eindeutig ergänzt: {found}")
        return LoincCheck(None, "missing", "LOINC fehlt und konnte nicht sicher ergänzt werden; nur als Text abgelegt")
    if not is_valid(code):
        return LoincCheck(None, "invalid_check_digit", f"LOINC {code} hat eine ungültige Prüfziffer; nicht codiert abgelegt")
    sim = name_matches(code, test_name)
    if code not in KNOWN:
        return LoincCheck(code, "ok_unknown", f"LOINC {code} formal gültig, Bezeichnung nicht in lokaler Tabelle (Prüfziffer OK)")
    if sim < 0.80:
        return LoincCheck(None, "name_code_mismatch", f"LOINC {code} passt nicht zum Testnamen „{test_name}“ ({KNOWN[code][0]}); nicht codiert abgelegt")
    return LoincCheck(code, "ok", "LOINC gültig und zum Testnamen passend")


if __name__ == "__main__":
    bad = [c for c in KNOWN if not is_valid(c)]
    assert not bad, f"seed table has invalid codes: {bad}"
    for code, name in [("6301-6", "INR (prothrombin time)"), ("14979-9", "aPTT"), ("777-3", "Platelets"),
                       ("3255-7", "Fibrinogen"), ("6301-7", "INR"), (None, "Thrombozyten"), ("777-3", "Fibrinogen")]:
        r = resolve(code, name)
        print(f"{str(code):8s} {name:24s} -> {r.status:20s} {r.code}  {r.note_de}")
