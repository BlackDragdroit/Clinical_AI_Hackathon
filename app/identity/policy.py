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
    """Same person by name: titles, case, umlaut spelling ignored; all given + family tokens must agree.
    TODO(MedEng): decide on double names / missing middle names, add cases to tests/test_policy.py."""
    return norm_tokens(expected_name) == norm_tokens(verified.full_name)


def identity_method_text(verified: EidAssertion) -> str:
    """Goes into Provenance.agent.role and Dr. Hofer's message."""
    return (f"Identität geprüft: ID Austria (simuliert, LoA {verified.loa}), Namensabgleich OK; "
            f"Besitz der Kontaktadresse über Einmal-Link")
