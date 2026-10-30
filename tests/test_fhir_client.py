"""A slow HAPI $validate (fresh server) must not fail the upload: nothing is filed, the answer goes to review."""
from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app import commands, db, fhir_client, status_message
from app.config import settings
from app.main import app
from tests.conftest import REQ1, link_path
from tests.test_flow import _answer, _send

REAL_VALIDATE = fhir_client.validate          # before the hapi fixture replaces it


def _timing_out(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)
    monkeypatch.setattr(fhir_client, "_client", lambda timeout=20: httpx.Client(
        base_url=settings.hapi_url, transport=httpx.MockTransport(handler)))


def test_validate_timeout_is_an_error_issue(monkeypatch):
    _timing_out(monkeypatch)
    [issue] = REAL_VALIDATE({"resourceType": "Bundle", "type": "transaction", "entry": []})
    assert issue["severity"] == "error" and issue["code"] == "timeout"


def test_upload_survives_a_validate_timeout(hapi, outbox, monkeypatch):
    rid = _send(REQ1)
    monkeypatch.setattr(fhir_client, "validate", REAL_VALIDATE)
    _timing_out(monkeypatch)
    with TestClient(app) as client:
        r = _answer(client, link_path(outbox[0]["link"]), "eva", "lab-result-maria-beispiel.md")
    assert r.status_code == 200 and "Eingangsnummer" in r.text            # the sender gets a receipt, not a 500
    assert db.get("requests", "id", rid)["status"] == "review" and not hapi.posted
    assert any("nicht abgelegt" in m["text"] for m in db.query("SELECT text FROM matrix_outbox WHERE request_id = ?", (rid,)))
    assert "FHIR-Prüfung fehlgeschlagen · erneut prüfen: !ablegen" in status_message.card_text(rid)

    monkeypatch.setattr(fhir_client, "validate", hapi.validate)             # HAPI is warm now
    assert commands.handle(f"!ablegen {rid}", settings.doctor_mxid).startswith("Abgelegt")
    assert db.get("requests", "id", rid)["status"] == "filed" and len(hapi.posted) == 1
