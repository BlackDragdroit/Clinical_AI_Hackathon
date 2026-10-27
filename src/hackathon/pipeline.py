"""Glue used by the script, API and UI: records -> Bundle + validation result."""

from fhir.resources.R4B.bundle import Bundle

from hackathon.mapping.bundle import to_transaction_bundle
from hackathon.mapping.patient import map_patient
from hackathon.validation.validate import ValidationResult, validate_resource


def convert_records(records: list[dict[str, str]]) -> tuple[Bundle, ValidationResult]:
    """Map rows to Patients, build a transaction Bundle and validate it.

    Rows that cannot be mapped are skipped and reported as errors (``row N: ...``).
    """
    patients, errors = [], []
    for index, record in enumerate(records, start=1):
        try:
            patients.append(map_patient(record))
        except ValueError as exc:
            errors.append(f"row {index}: {exc}".replace("\n", " "))
    bundle = to_transaction_bundle(patients)
    result = validate_resource(bundle.model_dump(mode="json", exclude_none=True), "Bundle")
    errors.extend(result.errors)
    return bundle, ValidationResult(ok=not errors, errors=errors)
