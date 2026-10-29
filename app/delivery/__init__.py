"""Pick the channel for a contact. Owner: SWE 2 (email/SMS), SWE 1 (FTAPI adapter)."""
from __future__ import annotations

from app.config import settings
from app.delivery.base import Channel


def channel_for(contact_kind: str) -> Channel:
    if contact_kind == "sms":
        from app.delivery.sms_inbox import SmsInbox
        return SmsInbox()
    if settings.email_channel == "ftapi":
        from app.delivery.ftapi_submitbox import FtapiSubmitBox
        return FtapiSubmitBox()
    from app.delivery.smtp_mailpit import SmtpMailpit
    return SmtpMailpit()
