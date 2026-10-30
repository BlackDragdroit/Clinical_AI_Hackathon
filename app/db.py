"""SQLite schema and the few helpers everyone uses. CONTRACT: change a column only after telling the team.

requests.status lifecycle:
  draft -> sent -> opened -> identified -> answered -> filed
                                                    -> review -> filed | discarded
                                                    -> rejected (quarantined)
  any state before answered -> blocked (identity attempts exhausted)
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    doc_type TEXT NOT NULL,              -- lab | report
    patient_ref TEXT NOT NULL,           -- Patient/maria-beispiel
    patient_name TEXT NOT NULL,          -- from HAPI, never sent outside before identity check
    patient_dob TEXT NOT NULL,           -- ISO date
    expected_name TEXT NOT NULL,         -- the named outside person, e.g. Dr. Eva Brandl
    contact_kind TEXT NOT NULL,          -- email | sms
    contact TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    task_ref TEXT,                       -- Task/123 on HAPI
    lint_warnings TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS tokens (
    token_hash TEXT PRIMARY KEY,         -- sha256 of the raw link token; the raw token is never stored
    request_id TEXT NOT NULL REFERENCES requests(id),
    contact TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,                        -- set when the answer is submitted (single use)
    id_attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS answers (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES requests(id),
    received_at TEXT NOT NULL,
    verified_name TEXT NOT NULL,
    identity_method TEXT NOT NULL,
    typed_name TEXT NOT NULL,
    typed_dob TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    decision TEXT NOT NULL,              -- file | review | reject (from core) after policy downgrade
    intake_json TEXT NOT NULL,           -- match details + messages
    bundle_json TEXT,                    -- transaction bundle (null on reject)
    filed_refs TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    request_id TEXT,
    actor TEXT NOT NULL,
    details TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sms_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    to_number TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS matrix_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    request_id TEXT,
    text TEXT NOT NULL,
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS matrix_status (
    request_id TEXT PRIMARY KEY REFERENCES requests(id),
    event_id TEXT NOT NULL,              -- the bot's status message, edited in place as the request moves
    text TEXT NOT NULL                   -- what that message says now
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def _connect() -> sqlite3.Connection:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(settings.db_path, isolation_level=None, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    con = _connect()
    try:
        yield con
    finally:
        con.close()


def init_db() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def insert(table: str, row: dict[str, Any]) -> None:
    row = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in row.items()}
    cols = ", ".join(row)
    with conn() as c:
        c.execute(f"INSERT INTO {table} ({cols}) VALUES ({', '.join('?' * len(row))})", list(row.values()))


def update(table: str, key: str, key_value: Any, **fields: Any) -> None:
    fields = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in fields.items()}
    with conn() as c:
        c.execute(f"UPDATE {table} SET {', '.join(f'{k} = ?' for k in fields)} WHERE {key} = ?",
                  [*fields.values(), key_value])


def get(table: str, key: str, key_value: Any) -> dict | None:
    with conn() as c:
        r = c.execute(f"SELECT * FROM {table} WHERE {key} = ?", (key_value,)).fetchone()
    return dict(r) if r else None


def query(sql: str, params: tuple = ()) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]
