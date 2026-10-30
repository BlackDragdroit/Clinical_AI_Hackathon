"""One Matrix status message per request, edited in place as the request moves. Owner: SWE 1.

The bot posts it once the request is sent and edits it on every change, so the room shows the progress
without a new message per step. The steps are the dashboard's (app/dashboard.py), from the audit log.
Alerts and results still arrive as their own messages via the notify outbox.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app import dashboard, db

TZ = ZoneInfo("Europe/Vienna")
ICON = {"done": "✅", "current": "⏳", "todo": "◻️", "warn": "⚠️", "error": "❌"}


def _time(ts: str) -> str:
    return datetime.fromisoformat(ts).astimezone(TZ).strftime("%H:%M")


def text(card: dict) -> str:
    steps = " → ".join(f"{ICON[s['state']]} {s['label']}" + (f" {_time(s['ts'])}" if s["ts"] else "")
                       for s in card["steps"])
    lines = [f"📋 Anfrage {card['id']} · {card['doc']} · {card['patient']} → {card['to']}", steps]
    lines += [f"⚠️ {a}" for a in card["alerts"]]
    if card["hint"]:
        lines.append(f"Im Chat: {card['hint']}")
    return "\n".join(lines)


def updates(since: str) -> list[tuple[str | None, str, str]]:
    """(event_id or None for a new message, request_id, text) for every status message that must change.
    Requests sent before `since` (the bot's start) get no new message, so a restart does not flood the room."""
    known = {r["request_id"]: r for r in db.query("SELECT * FROM matrix_status")}
    out = []
    for card in dashboard.cards():
        sent = card["steps"][0]["ts"]
        if not sent:
            continue                                    # drafts: the draft reply is the message
        new = text(card)
        row = known.get(card["id"])
        if row and row["text"] != new:
            out.append((row["event_id"], card["id"], new))
        elif not row and sent >= since:
            out.append((None, card["id"], new))
    return out


def saved(request_id: str, event_id: str, text_now: str) -> None:
    if db.get("matrix_status", "request_id", request_id):
        db.update("matrix_status", "request_id", request_id, text=text_now)
    else:
        db.insert("matrix_status", {"request_id": request_id, "event_id": event_id, "text": text_now})
