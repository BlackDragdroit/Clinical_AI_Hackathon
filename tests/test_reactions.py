"""Reactions as buttons: ✅/❌ under a bot message run its command, only for authorised senders, only once."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app import commands, db, reactions
from app.config import settings
from app.main import app
from tests.conftest import REQ1, link_path
from tests.test_flow import _answer, _send

DOCTOR = settings.doctor_mxid


def _draft() -> tuple[str, str]:
    card = commands.handle(REQ1, DOCTOR)
    return re.search(r"Anfrage (\w+)", card).group(1), card


def _review_message(outbox) -> tuple[str, str]:
    rid = _send(REQ1)
    with TestClient(app) as client:                     # birth date one day off -> core asks for review
        _answer(client, link_path(outbox[0]["link"]), "eva", "lab-result-maria-beispiel.md",
                typed=("Maria Beispiel", "13.03.1961"))
    assert db.get("requests", "id", rid)["status"] == "review"
    return rid, db.query("SELECT text FROM matrix_outbox WHERE request_id = ? ORDER BY id DESC", (rid,))[0]["text"]


def test_buttons_offered_by_messages(hapi, outbox):
    rid, card = _draft()
    assert reactions.buttons(card) == {"✅": f"!senden {rid}"}
    assert reactions.buttons(commands.handle(f"!senden {rid}", DOCTOR)) == {}     # the sent card offers nothing
    assert reactions.buttons(commands.HELP) == {}                                  # "!senden <id>" is no button


def test_tap_on_draft_sends_it_once(hapi, outbox):
    rid, card = _draft()
    assert reactions.register("$draft", card) == ["✅"]
    reply = reactions.handle("$draft", "✅", DOCTOR)
    assert reply.startswith(f"Anfrage {rid} gesendet") and db.get("requests", "id", rid)["status"] == "sent"
    assert reactions.handle("$draft", "✅", DOCTOR) is None                        # spent: no second send
    assert len(outbox) == 1


def test_unauthorised_tap_is_refused_and_keeps_the_button(hapi, outbox):
    rid, card = _draft()
    reactions.register("$draft", card)
    assert reactions.handle("$draft", "✅", "@mallory:evil.example").startswith("Keine Berechtigung")
    assert db.get("requests", "id", rid)["status"] == "draft" and not outbox
    assert reactions.handle("$draft", "✅", DOCTOR).startswith(f"Anfrage {rid} gesendet")


def test_other_keys_and_unknown_messages_do_nothing(hapi, outbox):
    _, card = _draft()
    reactions.register("$draft", card)
    assert reactions.handle("$draft", "🎉", DOCTOR) is None
    assert reactions.handle("$draft", "❌", DOCTOR) is None                        # a draft offers only ✅
    assert reactions.handle("$other", "✅", DOCTOR) is None
    assert reactions.handle("$draft", "👍", DOCTOR).startswith("Anfrage")         # 👍 counts as ✅


def test_review_tap_files_and_spends_both_buttons(hapi, outbox):
    rid, msg = _review_message(outbox)
    assert reactions.register("$review", msg) == ["✅", "❌"]
    assert reactions.handle("$review", "✅️", DOCTOR).startswith("Abgelegt")  # emoji variant selector
    assert db.get("requests", "id", rid)["status"] == "filed"
    assert reactions.handle("$review", "❌", DOCTOR) is None                       # cannot discard after filing


def test_review_tap_discards(hapi, outbox):
    rid, msg = _review_message(outbox)
    reactions.register("$review", msg)
    assert reactions.handle("$review", "👎", DOCTOR) == f"Antwort {rid} verworfen."
    assert db.get("requests", "id", rid)["status"] == "discarded"
