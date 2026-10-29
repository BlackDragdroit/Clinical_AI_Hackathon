"""The core decides correctly on the three scenario documents (guards the import path and the weights)."""
from app.core_bridge import Person, run_intake
from tests.conftest import doc

MARIA = Person.from_full("Maria Beispiel", "1961-03-12")
METHOD = "Identität geprüft: ID Austria (simuliert)"


def test_lab_for_maria_is_filed():
    r = run_intake(doc("lab-result-maria-beispiel.md"), MARIA, Person.from_full("Maria Beispiel", "12.03.1961"),
                   "Dr. Eva Brandl", "", METHOD, "Patient/maria-beispiel")
    assert r.decision == "file"
    kinds = {e["resource"]["resourceType"] for e in r.bundle["entry"]}
    assert {"Observation", "DiagnosticReport", "DocumentReference", "Provenance"} <= kinds


def test_lab_for_max_is_rejected():
    r = run_intake(doc("lab-result-max-beispiel.md"), MARIA, Person.from_full("Maria Beispiel", "12.03.1961"),
                   "Dr. Eva Brandl", "", METHOD, "Patient/maria-beispiel")
    assert r.decision == "reject" and r.bundle is None
    assert "Max" not in r.doctor_message_de and "Max" not in r.sender_message_de


def test_rehab_report_is_filed():
    r = run_intake(doc("rehab-report-maria-beispiel.md"), MARIA, Person.from_full("Maria Beispiel", "12.03.1961"),
                   "Stefan Kern", "", METHOD, "Patient/maria-beispiel")
    assert r.decision == "file"
