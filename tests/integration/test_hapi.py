import uuid

import pytest

from hackathon.fhir_client.client import FhirClient
from hackathon.mapping.bundle import to_transaction_bundle
from hackathon.mapping.patient import PATIENT_ID_SYSTEM, map_patient

pytestmark = pytest.mark.integration

# NOTE: the public HAPI server is readable by everyone. Synthetic data only!
HAPI_R4 = "https://hapi.fhir.org/baseR4"


def test_post_bundle_and_search_roundtrip() -> None:
    unique_id = f"hackathon-test-{uuid.uuid4()}"
    patient = map_patient(
        {
            "id": unique_id,
            "family_name": "Patient1",
            "given_name": "Test",
            "birth_date": "1980-01-15",
            "gender": "female",
        }
    )
    client = FhirClient(HAPI_R4)

    response = client.post_bundle(to_transaction_bundle([patient]))
    assert response["resourceType"] == "Bundle"

    found = client.search("Patient", {"identifier": f"{PATIENT_ID_SYSTEM}|{unique_id}"})
    assert found["total"] >= 1
