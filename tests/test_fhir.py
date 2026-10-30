"""Unit tests for core/fhir_build.py — FHIR resource structure (wave-3 coverage)."""
from __future__ import annotations

import sys
from pathlib import Path

# core/ is not on sys.path by default in the test environment; add it.
_CORE = str(Path(__file__).resolve().parent.parent / "core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from fhir_build import build  # noqa: E402 — must follow sys.path fixup
from parse_doc import parse_markdown  # noqa: E402

_LAB_MD = (Path(__file__).resolve().parent.parent / "scenario" / "documents" / "lab-result-maria-beispiel.md").read_text(encoding="utf-8")


def _make_bundle(content: str = _LAB_MD, sender: str = "Dr. Eva Brandl", org: str = "Labor Kanalstraße") -> dict:
    doc = parse_markdown(content)
    built = build(
        doc,
        patient_ref="Patient/maria-beispiel",
        sender_name=sender,
        sender_org=org,
        identity_method_text="Identität geprüft: ID Austria (simuliert)",
        original_filename="lab-result-maria-beispiel.md",
    )
    return built.bundle()


def _resources_by_type(bundle: dict, resource_type: str) -> list[dict]:
    return [
        e["resource"]
        for e in bundle["entry"]
        if e["resource"]["resourceType"] == resource_type
    ]


def test_fhir_bundle_practitioner_has_identifier():
    """Every Practitioner in the bundle must have identifier[0].system == 'urn:befundbruecke:sender'
    and a non-empty value (wave-3 FHIR coverage)."""
    bundle = _make_bundle()
    practitioners = _resources_by_type(bundle, "Practitioner")
    assert practitioners, "Bundle must contain at least one Practitioner resource"
    for p in practitioners:
        assert p.get("identifier"), f"Practitioner missing identifier: {p}"
        ident = p["identifier"][0]
        assert ident["system"] == "urn:befundbruecke:sender", \
            f"Expected urn:befundbruecke:sender, got {ident.get('system')!r}"
        assert ident.get("value"), f"Practitioner identifier value must be non-empty, got {ident!r}"


def test_fhir_bundle_organization_has_identifier():
    """Every Organization in the bundle must have identifier[0].system == 'urn:befundbruecke:org'
    and a non-empty value (wave-3 FHIR coverage)."""
    bundle = _make_bundle()
    orgs = _resources_by_type(bundle, "Organization")
    assert orgs, "Bundle must contain at least one Organization resource"
    for o in orgs:
        assert o.get("identifier"), f"Organization missing identifier: {o}"
        ident = o["identifier"][0]
        assert ident["system"] == "urn:befundbruecke:org", \
            f"Expected urn:befundbruecke:org, got {ident.get('system')!r}"
        assert ident.get("value"), f"Organization identifier value must be non-empty, got {ident!r}"
