"""Doctor commands, shared by the Matrix bot and the CLI: handle(text, sender) -> reply. Owner: SWE 1.

Anything that is not a !command is a request in plain German or English ("Bitte bei Dr. Eva Brandl …"):
the engine turns it into the same draft + confirmation card. Voice notes arrive here via from_engine().

!anfrage labor "Dr. Eva Brandl" eva.brandl@labor-kanal.example Patient/maria-beispiel Grund: Gerinnung vor Eingriff
!anfrage bericht "Stefan Kern" +436600000101 Patient/maria-beispiel Grund: Entlassungsbericht Reha
!senden <id>     !ablegen <id>     !verwerfen <id>     !status <id>     !hilfe
"""
from __future__ import annotations

import shlex

from app import audit, db, engine_client, intake_service, requests_service

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


def card(req: dict) -> str:
    warn = "".join(f"\n⚠️ {w}" for w in req["lint_warnings"])
    # TODO(SWE 1): nicer card (HTML formatted_body in Matrix)
    return (f"Anfrage {req['id']} (Entwurf)\nPatient: {req['patient_name']}, *{req['patient_dob']}\n"
            f"An: {req['expected_name']} über {req['contact_kind']} {req['contact']}\n"
            f"Grund: {req['reason']}{warn}\n→ !senden {req['id']}")


def from_engine(res: dict, sender: str, source: str) -> str:
    """Engine result (plain text or voice) -> draft + card, or a question back. Never sends anything."""
    asr = res.get("asr") or {}
    meta = {"input": source, "engine": res.get("version"), "llm": (res.get("models") or {}).get("llm"),
            "asr": asr.get("model"), "audio_sha256": asr.get("audio_sha256"), "ready": bool(res.get("ready")),
            "missing": res.get("missing", []), "flags": len(res.get("flags", [])), "timings_ms": res.get("timings_ms")}
    heard = (res.get("input") or {}).get("normalized") or asr.get("text") or ""
    flags = "".join(f"\n⚠️ {f}" for f in res.get("flags", []))
    patient = res.get("patient") or {}
    if not res.get("ready"):
        audit.log("request_parsed", None, sender, meta)
        cands = "".join(f"\n  • {c['ref']}: {c['name']}, *{c['dob']}" for c in patient.get("candidates", [])[:3]) \
            if patient.get("status") == "ambiguous" else ""
        return f"Verstanden: „{heard}“\n❓ {res.get('ask_de') or 'Bitte genauer angeben.'}{cands}{flags}"
    req = requests_service.draft(doc_kind=res["doc_type"], expected_name=res["recipient"], contact=res["contact"]["value"],
                                 patient_ref=patient["ref"], reason=res.get("reason") or "",
                                 panel_loinc=(res.get("panel") or {}).get("loinc", []), source=source)
    audit.log("request_parsed", req["id"], sender, meta)
    return f"{card(req)}\n(verstanden aus: „{heard}“){flags}"


def handle(text: str, sender: str) -> str:
    text = text.strip()
    cmd, _, arg = text.partition(" ")
    try:
        if not text.startswith("!"):
            return from_engine(engine_client.request_text(text), sender, "text")
        if cmd == "!anfrage":
            return card(requests_service.draft(**parse_anfrage(text)))
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
