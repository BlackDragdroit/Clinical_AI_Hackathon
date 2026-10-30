"""Fellegi–Sunter patient verification for BefundBrücke (pure stdlib).

Question answered: is the patient named in the answer (typed into the form and
parsed from the document) the patient Dr. Hofer requested?

Fields: family name, given name, birth date.
Each field is compared to a level; each level has a weight log2(m/u):
  m = P(level | same patient), u = P(level | different patient).
W = sum of weights.  W >= t_file -> file; W <= t_reject -> reject; else review.
m/u are estimated from labelled synthetic pairs (see gen_pairs.py / eval_matcher.py).
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# ----------------------------------------------------------------- names
_TITLES = {
    "dr", "ddr", "med", "univ", "prof", "mag", "mmag", "dipl", "ing", "di", "msc", "bsc",
    "mba", "phd", "priv", "doz", "oa", "oae", "fa", "pd", "rer", "nat", "jur", "phil",
    "dent", "vet", "herr", "frau", "mr", "mrs", "ms", "h", "c",
}
_UML = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})


def norm_tokens(s: str | None) -> list[str]:
    s = (s or "").translate(_UML)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    toks = [t for t in re.split(r"[^a-z]+", s) if t]
    return [t for t in toks if t not in _TITLES]


def jaro(s: str, t: str) -> float:
    if s == t:
        return 1.0
    ls, lt = len(s), len(t)
    if not ls or not lt:
        return 0.0
    md = max(0, max(ls, lt) // 2 - 1)
    sm, tm = [False] * ls, [False] * lt
    matches = 0
    for i in range(ls):
        for j in range(max(0, i - md), min(lt, i + md + 1)):
            if not tm[j] and s[i] == t[j]:
                sm[i] = tm[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    k = trans = 0
    for i in range(ls):
        if sm[i]:
            while not tm[k]:
                k += 1
            if s[i] != t[k]:
                trans += 1
            k += 1
    trans //= 2
    return (matches / ls + matches / lt + (matches - trans) / matches) / 3


def jaro_winkler(s: str, t: str, p: float = 0.1) -> float:
    j = jaro(s, t)
    l = 0
    for a, b in zip(s[:4], t[:4]):
        if a != b:
            break
        l += 1
    return j + l * p * (1 - j)


def name_sim(a: str | None, b: str | None) -> float:
    """-1 if a side is missing, else best Jaro-Winkler over whole name and tokens."""
    ta, tb = norm_tokens(a), norm_tokens(b)
    if not ta or not tb:
        return -1.0
    best = jaro_winkler("".join(ta), "".join(tb))
    for x in ta:
        for y in tb:
            if len(x) == 1 or len(y) == 1:          # initial, e.g. "M." vs "Maria"
                if x[0] == y[0]:
                    best = max(best, 0.85)
            else:
                best = max(best, jaro_winkler(x, y))
    return best


def name_level(sim: float) -> str:
    if sim < 0:
        return "missing"
    if sim >= 0.92:
        return "agree"
    if sim >= 0.80:
        return "partial"
    return "disagree"


def split_name(full: str) -> tuple[str, str]:
    """'Maria Anna Beispiel' -> ('Maria Anna', 'Beispiel'). Last token = family."""
    toks = [t for t in re.split(r"\s+", (full or "").strip()) if t]
    toks = [t for t in toks if t.rstrip(".").lower() not in _TITLES]
    if not toks:
        return "", ""
    if len(toks) == 1:
        return "", toks[0]
    return " ".join(toks[:-1]), toks[-1]


# ----------------------------------------------------------------- dates
_MONTHS = {
    "january": 1, "jan": 1, "jänner": 1, "jaenner": 1, "januar": 1,
    "february": 2, "feb": 2, "februar": 2,
    "march": 3, "mar": 3, "märz": 3, "maerz": 3,
    "april": 4, "apr": 4,
    "may": 5, "mai": 5,
    "june": 6, "jun": 6, "juni": 6,
    "july": 7, "jul": 7, "juli": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12, "dezember": 12, "dez": 12,
}


def parse_dob(s: str | None) -> Optional[date]:
    if not s:
        return None
    s = s.strip().lower().replace(" ", " ")
    s = unicodedata.normalize("NFKC", s)
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)                           # 1961-03-12
    if m:
        y, mo, d = map(int, m.groups())
        return _safe_date(y, mo, d)
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)                     # 12.03.1961, 12/03/1961
    if m:
        d, mo, y = map(int, m.groups())
        return _safe_date(y, mo, d)
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{2})(?!\d)", s)               # 12.3.61 (2-digit year)
    if m:
        d, mo, y2 = map(int, m.groups())
        y = (2000 + y2) if y2 <= 30 else (1900 + y2)
        return _safe_date(y, mo, d)
    m = re.search(r"(\d{1,2})\.?\s+([a-zäöü]+)\.?\s+(\d{4})", s)               # 12 March 1961 / 12. März 1961
    if m and m.group(2) in _MONTHS:
        return _safe_date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"([a-zäöü]+)\.?\s+(\d{1,2}),?\s+(\d{4})", s)                # March 12, 1961
    if m and m.group(1) in _MONTHS:
        return _safe_date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))
    return None


def _safe_date(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def dob_level(a: Optional[date], b: Optional[date]) -> str:
    if a is None or b is None:
        return "missing"
    if a == b:
        return "exact"
    if a.day <= 12 and _safe_date(a.year, a.day, a.month) == b:               # day/month swapped
        return "near"
    sa, sb = a.strftime("%Y%m%d"), b.strftime("%Y%m%d")
    if sum(x != y for x, y in zip(sa, sb)) == 1:                                # one digit typo
        return "near"
    if abs((a - b).days) <= 1:
        return "near"
    return "disagree"


# ----------------------------------------------------------------- model
LEVELS = {
    "family": ("agree", "partial", "disagree"),
    "given": ("agree", "partial", "disagree"),
    "dob": ("exact", "near", "disagree"),
}


@dataclass
class Person:
    given: str = ""
    family: str = ""
    dob: Optional[date] = None

    @classmethod
    def from_full(cls, full_name: str, dob: str | date | None) -> "Person":
        g, f = split_name(full_name)
        d = dob if isinstance(dob, date) else parse_dob(dob)
        return cls(given=g, family=f, dob=d)

    def display(self) -> str:
        return f"{self.given} {self.family}".strip() + (f", *{self.dob.isoformat()}" if self.dob else "")


def compare_levels(a: Person, b: Person) -> dict[str, str]:
    """Name order is not trusted ('Maria Beispiel' vs 'Beispiel Maria'): take the better of both orderings."""
    straight = (name_sim(a.family, b.family), name_sim(a.given, b.given))
    swapped = (name_sim(a.family, b.given), name_sim(a.given, b.family))
    fam, giv = max(straight, swapped, key=lambda p: p[0] + p[1])
    return {"family": name_level(fam), "given": name_level(giv), "dob": dob_level(a.dob, b.dob)}


@dataclass
class Weights:
    m: dict[str, dict[str, float]]
    u: dict[str, dict[str, float]]
    t_file: float = 8.0
    t_reject: float = 0.0

    def w(self, f: str, level: str) -> float:
        if level == "missing":
            return 0.0
        return math.log2(self.m[f][level] / self.u[f][level])

    def table(self) -> list[tuple[str, str, float, float, float]]:
        return [(f, lv, self.m[f][lv], self.u[f][lv], self.w(f, lv)) for f in LEVELS for lv in LEVELS[f]]

    @classmethod
    def estimate(cls, pairs: list[tuple[Person, Person, int]], alpha: float = 0.5) -> "Weights":
        """Supervised m/u estimation by counting with Laplace smoothing."""
        cm = {f: {lv: alpha for lv in LEVELS[f]} for f in LEVELS}
        cu = {f: {lv: alpha for lv in LEVELS[f]} for f in LEVELS}
        for a, b, y in pairs:
            lv = compare_levels(a, b)
            for f in LEVELS:
                if lv[f] == "missing":
                    continue
                (cm if y else cu)[f][lv[f]] += 1
        m = {f: {lv: cm[f][lv] / sum(cm[f].values()) for lv in LEVELS[f]} for f in LEVELS}
        u = {f: {lv: cu[f][lv] / sum(cu[f].values()) for lv in LEVELS[f]} for f in LEVELS}
        W = cls(m=m, u=u)
        # monotonicity: a partial/near agreement is never stronger evidence than full agreement
        for f in LEVELS:
            strong, weak = LEVELS[f][0], LEVELS[f][1]
            cap = W.w(f, strong) - 1.0
            if W.w(f, weak) > cap:
                W.u[f][weak] = W.m[f][weak] / (2 ** cap)
        return W

    def save(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump({"m": self.m, "u": self.u, "t_file": self.t_file, "t_reject": self.t_reject}, fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "Weights":
        with open(path) as fh:
            d = json.load(fh)
        return cls(**d)


# Prior weights, used until eval_matcher.py writes weights.json.
DEFAULT = Weights(
    m={"family": {"agree": 0.93, "partial": 0.05, "disagree": 0.02},
       "given": {"agree": 0.92, "partial": 0.05, "disagree": 0.03},
       "dob": {"exact": 0.90, "near": 0.07, "disagree": 0.03}},
    u={"family": {"agree": 0.30, "partial": 0.05, "disagree": 0.65},
       "given": {"agree": 0.12, "partial": 0.05, "disagree": 0.83},
       "dob": {"exact": 0.05, "near": 0.03, "disagree": 0.92}},
    t_file=8.0, t_reject=0.0,
)

_DE = {
    ("family", "agree"): "Nachname stimmt überein", ("family", "partial"): "Nachname ähnlich (Tippfehler?)",
    ("family", "disagree"): "Nachname weicht ab", ("given", "agree"): "Vorname stimmt überein",
    ("given", "partial"): "Vorname ähnlich", ("given", "disagree"): "Vorname weicht ab",
    ("dob", "exact"): "Geburtsdatum stimmt überein", ("dob", "near"): "Geburtsdatum fast gleich (Zahlendreher?)",
    ("dob", "disagree"): "Geburtsdatum weicht ab",
}


@dataclass
class MatchResult:
    score: float
    decision: str                       # file | review | reject
    levels: dict[str, str]
    weights: dict[str, float]
    reasons_de: list[str] = field(default_factory=list)


def compare(a: Person, b: Person, W: Weights = DEFAULT) -> MatchResult:
    lv = compare_levels(a, b)
    ws = {f: W.w(f, lv[f]) for f in LEVELS}
    score = sum(ws.values())
    # safety rules on top of the score: auto-filing needs an exact birth date and no disagreeing family name;
    # everything weaker goes to the doctor (review) or is rejected by the score
    hard_block = lv["dob"] != "exact" or lv["family"] == "disagree"
    # hard reject: same family name but birth year off by more than 1 year -> namesake, not same person
    hard_reject = (lv["family"] == "agree" and a.dob is not None and b.dob is not None
                   and abs(a.dob.year - b.dob.year) > 1)
    if hard_reject:
        decision = "reject"
    elif score >= W.t_file and not hard_block:
        decision = "file"
    elif score <= W.t_reject:
        decision = "reject"
    else:
        decision = "review"
    reasons = [_DE[(f, lv[f])] for f in LEVELS if lv[f] != "missing"]
    reasons += [f"{f}: fehlt" for f in LEVELS if lv[f] == "missing"]
    return MatchResult(round(score, 2), decision, lv, {k: round(v, 2) for k, v in ws.items()}, reasons)


def verify_answer(requested: Person, typed: Person, parsed: Person, W: Weights = DEFAULT) -> dict:
    """Three-way check: requested patient vs. what the sender typed vs. what the document says.
    File only if both typed and parsed match the requested patient; any reject -> reject."""
    r_typed = compare(requested, typed, W)
    r_parsed = compare(requested, parsed, W)
    r_cross = compare(typed, parsed, W)
    decisions = {r_typed.decision, r_parsed.decision}
    if "reject" in decisions:
        decision = "reject"
    elif decisions == {"file"}:
        decision = "file"
    else:
        decision = "review"
    if r_cross.decision == "reject" and decision != "reject":   # typed one patient, uploaded another
        decision = "review"
    return {
        "decision": decision,
        "requested_vs_typed": r_typed,
        "requested_vs_document": r_parsed,
        "typed_vs_document": r_cross,
    }


if __name__ == "__main__":
    maria = Person.from_full("Maria Beispiel", "12 March 1961")
    max_ = Person.from_full("Max Beispiel", "1 January 1960")
    typo = Person.from_full("Maria Beispeil", "12.03.1961")
    for b in (maria, max_, typo):
        r = compare(maria, b)
        print(f"{b.display():32s} W={r.score:6.2f} -> {r.decision:6s} {r.reasons_de}")
