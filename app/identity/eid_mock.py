"""Simulated ID Austria. Owner: SWE 2.

Real path: OIDC against ID Austria (the IdP returns a signed ID token with name, birth date, a
sector-specific pseudonym (bPK) and the level of assurance). Here the mock IdP page lets the tester
pick a test citizen and returns an HMAC-signed assertion with the same fields. CONTRACT: the portal
only ever consumes `EidAssertion` from `verify()`, so swapping in real OIDC touches only this file.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

from app.security import sign, unsign

PURPOSE = "eid-assertion"


@dataclass(frozen=True)
class EidAssertion:
    given: str
    family: str
    dob: str             # ISO date
    pseudonym: str       # stands in for the bPK: stable per person, not the name
    loa: str             # "substantial" | "high" (eIDAS level of assurance)

    @property
    def full_name(self) -> str:
        return f"{self.given} {self.family}"


def _p(given: str, family: str, dob: str) -> EidAssertion:
    pseud = "bpk-" + hashlib.sha256(f"{given}|{family}|{dob}".encode()).hexdigest()[:16]
    return EidAssertion(given, family, dob, pseud, "high")


# Synthetic test citizens shown on the mock IdP page. Add jury people here if they ask.
TEST_CITIZENS: dict[str, EidAssertion] = {
    "eva": _p("Eva", "Brandl", "1979-05-04"),          # the named lab physician (request 1)
    "stefan": _p("Stefan", "Kern", "1985-11-20"),      # the named discharge manager (request 2)
    "karl": _p("Karl", "Kollege", "1990-02-14"),       # M2: colleague the email was forwarded to
    "unbekannt": _p("Ulrike", "Unbekannt", "1972-07-30"),  # M1: whoever owns labor-kanaI.example
}


def issue(citizen_key: str, ttl_s: int = 300, link_token: str = "") -> str:
    payload = {**asdict(TEST_CITIZENS[citizen_key]), "lt": link_token}
    return sign(payload, PURPOSE, ttl_s)


def verify(assertion: str, link_token: str = "") -> EidAssertion | None:
    body = unsign(assertion, PURPOSE)
    if not body:
        return None
    if body.get("lt", "") != link_token:
        return None
    fields = {k: v for k, v in body.items() if k != "lt"}
    return EidAssertion(**fields)
