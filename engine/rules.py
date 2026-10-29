"""Rule-based request extraction (German + English): the CPU fallback and the cross-check for the model.

Every value is a slice of the (normalized) text with its span. Roles are decided by context:
the person next to a birth date is the patient, the person next to the contact is the recipient,
cue words ("bei", "von Dr.", "ask", "Patientin", "für", "for") break ties.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from engine._core import KNOWN, norm_tokens, parse_dob
from engine.lexicon import LAB_WORDS, PANEL_RE, PANELS, REPORT_STRONG, REPORT_WEAK


@dataclass
class Hit:
    value: str
    start: int
    end: int
    source: str = "rules"
    extra: dict = field(default_factory=dict)


EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<![\w/])(?:\+|00)?\d[\d \-/]{5,}\d(?![\w/])")
PATIENT_REF = re.compile(r"\bPatient/[A-Za-z0-9\-.]{1,64}\b")
_M = (r"(?:Jänner|Jaenner|Januar|January|Jan|Februar|February|Feb|März|Maerz|March|Mar|April|Apr|Mai|May|Juni|June|Jun|"
      r"Juli|July|Jul|August|Aug|September|Sept|Sep|Oktober|October|Okt|Oct|November|Nov|Dezember|December|Dez|Dec)")
DATE = re.compile(rf"\b(?:\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}\.\s?\d{{1,2}}\.\s?\d{{4}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}|"
                  rf"\d{{1,2}}\.?\s+{_M}\.?\s+\d{{4}}|{_M}\s+\d{{1,2}},?\s+\d{{4}})\b", re.I)
DOB_CUE = re.compile(r"(?:geb\.?|geboren(?: am)?|born(?: on)?|\*|dob|geburtsdatum|date of birth|birth ?date|jg\.?|jahrgang)\s*:?\s*$", re.I)

TITLE = r"(?:Univ\.-Prof\.|Prof\.|Professor(?:in)?|DDr\.|Dr\.|Dr|Doktor(?:in)?|Doctor|med\.|Mag\.|DI|OÄ|OA|Frau|Herrn|Herr|Fr\.|Hr\.|Mrs\.?|Mr\.?|Ms\.?|Miss)"
NAME = r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?"
PERSON_TITLED = re.compile(rf"(?:{TITLE}\s+)+{NAME}(?:\s+{NAME}){{0,2}}")
PERSON_CUED = re.compile(rf"(?:(?<=\bPatientin )|(?<=\bPatient )|(?<=\bpatient )|(?<=\bPat\. )|(?<=\bfür )|(?<=\bfor )|"
                         rf"(?<=\bbei )|(?<=\bvon )|(?<=\bfrom )|(?<=\bask )|(?<=\ban ))({NAME}(?:\s+{NAME}){{1,2}})")
PERSON_BARE = re.compile(rf"\b{NAME}\s+{NAME}\b")
# capitalised words that are not names (German capitalises nouns)
STOP = {w.lower() for w in """Labor Lab Laboratory Reha Rehab Rehaklinik Klinik Klinikum Krankenhaus Spital Hospital Praxis
    Institut Zentrum Clinic Ordination Gerinnung Befund Laborbefund Blutbild Werte Bitte Please Grund Reason Anfrage
    Entlassungsbericht Entlassungsbrief Bericht Report Eingriff Operation Telefon Phone Mail Email Handy Nummer Danke
    Thanks Kanalstraße Waldblick Beispielstadt Die Der Das Den Dem Ich Wir Sie Er Es Und Oder Von Bei Für For From The
    Ask Request Patientin Patient Geb Geboren Born Gerinnungswerte Nierenwerte Leberwerte Hallo Hi Liebe Lieber
    Montag Dienstag Mittwoch Donnerstag Freitag Samstag Sonntag Monday Tuesday Wednesday Thursday Friday Heute Morgen
    INR Discharge Summary Results Lab Blood Coagulation Kidney Liver Austria Österreich Wien Vienna""".split()}
ORG_WORD = r"(?:Labor|Laboratory|Lab|Reha|Rehaklinik|Rehabilitationszentrum|Klinik|Klinikum|Krankenhaus|Spital|Hospital|Praxis|Ordination|Institut|Zentrum|Clinic)"
ORG = re.compile(rf"\b(?:{ORG_WORD}(?:\s+[A-ZÄÖÜ][\wäöüß.-]+){{1,3}}|(?:[A-ZÄÖÜ][\wäöüß.-]+\s+){{1,2}}{ORG_WORD})\b")
REASON = [re.compile(r"(?:Grund|Reason|Anlass|Indikation|Fragestellung)\s*:\s*(?P<r>[^\n]+?)\s*[.!]?\s*$", re.I | re.M),
          re.compile(r"\b(?:wegen|aufgrund|because of|due to)\s+(?P<r>[^.,;\n]+)", re.I),
          re.compile(r"\b(?P<r>(?:vor|before|prior to)\s+(?:(?:dem|der|einem|einer|the|a|her|his|ihrem|ihrer|seinem|seiner)\s+)?"
                     r"(?:(?:geplanten|planned|anstehenden|upcoming|elektiven|elective)\s+)?[\wäöüß-]+)", re.I)]
RECIPIENT_CUE = re.compile(r"(?:\bbei|\ban|\bfrom|\bask|\bto|\bbitten sie|\bplease ask)\s*$", re.I)
PATIENT_CUE = re.compile(r"(?:\bpatientin|\bpatient|\bpat\.|\bfür|\bfor|\bof|\bzu|\bregarding|\bbetreffend)\s*$", re.I)
DR = {"dr", "prof", "mag", "ddr", "univ.-prof", "oä", "oa", "di", "doktor", "doktorin", "doctor", "professor", "professorin"}
LAY = {"frau", "herr", "herrn", "fr", "hr", "mrs", "mr", "ms", "miss"}


def _trim_person(text: str, start: int, end: int) -> Hit | None:
    """Cut a person match at the first non-name word ('Dr. Eva Brandl Labor' -> 'Dr. Eva Brandl')."""
    keep, seen_name = [], False
    for t in re.finditer(r"\S+", text[start:end]):
        w = t.group(0)
        is_title = re.fullmatch(TITLE, w) is not None
        if not is_title and w.lower().strip(".,") in STOP:
            break
        keep.append(t)
        seen_name |= not is_title
    if not seen_name:
        return None
    s, e = start + keep[0].start(), start + keep[-1].end()
    titles = [t.group(0) for t in keep if re.fullmatch(TITLE, t.group(0))]
    names = [t.group(0) for t in keep if re.fullmatch(TITLE, t.group(0)) is None]
    return Hit(text[s:e], s, e, extra={"titles": titles, "name_tokens": names})


def persons(text: str) -> list[Hit]:
    hits: list[Hit] = []
    for rx in (PERSON_TITLED, PERSON_CUED, PERSON_BARE):
        for m in rx.finditer(text):
            g = 1 if rx is PERSON_CUED else 0
            h = _trim_person(text, m.start(g), m.end(g))
            if not h or any(h.start < o.end and o.start < h.end for o in hits):
                continue
            if rx is not PERSON_TITLED and len(h.extra["name_tokens"]) < 2:
                continue
            hits.append(h)
    return sorted(hits, key=lambda h: h.start)


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
        if titles & DR:
            rec += 1
        if titles & LAY:
            pat += 0.5
        scores.append((p, pat, rec))
    patient = max((s for s in scores if s[1] > 0), key=lambda s: (s[1], -s[2]), default=None)
    recipient = max((s for s in scores if s[2] > 0 and (patient is None or s[0] is not patient[0])),
                    key=lambda s: (s[2], -s[1]), default=None)
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
