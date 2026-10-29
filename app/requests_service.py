"""Clinic side of a request: draft -> confirm -> send. Called by the Matrix bot and the CLI. Owner: SWE 1."""
from __future__ import annotations

from app import audit, db, fhir_client, misdelivery, tokens
from app.config import settings
from app.delivery import channel_for

DOC_TYPES = {"labor": "lab", "lab": "lab", "bericht": "report", "report": "report"}


def mask(contact: str) -> str:
    """For audit/Matrix: e***@labor-kanal.example, +43 *** 0101."""
    if "@" in contact:
        local, dom = contact.split("@", 1)
        return f"{local[:1]}***@{dom}"
    return f"{contact[:3]} *** {contact[-4:]}"


def draft(doc_kind: str, expected_name: str, contact: str, patient_ref: str, reason: str) -> dict:
    doc_type = DOC_TYPES[doc_kind.lower()]
    patient = fhir_client.read_patient(patient_ref)
    req = {
        "id": db.new_id(), "created_at": db.now(), "doc_type": doc_type, "patient_ref": patient_ref,
        "patient_name": patient["name"], "patient_dob": patient["dob"], "expected_name": expected_name,
        "contact_kind": "email" if "@" in contact else "sms", "contact": contact, "reason": reason,
        "status": "draft", "lint_warnings": misdelivery.lint_address(contact),
    }
    db.insert("requests", req)
    audit.log("request_drafted", req["id"], settings.doctor_mxid,
              {"doc_type": doc_type, "to": expected_name, "contact": mask(contact), "lint_warnings": req["lint_warnings"]})
    return req


def send(request_id: str, actor: str | None = None) -> dict:
    req = db.get("requests", "id", request_id)
    if not req or req["status"] != "draft":
        raise ValueError("Anfrage nicht gefunden oder bereits gesendet")
    raw = tokens.issue(req["id"], req["contact"])
    channel = channel_for(req["contact_kind"])
    msg_id = channel.send(req["contact"], tokens.link_for(raw))
    task_ref = fhir_client.create_task(req)
    db.update("requests", "id", req["id"], status="sent", task_ref=task_ref)
    audit.log("request_sent", req["id"], actor or settings.doctor_mxid,
              {"channel": channel.kind, "contact": mask(req["contact"]), "message_id": msg_id, "task": task_ref,
               "to": req["expected_name"], "ttl_h": settings.link_ttl_hours})
    return db.get("requests", "id", req["id"])
