from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hackathon.api.main import app
from hackathon.ingest.csv_reader import read_records
from hackathon.mapping.bundle import to_transaction_bundle
from hackathon.mapping.patient import map_patient
from hackathon.validation.validate import validate_resource

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "patients_sample.csv"
ROW = {
    "id": "1",
    "family_name": "Patient1",
    "given_name": "Test",
    "birth_date": "1980-01-15",
    "gender": "female",
}


def test_read_records() -> None:
    records = read_records(SAMPLE)
    assert len(records) == 5
    assert records[0]["family_name"] == "Patient1"


def test_map_patient() -> None:
    patient = map_patient(ROW)
    assert patient.name[0].family == "Patient1"
    assert patient.name[0].given == ["Test"]
    assert str(patient.birthDate) == "1980-01-15"
    assert patient.gender == "female"


def test_map_patient_phone() -> None:
    patient = map_patient({**ROW, "phone": "+43 1 5550100"})
    assert patient.telecom[0].system == "phone"
    assert patient.telecom[0].value == "+43 1 5550100"
    assert validate_resource(patient.model_dump(mode="json", exclude_none=True), "Patient").ok
    assert map_patient({**ROW, "phone": ""}).telecom is None


def test_map_patient_invalid_gender() -> None:
    with pytest.raises(ValueError):
        map_patient({**ROW, "gender": "not-a-gender"})


def test_bundle_is_valid_transaction() -> None:
    patients = [map_patient(r) for r in read_records(SAMPLE)]
    bundle = to_transaction_bundle(patients)
    data = bundle.model_dump(mode="json", exclude_none=True)
    assert data["type"] == "transaction"
    assert len(data["entry"]) == 5
    assert data["entry"][0]["request"] == {"method": "POST", "url": "Patient"}
    assert validate_resource(data, "Bundle").ok


def test_validate_valid_and_invalid() -> None:
    assert validate_resource({"resourceType": "Patient", "gender": "female"}, "Patient").ok
    bad = validate_resource({"resourceType": "Patient", "gender": 42}, "Patient")
    assert not bad.ok
    assert bad.errors
    assert not validate_resource({}, "NotAResource").ok


def test_api_health_and_convert() -> None:
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    response = client.post("/convert", files={"file": ("p.csv", SAMPLE.read_bytes(), "text/csv")})
    body = response.json()
    assert response.status_code == 200
    assert body["validation"] == {"ok": True, "errors": []}
    assert len(body["bundle"]["entry"]) == 5


def test_api_convert_reports_bad_row() -> None:
    csv_bytes = b"id,family_name,given_name,birth_date,gender\n1,A,B,1990-01-01,nope\n"
    body = TestClient(app).post("/convert", files={"file": ("p.csv", csv_bytes)}).json()
    assert body["validation"]["ok"] is False
    assert body["validation"]["errors"][0].startswith("row 1")
