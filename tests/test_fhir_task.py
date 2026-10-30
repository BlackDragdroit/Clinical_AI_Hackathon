from datetime import datetime, timezone

from app import fhir_client

REQ = {"reason": "Gerinnung vor Eingriff", "patient_ref": "Patient/maria-beispiel", "expected_name": "Dr. Eva Brandl",
       "doc_type": "lab"}


def test_task_has_execution_period_input_and_deadline():
    t = fhir_client.task_resource(REQ, datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc))
    assert t["executionPeriod"] == {"start": "2026-10-30T08:00:00+00:00"}
    assert t["restriction"]["period"]["end"] == "2026-11-02T08:00:00+00:00"
    assert t["input"][0]["valueCodeableConcept"]["coding"][0]["code"] == "11502-2"
    assert t["for"] == {"reference": "Patient/maria-beispiel"}


def test_report_requests_discharge_summary():
    t = fhir_client.task_resource({**REQ, "doc_type": "report", "reason": ""})
    assert t["input"][0]["valueCodeableConcept"]["coding"][0]["code"] == "18842-5"
    assert "description" not in t
