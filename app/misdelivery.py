"""Misdelivery detection. Owner: MedEng.

M1 wrong address  -> lint_address() warns before sending; the identity binding catches it after sending.
M2 forwarded      -> identity binding: verified eID name != expected person -> blocked.
M3 wrong patient  -> core three-way Fellegi–Sunter check returns reject (handled in intake_service).

The lint never blocks: Dr. Hofer sees the warnings on the draft card and decides. It only warns about
near-misses of domains we know; an unknown domain that resembles none of them is not suspicious.
Texts come from app/i18n.py (German default, English available).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app import i18n
from app.config import settings

# characters that render (nearly) the same in common fonts; applied before lower-casing so 'I' counts
_GLYPHS = str.maketrans({"I": "l", "1": "l", "|": "l", "O": "o", "0": "o"})
_MULTI = (("rn", "m"), ("vv", "w"))
_EMAIL = re.compile(r"^[^@\s]+@([^@\s]+\.[^@\s.]+)$")


@dataclass(frozen=True)
class Finding:
    """One lint result: a stable code (also the i18n key 'lint.<code>') and its text parameters."""
    code: str
    params: dict = field(default_factory=dict)

    def text(self, lang: str = i18n.DEFAULT) -> str:
        params = dict(self.params)
        if "diffs" in params:   # rendered per language: "„I“ statt „l“"
            params["diff"] = ", ".join(i18n.t("lint.diff_char", lang, got=g, want=w) for g, w in params.pop("diffs"))
        return i18n.t(f"lint.{self.code}", lang, **params)


def _skeleton(domain: str) -> str:
    s = domain.translate(_GLYPHS).lower()
    for a, b in _MULTI:
        s = s.replace(a, b)
    return s


def _distance(a: str, b: str) -> int:
    """Levenshtein distance (insert, delete, substitute)."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _diffs(got: str, want: str, limit: int = 3) -> list[tuple[str, str]]:
    """Where `got` differs from `want`, as (got, want) pieces: [('I', 'l')]."""
    out = [(got[i1:i2], want[j1:j2]) for op, i1, i2, j1, j2 in SequenceMatcher(None, got, want).get_opcodes()
           if op != "equal"]
    return out[:limit]


def _lint_email(contact: str, known: tuple[str, ...]) -> list[Finding]:
    m = _EMAIL.match(contact)
    if not m:
        return [Finding("email_format", {"contact": contact})]
    domain = m.group(1)
    lower = domain.lower()
    found: list[Finding] = []

    odd = sorted({c for c in domain if ord(c) > 127})
    if odd:
        found.append(Finding("non_ascii", {"domain": domain, "chars": " ".join(odd)}))
    if lower in known and domain == lower and not odd:
        return []

    look_alike = next((k for k in known if _skeleton(domain) == _skeleton(k) and lower != k), None)
    if look_alike:
        found.append(Finding("homoglyph", {"domain": domain, "known": look_alike, "diffs": _diffs(domain, look_alike)}))
    else:
        near = min(((_distance(lower, k), k) for k in known if k != lower), default=None)
        if near and near[0] <= 2:
            found.append(Finding("typo", {"domain": domain, "known": near[1], "distance": near[0]}))
        if domain != lower:   # the look-alike message already explains an uppercase I
            found.append(Finding("uppercase", {"domain": domain}))
    return found


def _lint_phone(contact: str) -> list[Finding]:
    p = re.sub(r"[\s\-/().]", "", contact)
    if p.startswith("00"):
        p = "+" + p[2:]
    if not re.fullmatch(r"\+?\d{6,15}", p):
        return [Finding("phone_format", {"contact": contact})]
    if not p.startswith("+"):
        if p.startswith("0"):
            return [Finding("phone_national", {"suggestion": "+43" + p[1:]})]
        return [Finding("phone_format", {"contact": contact})]
    if not p.startswith("+43"):
        return [Finding("phone_foreign")]
    national = p[3:]
    if not national.startswith("6"):
        return [Finding("phone_not_mobile")]
    if not 10 <= len(national) <= 13:
        return [Finding("phone_length", {"digits": len(national)})]
    return []


def lint_findings(contact: str, known_domains: tuple[str, ...] | None = None) -> list[Finding]:
    """Structured results, for pages that render the text themselves (e.g. in the viewer's language)."""
    known = tuple(d.lower() for d in (known_domains or settings.known_domains))
    contact = contact.strip()
    return _lint_email(contact, known) if "@" in contact else _lint_phone(contact)


def lint_address(contact: str, known_domains: tuple[str, ...] | None = None, lang: str = i18n.DEFAULT) -> list[str]:
    """Warnings for a contact Dr. Hofer typed, shown on the draft card before !senden. [] for a clean contact."""
    return [f.text(lang) for f in lint_findings(contact, known_domains)]


def classify_identity_failure(request: dict) -> str:
    """Code for the audit 'misdelivery_caught' event when the eID name does not match: 'M1' if the
    contact had lint warnings (probably a wrong address), else 'M2' (probably forwarded). We cannot know
    for sure, so the human label (misdelivery_label) says 'wahrscheinlich' / 'probably'."""
    warnings = request.get("lint_warnings") or []
    if isinstance(warnings, str):   # stored as JSON in SQLite
        warnings = json.loads(warnings or "[]")
    return "M1" if warnings else "M2"


def misdelivery_label(code: str, lang: str = i18n.DEFAULT) -> str:
    return i18n.t(f"misdelivery.{code}", lang)
