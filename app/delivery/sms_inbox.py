"""Simulated SMS: messages land in a table and are shown on /sms (the track allows this).
A real gateway (e.g. an SMS API) would be another Channel with the same send(). Owner: SWE 2."""
from __future__ import annotations

from app import db
from app.delivery.base import Channel, render_message


class SmsInbox(Channel):
    kind = "sms"

    def send(self, to: str, link: str) -> str:
        db.insert("sms_outbox", {"ts": db.now(), "to_number": to, "body": render_message("sms.txt", link)})
        return f"sms-{db.query('SELECT max(id) AS i FROM sms_outbox')[0]['i']}"
