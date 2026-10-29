"""Opaque single-use links. Owner: SWE 2.

256-bit random token, only its sha256 stored, bound to request + contact, TTL from settings,
max identity attempts from settings, single use (used_at set when the answer is submitted).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app import db
from app.config import settings


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue(request_id: str, contact: str) -> str:
    raw = secrets.token_urlsafe(32)
    created = datetime.now(timezone.utc)
    db.insert("tokens", {"token_hash": _hash(raw), "request_id": request_id, "contact": contact,
                         "created_at": created.isoformat(timespec="seconds"),
                         "expires_at": (created + timedelta(hours=settings.link_ttl_hours)).isoformat(timespec="seconds")})
    return raw


def link_for(raw: str) -> str:
    return f"{settings.base_url}/r/{raw}"


def resolve(raw: str) -> dict | None:
    """Token row if the link is valid right now (exists, not expired, not used, attempts left), else None.
    The caller shows the same neutral page either way, so a guesser learns nothing."""
    row = db.get("tokens", "token_hash", _hash(raw))
    if not row or row["used_at"] or row["id_attempts"] >= settings.max_identity_attempts:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        return None
    return row


def token_hash(raw: str) -> str:
    return _hash(raw)


def count_failed_attempt(raw: str) -> int:
    with db.conn() as c:
        c.execute("UPDATE tokens SET id_attempts = id_attempts + 1 WHERE token_hash = ?", (_hash(raw),))
        return c.execute("SELECT id_attempts FROM tokens WHERE token_hash = ?", (_hash(raw),)).fetchone()[0]


def mark_used(raw: str) -> None:
    db.update("tokens", "token_hash", _hash(raw), used_at=db.now())
