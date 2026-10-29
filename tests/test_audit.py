import pytest

from app import audit, db


def test_chain_verifies_and_detects_tampering():
    audit.log("request_sent", "r1", "@lena.hofer:klinikum.example", {"x": 1})
    audit.log("link_opened", "r1", "link ip=1.2.3.4", {})
    assert audit.verify_chain()
    with db.conn() as c:
        c.execute("UPDATE audit SET actor = 'someone else' WHERE seq = 1")
    assert not audit.verify_chain()


def test_unknown_event_is_rejected():
    with pytest.raises(ValueError):
        audit.log("request_snet", "r1", "x", {})
