"""Intake decision for one answer: parse -> three-way patient check -> FHIR bundle (or rejection).

This is the core the web service calls after the identity check passed. Pure function, no I/O.

python intake.py <document.md> --typed-name "Maria Beispiel" --typed-dob 12.03.1961 \
                 --sender "Dr. Eva Brandl" --sender-org "Labor Kanalstraße"
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime

from fhir_build import build
from fs_matcher import DEFAULT, Person, Weights, verify_answer
from parse_doc import parse_markdown

HERE = os.path.dirname(os.path.abspath(__file__))
WEIGHTS = Weights.load(os.path.join(HERE, "weights.json")) if os.path.exists(os.path.join(HERE, "weights.json")) else DEFAULT


@dataclass
class IntakeResult:
    decision: str                       # file | review | reject
    kind: str
    doctor_message_de: str              # what Dr. Hofer sees in Matrix
    sender_message_de: str              # what the outside person sees (never reveals the other patient)
    match: dict
    bundle: dict | None
    summary: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run_intake(document_text: str, requested: Person, typed: Person, sender_name: str, sender_org: str,
               identity_method_text: str, patient_ref: str, original_filename: str = "document.md",
               answer_sent_at: datetime | None = None) -> IntakeResult:
    doc = parse_markdown(document_text)
    parsed = Person.from_full(doc.patient_name, doc.patient_dob)
    chk = verify_answer(requested, typed, parsed, WEIGHTS)
    match = {k: (asdict(v) if hasattr(v, "levels") else v) for k, v in chk.items()}

    if chk["decision"] == "reject":
        return IntakeResult(
            decision="reject", kind=doc.kind, match=match, bundle=None,
            doctor_message_de=("⚠️ Antwort NICHT abgelegt: Das übermittelte Dokument betrifft einen anderen Patienten als angefragt "
                               f"(Abgleich: {', '.join(chk['requested_vs_document'].reasons_de)}). Absender wurde informiert."),
            sender_message_de="Das Dokument konnte nicht zugeordnet werden. Bitte prüfen Sie, ob Sie das richtige Dokument gewählt haben.",
        )

    built = build(doc, patient_ref, sender_name, sender_org, identity_method_text, answer_sent_at, original_filename)
    if chk["decision"] == "review":
        return IntakeResult(
            decision="review", kind=doc.kind, match=match, bundle=built.bundle(), summary=built.summary_lines, notes=built.notes,
            doctor_message_de=("🔍 Antwort erhalten, aber noch NICHT abgelegt – bitte Patientenzuordnung bestätigen: "
                               f"{', '.join(chk['requested_vs_document'].reasons_de)}. Antworten Sie mit !ablegen oder !verwerfen."),
            sender_message_de="Vielen Dank, Ihre Antwort wurde übermittelt und wird geprüft.",
        )
    n = len(built.entries)
    return IntakeResult(
        decision="file", kind=doc.kind, match=match, bundle=built.bundle(), summary=built.summary_lines, notes=built.notes,
        doctor_message_de=(f"✅ Antwort von {sender_name} ({sender_org}) abgelegt – {n} FHIR-Ressourcen. "
                           f"{identity_method_text}. " + (" | ".join(built.summary_lines) if built.summary_lines else "")
                           + (" Hinweise: " + "; ".join(built.notes) if built.notes else "")),
        sender_message_de="Vielen Dank, Ihre Antwort wurde sicher übermittelt.",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("document")
    ap.add_argument("--requested-name", default="Maria Beispiel")
    ap.add_argument("--requested-dob", default="1961-03-12")
    ap.add_argument("--patient-ref", default="Patient/maria-beispiel")
    ap.add_argument("--typed-name", required=True)
    ap.add_argument("--typed-dob", required=True)
    ap.add_argument("--sender", required=True)
    ap.add_argument("--sender-org", default="")
    ap.add_argument("--identity", default="Identität geprüft: ID Austria (simuliert), Namensabgleich OK; Besitz der Kontaktadresse über Einmal-Link")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    text = open(a.document, encoding="utf-8").read()
    res = run_intake(text, Person.from_full(a.requested_name, a.requested_dob), Person.from_full(a.typed_name, a.typed_dob),
                     a.sender, a.sender_org, a.identity, a.patient_ref, os.path.basename(a.document))
    print(f"decision={res.decision} kind={res.kind}")
    print("Dr. Hofer:", res.doctor_message_de)
    print("Sender   :", res.sender_message_de)
    for k in ("requested_vs_typed", "requested_vs_document", "typed_vs_document"):
        m = res.match[k]
        print(f"  {k:22s} W={m['score']:+6.2f} {m['decision']:7s} {m['reasons_de']}")
    if res.bundle and a.out:
        json.dump(res.bundle, open(a.out, "w"), indent=2, ensure_ascii=False)
        print("bundle written to", a.out)
