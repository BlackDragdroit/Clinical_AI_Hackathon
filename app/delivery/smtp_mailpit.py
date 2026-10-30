"""Email via plain SMTP. In the stack this is Mailpit; in production any SMTP relay. Owner: SWE 2."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from app.config import settings
from app.delivery.base import Channel, render_message


class SmtpMailpit(Channel):
    kind = "email"

    def send(self, to: str, link: str) -> str:
        msg = EmailMessage()
        msg["From"] = f"{settings.clinic_name} <{settings.mail_from}>"
        msg["To"] = to
        msg["Subject"] = render_message("email_subject.txt", link)
        msg["Message-ID"] = make_msgid(domain="klinikum.example")
        msg.set_content(render_message("email_body.txt", link))
        msg.add_alternative(render_message("email_body.html", link), subtype="html")   # big button on phones
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
            s.send_message(msg)
        return msg["Message-ID"]
