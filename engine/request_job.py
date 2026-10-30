"""Request job: Dr. Hofer's sentence (typed or transcribed, German or English) -> a checked request.

  normalize -> rules + model (in parallel in spirit; the model is optional) -> ground every value
  -> merge (agreement raises trust, disagreement on the contact blocks it) -> patient lookup (two identifiers)
  -> ready, or a German question back for what is missing.

Nothing is sent from here: the result becomes the confirmation card, and only `!senden` sends.
"""
from __future__ import annotations

import re
import time

from engine import rules
from engine._core import parse_dob
from engine.backends import llm
from engine.ground import locate
from engine.normalize import language, normalize
from engine.patients import Directory, PatientMatch, resolve

VERSION = "engine-0.1"

FIELDS = {
    "recipient_name": "string", "recipient_organisation": "string", "contact": "string",
    "patient_name": "string", "patient_birth_date": "string",
    "document_type": ["lab_result", "discharge_report", "other"],
    "requested_tests": "string", "reason": "string",
}
INSTRUCTIONS = (
    "You read a document request written or dictated by a hospital doctor, in German or English. "
    "Return JSON. Copy every string value exactly as it appears in the text (same spelling, same punctuation); "
    "use null if the text does not say it. recipient = the person outside the hospital who should send the document; "
    "patient = the person the document is about. contact = the recipient's e-mail address or phone number. "
    "document_type: lab_result for lab or blood values, discharge_report for discharge or rehab reports, else other. "
    "requested_tests = the tests or panel asked for (e.g. 'Gerinnung', 'blood count'). reason = why it is needed."
)
_LLM_KEY = {"recipient_name": "recipient_name", "recipient_org": "recipient_organisation", "contact": "contact",
            "patient_name": "patient_name", "patient_dob": "patient_birth_date", "panel": "requested_tests",
            "reason": "reason"}
_DOC = {"lab_result": "lab", "discharge_report": "report"}
_LAY = re.compile(r"^(?:(?:Frau|Herrn|Herr|Fr\.|Hr\.|Mrs\.?|Mr\.?|Ms\.?|Miss)\s+)+")
LABELS = {"recipient_name": "Empfänger/in", "contact": "Kontakt (E-Mail oder Handynummer)", "doc_type": "Dokumentart",
          "patient": "Patient/in mit Geburtsdatum"}


_SPOKEN_TITLE = [(re.compile(r"\b(?:Doktor(?:in)?|Doctor)\b"), "Dr."), (re.compile(r"\bProfessor(?:in)?\b"), "Prof."),
                 (re.compile(r"\bMagist(?:er|ra)\b"), "Mag.")]


def clean_name(name: str | None) -> str | None:
    """'Herrn Stefan Kern' -> 'Stefan Kern', 'Doktor Eva Brandl' -> 'Dr. Eva Brandl' (dictated titles written out,
    lay titles dropped), so the name compares cleanly with the eID name later."""
    if not name:
        return name
    for rx, short in _SPOKEN_TITLE:
        name = rx.sub(short, name)
    return _LAY.sub("", name).strip()


def _field(value: str, start: int, end: int, source: str, level: str = "exact", **extra) -> dict:
    return {"value": value, "start": start, "end": end, "source": source, "level": level, **extra}


def _merge(key: str, hit: rules.Hit | None, llm_value, text: str, flags: list[str], dropped: list[str]) -> dict | None:
    g = locate(llm_value, text) if isinstance(llm_value, str) and llm_value.strip() else None
    if isinstance(llm_value, str) and llm_value.strip() and g is None:
        dropped.append(key)                       # the model said something that is not in the text
    if hit and g:
        if hit.start < g.end and g.start < hit.end:   # same place in the text
            v = hit if len(hit.value) >= len(g.value) else None
            return _field(v.value, v.start, v.end, "rules+llm") if v else _field(g.value, g.start, g.end, "rules+llm", g.level)
        if key == "contact":
            flags.append("Kontakt uneindeutig: Regel und Modell finden verschiedene Adressen – bitte angeben")
            return None
        flags.append(f"{LABELS.get(key, key)}: Regel „{hit.value}“ und Modell „{g.value}“ uneinig – Modell übernommen")
        return _field(g.value, g.start, g.end, "llm", g.level, alt=hit.value)
    if hit:
        return _field(hit.value, hit.start, hit.end, "rules")
    if g:
        return _field(g.value, g.start, g.end, "llm", g.level)
    return None


def run(text: str, directory: Directory | None = None, use_llm: bool = True, use_rules: bool = True) -> dict:
    """use_rules=False is for the evaluation only (model alone); the rules still canonicalise what the model found."""
    t0 = time.perf_counter()
    norm = normalize(text)
    lang = language(norm)
    r = rules.extract(norm) if use_rules else dict.fromkeys(rules.extract(norm))
    t_rules = time.perf_counter()
    res = llm.extract(norm, FIELDS, INSTRUCTIONS) if use_llm else llm.LlmResult(None, "", 0, "disabled")
    data = res.data or {}
    flags: list[str] = []
    dropped: list[str] = []
    fields = {k: _merge(k, r[k], data.get(lk), norm, flags, dropped) for k, lk in _LLM_KEY.items()}

    # birth date: must parse to a real date
    dob_iso = None
    if fields["patient_dob"]:
        d = parse_dob(fields["patient_dob"]["value"])
        if d:
            dob_iso = fields["patient_dob"]["iso"] = d.isoformat()
        else:
            flags.append(f"Geburtsdatum „{fields['patient_dob']['value']}“ nicht lesbar")
            fields["patient_dob"] = None

    # document type: rules give the keyword as evidence, the model gives an enum
    doc_type, rule_dt, llm_dt = None, r["doc_type"], _DOC.get(data.get("document_type") or "")
    if rule_dt and llm_dt and rule_dt.extra["type"] != llm_dt:
        flags.append(f"Dokumentart unklar (Regel: {rule_dt.extra['type']}, Modell: {llm_dt}) – Regel übernommen")
    if rule_dt:
        doc_type = rule_dt.extra["type"]
        fields["doc_type"] = _field(rule_dt.value, rule_dt.start, rule_dt.end, "rules+llm" if llm_dt == doc_type else "rules")
    elif llm_dt:
        doc_type = llm_dt
        fields["doc_type"] = {"value": data["document_type"], "source": "llm", "level": "enum"}
    else:
        fields["doc_type"] = None

    # panel -> expected LOINC codes (for the completeness check on the answer)
    panel = None
    if fields["panel"]:
        p = rules.panel(fields["panel"]["value"]) or r["panel"]
        if p:
            panel = {"key": p.extra["key"], "label_de": p.extra["label_de"], "loinc": p.extra["loinc"]}
    elif r["panel"]:
        panel = {"key": r["panel"].extra["key"], "label_de": r["panel"].extra["label_de"], "loinc": r["panel"].extra["loinc"]}

    # contact: kind + canonical form (E.164 for phones)
    contact_kind = contact_value = None
    if fields["contact"]:
        c = rules.contacts(fields["contact"]["value"])
        if c:
            contact_kind = c[0].extra["kind"]
            contact_value = c[0].value if contact_kind == "email" else c[0].extra["e164"]
        else:
            flags.append(f"„{fields['contact']['value']}“ ist weder E-Mail noch Telefonnummer")
            fields["contact"] = None

    t_merge = time.perf_counter()
    ref = r["patient_ref"].value if r["patient_ref"] else None
    pname = clean_name(fields["patient_name"]["value"]) if fields["patient_name"] else None
    patient: PatientMatch = resolve(directory, pname, dob_iso, ref)
    t_patient = time.perf_counter()

    missing = [k for k in ("recipient_name", "contact", "doc_type") if not fields.get(k)]
    if patient.status not in ("unique", "explicit"):
        missing.append("patient")
    ask = None
    if missing:
        ask = "Bitte noch angeben: " + ", ".join(LABELS[m] for m in missing) + "."
        if patient.note_de and "patient" in missing:
            ask += f" ({patient.note_de})"
    reason_text = fields["reason"]["value"] if fields["reason"] else None
    if panel and (not reason_text or panel["label_de"].lower() not in reason_text.lower()):
        reason_text = f"{panel['label_de']} – {reason_text}" if reason_text else panel["label_de"]

    return {
        "version": VERSION,
        "input": {"text": text, "normalized": norm, "language": lang},
        "fields": fields,
        "recipient": clean_name(fields["recipient_name"]["value"]) if fields["recipient_name"] else None,
        "doc_type": doc_type,
        "contact": {"kind": contact_kind, "value": contact_value} if contact_value else None,
        "panel": panel,
        "reason": reason_text,
        "patient": patient.as_dict(),
        "flags": flags,
        "dropped_ungrounded": dropped,
        "missing": missing,
        "ready": not missing,
        "ask_de": ask,
        "models": {"llm": res.model or None, "llm_error": res.error},
        "timings_ms": {"rules": int((t_rules - t0) * 1000), "llm": res.ms, "merge": int((t_merge - t_rules) * 1000) - res.ms,
                       "patient": int((t_patient - t_merge) * 1000), "total": int((time.perf_counter() - t0) * 1000)},
    }
