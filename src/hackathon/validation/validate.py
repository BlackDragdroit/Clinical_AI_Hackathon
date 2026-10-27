"""Schema validation of FHIR resources."""

from dataclasses import dataclass, field

from fhir.resources.R4B import get_fhir_model_class
from pydantic import ValidationError


@dataclass
class ValidationResult:
    """Outcome of a validation: ``ok`` is True when ``errors`` is empty."""

    ok: bool
    errors: list[str] = field(default_factory=list)


def validate_resource(data: dict, resource_type: str) -> ValidationResult:
    """Validate ``data`` against the FHIR R4B schema of ``resource_type``.

    This checks structure, types and cardinality (schema level), not profiles or terminology.
    """
    try:
        model = get_fhir_model_class(resource_type)
    except (KeyError, ValueError):
        return ValidationResult(ok=False, errors=[f"Unknown resource type: {resource_type}"])
    try:
        model.model_validate(data)
    except ValidationError as exc:
        errors = [
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
        ]
        return ValidationResult(ok=False, errors=errors)
    return ValidationResult(ok=True)
