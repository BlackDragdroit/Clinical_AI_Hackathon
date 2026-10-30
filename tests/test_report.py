"""Readable report page behind "Befund öffnen": values, origin, and a key bound to one request."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import commands, report, status_message
from app.main import app
from tests.test_status_message import DOCTOR, _carded, _flow


def _filed(outbox) -> str:
    rid = _carded()
    commands.handle(f"!senden {rid}", DOCTOR)
    _flow(outbox)
    return rid


def test_page_shows_values_and_origin(hapi, outbox):
    rid = _filed(outbox)
    with TestClient(app) as client:
        html = client.get("/" + report.url(rid).split("/", 3)[3]).text     # path + key, without the host
    assert "Laborbefund · Maria Beispiel" in html and "geb. 12.03.1961" in html
    assert "INR (prothrombin time)" in html and ">1.0<" in html and "0.8 to 1.2" in html and "6301-6" in html
    assert "Herkunft und Prüfung" in html and "Eva Brandl" in html and "ID Austria" in html
    assert "DiagnosticReport/" in html                                  # the FHIR resources are still linked


def test_page_needs_the_key_for_its_own_request(hapi, outbox):
    rid = _filed(outbox)
    other = report.url("someother").split("?k=")[1]
    with TestClient(app) as client:
        assert client.get(f"/befund/{rid}").status_code == 404
        assert client.get(f"/befund/{rid}?k=nope").status_code == 404
        r = client.get(f"/befund/{rid}?k={other}")
        assert r.status_code == 404 and "Maria" not in r.text


def test_chat_link_opens_the_page(hapi, outbox):
    rid = _filed(outbox)
    card = status_message.card_text(rid)
    assert f"[Befund öffnen]({report.url(rid).split('?k=')[0]}?k=" in card
