"""Patient mapping."""

from fhir.resources.R4B.patient import Patient

PATIENT_ID_SYSTEM = "urn:hackathon:patient-id"
GENDERS = {"male", "female", "other", "unknown"}


def map_patient(record: dict[str, str]) -> Patient:
    """Map one CSV row (``id, family_name, given_name, birth_date, gender``) to a FHIR Patient.

    The source ``id`` is stored as an identifier (system ``PATIENT_ID_SYSTEM``) so the
    patient can be found again on a server that assigns its own resource ids.

    Raises:
        ValueError: if the row does not produce a valid Patient (for example an unknown gender).
    """
    data: dict = {
        "name": [{"family": record.get("family_name", ""), "given": [record.get("given_name", "")]}]
    }
    if record.get("id"):
        data["identifier"] = [{"system": PATIENT_ID_SYSTEM, "value": record["id"]}]
    if record.get("birth_date"):
        data["birthDate"] = record["birth_date"]
    if record.get("gender"):
        gender = record["gender"].lower()
        # fhir.resources does not enforce the code set for `code` fields, so check it here.
        if gender not in GENDERS:
            raise ValueError(
                f"invalid gender {record['gender']!r}; expected one of {sorted(GENDERS)}"
            )
        data["gender"] = gender
    # pydantic's ValidationError is a ValueError subclass.
    return Patient.model_validate(data)
