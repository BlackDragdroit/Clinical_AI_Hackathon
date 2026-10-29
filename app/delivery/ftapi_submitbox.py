"""FTAPI SubmitBox adapter (track partner). Owner: SWE 1.

Design: FTAPI hosts the public upload page as the third-party trust provider; it sees no patient
identity before the identity check. Status: NOT wired. FTAPI documents that a REST API exists
("Für individuelle Systemlösungen bietet FTAPI eine REST-API", ftapi.com/plattform/integrationen),
but publishes no reference; the API is licence-gated (Secure Intelligence / Enterprise tiers).
We do not guess endpoints. EMAIL_CHANNEL=mailpit is the default; this class only shows where FTAPI plugs in.

What we need from FTAPI to implement send() (ask at the booth):
  1. a test tenant with API access, its base URL, the auth method and header names
  2. the call that creates a per-request SubmitBox / "Datei anfordern" link for a named recipient
     (and whether links can be per request at all, or only one static mailbox per user)
  3. the call that sends a SecuMail to the recipient (or whether FTAPI sends the invitation itself)
  4. how we learn an upload arrived (webhook or polling) and the call to download it
"""
from __future__ import annotations

from app.delivery.base import Channel


class FtapiSubmitBox(Channel):
    kind = "email"

    def send(self, to: str, link: str) -> str:
        raise NotImplementedError("FTAPI adapter not wired (no public API reference); set EMAIL_CHANNEL=mailpit")
