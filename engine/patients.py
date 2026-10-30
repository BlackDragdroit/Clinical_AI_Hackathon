"""Which Patient does the request mean? Two identifiers (name + birth date) or an explicit Patient/<id>.

Candidates come from the clinic's FHIR server (search by birth date and by family name), and the core's
Fellegi–Sunter matcher ranks them. The answer is `unique` only when the best candidate passes the matcher's
`file` rule (exact birth date, family name agrees) and no other candidate gets past `reject`. Without a birth
date the engine never picks a patient on its own; it asks (two-identifier rule).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol

import httpx

from engine._core import WEIGHTS, Person, compare, split_name

MARGIN_BITS = 6.0      # best candidate must beat the runner-up by 64:1 odds


class Directory(Protocol):
    def read(self, ref: str) -> dict | None: ...
    def search(self, family: str | None, birthdate: str | None) -> list[dict]: ...


def _summary(p: dict) -> dict:
    n = (p.get("name") or [{}])[0]
    return {"ref": f"Patient/{p['id']}", "name": " ".join([*n.get("given", []), n.get("family", "")]).strip(),
            "dob": p.get("birthDate", "")}


class HapiDirectory:
    def __init__(self, base_url: str, timeout: float = 10):
        self.client = httpx.Client(base_url=base_url, timeout=timeout, headers={"Accept": "application/fhir+json"})

    def read(self, ref: str) -> dict | None:
        r = self.client.get(ref)
        return _summary(r.json()) if r.status_code == 200 else None

    def search(self, family: str | None, birthdate: str | None) -> list[dict]:
        out: dict[str, dict] = {}
        queries = []
        if birthdate:
            queries.append({"birthdate": birthdate, "_count": "50"})
        if family:
            queries.append({"family": family, "_count": "50"})
        for q in queries:
            r = self.client.get("Patient", params=q)
            if r.status_code != 200:
                continue
            for e in r.json().get("entry", []):
                s = _summary(e["resource"])
                out[s["ref"]] = s
        return list(out.values())


class MemoryDirectory:
    """For tests and the offline eval: a list of {'ref','name','dob'}."""
    def __init__(self, patients: list[dict]):
        self.patients = patients

    def read(self, ref: str) -> dict | None:
        return next((p for p in self.patients if p["ref"] == ref), None)

    def search(self, family: str | None, birthdate: str | None) -> list[dict]:
        fam = (family or "").lower()
        return [p for p in self.patients
                if (birthdate and p["dob"] == birthdate) or (fam and split_name(p["name"])[1].lower().startswith(fam[:4]))]


@dataclass
class PatientMatch:
    status: str                         # unique | ambiguous | not_found | need_dob | explicit | no_directory
    ref: str | None = None
    display: str | None = None
    candidates: list[dict] = field(default_factory=list)
    note_de: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def resolve(directory: Directory | None, name: str | None, dob_iso: str | None, explicit_ref: str | None) -> PatientMatch:
    if explicit_ref:
        if directory is None:
            return PatientMatch("explicit", explicit_ref, explicit_ref, note_de="Patient laut Referenz")
        p = directory.read(explicit_ref)
        if not p:
            return PatientMatch("not_found", note_de=f"{explicit_ref} nicht gefunden")
        return PatientMatch("explicit", p["ref"], f"{p['name']}, *{p['dob']}", [p], "Patient laut Referenz")
    if not name:
        return PatientMatch("not_found", note_de="Kein Patient im Text erkannt")
    if not dob_iso:
        return PatientMatch("need_dob", note_de="Bitte Geburtsdatum angeben (zweites Identifikationsmerkmal)")
    if directory is None:
        return PatientMatch("no_directory", note_de="Kein Patientenverzeichnis angebunden")
    wanted = Person.from_full(name, dob_iso)
    scored = []
    for c in directory.search(wanted.family or None, dob_iso):
        m = compare(wanted, Person.from_full(c["name"], c["dob"]), WEIGHTS)
        scored.append({**c, "score": m.score, "decision": m.decision})
    scored.sort(key=lambda c: c["score"], reverse=True)
    top = scored[:5]
    if not scored or scored[0]["decision"] == "reject":
        return PatientMatch("not_found", candidates=top, note_de="Kein passender Patient gefunden")
    best, rest = scored[0], scored[1:]
    # a namesake with another birth date scores far below; a near-twin (same date, similar name) also passes `file`
    if best["decision"] == "file" and all(c["decision"] != "file" and best["score"] - c["score"] >= MARGIN_BITS for c in rest):
        return PatientMatch("unique", best["ref"], f"{best['name']}, *{best['dob']}", top)
    return PatientMatch("ambiguous", candidates=top,
                        note_de="Mehrere mögliche Patienten – bitte mit Patient/<id> oder genauerem Namen wählen")
