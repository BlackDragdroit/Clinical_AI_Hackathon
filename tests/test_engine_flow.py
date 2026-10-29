"""End to end with the engine: plain-German request, voice request, PDF answer, scan answer with read-back."""
import io
import json
import re

from fastapi.testclient import TestClient
from PIL import Image

from app import audit, commands, db, engine_client
from app.config import settings
from app.main import app
from engine.backends import asr, ocr
from eval.render import md_to_pdf
from tests.conftest import doc, link_path

DOCTOR = settings.doctor_mxid
PLAIN_1 = ("Bitte bei Dr. Eva Brandl, eva.brandl@labor-kanal.example, die aktuelle Gerinnung von Frau Maria Beispiel, "
           "geb. 12.03.1961, anfordern – vor dem geplanten Eingriff.")


def _send_plain(text: str) -> str:
    reply = commands.handle(text, DOCTOR)
    rid = re.search(r"Anfrage (\w+) \(Entwurf\)", reply).group(1)
    assert "verstanden aus" in reply
    assert "gesendet" in commands.handle(f"!senden {rid}", DOCTOR)
    return rid


def _login(client: TestClient, path: str, citizen: str = "eva"):
    client.get(path)
    return client.post("/eid/authorize", data={"state": path.rsplit("/", 1)[1], "citizen": citizen})


def _matrix(rid: str) -> list[str]:
    return [m["text"] for m in db.query("SELECT * FROM matrix_outbox WHERE request_id = ?", (rid,))]


def test_plain_german_request_and_pdf_answer(hapi, outbox):
    rid = _send_plain(PLAIN_1)
    req = db.get("requests", "id", rid)
    assert req["source"] == "text" and json.loads(req["panel_loinc"]) == ["6301-6", "14979-9", "777-3", "3255-7"]
    assert req["expected_name"] == "Dr. Eva Brandl" and req["patient_ref"] == "Patient/maria-beispiel"
    with TestClient(app) as client:
        _login(client, link_path(outbox[0]["link"]))
        r = client.post(f"{link_path(outbox[0]['link'])}/answer", data={"typed_name": "Maria Beispiel", "typed_dob": "12.03.1961"},
                        files={"upload": ("befund.pdf", md_to_pdf(doc("lab-result-maria-beispiel.md")), "application/pdf")})
    assert "sicher übermittelt" in r.text and db.get("requests", "id", rid)["status"] == "filed"
    assert any("4/4 angefragte Parameter" in m for m in _matrix(rid))
    sent = [e for e in audit.entries(rid) if e["event"] == "answer_sent"][0]
    assert sent["details"]["read_by"] == "pdf-text"
    parsed = [e for e in audit.entries(rid) if e["event"] == "request_parsed"][0]
    assert parsed["details"]["input"] == "text" and "Maria" not in json.dumps(parsed["details"])


def test_incomplete_request_asks_and_drafts_nothing(hapi):
    reply = commands.handle("Bitte die Gerinnung von Frau Maria Beispiel bei Dr. Eva Brandl anfordern", DOCTOR)
    assert "❓" in reply and "Geburtsdatum" in reply
    assert not db.query("SELECT * FROM requests")


def test_voice_request_keeps_no_audio(hapi, monkeypatch):
    spoken = ("Bitte bei Doktor Eva Brandl, eva punkt brandl at labor minus kanal punkt example, die Gerinnung von "
              "Frau Maria Beispiel, geboren 12.3.1961, anfordern.")
    monkeypatch.setattr(asr, "transcribe", lambda audio, fn="voice.ogg", language=None: asr.AsrResult(spoken, "fake-asr", 40, "ab" * 32))
    reply = commands.from_engine(engine_client.request_audio(b"OggS fake audio"), DOCTOR, "voice")
    rid = re.search(r"Anfrage (\w+)", reply).group(1)
    req = db.get("requests", "id", rid)
    assert req["contact"] == "eva.brandl@labor-kanal.example" and req["source"] == "voice"
    parsed = [e for e in audit.entries(rid) if e["event"] == "request_parsed"][0]["details"]
    assert parsed["audio_sha256"] == "ab" * 32 and parsed["asr"] == "fake-asr"
    assert not any(isinstance(v, (bytes, bytearray)) for r in db.query("SELECT * FROM requests") for v in r.values())


def test_scan_goes_through_readback(hapi, outbox, monkeypatch):
    md = doc("lab-result-maria-beispiel.md")
    monkeypatch.setattr(ocr, "vlm", lambda png: ocr.OcrResult(md, "fake-vlm", 900))
    monkeypatch.setattr(ocr, "tesseract", lambda png: ocr.OcrResult(md.replace("| 3.1 |", "| 8.1 |"), "fake-tesseract", 700))
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, format="PNG")
    rid = _send_plain(PLAIN_1)
    path = link_path(outbox[0]["link"])
    with TestClient(app) as client:
        _login(client, path)
        r = client.post(f"{path}/answer", data={"typed_name": "Maria Beispiel", "typed_dob": "12.03.1961"},
                        files={"upload": ("foto.png", buf.getvalue(), "image/png")})
        assert "Bitte prüfen" in r.text and r.text.count('class="warnrow"') == 1       # fibrinogen read differently
        assert db.get("requests", "id", rid)["status"] != "filed"
        rb_id = re.search(r'name="rb_id" value="(\w+)"', r.text).group(1)
        r = client.post(f"{path}/readback", data={"rb_id": rb_id, "v:rows.3.result": "3.1"})
    assert "sicher übermittelt" in r.text and db.get("requests", "id", rid)["status"] == "filed"
    prov = [e["resource"] for e in hapi.posted[0]["entry"] if e["resource"]["resourceType"] == "Provenance"][0]
    assert "Read-back" in prov["agent"][0]["role"][0]["text"]
    assert any(e["event"] == "readback_confirmed" for e in audit.entries(rid))
