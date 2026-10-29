"""FTAPI SubmitBox adapter (track partner). Owner: SWE 1.

Design: FTAPI hosts the public upload page as the third-party trust provider; it sees no patient
identity before the identity check. If FTAPI gives us API access on site, implement send() against
it; otherwise keep this stub and say so in the README + video (it's a replaceable adapter, set
EMAIL_CHANNEL=mailpit).
"""
from __future__ import annotations

from app.delivery.base import Channel


class FtapiSubmitBox(Channel):
    kind = "email"

    def send(self, to: str, link: str) -> str:
        # TODO(SWE 1): ask the FTAPI people for sandbox API access + docs; never invent endpoints
        raise NotImplementedError("FTAPI adapter not wired; set EMAIL_CHANNEL=mailpit")
