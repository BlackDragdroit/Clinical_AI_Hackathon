"""Answer -> core decision -> file / review / quarantine, with audit + Matrix. Owner: MedEng.

Nothing reaches HAPI unless the core said `file` (or Dr. Hofer typed !ablegen on a `review`).
"""
from __future__ import annotations

import json
from pathlib import Path

from app import audit, db, fhir_client, notify
from app.config import settings
from app.core_bridge import Person, run_intake

SYSTEM = "system:befundbruecke"


def process_answer(req: dict, *, verified_name: str, identity_method: str, actor: str, typed_name: str,
                   typed_dob: str, filename: str, content: str, engine_notes: list[str] | None = None) -> dict:
    """Returns {'decision', 'sender_message_de', 'answer_id'}. Called by the portal after identity passed.
    `content` is the engine's canonical Markdown; `engine_notes` (completeness, recency, plausibility) are appended
    to Dr. Hofer's message on file/review, never on a reject (they describe the other patient's document)."""
    res = run_intake(content, Person.from_full(req["patient_name"], req["patient_dob"]),
                     Person.from_full(typed_name, typed_dob), verified_name, "", identity_method,
                     req["patient_ref"], filename)
    decision = res.decision
    # TODO(MedEng): downgrade file -> review when policy.auto_file_allowed is False (possession-only path)
    answer_id = db.new_id()
    db.insert("answers", {
        "id": answer_id, "request_id": req["id"], "received_at": db.now(), "verified_name": verified_name,
        "identity_method": identity_method, "typed_name": typed_name, "typed_dob": typed_dob, "filename": filename,
        "content": content, "decision": decision,
        "intake_json": {"match": res.match, "doctor": res.doctor_message_de, "sender": res.sender_message_de,
                        "summary": res.summary, "notes": res.notes},
        "bundle_json": json.dumps(res.bundle, ensure_ascii=False) if res.bundle else None,
    })

    notes = (" · " + " · ".join(engine_notes)) if engine_notes else ""
    if decision == "file":
        _file(req, answer_id, res.bundle, res.doctor_message_de + notes)
    elif decision == "review":
        db.update("requests", "id", req["id"], status="review")
        audit.log("review_requested", req["id"], SYSTEM, {"answer": answer_id, "match": _scores(res.match)})
        notify.doctor(f"{res.doctor_message_de}{notes} (Anfrage {req['id']}: !ablegen {req['id']} / !verwerfen {req['id']})", req["id"])
    else:  # reject: quarantine, never file; no data about the other patient in audit or Matrix
        db.update("requests", "id", req["id"], status="rejected")
        if req["task_ref"]:
            fhir_client.set_task_status(req["task_ref"], "in-progress")   # still waiting for the right document
        audit.log("misdelivery_caught", req["id"], SYSTEM,
                  {"type": "M3", "what": "Dokument betrifft anderen Patienten", "answer": answer_id,
                   "quarantined": True, "match": _scores(res.match)})
        notify.doctor(f"{res.doctor_message_de} (Anfrage {req['id']})", req["id"])
    return {"decision": decision, "sender_message_de": res.sender_message_de, "answer_id": answer_id}


def _scores(match: dict) -> dict:
    """Only scores + decisions go to the audit log, never the names/DOBs from the document."""
    return {k: {"W": v["score"], "decision": v["decision"]} for k, v in match.items() if isinstance(v, dict)}


def _file(req: dict, answer_id: str, bundle: dict, doctor_msg: str) -> list[str]:
    errors = fhir_client.validate(bundle)
    if errors:   # never file something HAPI rejects; Dr. Hofer gets told, the answer stays stored
        db.update("requests", "id", req["id"], status="review")
        notify.doctor(f"⚠️ Antwort {req['id']} nicht abgelegt: FHIR-Validierung {len(errors)} Fehler.", req["id"])
        return []
    refs = fhir_client.post_transaction(bundle)
    Path(settings.var_dir, "filed").mkdir(parents=True, exist_ok=True)
    Path(settings.var_dir, "filed", f"{req['id']}-{answer_id}.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2))
    db.update("answers", "id", answer_id, filed_refs=refs)
    db.update("requests", "id", req["id"], status="filed")
    if req["task_ref"]:
        fhir_client.set_task_status(req["task_ref"], "completed", refs)
    audit.log("answer_filed", req["id"], SYSTEM, {"answer": answer_id, "resources": refs, "task": req["task_ref"]})
    links = " ".join(f"{settings.hapi_public_url}/{r}" for r in refs if r.split("/")[0] in ("DiagnosticReport", "DocumentReference"))
    notify.doctor(f"{doctor_msg} {links}".strip(), req["id"])
    return refs


def confirm_review(request_id: str, *, actor: str, file_it: bool) -> str:
    req = db.get("requests", "id", request_id)
    if not req or req["status"] != "review":
        return "Keine Antwort zur Prüfung offen."
    ans = db.query("SELECT * FROM answers WHERE request_id = ? ORDER BY received_at DESC LIMIT 1", (request_id,))[0]
    audit.log("review_decided", request_id, actor, {"answer": ans["id"], "decision": "ablegen" if file_it else "verwerfen"})
    if not file_it:
        db.update("requests", "id", request_id, status="discarded")
        return f"Antwort {request_id} verworfen."
    refs = _file(req, ans["id"], json.loads(ans["bundle_json"]), f"✅ Antwort {request_id} nach Prüfung abgelegt.")
    return f"Abgelegt: {len(refs)} Ressourcen." if refs else "Nicht abgelegt (Validierung)."
