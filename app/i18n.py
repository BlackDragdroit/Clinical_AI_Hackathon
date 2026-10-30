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

    # audit page (/audit): page chrome
    "audit.brand": {"de": "I.R.I.S. · BefundBrücke", "en": "I.R.I.S. · BefundBrücke"},
    "audit.title": {"de": "Audit-Protokoll", "en": "Audit log"},
    "audit.subtitle": {
        "de": "Jeder Schritt jeder Anfrage: wer, was, wann. Nur anhängen, hash-verkettet.",
        "en": "Every step of every request: who, what, when. Append-only, hash-chained.",
    },
    "audit.lang_label": {"de": "Sprache", "en": "Language"},
    "audit.skip": {"de": "Zum Verlauf springen", "en": "Skip to timeline"},
    "audit.request": {"de": "Anfrage {id}", "en": "Request {id}"},
    "audit.all": {"de": "Alle", "en": "All"},
    "audit.all_requests": {"de": "Alle Anfragen", "en": "All requests"},
    "audit.json": {"de": "JSON-Export", "en": "JSON export"},
    "audit.chain.ok": {"de": "Hash-Kette intakt", "en": "Hash chain intact"},
    "audit.chain.broken": {"de": "Hash-Kette verletzt ab Eintrag #{seq}", "en": "Hash chain broken from entry #{seq}"},
    "audit.chain.broken_rows": {"de": "{n} Einträge prüfen nicht", "en": "{n} entries do not verify"},
    "audit.chain.entries": {"de": "Einträge", "en": "Entries"},
    "audit.chain.in_scope": {"de": "{n} in dieser Anfrage", "en": "{n} in this request"},
    "audit.chain.head": {"de": "Letzter Hash", "en": "Latest hash"},
    "audit.chain.empty": {"de": "noch leer", "en": "still empty"},
    "audit.chain.explain": {
        "de": "SHA-256 über vorherigen Hash, Zeit, Ereignis, Anfrage, Akteur und Details. "
              "Wer einen Eintrag ändert oder löscht, bricht die Kette ab dieser Stelle.",
        "en": "SHA-256 over previous hash, time, event, request, actor and details. "
              "Editing or deleting an entry breaks the chain from that point.",
    },
    "audit.coverage.title": {"de": "Abdeckung der 6 Pflichtschritte", "en": "Coverage of the 6 required steps"},
    "audit.coverage.scope_all": {"de": "über alle Anfragen", "en": "across all requests"},
    "audit.coverage.scope_one": {"de": "für Anfrage {id}", "en": "for request {id}"},
    "audit.coverage.done": {"de": "erfasst", "en": "logged"},
    "audit.coverage.missing": {"de": "fehlt", "en": "missing"},
    "audit.coverage.no_misdelivery": {
        "de": "„Fehlzustellung erkannt“ zählt nur, wo eine aufgetreten ist – in dieser Anfrage keine.",
        "en": "“Misdelivery caught” only counts where one happened – none in this request.",
    },
    "audit.step.request_sent": {"de": "Anfrage gesendet", "en": "Request sent"},
    "audit.step.link_opened": {"de": "Link geöffnet", "en": "Link opened"},
    "audit.step.identity_checked": {"de": "Identität geprüft", "en": "Identity checked"},
    "audit.step.answer_sent": {"de": "Antwort übermittelt", "en": "Answer sent"},
    "audit.step.answer_filed": {"de": "In FHIR abgelegt", "en": "Filed in FHIR"},
    "audit.step.misdelivery_caught": {"de": "Fehlzustellung erkannt", "en": "Misdelivery caught"},
    "audit.requests.title": {"de": "Anfragen", "en": "Requests"},
    "audit.requests.hint": {
        "de": "Zeile wählen, um den Verlauf auf diese Anfrage zu filtern.",
        "en": "Pick a row to filter the timeline to that request.",
    },
    "audit.requests.empty": {
        "de": "Noch keine Anfragen. Sie entstehen mit !anfrage im Matrix-Raum.",
        "en": "No requests yet. They start with !anfrage in the Matrix room.",
    },
    "audit.col.id": {"de": "Anfrage", "en": "Request"},
    "audit.col.doc": {"de": "Dokument", "en": "Document"},
    "audit.col.sender": {"de": "Erwarteter Absender", "en": "Expected sender"},
    "audit.col.contact": {"de": "Kontakt", "en": "Contact"},
    "audit.col.patient": {"de": "Patient", "en": "Patient"},
    "audit.col.status": {"de": "Status", "en": "Status"},
    "audit.col.coverage": {"de": "Abdeckung", "en": "Coverage"},
    "audit.col.misdelivery": {"de": "Fehlzustellung", "en": "Misdelivery"},
    "audit.col.created": {"de": "Angelegt", "en": "Created"},
    "audit.col.time": {"de": "Zeit", "en": "Time"},
    "audit.col.who": {"de": "Wer", "en": "Who"},
    "audit.col.what": {"de": "Was", "en": "What"},
    "audit.none": {"de": "keine", "en": "none"},
    "audit.timeline.title": {"de": "Verlauf", "en": "Timeline"},
    "audit.timeline.count": {"de": "{n} Einträge", "en": "{n} entries"},
    "audit.timeline.empty": {
        "de": "Noch keine Einträge. Jeder Schritt einer Anfrage erscheint hier, sobald er passiert.",
        "en": "No entries yet. Each step of a request shows up here as soon as it happens.",
    },
    "audit.timeline.unknown_request": {
        "de": "Zu Anfrage „{id}“ gibt es keine Einträge.",
        "en": "There are no entries for request “{id}”.",
    },
    "audit.raw.summary": {"de": "Rohdaten und Hash", "en": "Raw data and hash"},
    "audit.raw.event": {"de": "Ereignis", "en": "Event"},
    "audit.raw.actor": {"de": "Akteur (gespeichert)", "en": "Actor (as stored)"},
    "audit.raw.utc": {"de": "Zeit (UTC, gespeichert)", "en": "Time (UTC, as stored)"},
    "audit.raw.details": {"de": "Details", "en": "Details"},
    "audit.raw.hash": {"de": "Hash", "en": "Hash"},
    "audit.raw.prev": {"de": "Vorheriger Hash", "en": "Previous hash"},
    "audit.row.broken": {"de": "Hash stimmt nicht", "en": "Hash does not verify"},
    "audit.tone.ok": {"de": "abgelegt", "en": "filed"},
    "audit.tone.warn": {"de": "Prüfung nötig", "en": "review needed"},
    "audit.tone.bad": {"de": "fehlgeschlagen", "en": "failed"},
    "audit.tone.alert": {"de": "Fehlzustellung", "en": "misdelivery"},
    "audit.tone.pass": {"de": "bestätigt", "en": "confirmed"},
    "audit.tone.info": {"de": "Schritt", "en": "step"},
    "audit.mis.title": {"de": "Fehlzustellungen", "en": "Misdeliveries"},
    "audit.mis.caught": {"de": "erkannt", "en": "caught"},
    "audit.mis.not_caught": {"de": "nicht aufgetreten", "en": "did not occur"},
    "audit.mis.how.M1": {
        "de": "Adress-Lint warnt vor dem Senden; die eID-Bindung sperrt danach.",
        "en": "Address lint warns before sending; the eID binding blocks afterwards.",
    },
    "audit.mis.how.M2": {
        "de": "eID-Name ≠ erwartete Person: nichts offengelegt, nichts abgelegt.",
        "en": "eID name ≠ expected person: nothing revealed, nothing filed.",
    },
    "audit.mis.how.M3": {
        "de": "Dreifach-Abgleich (Fellegi–Sunter) weist das Dokument ab; Quarantäne.",
        "en": "Three-way match (Fellegi–Sunter) rejects the document; quarantined.",
    },
    "audit.footer.internal": {
        "de": "Klinikintern – in Produktion hinter Klinik-Login",
        "en": "Clinic-internal – behind the clinic login in production",
    },
    "audit.footer.tz": {
        "de": "Zeiten in {tz}, gespeichert als UTC. Patienten nur als Referenz, Kontakte maskiert.",
        "en": "Times in {tz}, stored as UTC. Patients by reference only, contacts masked.",
    },

    # audit page: design switch (both looks) and the /audit/apple variant
    "audit.design": {"de": "Design", "en": "Design"},
    "audit.design.standard": {"de": "Standard", "en": "Standard"},
    "audit.design.apple": {"de": "Apple", "en": "Apple"},
    "audit.apple.integrity": {"de": "Integrität", "en": "Integrity"},
    "audit.apple.strip": {"de": "Ein Glied pro Eintrag, ältester links.", "en": "One link per entry, oldest first."},
    "audit.apple.strip_scope": {"de": "Gefüllt: Einträge dieser Anfrage.", "en": "Filled: entries of this request."},
    "audit.apple.jump_broken": {"de": "Zum ersten verletzten Eintrag", "en": "Go to the first broken entry"},
    # /audit/apple as a formal audit record: document header, findings as statements, ledger columns
    "audit.apple.meta.clinic": {"de": "Klinik", "en": "Clinic"},
    "audit.apple.meta.scope": {"de": "Umfang", "en": "Scope"},
    "audit.apple.meta.tz": {"de": "Zeitzone", "en": "Time zone"},
    "audit.apple.meta.tz_value": {"de": "{tz}, gespeichert als UTC", "en": "{tz}, stored as UTC"},
    "audit.apple.meta.class": {"de": "Einstufung", "en": "Classification"},
    "audit.apple.meta.internal": {"de": "Klinikintern", "en": "Clinic-internal"},
    "audit.apple.show_all": {"de": "Alle Anfragen anzeigen", "en": "Show all requests"},
    "audit.apple.chain_ok": {"de": "Hash-Kette geprüft: intakt", "en": "Hash chain verified: intact"},
    "audit.apple.chain_detail": {"de": "{n} Einträge, letzter Hash", "en": "{n} entries, latest hash"},
    "audit.apple.coverage": {"de": "Pflichtschritte: {n} von 6 protokolliert", "en": "Required steps: {n} of 6 logged"},
    "audit.apple.logged": {"de": "protokolliert", "en": "logged"},
    "audit.apple.col.step": {"de": "Schritt", "en": "Step"},
    "audit.apple.col.actor": {"de": "Akteur", "en": "Actor"},
    "audit.apple.col.type": {"de": "Typ", "en": "Type"},

    # audit page: who
    "audit.actor.link": {"de": "Link (IP {ip})", "en": "Link (IP {ip})"},
    "audit.actor.eid": {"de": "eID: {name}", "en": "eID: {name}"},
    "audit.actor.system": {"de": "System", "en": "System"},

    # audit page: codes -> words
    "audit.doc.lab": {"de": "Laborbefund", "en": "lab result"},
    "audit.doc.report": {"de": "Entlassungsbericht", "en": "discharge report"},
    "audit.channel.email": {"de": "E-Mail", "en": "email"},
    "audit.channel.sms": {"de": "SMS", "en": "SMS"},
    "audit.method.eid-mock": {"de": "ID Austria, simuliert", "en": "ID Austria, simulated"},
    "audit.loa.high": {"de": "hoch", "en": "high"},
    "audit.loa.substantial": {"de": "substanziell", "en": "substantial"},
    "audit.status.draft": {"de": "Entwurf", "en": "Draft"},
    "audit.status.sent": {"de": "Gesendet", "en": "Sent"},
    "audit.status.opened": {"de": "Link geöffnet", "en": "Link opened"},
    "audit.status.identified": {"de": "Identifiziert", "en": "Identified"},
    "audit.status.answered": {"de": "Beantwortet", "en": "Answered"},
    "audit.status.filed": {"de": "Abgelegt", "en": "Filed"},
    "audit.status.review": {"de": "In Prüfung", "en": "In review"},
    "audit.status.rejected": {"de": "Abgewiesen, Quarantäne", "en": "Rejected, quarantined"},
    "audit.status.discarded": {"de": "Verworfen", "en": "Discarded"},
    "audit.status.blocked": {"de": "Gesperrt", "en": "Blocked"},

    # audit page: what (one sentence per event; built by audit.describe)
    "audit.ev.request_drafted": {"de": "Anfrage entworfen: {doc} von {to} über {contact}",
                                 "en": "Request drafted: {doc} from {to} via {contact}"},
    "audit.ev.lint_warnings": {"de": " – {n} Warnung(en) zur Adresse", "en": " – {n} address warning(s)"},
    "audit.ev.request_sent": {"de": "Anfrage per {channel} an {to} gesendet ({contact})",
                              "en": "Request sent by {channel} to {to} ({contact})"},
    "audit.ev.ttl": {"de": ", Link {h} h gültig", "en": ", link valid for {h} h"},
    "audit.ev.link_opened": {"de": "Link geöffnet", "en": "Link opened"},
    "audit.ev.link_reopened": {"de": "Link erneut geöffnet", "en": "Link opened again"},
    "audit.ev.identity_ok": {"de": "Identität geprüft: bestätigt ({method}, Vertrauensniveau {loa})",
                             "en": "Identity checked: confirmed ({method}, level of assurance {loa})"},
    "audit.ev.identity_failed": {"de": "Identität geprüft: fehlgeschlagen (Versuch {attempt})",
                                 "en": "Identity checked: failed (attempt {attempt})"},
    "audit.ev.misdelivery_names": {"de": "{label} – verifiziert: {verified} ≠ erwartet: {expected}",
                                   "en": "{label} – verified: {verified} ≠ expected: {expected}"},
    "audit.ev.misdelivery_m3": {"de": "{label} – Antwort in Quarantäne, nichts abgelegt",
                                "en": "{label} – answer quarantined, nothing filed"},
    "audit.ev.misdelivery_other": {"de": "Fehlzustellung erkannt ({code})", "en": "Misdelivery caught ({code})"},
    "audit.ev.patient_revealed": {"de": "Patient und Anfrage angezeigt – erst nach bestätigter Identität",
                                  "en": "Patient and request shown – only after confirmed identity"},
    "audit.ev.answer_sent": {"de": "Antwort übermittelt: {filename} ({size})", "en": "Answer sent: {filename} ({size})"},
    "audit.ev.answer_filed": {"de": "In FHIR abgelegt: {n} Ressourcen", "en": "Filed in FHIR: {n} resources"},
    "audit.ev.answer_filed_one": {"de": "In FHIR abgelegt: 1 Ressource", "en": "Filed in FHIR: 1 resource"},
    "audit.ev.task_completed": {"de": ", {task} abgeschlossen", "en": ", {task} completed"},
    "audit.ev.review_requested": {"de": "Zur ärztlichen Prüfung vorgelegt – Zuordnung nicht eindeutig, noch nichts abgelegt",
                                  "en": "Sent to the doctor for review – match not certain, nothing filed yet"},
    "audit.ev.review_file": {"de": "Prüfung entschieden: ablegen", "en": "Review decided: file"},
    "audit.ev.review_discard": {"de": "Prüfung entschieden: verwerfen", "en": "Review decided: discard"},
    "audit.ev.request_parsed": {"de": "Anfrage aus Chat-Nachricht erkannt", "en": "Request recognised from chat message"},
    "audit.ev.request_parsed_doc": {"de": "Anfrage aus Chat-Nachricht erkannt: {doc} von {to}",
                                    "en": "Request recognised from chat message: {doc} from {to}"},
    "audit.ev.readback_shown": {"de": "Zusammenfassung zur Bestätigung angezeigt", "en": "Read-back shown for confirmation"},
    "audit.ev.readback_confirmed": {"de": "Zusammenfassung bestätigt", "en": "Read-back confirmed"},
    "audit.ev.unknown": {"de": "Ereignis „{event}“ (ohne Beschreibung)", "en": "Event “{event}” (no description)"},
    "audit.note.nothing_revealed": {"de": "Nichts offengelegt: kein Patient, kein Dokumenttyp.",
                                    "en": "Nothing revealed: no patient, no document type."},
    "audit.note.doctor_alerted": {"de": "{doctor} im Matrix-Raum gewarnt.", "en": "{doctor} alerted in the Matrix room."},
    "audit.note.m3_scores": {"de": "Im Protokoll nur Abgleich-Werte, keine Daten des anderen Patienten.",
                             "en": "Only match scores are logged, no data about the other patient."},

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
