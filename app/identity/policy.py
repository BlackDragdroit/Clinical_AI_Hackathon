"""Which identity check each document type needs, and the name check. Owner: MedEng.

The table below is README design answer 2. Keep the reasons short and clinical.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core_bridge import norm_tokens
from app.identity.eid_mock import EidAssertion


@dataclass(frozen=True)
class Policy:
    doc_type: str
    require_eid: bool
    auto_file_allowed: bool
    reason_de: str


POLICIES = {
    "lab": Policy("lab", True, True,
                  "Laborwerte steuern eine Eingriffsentscheidung: Besitz des Links + ID Austria + Namensabgleich mit der angefragten Person."),
    "report": Policy("report", True, True,
                     "Entlassungsberichte versendet oft die Verwaltung im Auftrag der Ärztin: Absender per ID Austria geprüft, "
                     "Autorin laut Dokument wird getrennt festgehalten."),
}
# TODO(MedEng): possession-only path (no eID available) -> allowed to answer, never auto-filed (always review)


def policy_for(doc_type: str) -> Policy:
    return POLICIES[doc_type]


def names_match(expected_name: str, verified: EidAssertion) -> bool:
    """Is the eID-verified person the one Dr. Hofer named? Conservative: a false "no" only costs a retry.

    Titles, case and umlaut spelling are ignored, and hyphen == space (both via norm_tokens), so
    "Müller-Lüdenscheidt" == "Mueller Luedenscheidt" and "Eva-Maria" == "Eva Maria".
    - Family name: the eID family name (all its parts) must be exactly the last tokens Dr. Hofer typed.
      A missing or extra family-name part on either side is no match ("Eva Müller-Brandl" ≠ eID "Eva Brandl").
    - Given names: every given name Dr. Hofer typed must appear on the eID, in the same order. The eID may
      carry additional given names she did not type ("Eva Brandl" == eID "Eva Maria Brandl"), not the reverse.
    - At least one given name must be typed: a family name alone ("Dr. Brandl") never binds an identity.
    """
    typed = norm_tokens(expected_name)
    family = norm_tokens(verified.family)
    given = norm_tokens(verified.given)
    n = len(family)
    if not n or len(typed) <= n or typed[-n:] != family:
        return False
    remaining = iter(given)
    return all(tok in remaining for tok in typed[:-n])      # ordered subsequence of the eID given names


def identity_method_text(verified: EidAssertion) -> str:
    """Goes into Provenance.agent.role and Dr. Hofer's message."""
    return (f"Identität geprüft: ID Austria (simuliert, LoA {verified.loa}), Namensabgleich OK; "
            f"Besitz der Kontaktadresse über Einmal-Link")
