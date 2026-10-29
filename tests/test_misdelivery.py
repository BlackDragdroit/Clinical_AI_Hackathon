"""M1 address lint. Owner: MedEng. Remove the xfail marker once lint_address is implemented."""
import pytest

from app.misdelivery import lint_address

KNOWN = ("labor-kanal.example", "reha-waldblick.example")


def test_lint_clean_address_has_no_warning():
    assert lint_address("eva.brandl@labor-kanal.example", KNOWN) == []


@pytest.mark.xfail(strict=True, reason="TODO(MedEng): implement lint_address")
@pytest.mark.parametrize("contact", [
    "eva.brandl@labor-kanaI.example",     # capital I for l (scenario M1)
    "eva.brandl@labor-kana1.example",     # digit 1 for l
    "eva.brandl@labor-kanal.exampel",     # typo in TLD
    "eva.brandl@lab0r-kanal.example",     # zero for o
])
def test_lint_suspicious_address_warns(contact):
    assert lint_address(contact, KNOWN)
