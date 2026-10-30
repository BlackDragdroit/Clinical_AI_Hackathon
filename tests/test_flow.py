"""End to end on the scenario with a fake HAPI: request 1 by email, request 2 by SMS, M1–M3, audit 6/6."""
import re

from fastapi.testclient import TestClient

from app import audit, commands, db
from app.config import settings
from app.main import app
from tests.conftest import REQ1, REQ2, doc, link_path

DOCTOR = settings.doctor_mxid


def _send(cmd: str) -> str:
    rid = re.search(r"Anfrage (\w+)", commands.handle(cmd, DOCTOR)).group(1)
    assert "gesendet" in commands.handle(f"!senden {rid}", DOCTOR)
    return rid


def _answer(client: TestClient, path: str, citizen: str, document: str, typed=("Maria Beispiel", "12.03.1961")):
    landing = client.get(path)
    assert landing.status_code == 200
    assert not re.search(r"\b(Maria|1961|Labor|Gerinnung)\b", landing.text)        # nothing before identity
    r = client.post("/eid/authorize", data={"state": path.rsplit("/", 1)[1], "citizen": citizen})
    if r.status_code != 200 or "Sicher senden" not in r.text:
        return r
    return client.post(f"{path}/answer", data={"typed_name": typed[0], "typed_dob": typed[1]},
                       files={"upload": ("befund.md", doc(document).encode(), "text/markdown")})


def test_request_1_happy_path(hapi, outbox):
    rid = _send(REQ1)
    with TestClient(app) as client:
        r = _answer(client, link_path(outbox[0]["link"]), "eva", "lab-result-maria-beispiel.md")
    assert "sicher übermittelt" in r.text
    assert db.get("requests", "id", rid)["status"] == "filed"
    assert len(hapi.posted) == 1 and hapi.task_status["Task/1"] == "completed"
    cov = audit.coverage(rid)
    assert all(cov[e] for e in ("request_sent", "link_opened", "identity_checked", "answer_sent", "answer_filed"))
    assert audit.verify_chain()


def test_m1_wrong_address_stranger_sees_nothing(hapi, outbox):
    rid = _send(REQ1.replace("labor-kanal", "labor-kanaI"))
    with TestClient(app) as client:
        r = _answer(client, link_path(outbox[0]["link"]), "unbekannt", "lab-result-maria-beispiel.md")
    assert r.status_code == 403 and "Maria" not in r.text
    events = [(e["event"], e["details"].get("result")) for e in audit.entries(rid)]
    assert ("identity_checked", "FAILED") in events and ("misdelivery_caught", None) in events
    assert not hapi.posted


def test_m2_forwarded_colleague_blocked(hapi, outbox):
    rid = _send(REQ1)
    with TestClient(app) as client:
        r = _answer(client, link_path(outbox[0]["link"]), "karl", "lab-result-maria-beispiel.md")
        assert client.get(link_path(outbox[0]["link"]) + "/answer").status_code == 404   # no session -> no form
    assert r.status_code == 403 and not hapi.posted
    assert any("Karl Kollege" in m["text"] and "Dr. Eva Brandl" in m["text"] for m in db.query("SELECT * FROM matrix_outbox"))
    assert audit.coverage(rid)["misdelivery_caught"]


def test_m3_wrong_patient_not_filed(hapi, outbox):
    rid = _send(REQ1)
    with TestClient(app) as client:
        r = _answer(client, link_path(outbox[0]["link"]), "eva", "lab-result-max-beispiel.md",
                    typed=("Max Beispiel", "01.01.1960"))
    assert "nicht zugeordnet" in r.text
    assert not hapi.posted and db.get("requests", "id", rid)["status"] == "rejected"
    msgs = [m["text"] for m in db.query("SELECT * FROM matrix_outbox WHERE request_id = ?", (rid,))]
    assert msgs and all("Max" not in m and "1960" not in m for m in msgs)
    assert all("Max" not in str(e["details"]) for e in audit.entries(rid))
    assert audit.coverage(rid)["misdelivery_caught"]


def test_request_2_by_sms(hapi, outbox):
    rid = _send(REQ2)
    sms = db.query("SELECT * FROM sms_outbox")[0]
    link = re.search(r"https?://\S+", sms["body"]).group(0)
    with TestClient(app) as client:
        assert "Simulation" in client.get("/sms").text
        r = _answer(client, link_path(link), "stefan", "rehab-report-maria-beispiel.md")
    assert "sicher übermittelt" in r.text and db.get("requests", "id", rid)["status"] == "filed"


def test_link_is_single_use(hapi, outbox):
    _send(REQ1)
    path = link_path(outbox[0]["link"])
    with TestClient(app) as client:
        _answer(client, path, "eva", "lab-result-maria-beispiel.md")
        assert client.get(path).status_code == 404


def test_dob_typed_without_dots_is_filed(hapi, outbox):
    """Phone number pads have no dot; '12031961' must not push a correct answer into review."""
    rid = _send(REQ1)
    with TestClient(app) as client:
        r = _answer(client, link_path(outbox[0]["link"]), "eva", "lab-result-maria-beispiel.md",
                    typed=("Maria Beispiel", "12031961"))
    assert "sicher übermittelt" in r.text and db.get("requests", "id", rid)["status"] == "filed"


def test_m3_receipt_has_no_tick_and_doctor_gets_next_step(hapi, outbox):
    rid = _send(REQ1)
    with TestClient(app) as client:
        r = _answer(client, link_path(outbox[0]["link"]), "eva", "lab-result-max-beispiel.md",
                    typed=("Max Beispiel", "01.01.1960"))
    assert "✓ Danke" not in r.text and "meldet sich bei Ihnen" in r.text
    assert "!anfrage" in db.query("SELECT text FROM matrix_outbox WHERE request_id = ?", (rid,))[-1]["text"]


def test_hapi_down_keeps_link_valid(hapi, outbox, monkeypatch):
    from app import fhir_client
    import httpx
    rid = _send(REQ1)
    path = link_path(outbox[0]["link"])

    def down(bundle):
        raise httpx.ConnectError("HAPI down")
    with TestClient(app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(fhir_client, "validate", down)
        r = _answer(client, path, "eva", "lab-result-maria-beispiel.md")
        assert r.status_code == 503 and "Link bleibt gültig" in r.text
        assert db.get("requests", "id", rid)["status"] == "identified" and not hapi.posted
        assert "nicht verarbeitet" in db.query("SELECT text FROM matrix_outbox")[-1]["text"]
        monkeypatch.setattr(fhir_client, "validate", hapi.validate)          # HAPI back: same link, send again
        r = client.post(f"{path}/answer", data={"typed_name": "Maria Beispiel", "typed_dob": "12.03.1961"},
                        files={"upload": ("befund.md", doc("lab-result-maria-beispiel.md").encode(), "text/markdown")})
    assert "sicher übermittelt" in r.text and len(hapi.posted) == 1


def test_oversized_text_upload_refused_link_stays_valid(hapi, outbox):
    rid = _send(REQ1)
    path = link_path(outbox[0]["link"])
    with TestClient(app) as client:
        client.get(path)
        client.post("/eid/authorize", data={"state": path.rsplit("/", 1)[1], "citizen": "eva"})
        r = client.post(f"{path}/answer", data={"typed_name": "Maria Beispiel", "typed_dob": "12.03.1961"},
                        files={"upload": ("big.md", b"x" * (2 * 2**20), "text/markdown")})
        assert r.status_code == 400 and "zu groß" in r.text
        assert client.get(f"{path}/answer").status_code == 200
    assert db.get("requests", "id", rid)["status"] == "identified"


def test_link_claim_is_atomic(hapi, outbox):
    from app import tokens
    _send(REQ1)
    raw = link_path(outbox[0]["link"]).rsplit("/", 1)[1]
    assert tokens.claim(raw) and not tokens.claim(raw)


def test_wrong_doc_type_goes_to_review(hapi, outbox):
    """Lab request answered with a discharge report must go to review, not be auto-filed (P1 / O1)."""
    rid = _send(REQ1)          # REQ1 is a `labor` (doc_type=lab) request
    with TestClient(app) as client:
        # Submit a discharge/rehab report (doc kind=report) in answer to a lab request
        r = _answer(client, link_path(outbox[0]["link"]), "eva", "rehab-report-maria-beispiel.md")
    # The sender sees the "under review" receipt, not the success message
    assert "sicher übermittelt" not in r.text
    req_row = db.get("requests", "id", rid)
    assert req_row["status"] == "review", f"Expected review, got {req_row['status']}"
    assert not hapi.posted, "Wrong-doc-type answer must not be filed on HAPI"
    # Dr. Hofer's Matrix message must mention the mismatch
    msgs = [m["text"] for m in db.query("SELECT text FROM matrix_outbox WHERE request_id = ?", (rid,))]
    assert any("Falscher Dokumenttyp" in m or "Laborbefund" in m for m in msgs), \
        f"Expected mismatch reason in doctor notification, got: {msgs}"
