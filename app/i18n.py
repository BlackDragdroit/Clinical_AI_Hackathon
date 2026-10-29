"""DE/EN strings for the outside portal. German is the default and the only language before a visitor picks one.

Pre-identity strings (landing, invalid, identity_failed, eID mock) must stay neutral: no patient, no document type.
"""
from __future__ import annotations

LANGS = ("de", "en")
DEFAULT = "de"

STRINGS: dict[str, dict[str, str]] = {
    "de": {
        "neutral": "{clinic} hat eine sichere Dokumentenanfrage an Sie gerichtet.",
        "title": "Sichere Dokumentenanfrage",
        "step_identity": "Identität bestätigen",
        "step_upload": "Dokument senden",
        "step_done": "Fertig",
        "step_of": "Schritt {n} von 2",
        "landing_hint": "Bitte bestätigen Sie zuerst, wer Sie sind. Danach sehen Sie, worum es geht.",
        "landing_btn": "Mit ID Austria anmelden",
        "landing_time": "Dauert etwa eine Minute. Kein Konto, keine Installation.",
        "invalid_h": "Link nicht gültig",
        "invalid_p": "Dieser Link ist nicht (mehr) gültig. Bitte wenden Sie sich an {clinic}.",
        "failed_h": "Anfrage nicht für Sie bestimmt",
        "failed_p": "Diese Anfrage ist an eine bestimmte Person gerichtet. Ihre Identität passt nicht dazu, "
                    "daher können wir keine Inhalte anzeigen.",
        "failed_small": "Wenn Sie die Nachricht weitergeleitet bekommen oder irrtümlich erhalten haben, müssen Sie "
                        "nichts tun. Die anfragende Stelle wurde informiert.",
        "signed_in_as": "Angemeldet als {name}",
        "answer_h": "{doc} angefragt",
        "answer_intro": "{doctor}, {clinic}, bittet um den {doc} für",
        "reason": "Grund: {reason}",
        "f_name": "Name der Patientin / des Patienten (wie im Dokument)",
        "f_dob": "Geburtsdatum",
        "f_dob_ph": "TT.MM.JJJJ",
        "f_upload": "Dokument hochladen (.md, .txt)",
        "f_or": "oder",
        "f_paste": "Inhalt einfügen",
        "send": "Sicher senden",
        "err_empty": "Bitte Datei hochladen oder Text eingeben.",
        "done_h": "Danke",
        "receipt_no": "Eingangsnummer: {receipt}",
        "eid_title": "ID Austria (Simulation)",
        "eid_sim": "SIMULATION – dies ist kein echter ID-Austria-Login. Es werden keine echten Daten verwendet.",
        "eid_h": "Anmelden",
        "eid_sub": "Ein Dienst möchte Ihre Identität prüfen.",
        "eid_service": "Anfragender Dienst",
        "eid_shares": "Folgende Daten werden übermittelt",
        "eid_d_name": "Vor- und Nachname",
        "eid_d_dob": "Geburtsdatum",
        "eid_d_bpk": "Bereichsspezifisches Personenkennzeichen (bPK)",
        "eid_d_loa": "Vertrauensniveau (eIDAS)",
        "eid_pick": "Testperson wählen",
        "eid_confirm": "Freigeben und weiter",
        "eid_cancel": "Abbrechen",
        "eid_note": "In Produktion bestätigen Sie hier in der ID-Austria-App. Hier wählen Sie eine synthetische Testperson.",
        "lang_switch": "English",
        "lang_code": "en",
        "footer": "Sichere Übermittlung · {clinic}",
    },
    "en": {
        "neutral": "{clinic} has sent you a secure document request.",
        "title": "Secure document request",
        "step_identity": "Confirm identity",
        "step_upload": "Send document",
        "step_done": "Done",
        "step_of": "Step {n} of 2",
        "landing_hint": "Please confirm who you are first. After that you will see what this is about.",
        "landing_btn": "Sign in with ID Austria",
        "landing_time": "Takes about a minute. No account, no installation.",
        "invalid_h": "Link not valid",
        "invalid_p": "This link is no longer valid. Please contact {clinic}.",
        "failed_h": "This request is not for you",
        "failed_p": "This request is addressed to a specific person. Your identity does not match, "
                    "so we cannot show any content.",
        "failed_small": "If this message was forwarded to you or reached you by mistake, you do not need to do "
                        "anything. The requesting office has been informed.",
        "signed_in_as": "Signed in as {name}",
        "answer_h": "{doc} requested",
        "answer_intro": "{doctor}, {clinic}, asks for the {doc} of",
        "reason": "Reason: {reason}",
        "f_name": "Patient name (as in the document)",
        "f_dob": "Date of birth",
        "f_dob_ph": "DD.MM.YYYY",
        "f_upload": "Upload document (.md, .txt)",
        "f_or": "or",
        "f_paste": "Paste the content",
        "send": "Send securely",
        "err_empty": "Please upload a file or enter text.",
        "done_h": "Thank you",
        "receipt_no": "Receipt number: {receipt}",
        "eid_title": "ID Austria (simulation)",
        "eid_sim": "SIMULATION – this is not a real ID Austria login. No real data is used.",
        "eid_h": "Sign in",
        "eid_sub": "A service wants to verify your identity.",
        "eid_service": "Requesting service",
        "eid_shares": "The following data will be shared",
        "eid_d_name": "First and last name",
        "eid_d_dob": "Date of birth",
        "eid_d_bpk": "Sector-specific personal identifier (bPK)",
        "eid_d_loa": "Level of assurance (eIDAS)",
        "eid_pick": "Choose a test person",
        "eid_confirm": "Approve and continue",
        "eid_cancel": "Cancel",
        "eid_note": "In production you approve this in the ID Austria app. Here you pick a synthetic test person.",
        "lang_switch": "Deutsch",
        "lang_code": "de",
        "footer": "Secure transfer · {clinic}",
    },
}

DOC_LABEL = {
    "de": {"lab": "Laborbefund", "report": "Entlassungsbericht"},
    "en": {"lab": "lab result", "report": "discharge report"},
}


def pick(raw: str | None) -> str:
    return raw if raw in LANGS else DEFAULT


def tr(lang: str, key: str, **kw: object) -> str:
    return STRINGS[lang][key].format(**kw)
