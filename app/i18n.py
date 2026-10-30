"""DE/EN texts in one place: t(key, lang, **params). Owner: MedEng (catalogue open to everyone).

German is the default and the fallback: a key missing in English shows the German text, a key
missing everywhere shows the key itself, so a gap is visible instead of crashing a page.

Language choice for a page, in this order: `?lang=en`, the `lang` cookie, the browser's
Accept-Language, else German. Wiring it into the portal is two lines in app/main.py:

    i18n.install(templates)                        # once, after `templates = Jinja2Templates(...)`
    ... _page(...): ctx["lang"] = i18n.resolve_lang(request)

then in a template: {{ t("portal.neutral", lang, clinic=clinic) }} and a toggle link to
?lang={{ other_lang(lang) }}. Call `i18n.remember(response, lang)` to keep the choice in a cookie.

Hard rule 1 still applies: texts that go into an email or SMS must not contain the patient's
name, birth date or the document type, in any language.
"""
from __future__ import annotations

from typing import Any

LANGS = ("de", "en")
DEFAULT = "de"
COOKIE = "lang"

MESSAGES: dict[str, dict[str, str]] = {
    # address lint (app/misdelivery.py), shown on the draft card after "⚠️ Kontakt prüfen:"
    "lint.email_format": {
        "de": "„{contact}“ ist keine gültige E-Mail-Adresse",
        "en": "“{contact}” is not a valid email address",
    },
    "lint.homoglyph": {
        "de": "Domain „{domain}“ sieht aus wie „{known}“, ist aber nicht dieselbe ({diff})",
        "en": "Domain “{domain}” looks like “{known}” but is not the same ({diff})",
    },
    "lint.typo": {
        "de": "Domain „{domain}“ weicht in {distance} Zeichen von „{known}“ ab – Tippfehler?",
        "en": "Domain “{domain}” differs from “{known}” in {distance} character(s) – typo?",
    },
    "lint.uppercase": {
        "de": "Großbuchstaben in der Domain „{domain}“ – Domains unterscheiden nicht nach Groß/klein, "
              "ein großes I ist oft ein getarntes l",
        "en": "Uppercase letters in the domain “{domain}” – domains are case-insensitive, "
              "a capital I is often a disguised l",
    },
    "lint.non_ascii": {
        "de": "Domain „{domain}“ enthält Sonderzeichen ({chars}), die wie normale Buchstaben aussehen können",
        "en": "Domain “{domain}” contains special characters ({chars}) that can look like normal letters",
    },
    "lint.phone_format": {
        "de": "„{contact}“ ist keine gültige Telefonnummer (erwartet: +43 6xx …)",
        "en": "“{contact}” is not a valid phone number (expected: +43 6xx …)",
    },
    "lint.phone_national": {
        "de": "Nummer ohne Ländervorwahl – gemeint ist vermutlich {suggestion}",
        "en": "Number without country code – probably {suggestion}",
    },
    "lint.phone_foreign": {
        "de": "Keine österreichische Nummer (+43) – bitte Ländervorwahl prüfen",
        "en": "Not an Austrian number (+43) – please check the country code",
    },
    "lint.phone_not_mobile": {
        "de": "Keine österreichische Mobilnummer (+43 6…) – eine SMS kommt dort vermutlich nicht an",
        "en": "Not an Austrian mobile number (+43 6…) – an SMS will probably not arrive",
    },
    "lint.phone_length": {
        "de": "Ungewöhnliche Länge ({digits} Ziffern nach +43) – Ziffer vergessen oder zu viel?",
        "en": "Unusual length ({digits} digits after +43) – a digit missing or extra?",
    },
    "lint.diff_char": {"de": "„{got}“ statt „{want}“", "en": "“{got}” instead of “{want}”"},

    # misdelivery labels (audit page, Matrix alerts); codes are stable, the wording says what we can know
    "misdelivery.M1": {"de": "M1 – wahrscheinlich falsche Adresse", "en": "M1 – probably wrong address"},
    "misdelivery.M2": {"de": "M2 – wahrscheinlich weitergeleitet", "en": "M2 – probably forwarded"},
    "misdelivery.M3": {"de": "M3 – Dokument betrifft anderen Patienten", "en": "M3 – document is about another patient"},

    # language toggle
    "lang.name.de": {"de": "Deutsch", "en": "German"},
    "lang.name.en": {"de": "Englisch", "en": "English"},
    "lang.switch": {"de": "English", "en": "Deutsch"},
}


def norm_lang(lang: str | None) -> str:
    """'en-GB' -> 'en'; anything unknown -> German."""
    code = (lang or "").strip().lower()[:2]
    return code if code in LANGS else DEFAULT


def t(key: str, lang: str | None = DEFAULT, **params: Any) -> str:
    entry = MESSAGES.get(key)
    if not entry:
        return key
    text = entry.get(norm_lang(lang)) or entry[DEFAULT]
    try:
        return text.format(**params)
    except (KeyError, IndexError):   # a missing parameter must not break a page
        return text


def other_lang(lang: str | None) -> str:
    return "en" if norm_lang(lang) == "de" else "de"


def _accept_language(header: str) -> str | None:
    """First supported language in an Accept-Language header, by q-value."""
    best: list[tuple[float, str]] = []
    for part in header.split(","):
        tag, _, q = part.strip().partition(";q=")
        try:
            weight = float(q) if q else 1.0
        except ValueError:
            weight = 0.0
        code = tag.strip().lower()[:2]
        if code in LANGS:
            best.append((weight, code))
    return max(best)[1] if best else None


def resolve_lang(request: Any) -> str:
    """For a Starlette/FastAPI Request: ?lang= > cookie > Accept-Language > German."""
    q = request.query_params.get("lang")
    if q:
        return norm_lang(q)
    c = request.cookies.get(COOKIE)
    if c:
        return norm_lang(c)
    return _accept_language(request.headers.get("accept-language", "")) or DEFAULT


def remember(response: Any, lang: str) -> None:
    response.set_cookie(COOKIE, norm_lang(lang), max_age=365 * 24 * 3600, samesite="lax")


def install(templates: Any) -> None:
    """Make t(), other_lang() and LANGS available in every Jinja template."""
    templates.env.globals.update(t=t, other_lang=other_lang, LANGS=LANGS)
