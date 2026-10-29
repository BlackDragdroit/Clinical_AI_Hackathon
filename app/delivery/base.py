"""Delivery channel CONTRACT. Every vendor sits behind this (track rule: each component replaceable).

A channel only ever receives the recipient and the opaque link. It never sees the patient, the
document type or the reason, so it cannot leak them (hard rule 1). Texts come from messages.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.config import settings

_env = Environment(loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "templates" / "messages"),
                   undefined=StrictUndefined, autoescape=False)

# every outgoing text template; the leak test renders all of them
MESSAGE_TEMPLATES = ("email_subject.txt", "email_body.txt", "sms.txt")


def render_message(template: str, link: str) -> str:
    """The ONLY variables a message may use: the link and the clinic name."""
    return _env.get_template(template).render(link=link, clinic=settings.clinic_name).strip()


class Channel(ABC):
    kind: str            # email | sms

    @abstractmethod
    def send(self, to: str, link: str) -> str:
        """Send the neutral message with `link` to `to`. Returns a provider message id."""
