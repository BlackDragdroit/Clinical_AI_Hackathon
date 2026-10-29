from app import db, tokens
from app.config import settings
from app.identity import eid_mock


def _req():
    db.insert("requests", {"id": "r1", "created_at": db.now(), "doc_type": "lab", "patient_ref": "Patient/x",
                           "patient_name": "A B", "patient_dob": "2000-01-01", "expected_name": "Dr. Eva Brandl",
                           "contact_kind": "email", "contact": "e@x.example", "status": "sent"})


def test_token_is_256_bit_and_only_hash_stored():
    _req()
    raw = tokens.issue("r1", "e@x.example")
    assert len(raw) >= 43
    assert db.query("SELECT count(*) AS n FROM tokens WHERE token_hash = ?", (raw,))[0]["n"] == 0
    assert tokens.resolve(raw)["request_id"] == "r1"


def test_token_single_use_and_attempt_limit():
    _req()
    raw = tokens.issue("r1", "e@x.example")
    for _ in range(settings.max_identity_attempts):
        tokens.count_failed_attempt(raw)
    assert tokens.resolve(raw) is None
    raw2 = tokens.issue("r1", "e@x.example")
    tokens.mark_used(raw2)
    assert tokens.resolve(raw2) is None


def test_expired_token_is_invalid():
    _req()
    raw = tokens.issue("r1", "e@x.example")
    db.update("tokens", "token_hash", tokens.token_hash(raw), expires_at="2000-01-01T00:00:00+00:00")
    assert tokens.resolve(raw) is None


def test_eid_assertion_tamper_fails():
    a = eid_mock.issue("eva")
    assert eid_mock.verify(a).family == "Brandl"
    raw, mac = a.split(".")
    assert eid_mock.verify(raw[:-2] + "xx." + mac) is None


def _client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


def test_landing_neutral_text_is_exact_in_german_and_english():
    _req()
    raw = tokens.issue("r1", "e@x.example")
    with _client() as c:
        assert f"{settings.clinic_name} hat eine sichere Dokumentenanfrage an Sie gerichtet." in c.get(f"/r/{raw}").text
        c.get("/lang/en?next=/health")
        en = c.get(f"/r/{raw}").text
    assert f"{settings.clinic_name} has sent you a secure document request." in en
    assert 'lang="en"' in en


def test_lang_switch_rejects_open_redirect():
    with _client() as c:
        for bad in ("https://evil.example", "//evil.example", "/\\evil.example"):
            r = c.get("/lang/en", params={"next": bad}, follow_redirects=False)
            assert r.headers["location"] == "/"
        assert c.get("/lang/xx", follow_redirects=False).cookies.get("bb_lang") == "de"


def test_eid_page_is_labelled_simulation_in_both_languages():
    with _client() as c:
        assert "SIMULATION" in c.get("/eid/authorize?state=x").text
        c.get("/lang/en")
        assert "SIMULATION" in c.get("/eid/authorize?state=x").text


def test_attempts_exhausted_blocks_request_and_alerts_once():
    from app import audit
    _req()
    raw = tokens.issue("r1", "e@x.example")
    statuses, bodies = [], []
    with _client() as c:
        for _ in range(settings.max_identity_attempts + 2):
            r = c.get(f"/r/{raw}/callback", params={"assertion": eid_mock.issue("karl")})
            statuses.append(r.status_code)
            bodies.append(r.text)
        landing = c.get(f"/r/{raw}")
        unknown = c.get("/r/does-not-exist")
    n = settings.max_identity_attempts
    assert statuses[:n - 1] == [403] * (n - 1)
    assert statuses[n - 1:] == [404] * 3                       # last failed attempt and later ones: neutral dead-link page
    import re
    def strip(html): return re.sub(r'<a class="lang".*?</a>', "", html)     # the toggle echoes the page's own path
    assert strip(bodies[n - 1]) == strip(bodies[n]) == strip(unknown.text) == strip(landing.text)
    assert db.get("requests", "id", "r1")["status"] == "blocked"
    alerts = [m for m in db.query("SELECT * FROM matrix_outbox WHERE request_id = 'r1'") if "gesperrt" in m["text"]]
    assert len(alerts) == 1
    flags = [e["details"]["blocked"] for e in audit.entries("r1") if e["event"] == "identity_checked"]
    assert flags == [False] * (n - 1) + [True]                 # the exhausting attempt is marked in the audit trail
