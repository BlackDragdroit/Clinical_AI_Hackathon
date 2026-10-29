"""Tell Dr. Hofer something. CONTRACT: everyone calls `notify.doctor(text, request_id)`.

Messages go into the matrix_outbox table; the bot (MATRIX_ENABLED=1) or the console printer
(MATRIX_ENABLED=0) drains it. So nobody depends on Synapse being up to develop their part.
"""
from __future__ import annotations

from app import db


def doctor(text: str, request_id: str | None = None) -> None:
    db.insert("matrix_outbox", {"ts": db.now(), "request_id": request_id, "text": text})


def pending() -> list[dict]:
    return db.query("SELECT * FROM matrix_outbox WHERE sent_at IS NULL ORDER BY id")


def mark_sent(msg_id: int) -> None:
    db.update("matrix_outbox", "id", msg_id, sent_at=db.now())
