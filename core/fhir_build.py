"""Build FHIR R4 resources (plain JSON, standard elements only) from a ParsedDoc.

Lab report  -> Observation per row (LOINC + UCUM + reference range + interpretation),
               DiagnosticReport (LAB, results, presentedForm), DocumentReference (original file),
               Provenance (target = all of the above)
Rehab report-> DocumentReference (LOINC 18842-5, text/markdown attached, context.period),
               Provenance
Everything goes into one transaction Bundle with urn:uuid fullUrls.
Timezone: Europe/Vienna (so +02:00 / +01:00 are right automatically).
"""
from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from loinc import resolve
from parse_doc import ParsedDoc, interpret, parse_datetime, parse_period

VIENNA = ZoneInfo("Europe/Vienna")
UCUM = "http://unitsofmeasure.org"
LOINC = "http://loinc.org"
OBS_CAT = "http://terminology.hl7.org/CodeSystem/observation-category"
V3_INTERP = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
V2_0074 = "http://terminology.hl7.org/CodeSystem/v2-0074"
PROV_TYPE = "http://terminology.hl7.org/CodeSystem/provenance-participant-type"
IDENTITY_POLICY_URI = "https://example.org/befundbruecke/policy/identity-v1"   # TODO: point at README anchor

UCUM_MAP = {
    "10^9/l": "10*9/L", "10^9/L": "10*9/L", "g/l": "10*9/L", "G/L": "10*9/L", "10^12/l": "10*12/L", "T/L": "10*12/L",
    "g/L": "g/L", "g/dl": "g/dL", "g/dL": "g/dL", "mg/dl": "mg/dL", "mg/dL": "mg/dL", "mg/l": "mg/L", "mg/L": "mg/L",
    "mmol/l": "mmol/L", "mmol/L": "mmol/L", "µmol/l": "umol/L", "µmol/L": "umol/L", "umol/L": "umol/L",
    "s": "s", "sec": "s", "%": "%", "U/l": "U/L", "U/L": "U/L", "fl": "fL", "fL": "fL", "pg": "pg",
    "ng/ml": "ng/mL", "ng/mL": "ng/mL", "mIU/L": "m[IU]/L", "mU/L": "mU/L", "IU/L": "[IU]/L",
}


def urn() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


def dt_local(d: datetime | date | None) -> Optional[str]:
    if d is None:
        return None
    if isinstance(d, datetime):
        if d.tzinfo is None:
            d = d.replace(tzinfo=VIENNA)
        return d.isoformat(timespec="seconds")
    return d.isoformat()


def instant_now() -> str:
    return datetime.now(VIENNA).isoformat(timespec="seconds")


def quantity(value: float, unit: str) -> dict:
    q: dict = {"value": value}
    u = (unit or "").strip()
    if u:
        q["unit"] = u
        code = UCUM_MAP.get(u) or UCUM_MAP.get(u.lower())
        if code:
            q["system"] = UCUM
            q["code"] = code
    return q


def human_name(full: str) -> dict:
    from fs_matcher import split_name
    toks = full.replace(",", " ").split()
    prefix = [t for t in toks if t.rstrip(".").lower() in {"dr", "mag", "di", "prof", "oä", "oa", "pd"}]
    core = " ".join(t for t in toks if t not in prefix)
    given, family = split_name(core)
    hn: dict = {"text": full}
    if family:
        hn["family"] = family
    if given:
        hn["given"] = given.split()
    if prefix:
        hn["prefix"] = prefix
    return hn


def practitioner(full_name: str) -> dict:
    name = full_name.split(",")[0].strip()
    return {"resourceType": "Practitioner", "name": [human_name(name)]}


def organization(name: str) -> dict:
    return {"resourceType": "Organization", "name": name}


def device() -> dict:
    return {"resourceType": "Device",
            "deviceName": [{"name": "BefundBrücke intake service", "type": "manufacturer-name"}],
            "version": [{"value": "0.1.0"}]}


def attachment(text: str, title: str, content_type: str = "text/markdown", creation: str | None = None) -> dict:
    raw = text.encode("utf-8")
    a = {"contentType": content_type, "data": base64.b64encode(raw).decode(), "title": title,
         "hash": base64.b64encode(hashlib.sha1(raw).digest()).decode(), "size": len(raw)}
    if creation:
        a["creation"] = creation
    return a


class Built:
    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.notes: list[str] = []
        self.summary_lines: list[str] = []

    def add(self, resource: dict) -> str:
        full = urn()
        self.entries.append({"fullUrl": full, "resource": resource,
                             "request": {"method": "POST", "url": resource["resourceType"]}})
        return full

    def bundle(self) -> dict:
        return {"resourceType": "Bundle", "type": "transaction", "entry": self.entries}


def build(doc: ParsedDoc, patient_ref: str, sender_name: str, sender_org: str,
          identity_method_text: str, answer_sent_at: datetime | None = None,
          original_filename: str = "document.md") -> Built:
    b = Built()
    sender_org_ref = b.add(organization(sender_org or doc.org or "Unbekannte Organisation"))
    sender_ref = b.add(practitioner(sender_name))
    device_ref = b.add(device())
    sent_at = dt_local(answer_sent_at or datetime.now(VIENNA))
    targets: list[str] = []
    entity_ref: Optional[str] = None

    if doc.kind == "lab":
        taken = parse_datetime(doc.fields.get("Sample taken") or doc.fields.get("Abnahme") or doc.fields.get("Entnahme") or "")
        reported = parse_datetime(doc.fields.get("Reported") or doc.fields.get("Befundet") or doc.fields.get("Bericht") or "")
        validator_name = (doc.fields.get("Validated by") or doc.fields.get("Validiert von") or "").split(",")[0].strip()
        performer_ref = sender_ref
        if validator_name and validator_name.lower() not in sender_name.lower():
            performer_ref = b.add(practitioner(validator_name))
            b.notes.append(f"Befund validiert von {validator_name} (laut Dokument, nicht identitätsgeprüft)")
        obs_refs = []
        for r in doc.rows:
            lc = resolve(r.loinc, r.test)
            if lc.status not in ("ok", "ok_unknown"):
                b.notes.append(f"{r.test}: {lc.note_de}")
            code: dict = {"text": r.test}
            if lc.code:
                code["coding"] = [{"system": LOINC, "code": lc.code}]
            obs: dict = {
                "resourceType": "Observation", "status": "final",
                "category": [{"coding": [{"system": OBS_CAT, "code": "laboratory", "display": "Laboratory"}]}],
                "code": code, "subject": {"reference": patient_ref},
                "performer": [{"reference": performer_ref}, {"reference": sender_org_ref}],
            }
            if taken:
                obs["effectiveDateTime"] = dt_local(taken)
            if reported:
                obs["issued"] = dt_local(reported)
            if r.value is not None:
                obs["valueQuantity"] = quantity(r.value, r.unit)
            elif r.raw_value:
                obs["valueString"] = r.raw_value
            flag = interpret(r.value, r.ref_low, r.ref_high)
            if flag:
                obs["interpretation"] = [{"coding": [{"system": V3_INTERP, "code": flag}]}]
            if r.ref_low is not None or r.ref_high is not None:
                rr: dict = {}
                if r.ref_low is not None:
                    rr["low"] = quantity(r.ref_low, r.unit)
                if r.ref_high is not None:
                    rr["high"] = quantity(r.ref_high, r.unit)
                if r.ref_raw:
                    rr["text"] = r.ref_raw
                obs["referenceRange"] = [rr]
            obs_refs.append(b.add(obs))
            b.summary_lines.append(f"{r.test}: {r.raw_value} {r.unit}".strip() + (f" ({flag})" if flag and flag != "N" else ""))
        targets += obs_refs
        docref = {
            "resourceType": "DocumentReference", "status": "current", "docStatus": "final",
            "type": {"coding": [{"system": LOINC, "code": "11502-2"}], "text": doc.title or "Laborbefund"},
            "subject": {"reference": patient_ref}, "date": instant_now(),
            "author": [{"reference": sender_ref}], "custodian": {"reference": sender_org_ref},
            "description": f"Originaldokument, übermittelt von {sender_name}",
            "content": [{"attachment": attachment(doc.raw, original_filename, creation=dt_local(reported) if reported else None)}],
        }
        entity_ref = b.add(docref)
        targets.append(entity_ref)
        dr: dict = {
            "resourceType": "DiagnosticReport", "status": "final",
            "category": [{"coding": [{"system": V2_0074, "code": "LAB", "display": "Laboratory"}]}],
            "code": {"coding": [{"system": LOINC, "code": "11502-2"}], "text": f"{doc.org}: {doc.title}".strip(": ")},
            "subject": {"reference": patient_ref},
            "performer": [{"reference": performer_ref}, {"reference": sender_org_ref}],
            "result": [{"reference": o} for o in obs_refs],
            "presentedForm": [attachment(doc.raw, original_filename)],
        }
        if taken:
            dr["effectiveDateTime"] = dt_local(taken)
        if reported:
            dr["issued"] = dt_local(reported)
        if doc.fields.get("_text"):
            dr["conclusion"] = doc.fields["_text"].strip()
        targets.append(b.add(dr))

    else:  # narrative report -> DocumentReference
        author_name = (doc.fields.get("Written by") or doc.fields.get("Erstellt von") or doc.fields.get("Verfasst von") or "").split(",")[0].strip()
        authors = [{"reference": sender_ref}]
        if author_name and author_name.lower() not in sender_name.lower():
            authors.insert(0, {"reference": b.add(practitioner(author_name))})
            b.notes.append(f"Verfasst von {author_name} (laut Dokument, nicht identitätsgeprüft); gesendet von {sender_name}")
        start, end = parse_period(doc.fields.get("Stay") or doc.fields.get("Aufenthalt") or "")
        docref = {
            "resourceType": "DocumentReference", "status": "current", "docStatus": "final",
            "type": {"coding": [{"system": LOINC, "code": "18842-5"}], "text": doc.title or "Entlassungsbericht"},
            "subject": {"reference": patient_ref}, "date": instant_now(),
            "author": authors, "custodian": {"reference": sender_org_ref},
            "description": (doc.fields.get("Reason") or doc.fields.get("Grund") or doc.title),
            "content": [{"attachment": attachment(doc.raw, original_filename, creation=dt_local(end) if end else None)}],
        }
        if start or end:
            period = {}
            if start:
                period["start"] = start.isoformat()
            if end:
                period["end"] = end.isoformat()
            docref["context"] = {"period": period}
        targets.append(b.add(docref))
        for k in ("Medication at discharge", "Medikation bei Entlassung", "Recommendations", "Empfehlungen"):
            if k in doc.sections:
                b.summary_lines.append(f"{k}: " + " · ".join(l.lstrip("- ").strip() for l in doc.sections[k].splitlines()))

    prov: dict = {
        "resourceType": "Provenance", "target": [{"reference": t} for t in targets],
        "occurredDateTime": sent_at, "recorded": instant_now(), "policy": [IDENTITY_POLICY_URI],
        "agent": [
            {"type": {"coding": [{"system": PROV_TYPE, "code": "author"}]},
             "role": [{"text": identity_method_text}],
             "who": {"reference": sender_ref}, "onBehalfOf": {"reference": sender_org_ref}},
            {"type": {"coding": [{"system": PROV_TYPE, "code": "assembler"}]},
             "role": [{"text": "Dokument geparst und als FHIR abgelegt"}],
             "who": {"reference": device_ref}},
        ],
    }
    if entity_ref:
        prov["entity"] = [{"role": "source", "what": {"reference": entity_ref}}]
    b.add(prov)
    return b


if __name__ == "__main__":
    import json
    import sys
    from parse_doc import parse_markdown
    path = sys.argv[1]
    doc = parse_markdown(open(path, encoding="utf-8").read())
    sender = "Dr. Eva Brandl" if doc.kind == "lab" else "Stefan Kern"
    built = build(doc, "Patient/maria-beispiel", sender, doc.org,
                  "Identität geprüft: ID Austria (simuliert), Namensabgleich OK; Besitz der Kontaktadresse über Einmal-Link",
                  original_filename=path.split("/")[-1])
    out = path.split("/")[-1].replace(".md", ".bundle.json")
    json.dump(built.bundle(), open(out, "w"), indent=2, ensure_ascii=False)
    print(f"{out}: {len(built.entries)} resources; summary: {built.summary_lines}; notes: {built.notes}")
