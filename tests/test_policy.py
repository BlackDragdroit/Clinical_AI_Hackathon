import pytest

from app.identity import eid_mock, policy
from app.identity.eid_mock import EidAssertion

EVA, KARL = eid_mock.TEST_CITIZENS["eva"], eid_mock.TEST_CITIZENS["karl"]


def eid(given: str, family: str) -> EidAssertion:
    return EidAssertion(given, family, "1979-05-04", "bpk-test", "high")


@pytest.mark.parametrize("expected", ["Dr. Eva Brandl", "eva brandl", "OÄ Dr. med. Eva Brandl"])
def test_named_person_matches(expected):
    assert policy.names_match(expected, EVA)


def test_colleague_does_not_match():
    assert not policy.names_match("Dr. Eva Brandl", KARL)


@pytest.mark.parametrize("expected, given, family", [
    ("Dr. Eva Brandl", "Eva", "Brandl"),                                   # exact
    ("DR. EVA BRANDL", "Eva", "Brandl"),                                   # case
    ("Univ.-Prof. Dr. Eva Brandl, MSc", "Eva", "Brandl"),                  # titles before and after
    ("Jürgen Weiß", "Juergen", "Weiss"),                                   # umlaut / ß spelling
    ("Dr. Eva Müller-Lüdenscheidt", "Eva", "Mueller-Luedenscheidt"),       # umlaut in a double family name
    ("Eva Müller Lüdenscheidt", "Eva", "Müller-Lüdenscheidt"),             # hyphen vs space, family
    ("Eva-Maria Brandl", "Eva Maria", "Brandl"),                           # hyphen vs space, given
    ("Eva Maria Brandl", "Eva-Maria", "Brandl"),
    ("Dr. Eva Brandl", "Eva Maria", "Brandl"),                             # extra middle name on the eID
    ("Dr. Maria Brandl", "Eva Maria", "Brandl"),                           # typed the second given name only
    ("Eva von Brandl", "Eva", "von Brandl"),                               # multi-token family name
])
def test_same_person_matches(expected, given, family):
    assert policy.names_match(expected, eid(given, family))


@pytest.mark.parametrize("expected, given, family", [
    ("Dr. Eva Brandl", "Karl", "Kollege"),                                 # different person (M2)
    ("Dr. Eva Brandl", "Anna", "Brandl"),                                  # same family, different given name
    ("Dr. Eva Müller-Brandl", "Eva", "Brandl"),                            # family part missing on the eID
    ("Dr. Eva Brandl", "Eva", "Müller-Brandl"),                            # eID has an extra family part
    ("Eva Maria Brandl", "Eva", "Brandl"),                                 # typed middle name not on the eID
    ("Maria Eva Brandl", "Eva Maria", "Brandl"),                           # given names in another order
    ("Dr. Brandl", "Eva", "Brandl"),                                       # family name alone never binds
    ("Brandl Eva", "Eva", "Brandl"),                                       # family-first order not guessed
    ("Dr. Eva Brandt", "Eva", "Brandl"),                                   # one letter off is a different name
    ("", "Eva", "Brandl"),
])
def test_other_person_does_not_match(expected, given, family):
    assert not policy.names_match(expected, eid(given, family))
