import pytest

from app.commands import parse_anfrage
from tests.conftest import REQ1, REQ2


def test_parse_request_1():
    p = parse_anfrage(REQ1)
    assert p == {"doc_kind": "labor", "expected_name": "Dr. Eva Brandl", "contact": "eva.brandl@labor-kanal.example",
                 "patient_ref": "Patient/maria-beispiel", "reason": "Gerinnung vor Eingriff"}


def test_parse_request_2_sms():
    assert parse_anfrage(REQ2)["contact"] == "+436600000101"


def test_bad_command_raises():
    with pytest.raises(ValueError):
        parse_anfrage("!anfrage labor nur zwei")
