"""Bundle construction."""

import uuid

from fhir.resources.R4B.bundle import Bundle
from fhir.resources.R4B.resource import Resource


def to_transaction_bundle(resources: list[Resource]) -> Bundle:
    """Wrap resources in a FHIR transaction Bundle (one ``POST`` entry per resource)."""
    entries = [
        {
            "fullUrl": f"urn:uuid:{uuid.uuid4()}",
            "resource": resource.model_dump(mode="json", exclude_none=True),
            "request": {"method": "POST", "url": resource.get_resource_type()},
        }
        for resource in resources
    ]
    return Bundle.model_validate(
        {"resourceType": "Bundle", "type": "transaction", "entry": entries}
    )
