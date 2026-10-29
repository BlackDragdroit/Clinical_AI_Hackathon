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
