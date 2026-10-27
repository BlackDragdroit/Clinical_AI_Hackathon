"""Minimal FHIR REST client."""

import httpx
from fhir.resources.R4B.bundle import Bundle

_HEADERS = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}


class FhirClient:
    """Thin wrapper around a FHIR R4 server's REST API."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def post_bundle(self, bundle: Bundle | dict) -> dict:
        """POST a transaction Bundle to the server root and return the response Bundle as dict."""
        payload = (
            bundle
            if isinstance(bundle, dict)
            else bundle.model_dump(mode="json", exclude_none=True)
        )
        response = httpx.post(self.base_url, json=payload, headers=_HEADERS, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def search(self, resource_type: str, params: dict) -> dict:
        """Run a FHIR search (``GET [base]/[type]?params``) and return the searchset Bundle."""
        response = httpx.get(
            f"{self.base_url}/{resource_type}",
            params=params,
            headers={"Accept": "application/fhir+json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
