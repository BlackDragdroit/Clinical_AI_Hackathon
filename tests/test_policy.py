import pytest

from app.identity import eid_mock, policy

EVA, KARL = eid_mock.TEST_CITIZENS["eva"], eid_mock.TEST_CITIZENS["karl"]


@pytest.mark.parametrize("expected", ["Dr. Eva Brandl", "eva brandl", "OÄ Dr. med. Eva Brandl"])
def test_named_person_matches(expected):
    assert policy.names_match(expected, EVA)


def test_colleague_does_not_match():
    assert not policy.names_match("Dr. Eva Brandl", KARL)
