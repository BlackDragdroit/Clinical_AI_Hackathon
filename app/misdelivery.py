"""Misdelivery detection. Owner: MedEng.

M1 wrong address  -> lint_address() warns before sending; the identity binding catches it after sending.
M2 forwarded      -> identity binding: verified eID name != expected person -> blocked.
M3 wrong patient  -> core three-way Fellegi–Sunter check returns reject (handled in intake_service).
"""
from __future__ import annotations

from app.config import settings


def lint_address(contact: str, known_domains: tuple[str, ...] | None = None) -> list[str]:
    """Warnings (German) for a contact Dr. Hofer typed, shown on the confirmation card before !senden.

    TODO(MedEng): implement and make tests/test_misdelivery.py::test_lint_* pass:
      - any uppercase letter in the domain part (domains are case-insensitive, so 'I' is suspicious)
      - homoglyph skeleton (I/l/1, O/0, rn/m, vv/w) equal to a known domain but the domain differs
      - Levenshtein distance <= 2 to a known domain but not equal
      - phone numbers: not +43… / wrong length
    Return [] for a clean contact. Never block; Dr. Hofer decides.
    """
    known_domains = known_domains or settings.known_domains
    return []


def classify_identity_failure(request: dict) -> str:
    """Label for the audit 'misdelivery_caught' event when the eID name does not match.
    TODO(MedEng): M1 if the request's contact had lint warnings, else M2 (forwarded). Keep it honest:
    we cannot know for sure, so the label says 'wahrscheinlich'."""
    return "M1/M2"
