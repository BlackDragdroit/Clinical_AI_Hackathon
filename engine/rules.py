"""Rule-based request extraction (German + English): the CPU fallback and the cross-check for the model.

Every value is a slice of the (normalized) text with its span. Roles are decided by context:
the person next to a birth date is the patient, the person next to the contact is the recipient,
cue words ("bei", "von Dr.", "ask", "Patientin", "für", "for") break ties.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from engine._core import KNOWN, norm_tokens, parse_dob
from engine.lexicon import ELGA, LAB_WORDS, PANEL_RE, PANELS, REPORT_STRONG, REPORT_WEAK


@dataclass
class Hit:
    value: str
    start: int
    end: int
    source: str = "rules"
    extra: dict = field(default_factory=dict)


EMAIL = re.compile(r"[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<![\w/])(?:\+|00)?\d[\d \-/]{5,}\d(?![\w/])")
PATIENT_REF = re.compile(r"\bPatient/[A-Za-z0-9\-.]{1,64}\b")
_M = (r"(?:Jänner|Jaenner|Januar|January|Jan|Februar|February|Feb|März|Maerz|March|Mar|April|Apr|Mai|May|Juni|June|Jun|"
      r"Juli|July|Jul|August|Aug|September|Sept|Sep|Oktober|October|Okt|Oct|November|Nov|Dezember|December|Dez|Dec)")
DATE = re.compile(rf"\b(?:\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}\.\s?\d{{1,2}}\.\s?\d{{4}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}|"
                  rf"\d{{1,2}}\.?\s+{_M}\.?\s+\d{{4}}|{_M}\s+\d{{1,2}},?\s+\d{{4}})\b", re.I)
DOB_CUE = re.compile(r"(?:geb\.?|geboren(?: am)?|born(?: on)?|\*|dob|geburtsdatum|date of birth|birth ?date|jg\.?|jahrgang)\s*:?\s*$", re.I)

TITLE = r"(?:Univ\.-Prof\.|Prof\.|Professor(?:in)?|DDr\.|Dr\.|Dr|Doktor(?:in)?|Doctor|med\.|Mag\.|Magister|Magistra|DI|OÄ|OA|Frau|Herrn|Herr|Fr\.|Hr\.|Mrs\.?|Mr\.?|Ms\.?|Miss)"
_UP = "A-Z" + "".join(c for c in map(chr, range(0xC0, 0x250)) if c.isupper())
_LO = "a-z" + "".join(c for c in map(chr, range(0xDF, 0x250)) if c.islower())
NAME = rf"[{_UP}][{_LO}]+(?:-[{_UP}][{_LO}]+)?"          # Latin letters incl. é ć ş ž, double-barrelled
# capitalised words that are not names (German capitalises nouns)
STOP = {w.lower() for w in """Labor Lab Laboratory Reha Rehab Rehaklinik Klinik Klinikum Krankenhaus Spital Hospital Praxis
    Institut Zentrum Clinic Ordination Gerinnung Befund Laborbefund Blutbild Werte Bitte Please Grund Reason Anfrage
    Entlassungsbericht Entlassungsbrief Bericht Report Eingriff Operation Telefon Phone Mail Email Handy Nummer Danke
    Thanks Kanalstraße Waldblick Beispielstadt Die Der Das Den Dem Ich Wir Sie Er Es Und Oder Von Bei Für For From The
    Ask Request Patientin Patient Geb Geboren Born Gerinnungswerte Nierenwerte Leberwerte Hallo Hi Liebe Lieber
    Montag Dienstag Mittwoch Donnerstag Freitag Samstag Sonntag Monday Tuesday Wednesday Thursday Friday Heute Morgen
    INR Discharge Summary Results Lab Blood Coagulation Kidney Liver Austria Österreich Wien Vienna Blutzucker
    Blutfette Cholesterin Entzündungswerte Nierenfunktion Leberfunktion Elektrolyte Glukose Kreatinin Thrombozyten
    Kontrolle Verlauf Termin Station Zimmer Ambulanz Danke Dringend Urgent Thank""".split()}
ORG_PREFIX = ("labor", "lab", "reha", "klinik", "zentral", "zentrum", "praxis", "spital", "kranken", "ordination",
              "institut", "hospital", "clinic", "medizin", "gesundheit", "ambulatorium")
RECIPIENT_AFTER = re.compile(r"^[\s,]*(?:\([^)]*\)\s*|[^.;:\n]{0,45}?,\s*)?(?:anschreiben|kontaktieren|anrufen|fragen|anfragen|bitten|schreiben|"
                             r"contact|ask|email|text)\b", re.I)
ORG_WORD = r"(?:Labor|Laboratory|Lab|Reha|Rehaklinik|Rehabilitationszentrum|Klinik|Klinikum|Krankenhaus|Spital|Hospital|Praxis|Ordination|Institut|Zentrum|Clinic)"
ORG = re.compile(rf"\b(?:{ORG_WORD}(?:\s+[A-ZÄÖÜ][\wäöüß.-]+){{1,3}}|(?:[A-ZÄÖÜ][\wäöüß.-]+\s+){{1,2}}{ORG_WORD})\b")
REASON = [re.compile(r"(?:Grund|Reason|Anlass|Indikation|Fragestellung)\s*:\s*(?P<r>[^\n]+?)\s*[.!]?\s*$", re.I | re.M),
          re.compile(r"\b(?:wegen|aufgrund|because of|due to)\s+(?P<r>[^.,;\n]+)", re.I),
          re.compile(r"\b(?P<r>(?:vor|before|prior to)\s+(?:(?:dem|der|einem|einer|the|a|her|his|ihrem|ihrer|seinem|seiner)\s+)?"
                     r"(?:(?:geplanten|planned|anstehenden|upcoming|elektiven|elective)\s+)?[\wäöüß-]+)", re.I)]
RECIPIENT_CUE = re.compile(r"(?:\bbei|\ban|\bfrom|\bask|\bto|\bbitten sie|\bplease ask)\s*$", re.I)
PATIENT_CUE = re.compile(r"(?:\bpatientin|\bpatient|\bpat\.|\bfür|\bfor|\bof|\bzu|\bregarding|\bbetreffend)\s*$", re.I)
DR = {"dr", "prof", "mag", "ddr", "univ.-prof", "oä", "oa", "di", "doktor", "doktorin", "doctor", "professor", "professorin", "magister", "magistra"}
LAY = {"frau", "herr", "herrn", "fr", "hr", "mrs", "mr", "ms", "miss"}


def _is_org(core: str) -> bool:
    w = core.lower().strip(".,;:()")
    return w.startswith(ORG_PREFIX) and w not in ("labor",) or w in ("labor",)


def persons(text: str) -> list[Hit]:
    """Runs of titles + capitalised name tokens. A run needs a title + a name, or two names. Runs are split at a
    title that follows a name ('Nierenwerte Frau Maria Beispiel'), and a run right after an organisation word
    that starts with a title belongs to the organisation ('Labor Dr. Wimmer')."""
    hits: list[Hit] = []
    run: list[tuple[str, int, int, bool]] = []
    state = {"org": False}

    def close() -> None:
        while run and run[-1][3]:
            run.pop()
        names = [t for t in run if not t[3]]
        titles = [t for t in run if t[3]]
        if names and (titles or len(names) >= 2) and not state["org"]:
            s0, e0 = run[0][1], run[-1][2]
            hits.append(Hit(text[s0:e0], s0, e0, extra={"titles": [t[0] for t in titles], "name_tokens": [t[0] for t in names]}))
        run.clear()
        state["org"] = False

    prev_org = False
    for m in re.finditer(r"\S+", text):
        w = m.group(0)
        lead = len(w) - len(w.lstrip("(\"'„“"))
        core = w[lead:].rstrip(",;:!?)\"'“”")
        trail_punct = len(core) < len(w) - lead
        is_title = re.fullmatch(TITLE, core) is not None
        bare = core[:-1] if core.endswith(".") and not is_title else core
        sentence_end = bare != core
        is_name = (not is_title and re.fullmatch(NAME, bare) is not None and bare.lower() not in STOP and not _is_org(bare))
        start = m.start() + lead
        if is_title and run and not run[-1][3] and not state["org"]:
            close()                                          # a new person starts at a title after a name
        if is_title or is_name:
            if not run:
                state["org"] = prev_org and is_title            # "Labor Dr. Wimmer" is a lab, not a person
            elif state["org"] and is_title and any(not t[3] for t in run):
                run.clear()
                state["org"] = False
            run.append((bare if is_name else core, start, start + len(bare if is_name else core), is_title))
            if lead or trail_punct or sentence_end:
                close()
        else:
            close()
        prev_org = _is_org(core) or (prev_org and (is_name or is_title) and not trail_punct)
    close()
    return hits


def dates(text: str) -> list[Hit]:
    out = []
    for m in DATE.finditer(text):
        d = parse_dob(m.group(0))
        if d:
            cue = bool(DOB_CUE.search(text[max(0, m.start() - 25):m.start()]))
            out.append(Hit(m.group(0), m.start(), m.end(), extra={"iso": d.isoformat(), "dob_cue": cue}))
    return out


def contacts(text: str) -> list[Hit]:
    out = [Hit(m.group(0), m.start(), m.end(), extra={"kind": "email"}) for m in EMAIL.finditer(text)]
    for m in PHONE.finditer(text):
        if any(m.start() < o.end and o.start < m.end() for o in out):
            continue
        raw = m.group(0)
        if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", raw) or DATE.fullmatch(raw):
            continue
        digits = re.sub(r"[^\d+]", "", raw)
        if len(digits.lstrip("+")) < 7:
            continue
        e164 = "+" + digits[2:] if digits.startswith("00") else ("+43" + digits[1:] if digits.startswith("0") else digits)
        out.append(Hit(raw, m.start(), m.end(), extra={"kind": "sms", "e164": e164}))
    return sorted(out, key=lambda h: h.start)


def doc_type(text: str) -> Hit | None:
    m = REPORT_STRONG.search(text)
    if m:
        return Hit(m.group(0), m.start(), m.end(), extra={"type": "report"})
    m = PANEL_RE.search(text) or LAB_WORDS.search(text)
    if m:
        return Hit(m.group(0), m.start(), m.end(), extra={"type": "lab"})
    m = REPORT_WEAK.search(text)
    return Hit(m.group(0), m.start(), m.end(), extra={"type": "report"}) if m else None


def panel(text: str) -> Hit | None:
    m = PANEL_RE.search(text)
    if m:
        key = next(k for k, v in m.groupdict().items() if v)
        p = next(p for p in PANELS if p.key == key)
        return Hit(m.group(0), m.start(), m.end(), extra={"key": key, "loinc": list(p.loinc), "label_de": p.label_de})
    # single named tests ("INR", "Thrombozyten", "CRP")
    for code, (name, syns) in KNOWN.items():
        if code in ("11502-2", "18842-5"):
            continue
        for syn in sorted(syns, key=len, reverse=True):
            if len(syn) < 2:
                continue
            m = re.search(rf"\b{re.escape(syn)}\b", text, re.I)
            if m and (len(syn) > 3 or m.group(0).isupper()):
                return Hit(m.group(0), m.start(), m.end(), extra={"key": "single", "loinc": [code], "label_de": m.group(0)})
    for code, (name, _unit, _panel) in ELGA.items():          # Austrian lab names: "Gamma-GT", "Ferritin", "PTZ"
        short = re.split(r"\s*[(/,]", name)[0].strip()
        if len(short) < 3:
            continue
        m = re.search(rf"(?<![\w-]){re.escape(short)}(?![\w-])", text, re.I)
        if m and (len(short) > 3 or m.group(0).isupper()):
            return Hit(m.group(0), m.start(), m.end(), extra={"key": "single", "loinc": [code], "label_de": name})
    return None


def reason(text: str) -> Hit | None:
    for rx in REASON:
        m = rx.search(text)
        if m:
            r = m.group("r").strip().rstrip(".,;")
            s = m.start("r")
            return Hit(r, s, s + len(r))
    return None


def org_near(text: str, after: int, window: int = 80) -> Hit | None:
    for m in ORG.finditer(text, after, min(len(text), after + window)):
        return Hit(m.group(0), m.start(), m.end())
    return None


def _gap(text: str, a: int, b: int) -> str:
    return text[a:b] if a <= b else text[b:a]


def extract(text: str) -> dict[str, Hit | None]:
    """Field -> Hit (or None). Fields: recipient_name, recipient_org, contact, patient_name, patient_dob,
    patient_ref, doc_type, panel, reason."""
    ps, ds, cs = persons(text), dates(text), contacts(text)
    dob = next((d for d in ds if d.extra["dob_cue"]), None)
    scores = []
    for p in ps:
        pat = rec = 0.0
        before = text[max(0, p.start - 20):p.start]
        titles = {t.lower().rstrip(".") for t in p.extra["titles"]}
        for d in ds:
            gap = _gap(text, p.end, d.start)
            if d.start >= p.end and len(gap) <= 22 and re.fullmatch(r"[\s,(]*(?:geb\.?|geboren(?: am)?|born(?: on)?|\*|dob:?)?[\s(*]*", gap, re.I):
                pat += 3
                dob = dob or d
        for c in cs:
            gap = _gap(text, p.end, c.start) if c.start >= p.end else _gap(text, c.end, p.start)
            if len(gap) <= 60 and "\n" not in gap and not any(o is not p and min(p.end, c.start) < o.start < max(p.end, c.start) for o in ps):
                rec += 3
        von = re.search(r"\b(?:von|vom|from)\s+$", before, re.I)       # "von Dr. X" sends, "von Frau Y" is about
        if RECIPIENT_CUE.search(before) or (von and titles & DR):
            rec += 2
        if PATIENT_CUE.search(before) or (von and titles & LAY):
            pat += 2
        if RECIPIENT_AFTER.search(text[p.end:p.end + 40]):
            rec += 2
        if titles & DR:
            rec += 1
        if titles & LAY:
            pat += 0.5
        scores.append((p, pat, rec))
    # joint assignment: best (patient, recipient) pair, different people, each with a positive score
    best, patient, recipient = 0.0, None, None
    for a in [None, *scores]:
        for b in [None, *scores]:
            if (a and b and a[0] is b[0]) or (a and a[1] <= 0) or (b and b[2] <= 0):
                continue
            total = (a[1] - 0.25 * a[2] if a else 0) + (b[2] - 0.25 * b[1] if b else 0)
            if total > best:
                best, patient, recipient = total, a, b
    rec_hit = recipient[0] if recipient else None
    contact = None
    if cs:
        anchor = rec_hit.end if rec_hit else 0
        contact = min(cs, key=lambda c: abs(c.start - anchor))
    pat_hit = patient[0] if patient else None
    if pat_hit is not None and dob is not None and dob.start < pat_hit.end:
        dob = next((d for d in ds if d.start >= pat_hit.end), dob)
    ref = PATIENT_REF.search(text)
    return {
        "recipient_name": rec_hit,
        "recipient_org": org_near(text, rec_hit.end) if rec_hit else None,
        "contact": contact,
        "patient_name": pat_hit,
        "patient_dob": dob,
        "patient_ref": Hit(ref.group(0), ref.start(), ref.end()) if ref else None,
        "doc_type": doc_type(text),
        "panel": panel(text),
        "reason": reason(text),
    }


def same_person(a: str | None, b: str | None) -> bool:
    return bool(a and b) and norm_tokens(a) == norm_tokens(b)
