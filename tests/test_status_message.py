"""One card per request, edited in place; one-line pings only where Dr. Hofer has to look; no acks."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app import commands, db, matrix_format, reactions, status_message
from app.config import settings
from app.main import app
from tests.conftest import REQ1, REQ2, link_path
from tests.test_flow import _answer

DOCTOR = settings.doctor_mxid
EPOCH = "1970-01-01T00:00:00+00:00"
LATER = "9999-01-01T00:00:00+00:00"


def _carded() -> str:
    """!anfrage as the bot handles it: the draft reply becomes the card."""
    rid = status_message.drafted(commands.handle(REQ1, DOCTOR))
    status_message.saved(rid, "$card", status_message.card_text(rid))
    return rid


def _flow(outbox, citizen="eva", document="lab-result-maria-beispiel.md", typed=("Maria Beispiel", "12.03.1961")):
    with TestClient(app) as client:
        _answer(client, link_path(outbox[0]["link"]), citizen, document, typed=typed)


def _pings() -> list[str]:
    return [text for _, text, _, _ in status_message.pings()]


def test_draft_card_has_what_to_check_and_one_action(hapi, outbox):
    reply = commands.handle(REQ1, DOCTOR)
    rid = status_message.drafted(reply)
    assert rid and status_message.drafted("Befehl nicht ausgeführt\n…") is None
    lines = status_message.card_text(rid).split("\n")
    assert lines == ["Laborbefund · Maria Beispiel, geb. 12.03.1961",
                     "an Dr. Eva Brandl · eva.brandl@labor-kanal.example",
                     f"„Senden“ tippen · Anfrage {rid}"]


def test_draft_card_keeps_the_replys_warnings_and_is_not_rerendered(hapi, outbox):
    reply = commands.handle(REQ1.replace("labor-kanal", "labor-kanaI"), DOCTOR)
    reply += "\nVerstanden aus: „Laborbefund von Dr. Brandl für Maria Beispiel“"       # as the engine adds it
    rid = status_message.drafted(reply)
    text = status_message.card_text(rid, reply)
    assert "⚠️ Kontakt prüfen:" in text and "Verstanden aus: „Laborbefund" in text
    status_message.saved(rid, "$card", text)
    assert status_message.updates(EPOCH) == []                        # not edited back to a card without them


def test_card_is_edited_through_to_filed(hapi, outbox):
    rid = _carded()
    commands.handle(f"!senden {rid}", DOCTOR)
    [(event_id, req, text)] = status_message.updates(LATER)          # known card: edited, whatever `since` is
    assert (event_id, req) == ("$card", rid)
    assert re.search(r"^●○○○○  Gesendet – wartet, bis der Link geöffnet wird · \d\d:\d\d$", text, re.M)
    status_message.saved(rid, event_id, text)
    assert status_message.updates(LATER) == []                        # nothing changed, nothing sent

    _flow(outbox)
    [(event_id, _, text)] = status_message.updates(LATER)
    lines = text.split("\n")
    assert event_id == "$card" and lines[0] == "Laborbefund · Maria Beispiel" and lines[1] == "an Dr. Eva Brandl · E-Mail"
    assert re.match(r"●●●●●  Abgelegt · \d\d:\d\d$", lines[2])
    assert lines[3] == "INR (prothrombin time): 1.0 · aPTT: 31 s · Platelets: 245 10^9/L · Fibrinogen: 3.1 g/L"
    # the readable report page (app/report.py), signed for this request; the FHIR resources are linked from there
    assert re.match(rf"\[Befund öffnen\]\({re.escape(settings.base_url)}/befund/{rid}\?k=[\w.-]+\)$", lines[4])


def test_report_card_shows_only_the_link(hapi, outbox):
    rid = status_message.drafted(commands.handle(REQ2, DOCTOR))
    status_message.saved(rid, "$card", status_message.card_text(rid))
    commands.handle(f"!senden {rid}", DOCTOR)
    sms = db.query("SELECT * FROM sms_outbox")[0]
    with TestClient(app) as client:
        _answer(client, link_path(re.search(r"https?://\S+", sms["body"]).group(0)), "stefan", "rehab-report-maria-beispiel.md")
    lines = status_message.card_text(rid).split("\n")
    assert re.match(r"●●●●●  Abgelegt", lines[2]) and len(lines) == 4
    assert lines[3].startswith(f"[Befund öffnen]({settings.base_url}/befund/")


def test_request_sent_outside_matrix_gets_a_card_only_after_bot_start(hapi, outbox):
    rid = status_message.drafted(commands.handle(REQ1, DOCTOR))
    commands.handle(f"!senden {rid}", DOCTOR)
    assert status_message.updates(LATER) == []                        # sent before the bot started: no flood
    [(event_id, req, _)] = status_message.updates(EPOCH)
    assert event_id is None and req == rid


def test_acks_of_own_actions_are_not_posted(hapi, outbox):
    rid = _carded()
    sent = commands.handle(f"!senden {rid}", DOCTOR)
    assert status_message.is_ack(f"!senden {rid}", sent)
    assert not status_message.is_ack(f"!senden {rid}", "Befehl nicht ausgeführt\nAnfrage nicht gefunden")
    assert not status_message.is_ack("!senden deadbeef", "Anfrage deadbeef gesendet an X")   # no card: say it
    assert not status_message.is_ack(f"!status {rid}", "Anfrage …")
    assert status_message.is_ack(f"!ablegen {rid}", "Abgelegt: 11 Ressourcen.")
    assert not status_message.is_ack(f"!ablegen {rid}", "Nicht abgelegt (Validierung).")


def test_notify_texts_the_card_replaces(hapi, outbox):
    rid = _carded()
    assert status_message.replaced("✅ Antwort von Eva Brandl … abgelegt", rid)
    assert status_message.replaced("⚠️ Fehlzustellung erkannt (Anfrage x)", rid)
    assert not status_message.replaced(f"⚠️ Antwort {rid} nicht abgelegt: FHIR-Validierung 2 Fehler.", rid)
    assert not status_message.replaced("✅ Antwort von Eva Brandl … abgelegt", "nocard01")


def test_filed_pings_once(hapi, outbox):
    rid = _carded()
    commands.handle(f"!senden {rid}", DOCTOR)
    assert _pings() == []                                             # sending and opening need no ping
    _flow(outbox)
    [(req, text, buttons, seq)] = status_message.pings()
    assert (req, buttons) == (rid, {}) and text.startswith("✅ Laborbefund · Maria Beispiel ist da: INR (prothrombin time): 1.0")
    assert "[Befund öffnen](" in text                                 # the values and where to open them
    status_message.pinged(rid, seq)
    assert _pings() == []


def test_forwarded_link_pings_and_shows_on_card(hapi, outbox):
    rid = _carded()
    commands.handle(f"!senden {rid}", DOCTOR)
    _flow(outbox, citizen="karl")
    assert _pings() == ["⚠️ Laborbefund · Maria Beispiel: Karl Kollege hat den Link geöffnet, nicht Dr. Eva Brandl. "
                        "Nichts offengelegt."]
    text = status_message.card_text(rid)
    assert "●●○○○  Falsche Person – wartet weiter auf Dr. Eva Brandl" in text
    assert "⚠️ Karl Kollege hat den Link geöffnet" in text


def test_wrong_patient_pings_without_naming_them(hapi, outbox):
    rid = _carded()
    commands.handle(f"!senden {rid}", DOCTOR)
    _flow(outbox, document="lab-result-max-beispiel.md", typed=("Max Beispiel", "01.01.1960"))
    assert _pings() == ["⛔ Laborbefund · Maria Beispiel: Dokument betrifft anderen Patienten. Nicht abgelegt. "
                        "Link verbraucht – für das richtige Dokument neue Anfrage stellen."]
    assert "Max" not in status_message.card_text(rid)


def test_review_pings_with_buttons_and_no_done_ping_after_own_decision(hapi, outbox):
    rid = _carded()
    commands.handle(f"!senden {rid}", DOCTOR)
    _flow(outbox, typed=("Maria Beispiel", "13.03.1961"))
    [(_, text, buttons, seq)] = status_message.pings()
    assert text == "🔍 Laborbefund · Maria Beispiel: Zuordnung unsicher. Ablegen oder verwerfen?"
    assert buttons == {"Ablegen": f"!ablegen {rid}", "Verwerfen": f"!verwerfen {rid}"}
    status_message.pinged(rid, seq)
    commands.handle(f"!ablegen {rid}", DOCTOR)
    assert _pings() == []                                             # she tapped it: no "ist da"
    assert "●●●●●  Abgelegt" in status_message.card_text(rid)


def test_edit_content_replaces_original():
    c = matrix_format.edit("$orig", "Laborbefund · Maria Beispiel\n●○○○○  Gesendet")
    assert c["m.relates_to"] == {"rel_type": "m.replace", "event_id": "$orig"}
    assert c["m.new_content"]["body"] == "Laborbefund · Maria Beispiel\n●○○○○  Gesendet" and c["body"].startswith("* ")


def test_ping_is_a_reply_to_its_card_and_shows_the_decision(hapi, outbox):
    rid = _carded()
    commands.handle(f"!senden {rid}", DOCTOR)
    _flow(outbox, typed=("Maria Beispiel", "13.03.1961"))
    [(_, _, buttons, _)] = status_message.pings()
    assert status_message.card_event(rid) == "$card"
    assert matrix_format.content("x", "$card")["m.relates_to"] == {"m.in_reply_to": {"event_id": "$card"}}
    reactions.offer("$ping", buttons)
    assert status_message.decided(f"!senden {rid}") == []
    [(event_id, text)] = status_message.decided(f"!ablegen {rid}")
    assert event_id == "$ping"
    assert re.fullmatch(r"🔍 Laborbefund · Maria Beispiel: Zuordnung unsicher → abgelegt · \d\d:\d\d", text)
    assert "→ verworfen ·" in status_message.decided(f"!verwerfen {rid}")[0][1]


def test_english_request_gets_an_english_card_and_pings(hapi, outbox):
    """A request written in English: card, status and pings in English; the button word stays the same."""
    from app import requests_service
    req = requests_service.draft(doc_kind="labor", expected_name="Dr. Eva Brandl", contact="eva.brandl@labor-kanal.example",
                                 patient_ref="Patient/maria-beispiel", reason="", source="text", lang="en")
    draft = status_message.card_text(req["id"])
    assert draft.startswith("Lab result · Maria Beispiel, born 12.03.1961") and "\nto Dr. Eva Brandl · " in draft
    assert draft.endswith(f"Tap „{reactions.SENDEN}“ · Request {req['id']}")
    status_message.saved(req["id"], "$card", draft)
    commands.handle(f"!senden {req['id']}", DOCTOR)
    sent = status_message.card_text(req["id"])
    assert "Sent – waiting for the link to be opened" in sent and "\nto Dr. Eva Brandl · email" in sent
    _flow(outbox)
    pings = [p[1] for p in status_message.pings() if p[0] == req["id"]]
    assert len(pings) == 1 and pings[0].startswith("✅ Lab result · Maria Beispiel has arrived: INR") and "[Open result](" in pings[0]
    html = matrix_format.to_html(status_message.card_text(req["id"]))
    assert '<font color="#17693f">Filed · ' in html and "Open result" in html


def test_a_question_is_answered_with_the_latest_results(hapi, outbox):
    """'Wo ist der Befund?' has no recipient, contact or patient: no 'incomplete request', but where things are."""
    rid = _carded()
    commands.handle(f"!senden {rid}", DOCTOR)
    _flow(outbox)
    question = {"ready": False, "missing": ["recipient_name", "contact", "patient"],
                "input": {"normalized": "Wo ist der Befund?", "language": "de"}}
    reply = commands.from_engine(question, DOCTOR, "text")
    assert reply.startswith("Keine neue Anfrage erkannt. Zuletzt:")
    assert "Laborbefund · Maria Beispiel – Abgelegt" in reply and "INR (prothrombin time): 1.0" in reply and "[Befund öffnen](" in reply
    question["input"]["language"] = "en"
    assert commands.from_engine(question, DOCTOR, "text").startswith("No new request recognised. Latest:\nLab result · Maria Beispiel – Filed")

