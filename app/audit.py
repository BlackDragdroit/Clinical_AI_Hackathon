"""Append-only, hash-chained audit log. CONTRACT: everyone calls `audit.log(...)`. Owner: MedEng.

Every entry answers who (actor), what (event + details), when (ts). Each hash covers the previous
hash, so editing or deleting a row breaks `verify_chain()`.

Details must never contain the name or birth date of a patient other than the requested one (M3).
"""
from __future__ import annotations

import hashlib
import json

from app import db

# the six steps the track measures (README "Audit coverage")
REQUIRED = ("request_sent", "link_opened", "identity_checked", "answer_sent", "answer_filed", "misdelivery_caught")
# extra events we log for need-to-know and review decisions
EXTRA = ("request_drafted", "patient_revealed", "review_requested", "review_decided")
EVENTS = REQUIRED + EXTRA

GENESIS = "0" * 64


def _digest(prev_hash: str, ts: str, event: str, request_id: str | None, actor: str, details: str) -> str:
    return hashlib.sha256("|".join([prev_hash, ts, event, request_id or "", actor, details]).encode()).hexdigest()


def log(event: str, request_id: str | None, actor: str, details: dict) -> dict:
    """actor examples: '@lena.hofer:klinikum.example', 'link ip=1.2.3.4', 'eid:<pseudonym> Eva Brandl',
    'system:befundbruecke'. Unknown event names raise, so a typo cannot silently drop a metric."""
    if event not in EVENTS:
        raise ValueError(f"unknown audit event {event!r}")
    ts = db.now()
    det = json.dumps(details, ensure_ascii=False, sort_keys=True)
    with db.conn() as c:
        c.execute("BEGIN IMMEDIATE")
        last = c.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else GENESIS
        h = _digest(prev, ts, event, request_id, actor, det)
        c.execute("INSERT INTO audit (ts, event, request_id, actor, details, prev_hash, hash) VALUES (?,?,?,?,?,?,?)",
                  (ts, event, request_id, actor, det, prev, h))
        c.execute("COMMIT")
    return {"ts": ts, "event": event, "request_id": request_id, "actor": actor, "details": details, "hash": h}


def entries(request_id: str | None = None) -> list[dict]:
    if request_id:
        rows = db.query("SELECT * FROM audit WHERE request_id = ? ORDER BY seq", (request_id,))
    else:
        rows = db.query("SELECT * FROM audit ORDER BY seq")
    for r in rows:
        r["details"] = json.loads(r["details"])
    return rows


def verify_chain() -> bool:
    prev = GENESIS
    for r in db.query("SELECT * FROM audit ORDER BY seq"):
        if r["prev_hash"] != prev or r["hash"] != _digest(prev, r["ts"], r["event"], r["request_id"], r["actor"], r["details"]):
            return False
        prev = r["hash"]
    return True


def coverage(request_id: str | None = None) -> dict[str, bool]:
    seen = {e["event"] for e in entries(request_id)}
    return {ev: ev in seen for ev in REQUIRED}
