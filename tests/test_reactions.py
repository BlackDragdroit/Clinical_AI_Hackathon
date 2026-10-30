"""Reactions as buttons: word pills under a bot message run its command, only for authorised senders, only once."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app import commands, db, reactions
from app.config import settings
from app.main import app
from tests.conftest import REQ1, link_path
from tests.test_flow import _answer, _send

DOCTOR = settings.doctor_mxid


def _tap(event_id: str, key: str, sender: str) -> str | None:
    done = reactions.handle(event_id, key, sender)
    return done[1] if done else None


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
    assert reactions.buttons(card) == {"Senden": f"!senden {rid}"}
    assert reactions.buttons(commands.handle(f"!senden {rid}", DOCTOR)) == {}     # the sent card offers nothing
    assert reactions.buttons(commands.HELP) == {}                                  # "!senden <id>" is no button


def test_tap_on_draft_sends_it_once(hapi, outbox):
    rid, card = _draft()
    assert reactions.register("$draft", card) == ["Senden"]
    reply = _tap("$draft", "Senden", DOCTOR)
    assert reply.startswith(f"Anfrage {rid} gesendet") and db.get("requests", "id", rid)["status"] == "sent"
    assert _tap("$draft", "Senden", DOCTOR) is None                   # spent: no second send
    assert len(outbox) == 1


def test_unauthorised_tap_is_refused_and_keeps_the_button(hapi, outbox):
    rid, card = _draft()
    reactions.register("$draft", card)
    assert _tap("$draft", "Senden", "@mallory:evil.example").startswith("Keine Berechtigung")
    assert db.get("requests", "id", rid)["status"] == "draft" and not outbox
    assert _tap("$draft", "Senden", DOCTOR).startswith(f"Anfrage {rid} gesendet")


def test_other_keys_and_unknown_messages_do_nothing(hapi, outbox):
    _, card = _draft()
    reactions.register("$draft", card)
    assert _tap("$draft", "🎉", DOCTOR) is None
    assert _tap("$draft", "❌", DOCTOR) is None                        # a draft offers only Senden
    assert _tap("$draft", "Ablegen", DOCTOR) is None                  # a word presses only its own button
    assert _tap("$other", "Senden", DOCTOR) is None
    assert _tap("$draft", "👍", DOCTOR).startswith("Anfrage")         # 👍 counts as Senden


def test_review_tap_files_and_spends_both_buttons(hapi, outbox):
    rid, msg = _review_message(outbox)
    assert reactions.register("$review", msg) == ["Ablegen", "Verwerfen"]
    assert _tap("$review", "Ablegen", DOCTOR).startswith("Abgelegt")
    assert db.get("requests", "id", rid)["status"] == "filed"
    assert _tap("$review", "Verwerfen", DOCTOR) is None               # cannot discard after filing


def test_review_tap_discards(hapi, outbox):
    rid, msg = _review_message(outbox)
    reactions.register("$review", msg)
    assert _tap("$review", "Verwerfen", DOCTOR) == f"Antwort {rid} verworfen."
    assert db.get("requests", "id", rid)["status"] == "discarded"


def test_emoji_tap_presses_the_matching_word_button(hapi, outbox):
    rid, msg = _review_message(outbox)
    reactions.register("$review", msg)                              # pills: Ablegen, Verwerfen
    assert _tap("$review", "✅️", DOCTOR).startswith("Abgelegt")    # ✅ (variant selector too) means Ablegen
    assert db.get("requests", "id", rid)["status"] == "filed"
    reactions.offer("$ping", {"Ablegen": "!ablegen ab12cd34", "Verwerfen": "!verwerfen ab12cd34"})
    assert reactions.handle("$ping", "👎", DOCTOR)[0] == "!verwerfen ab12cd34"   # 👎 means Verwerfen


def test_messages_from_before_the_words_keep_their_emoji_buttons(hapi, outbox):
    rid, _ = _draft()
    reactions.offer("$old", {"✅": f"!senden {rid}"})                 # as stored before the word pills
    assert _tap("$old", "❌", DOCTOR) is None
    assert _tap("$old", "👍", DOCTOR).startswith(f"Anfrage {rid} gesendet")


def test_typed_command_spends_the_buttons_that_offered_it(hapi, outbox):
    rid, card = _draft()
    reactions.register("$draft", card)
    commands.handle(f"!senden {rid}", DOCTOR)                       # typed instead of tapped
    reactions.spend(f"!senden {rid}")
    assert _tap("$draft", "Senden", DOCTOR) is None                 # the leftover pill does nothing
