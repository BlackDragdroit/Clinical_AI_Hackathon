"""Doctor commands, shared by the Matrix bot and the CLI: handle(text, sender) -> reply. Owner: SWE 1.

!anfrage labor "Dr. Eva Brandl" eva.brandl@labor-kanal.example Patient/maria-beispiel Grund: Gerinnung vor Eingriff
!anfrage bericht "Stefan Kern" +436600000101 Patient/maria-beispiel Grund: Entlassungsbericht Reha
!senden <id>     !ablegen <id>     !verwerfen <id>     !status <id>     !hilfe
"""
from __future__ import annotations

import shlex

from app import db, intake_service, requests_service

HELP = __doc__.split("\n", 2)[2].strip()


def parse_anfrage(text: str) -> dict:
    head, _, reason = text.partition("Grund:")
    parts = shlex.split(head)
    if len(parts) != 5 or parts[0] != "!anfrage":
        raise ValueError('Format: !anfrage labor|bericht "Name" kontakt Patient/<id> Grund: …')
    _, kind, name, contact, patient_ref = parts
    if kind.lower() not in requests_service.DOC_TYPES:
        raise ValueError("Dokumentart: labor oder bericht")
    return {"doc_kind": kind, "expected_name": name, "contact": contact.replace(" ", ""),
            "patient_ref": patient_ref, "reason": reason.strip()}


def handle(text: str, sender: str) -> str:
    text = text.strip()
    cmd, _, arg = text.partition(" ")
    try:
        if cmd == "!anfrage":
            req = requests_service.draft(**parse_anfrage(text))
            warn = "".join(f"\n⚠️ {w}" for w in req["lint_warnings"])
            # TODO(SWE 1): nicer card (HTML formatted_body in Matrix)
            return (f"Anfrage {req['id']} (Entwurf)\nPatient: {req['patient_name']}, *{req['patient_dob']}\n"
                    f"An: {req['expected_name']} über {req['contact_kind']} {req['contact']}\n"
                    f"Grund: {req['reason']}{warn}\n→ !senden {req['id']}")
        if cmd == "!senden":
            req = requests_service.send(arg.strip(), actor=sender)
            return f"Anfrage {req['id']} gesendet. FHIR {req['task_ref']} angelegt."
        if cmd == "!ablegen":
            return intake_service.confirm_review(arg.strip(), actor=sender, file_it=True)
        if cmd == "!verwerfen":
            return intake_service.confirm_review(arg.strip(), actor=sender, file_it=False)
        if cmd == "!status":
            req = db.get("requests", "id", arg.strip())
            return f"{req['id']}: {req['status']}" if req else "Unbekannte Anfrage"
        return HELP
    except Exception as e:  # the doctor sees the error in the room instead of silence
        return f"Fehler: {e}"
