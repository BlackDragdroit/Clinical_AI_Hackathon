"""Tests for TTL-based retention purge: P17."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import audit, db
from app.main import app


def _old_ts(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def _make_request() -> str:
    """Insert a minimal request row; returns its id."""
    rid = db.new_id()
    db.insert("requests", {
        "id": rid,
        "created_at": db.now(),
        "doc_type": "lab",
        "patient_ref": "Patient/test",
        "patient_name": "Test Patient",
        "patient_dob": "1980-01-01",
        "expected_name": "Dr. Test",
        "contact_kind": "email",
        "contact": "test@example.com",
        "reason": "Purge test",
        "status": "answered",
    })
    return rid


def _insert_answer(rid: str, decision: str, received_at: str) -> str:
    aid = db.new_id()
    db.insert("answers", {
        "id": aid,
        "request_id": rid,
        "received_at": received_at,
        "verified_name": "Dr. Test",
        "identity_method": "eid",
        "typed_name": "Dr. Test",
        "typed_dob": "1980-01-01",
        "filename": "test.md",
        "content": "# Test",
        "decision": decision,
        "intake_json": "{}",
    })
    return aid


def _insert_token(rid: str, used_at: str | None, created_at: str) -> str:
    import hashlib, secrets
    raw = secrets.token_urlsafe(16)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(timespec="seconds")
    db.insert("tokens", {
        "token_hash": token_hash,
        "request_id": rid,
        "contact": "test@example.com",
        "created_at": created_at,
        "expires_at": expires_at,
        "used_at": used_at,
    })
    return token_hash


def test_purge_removes_old_quarantine_and_tokens():
    rid = _make_request()

    # OLD reject answer (> 30 days) — should be purged
    old_reject = _insert_answer(rid, "reject", _old_ts(35))
    # RECENT reject answer (< 30 days) — must stay
    recent_reject = _insert_answer(rid, "reject", _old_ts(5))
    # Old file answer (not reject) — must stay regardless of age
    old_file = _insert_answer(rid, "file", _old_ts(35))

    # OLD used token (> 90 days) — should be purged
    old_used_token = _insert_token(rid, db.now(), _old_ts(95))
    # RECENT used token (< 90 days) — must stay
    recent_used_token = _insert_token(rid, db.now(), _old_ts(5))
    # OLD unused/unexpired token (> 90 days old, but used_at is None) — must stay (not used, not expired at time of check)
    # Actually per spec: tokens are purged when (used_at IS NOT NULL OR expires_at < now) AND created_at < cutoff.
    # A token with used_at=None and expires_at in the future won't be purged regardless of age.
    old_fresh_token = _insert_token(rid, None, _old_ts(95))

    # Record audit count before purge
    audit_before = len(db.query("SELECT * FROM audit"))

    with TestClient(app) as client:
        r = client.post("/admin/purge")
    assert r.status_code == 200
    body = r.json()
    assert body["purged_answers"] == 1
    assert body["purged_tokens"] == 1
    assert body["ttl_days"] == {"quarantine": 30, "token": 90}

    # Old reject gone, recent reject and file still here
    assert db.get("answers", "id", old_reject) is None
    assert db.get("answers", "id", recent_reject) is not None
    assert db.get("answers", "id", old_file) is not None

    # Old used token gone; recent used token and the old-but-fresh token still here
    assert db.get("tokens", "token_hash", old_used_token) is None
    assert db.get("tokens", "token_hash", recent_used_token) is not None
    assert db.get("tokens", "token_hash", old_fresh_token) is not None

    # Audit log untouched
    assert len(db.query("SELECT * FROM audit")) == audit_before
