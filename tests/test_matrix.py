"""Doctor-facing Matrix messages: who may command the bot, how cards and errors read, HTML rendering."""
import httpx

from app import commands, matrix_format
from app.config import settings
from tests.conftest import REQ1


def test_unauthorized_sender_is_refused(hapi):
    reply = commands.handle(REQ1, "@mallory:evil.example")
    assert reply.startswith("Keine Berechtigung") and not hapi.task_status


def test_draft_card_states_what_and_next_step(hapi):
    card = commands.handle(REQ1, settings.doctor_mxid)
    lines = card.split("\n")
    assert lines[0].endswith("Entwurf, noch nicht gesendet")
    assert "Patient: Maria Beispiel, geb. 12.03.1961" in lines
    assert "Dokument: Laborbefund" in lines
    assert lines[-1].startswith("Senden: !senden ")


def test_unreachable_fhir_server_says_nothing_was_sent(monkeypatch):
    def down(_ref):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr("app.fhir_client.read_patient", down)
    reply = commands.handle(REQ1, settings.doctor_mxid)
    assert reply.startswith("FHIR-Server nicht erreichbar") and "Nichts wurde" in reply


def test_html_bolds_first_line_links_urls_codes_commands():
    h = matrix_format.to_html("Anfrage ab12cd34 <ok>\nSenden: !senden ab12cd34\nhttp://localhost:8090/fhir/DiagnosticReport/9ae0.")
    assert h.startswith("<strong>Anfrage ab12cd34 &lt;ok&gt;</strong>")
    assert "<code>!senden ab12cd34</code>" in h
    assert '<a href="http://localhost:8090/fhir/DiagnosticReport/9ae0">DiagnosticReport/9ae0</a>.' in h
    c = matrix_format.content("x")
    assert c["format"] == "org.matrix.custom.html" and c["body"] == "x"
