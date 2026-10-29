"""HAPI FHIR R4 client: patient lookup, Task lifecycle, $validate, transaction. Owner: SWE 1."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

FHIR_JSON = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}


def _client() -> httpx.Client:
    return httpx.Client(base_url=settings.hapi_url, headers=FHIR_JSON, timeout=20)


def read_patient(patient_ref: str) -> dict:
    """Returns {'name': 'Maria Beispiel', 'dob': '1961-03-12'}; raises httpx.HTTPStatusError if unknown."""
    with _client() as c:
        r = c.get(patient_ref)
        r.raise_for_status()
        p = r.json()
    n = (p.get("name") or [{}])[0]
    return {"name": " ".join([*n.get("given", []), n.get("family", "")]).strip(), "dob": p.get("birthDate", "")}


def create_task(request: dict) -> str:
    """Task(status=requested) for the outstanding request. Returns 'Task/<id>'."""
    start = datetime.now(timezone.utc)
    task = {
        "resourceType": "Task", "status": "requested", "intent": "order",
        "code": {"text": "Dokument von externer Stelle anfordern"},
        "description": request["reason"] or None,
        "for": {"reference": request["patient_ref"]},
        "authoredOn": start.isoformat(timespec="seconds"),
        "requester": {"display": settings.doctor_name},
        "owner": {"display": request["expected_name"]},
        "restriction": {"period": {"end": (start + timedelta(hours=settings.link_ttl_hours)).isoformat(timespec="seconds")}},
        # TODO(SWE 1): executionPeriod per plan; check against R4 Task + validator, Task.input with doc type
    }
    task = {k: v for k, v in task.items() if v is not None}
    with _client() as c:
        r = c.post("Task", json=task)
        r.raise_for_status()
        return f"Task/{r.json()['id']}"


def set_task_status(task_ref: str, status: str, output_refs: list[str] | None = None) -> None:
    """status: in-progress | completed | rejected | cancelled. output_refs = filed resources."""
    with _client() as c:
        task = c.get(task_ref).raise_for_status().json()
        task["status"] = status
        if output_refs:
            task["output"] = [{"type": {"text": "abgelegte Ressource"}, "valueReference": {"reference": ref}}
                              for ref in output_refs]
        c.put(task_ref, json=task).raise_for_status()


def validate(bundle: dict) -> list[dict]:
    """HAPI $validate on the bundle. Returns OperationOutcome issues with severity error/fatal.
    The official HL7 validator (scripts/validate_all.sh) is the number we report; this is the fast gate."""
    with _client() as c:
        r = c.post("Bundle/$validate", json=bundle)
    oo = r.json()
    return [i for i in oo.get("issue", []) if i.get("severity") in ("error", "fatal")]


def post_transaction(bundle: dict) -> list[str]:
    """POST the transaction bundle. Returns the created references, e.g. ['Observation/12', ...]."""
    with _client() as c:
        r = c.post("", json=bundle)
        r.raise_for_status()
    refs = []
    for e in r.json().get("entry", []):
        loc = e.get("response", {}).get("location", "")      # 'Observation/12/_history/1'
        if loc:
            refs.append("/".join(loc.split("/")[:2]))
    return refs
