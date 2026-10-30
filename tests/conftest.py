"""Test setup: a fresh SQLite per test, a fake HAPI and a fake mail channel. No network, no Docker."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

os.environ.setdefault("DB_PATH", str(Path(tempfile.mkdtemp()) / "test.sqlite"))
os.environ.setdefault("MATRIX_ENABLED", "0")

import pytest  # noqa: E402

from app import db, fhir_client  # noqa: E402
from app.config import settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCENARIO = ROOT / "scenario"
REQ1 = '!anfrage labor "Dr. Eva Brandl" eva.brandl@labor-kanal.example Patient/maria-beispiel Grund: Gerinnung vor Eingriff'
REQ2 = '!anfrage bericht "Stefan Kern" +436600000101 Patient/maria-beispiel Grund: Entlassungsbericht'


def doc(name: str) -> str:
    return (SCENARIO / "documents" / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    object.__setattr__(settings, "db_path", str(tmp_path / "bb.sqlite"))
    object.__setattr__(settings, "var_dir", str(tmp_path / "var"))
    db.init_db()
    yield


class FakeHapi:
    def __init__(self):
        self.posted: list[dict] = []
        self.task_status: dict[str, str] = {}

    def read_patient(self, ref):
        assert ref in ("Patient/maria-beispiel", "Patient/maria-1985")
        return {"name": "Maria Beispiel", "dob": "1961-03-12" if ref == "Patient/maria-beispiel" else "1985-07-02"}

    def search_patients(self, family, birthdate):
        maria = {"ref": "Patient/maria-beispiel", "name": "Maria Beispiel", "dob": "1961-03-12"}
        namesake = {"ref": "Patient/maria-1985", "name": "Maria Beispiel", "dob": "1985-07-02"}
        return [p for p in (maria, namesake) if p["dob"] == birthdate or (family or "").lower() == "beispiel"]

    def create_task(self, req):
        ref = f"Task/{len(self.task_status) + 1}"
        self.task_status[ref] = "requested"
        return ref

    def set_task_status(self, ref, status, output_refs=None):
        self.task_status[ref] = status

    def validate(self, bundle):
        return []

    def post_transaction(self, bundle):
        self.posted.append(bundle)
        return [f"{e['resource']['resourceType']}/{i}" for i, e in enumerate(bundle["entry"])]


@pytest.fixture
def hapi(monkeypatch):
    fake = FakeHapi()
    for name in ("read_patient", "search_patients", "create_task", "set_task_status", "validate", "post_transaction"):
        monkeypatch.setattr(fhir_client, name, getattr(fake, name))
    return fake


@pytest.fixture
def outbox(monkeypatch):
    """Captures sent emails instead of talking SMTP. SMS uses the real in-app inbox."""
    sent: list[dict] = []
    from app.delivery.smtp_mailpit import SmtpMailpit
    from app.delivery.base import render_message

    def fake_send(self, to, link):
        sent.append({"to": to, "link": link, "subject": render_message("email_subject.txt", link),
                     "body": render_message("email_body.txt", link)})
        return f"<msg{len(sent)}@test>"
    monkeypatch.setattr(SmtpMailpit, "send", fake_send)
    return sent


def link_path(link: str) -> str:
    return re.sub(r"^https?://[^/]+", "", link)
