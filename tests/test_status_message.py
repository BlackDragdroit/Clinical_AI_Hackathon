"""One Matrix status message per request: posted once when sent, edited as the request moves, never re-posted."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app import commands, db, matrix_format, status_message
from app.config import settings
from app.main import app
from tests.conftest import REQ1, link_path
from tests.test_flow import _answer, _send

EPOCH = "1970-01-01T00:00:00+00:00"


def test_draft_gets_no_status_message(hapi, outbox):
    commands.handle(REQ1, settings.doctor_mxid)
    assert status_message.updates(EPOCH) == []


def test_posted_once_then_edited_on_progress(hapi, outbox):
    rid = _send(REQ1)
    [(event_id, req, text)] = status_message.updates(EPOCH)
    assert event_id is None and req == rid
    assert text.startswith(f"📋 Anfrage {rid} · Laborbefund · Maria Beispiel → Dr. Eva Brandl")
    assert re.search(r"✅ Gesendet \d\d:\d\d → ⏳ Geöffnet → ◻️ Identität → ◻️ Antwort → ◻️ Abgelegt", text)
    status_message.saved(rid, "$status1", text)
    assert status_message.updates(EPOCH) == []                      # nothing changed, nothing sent

    with TestClient(app) as client:
        _answer(client, link_path(outbox[0]["link"]), "eva", "lab-result-maria-beispiel.md")
    [(event_id, req, text)] = status_message.updates(EPOCH)
    assert (event_id, req) == ("$status1", rid)                     # an edit of the same message, not a new one
    assert "✅ Abgelegt" in text and "⏳" not in text
    status_message.saved(rid, event_id, text)
    assert db.get("matrix_status", "request_id", rid)["event_id"] == "$status1"


def test_requests_sent_before_bot_start_are_not_reposted(hapi, outbox):
    _send(REQ1)
    assert status_message.updates("9999-01-01T00:00:00+00:00") == []


def test_misdelivery_shows_in_status(hapi, outbox):
    rid = _send(REQ1)
    with TestClient(app) as client:
        _answer(client, link_path(outbox[0]["link"]), "karl", "lab-result-maria-beispiel.md")
    [(_, _, text)] = status_message.updates(EPOCH)
    assert "❌ Identität" in text and "⚠️ Fehlzustellung erkannt: verifiziert Karl Kollege" in text
    assert rid in text


def test_edit_content_replaces_original():
    c = matrix_format.edit("$orig", "📋 Anfrage ab12cd34\n✅ Gesendet")
    assert c["m.relates_to"] == {"rel_type": "m.replace", "event_id": "$orig"}
    assert c["m.new_content"]["body"] == "📋 Anfrage ab12cd34\n✅ Gesendet" and c["body"].startswith("* ")
    assert c["m.new_content"]["formatted_body"].startswith("<strong>📋 Anfrage ab12cd34</strong>")
