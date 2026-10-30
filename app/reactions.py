"""Reactions as buttons: tapping ✅ / ❌ under a bot message runs the command that message offers. Owner: SWE 1.

When the bot posts a message that names `!senden <id>`, or `!ablegen <id>` / `!verwerfen <id>`, it reacts
with ✅ (and ❌) itself, so Dr. Hofer only has to tap the pill. The command then goes through
commands.handle like a typed one, so AUTHORIZED_SENDERS applies unchanged. Each message's buttons work
once: after the first authorised tap, further taps on that message do nothing.
"""
from __future__ import annotations

import re

from app import commands, db
from app.config import settings

YES, NO = "✅", "❌"
ALIASES = {"✅": YES, "👍": YES, "❌": NO, "👎": NO}
_CMD = re.compile(r"!(senden|ablegen|verwerfen) ([a-z0-9]{8})\b")
_KEY = {"senden": YES, "ablegen": YES, "verwerfen": NO}


def buttons(text: str) -> dict[str, str]:
    """{reaction key: command} offered by a bot message, e.g. {'✅': '!ablegen ab12cd34', '❌': '!verwerfen ab12cd34'}."""
    out: dict[str, str] = {}
    for verb, rid in _CMD.findall(text):
        out.setdefault(_KEY[verb], f"!{verb} {rid}")
    return out


def register(event_id: str, text: str) -> list[str]:
    """Remembers the buttons of a message the bot just sent; returns the keys the bot should react with."""
    offered = buttons(text)
    for key, command in offered.items():
        db.insert("matrix_actions", {"event_id": event_id, "key": key, "command": command})
    return list(offered)


def handle(event_id: str, key: str, sender: str) -> str | None:
    """A reaction arrived. Returns the bot's reply, or None if the reaction is not a button."""
    key = ALIASES.get(key.replace("️", ""))
    rows = db.query("SELECT * FROM matrix_actions WHERE event_id = ? AND key = ? AND used_at IS NULL", (event_id, key))
    if not rows:
        return None
    reply = commands.handle(rows[0]["command"], sender)
    if sender in settings.authorized_senders:     # an unauthorised tap is refused and does not use the button up
        with db.conn() as c:
            c.execute("UPDATE matrix_actions SET used_at = ? WHERE event_id = ?", (db.now(), event_id))
    return reply
