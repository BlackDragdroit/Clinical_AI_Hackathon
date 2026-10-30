"""DE/EN texts in one place: t(key, lang, **params). Owner: MedEng (catalogue open to everyone).

German is the default and the fallback: a key missing in English shows the German text, a key
missing everywhere shows the key itself, so a gap is visible instead of crashing a page.

Language choice for a page, in this order: `?lang=en`, the `lang` cookie, else German.
(`_accept_language` stays available, but pages do not use it: the first page must be German.)
The portal (`_page` in app/main.py) resolves the language once per page and passes templates a `t(key, **params)`
already bound to that language and the clinic name, so a template writes {{ t("portal.neutral") }}. The toggle
links to ?lang=<other>, and `i18n.remember(response, lang)` keeps the choice in a cookie. Other Jinja users can
call `install(templates)` for the plain `t(key, lang, **params)`.

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

    # outside portal (app/main.py + app/templates); before identity: neutral, no patient, no document type
    "portal.neutral": {"de": '{clinic} hat eine sichere Dokumentenanfrage an Sie gerichtet.', "en": '{clinic} has sent you a secure document request.'},
    "portal.title": {"de": 'Sichere Dokumentenanfrage', "en": 'Secure document request'},
    "portal.step_identity": {"de": 'Identität bestätigen', "en": 'Confirm identity'},
    "portal.step_upload": {"de": 'Dokument senden', "en": 'Send document'},
    "portal.step_done": {"de": 'Fertig', "en": 'Done'},
    "portal.step_of": {"de": 'Schritt {n} von 2', "en": 'Step {n} of 2'},
    "portal.landing_hint": {"de": 'Bitte bestätigen Sie zuerst, wer Sie sind. Danach sehen Sie, worum es geht.', "en": 'Please confirm who you are first. After that you will see what this is about.'},
    "portal.landing_btn": {"de": 'Mit ID Austria anmelden', "en": 'Sign in with ID Austria'},
    "portal.landing_time": {"de": 'Dauert etwa eine Minute. Kein Konto, keine Installation.', "en": 'Takes about a minute. No account, no installation.'},
    "portal.invalid_h": {"de": 'Link nicht gültig', "en": 'Link not valid'},
    "portal.invalid_p": {"de": 'Dieser Link ist nicht (mehr) gültig. Bitte wenden Sie sich an {clinic}.', "en": 'This link is no longer valid. Please contact {clinic}.'},
    "portal.failed_h": {"de": 'Anfrage nicht für Sie bestimmt', "en": 'This request is not for you'},
    "portal.failed_p": {"de": 'Diese Anfrage ist an eine bestimmte Person gerichtet. Ihre Identität passt nicht dazu, daher können wir keine Inhalte anzeigen.', "en": 'This request is addressed to a specific person. Your identity does not match, so we cannot show any content.'},
    "portal.failed_small": {"de": 'Wenn Sie die Nachricht weitergeleitet bekommen oder irrtümlich erhalten haben, müssen Sie nichts tun. Die anfragende Stelle wurde informiert.', "en": 'If this message was forwarded to you or reached you by mistake, you do not need to do anything. The requesting office has been informed.'},
    "portal.signed_in_as": {"de": 'Angemeldet als {name}', "en": 'Signed in as {name}'},
    "portal.answer_h": {"de": '{doc} angefragt', "en": '{doc} requested'},
    "portal.answer_intro": {"de": '{doctor}, {clinic}, bittet um den {doc} für', "en": '{doctor}, {clinic}, asks for the {doc} of'},
    "portal.reason": {"de": 'Grund: {reason}', "en": 'Reason: {reason}'},
    "portal.f_name": {"de": 'Name der Patientin / des Patienten (wie im Dokument)', "en": 'Patient name (as in the document)'},
    "portal.f_dob": {"de": 'Geburtsdatum', "en": 'Date of birth'},
    "portal.f_dob_ph": {"de": 'TT.MM.JJJJ', "en": 'DD.MM.YYYY'},
    "portal.f_upload": {"de": 'Dokument hochladen (.md, .txt)', "en": 'Upload document (.md, .txt)'},
    "portal.f_or": {"de": 'oder', "en": 'or'},
    "portal.f_paste": {"de": 'Inhalt einfügen', "en": 'Paste the content'},
    "portal.send": {"de": 'Sicher senden', "en": 'Send securely'},
    "portal.err_empty": {"de": 'Bitte Datei hochladen oder Text eingeben.', "en": 'Please upload a file or enter text.'},
    "portal.done_h": {"de": 'Danke', "en": 'Thank you'},
    "portal.receipt_no": {"de": 'Eingangsnummer: {receipt}', "en": 'Receipt number: {receipt}'},
    "portal.eid_title": {"de": 'ID Austria (Simulation)', "en": 'ID Austria (simulation)'},
    "portal.eid_sim": {"de": 'SIMULATION – dies ist kein echter ID-Austria-Login. Es werden keine echten Daten verwendet.', "en": 'SIMULATION – this is not a real ID Austria login. No real data is used.'},
    "portal.eid_h": {"de": 'Anmelden', "en": 'Sign in'},
    "portal.eid_sub": {"de": 'Ein Dienst möchte Ihre Identität prüfen.', "en": 'A service wants to verify your identity.'},
    "portal.eid_service": {"de": 'Anfragender Dienst', "en": 'Requesting service'},
    "portal.eid_shares": {"de": 'Folgende Daten werden übermittelt', "en": 'The following data will be shared'},
    "portal.eid_d_name": {"de": 'Vor- und Nachname', "en": 'First and last name'},
    "portal.eid_d_dob": {"de": 'Geburtsdatum', "en": 'Date of birth'},
    "portal.eid_d_bpk": {"de": 'Bereichsspezifisches Personenkennzeichen (bPK)', "en": 'Sector-specific personal identifier (bPK)'},
    "portal.eid_d_loa": {"de": 'Vertrauensniveau (eIDAS)', "en": 'Level of assurance (eIDAS)'},
    "portal.eid_pick": {"de": 'Testperson wählen', "en": 'Choose a test person'},
    "portal.eid_confirm": {"de": 'Freigeben und weiter', "en": 'Approve and continue'},
    "portal.eid_cancel": {"de": 'Abbrechen', "en": 'Cancel'},
    "portal.eid_note": {"de": 'In Produktion bestätigen Sie hier in der ID-Austria-App. Hier wählen Sie eine synthetische Testperson.', "en": 'In production you approve this in the ID Austria app. Here you pick a synthetic test person.'},
    "portal.footer": {"de": 'Sichere Übermittlung · {clinic}', "en": 'Secure transfer · {clinic}'},
    # requested document type, shown only after identity
    "doc.lab": {"de": 'Laborbefund', "en": 'lab result'},
    "doc.report": {"de": 'Entlassungsbericht', "en": 'discharge report'},

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
    """For a Starlette/FastAPI Request: ?lang= > cookie > German.
    Not Accept-Language: the first page must show the agreed German sentence on any browser (decided with SWE 2)."""
    q = request.query_params.get("lang")
    if q:
        return norm_lang(q)
    return norm_lang(request.cookies.get(COOKIE))


def remember(response: Any, lang: str, secure: bool = False) -> None:
    response.set_cookie(COOKIE, norm_lang(lang), max_age=365 * 24 * 3600, samesite="lax", secure=secure)


def install(templates: Any) -> None:
    """Make t(), other_lang() and LANGS available in every Jinja template."""
    templates.env.globals.update(t=t, other_lang=other_lang, LANGS=LANGS)
