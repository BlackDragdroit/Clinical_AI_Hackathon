"""Reactions as buttons: tapping "Senden", "Ablegen" or "Verwerfen" under a bot message runs the command that message
offers. Owner: SWE 1.

When the bot posts a message that names `!senden <id>`, or `!ablegen <id>` / `!verwerfen <id>`, it reacts with that
word itself, so Dr. Hofer only has to tap the pill (a reaction key can be any string; Element shows it as a text pill,
so the chat needs no emoji). Emoji taps still count: ✅ / 👍 press a message's Senden or Ablegen, ❌ / 👎 its
Verwerfen, and older messages keep their ✅ / ❌ pills. The command then goes through commands.handle like a typed
one, so AUTHORIZED_SENDERS applies unchanged. Each message's buttons work once: after the first authorised tap,
further taps on that message do nothing.
"""
from __future__ import annotations

import re

from app import commands, db
from app.config import settings

SENDEN, ABLEGEN, VERWERFEN = "Senden", "Ablegen", "Verwerfen"
_KEY = {"senden": SENDEN, "ablegen": ABLEGEN, "verwerfen": VERWERFEN}   # the button each command gets
# an emoji tap presses the message's yes or no button; "✅" / "❌" were the buttons before the words
YES, NO = (SENDEN, ABLEGEN, "✅"), (VERWERFEN, "❌")
ALIASES = {"✅": YES, "👍": YES, "❌": NO, "👎": NO}
_CMD = re.compile(r"!(senden|ablegen|verwerfen) ([a-z0-9]{8})\b")


def buttons(text: str) -> dict[str, str]:
    """{reaction key: command} offered by a bot message,
    e.g. {'Ablegen': '!ablegen ab12cd34', 'Verwerfen': '!verwerfen ab12cd34'}."""
    out: dict[str, str] = {}
    for verb, rid in _CMD.findall(text):
        out.setdefault(_KEY[verb], f"!{verb} {rid}")
    return out


def offer(event_id: str, offered: dict[str, str]) -> list[str]:
    """Remembers the buttons {key: command} of a message the bot just sent; returns the keys to react with."""
    for key, command in offered.items():
        db.insert("matrix_actions", {"event_id": event_id, "key": key, "command": command})
    return list(offered)


def register(event_id: str, text: str) -> list[str]:
    """Like offer(), with the buttons a message's text names."""
    return offer(event_id, buttons(text))


def spend(command: str) -> None:
    """`command` ran (typed or tapped): every message offering it has its buttons used up, so a later tap
    cannot run it again or its alternative."""
    with db.conn() as c:
        c.execute("UPDATE matrix_actions SET used_at = ? WHERE used_at IS NULL AND event_id IN "
                  "(SELECT event_id FROM matrix_actions WHERE command = ?)", (db.now(), command.strip()))


def handle(event_id: str, key: str, sender: str) -> tuple[str, str] | None:
    """A reaction arrived. Returns (command run, the bot's reply), or None if the reaction is not a button."""
    key = key.replace("\ufe0f", "")                    # ✅️ (emoji presentation) is ✅
    keys = ALIASES.get(key, (key,))                    # a word presses only its own button
    rows = [r for r in db.query("SELECT * FROM matrix_actions WHERE event_id = ? AND used_at IS NULL", (event_id,))
            if r["key"] in keys]
    if not rows:
        return None
    command = rows[0]["command"]
    reply = commands.handle(command, sender)
    if sender in settings.authorized_senders:     # an unauthorised tap is refused and does not use the button up
        with db.conn() as c:
            c.execute("UPDATE matrix_actions SET used_at = ? WHERE event_id = ?", (db.now(), event_id))
    return command, reply
