"""M1 address lint + M1/M2 label. Owner: MedEng."""
import pytest

from app import i18n
from app.misdelivery import classify_identity_failure, lint_address, lint_findings, misdelivery_label

KNOWN = ("labor-kanal.example", "reha-waldblick.example")


@pytest.mark.parametrize("contact", [
    "eva.brandl@labor-kanal.example",
    "Eva.Brandl@labor-kanal.example",       # the local part may have capitals
    "someone@unrelated-lab.example",        # unknown, resembles nothing we know: not suspicious
    "+436600000101",                        # scenario request 2
    "+43 664 1234567",
    "+4367612345678",
])
def test_lint_clean_contact_has_no_warning(contact):
    assert lint_address(contact, KNOWN) == []


@pytest.mark.parametrize("contact", [
    "eva.brandl@labor-kanaI.example",     # capital I for l (scenario M1)
    "eva.brandl@labor-kana1.example",     # digit 1 for l
    "eva.brandl@labor-kanal.exampel",     # typo in TLD
    "eva.brandl@lab0r-kanal.example",     # zero for o
    "s.kern@reha-waIdblick.example",      # second known domain
    "eva.brandl@Labor-Kanal.example",     # same domain, but capitals are suspicious
    "eva.brandl@lаbor-kanal.example",     # Cyrillic а
    "eva.brandl@labor-kanal",             # no TLD
    "0660 0000101",                       # no country code
    "+4366000001",                        # too short
    "+49 151 12345678",                   # not Austrian
    "+43 1 4040000",                      # Austrian landline: SMS will not arrive
    "+43 66O 0000101",                    # letter O in a number
])
def test_lint_suspicious_contact_warns(contact):
    assert lint_address(contact, KNOWN)


def test_m1_warning_names_the_real_domain_and_the_swapped_letter():
    [w] = lint_address("eva.brandl@labor-kanaI.example", KNOWN)
    assert "labor-kanal.example" in w and "„I“ statt „l“" in w


def test_lint_codes():
    codes = lambda c: [f.code for f in lint_findings(c, KNOWN)]   # noqa: E731
    assert codes("eva.brandl@labor-kanaI.example") == ["homoglyph"]
    assert codes("eva.brandl@labor-kanal.exampel") == ["typo"]
    assert codes("0660 0000101") == ["phone_national"]
    assert codes("+43 1 4040000") == ["phone_not_mobile"]


def test_lint_english():
    [w] = lint_address("eva.brandl@labor-kanaI.example", KNOWN, lang="en")
    assert w.startswith("Domain “labor-kanaI.example” looks like “labor-kanal.example”") and "“I” instead of “l”" in w


def test_lint_texts_exist_in_both_languages():
    for key, entry in i18n.MESSAGES.items():
        assert set(entry) == set(i18n.LANGS), key


def test_classify_identity_failure():
    assert classify_identity_failure({"lint_warnings": ["x"]}) == "M1"
    assert classify_identity_failure({"lint_warnings": '["x"]'}) == "M1"     # as stored in SQLite
    assert classify_identity_failure({"lint_warnings": "[]"}) == "M2"
    assert classify_identity_failure({}) == "M2"
    assert "wahrscheinlich" in misdelivery_label("M2") and "probably" in misdelivery_label("M2", "en")


def test_i18n_fallbacks():
    assert i18n.t("no.such.key") == "no.such.key"
    assert i18n.t("misdelivery.M1", "fr") == i18n.t("misdelivery.M1", "de")
    assert i18n.norm_lang("en-GB") == "en"
    assert i18n._accept_language("fr-FR,en;q=0.8,de;q=0.9") == "de"
