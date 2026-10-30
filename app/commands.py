"""Doctor commands, shared by the Matrix bot and the CLI: handle(text, sender) -> reply. Owner: SWE 1.

Anything that is not a !command is a request in plain German or English ("Bitte bei Dr. Eva Brandl …"):
the engine turns it into the same draft card. Voice notes arrive via from_engine().

Replies are plain text; the bot renders them as HTML (app/matrix_format.py). Copy rules: the first
line says what happened, one fact per line, the next step is the exact command to type.
"""
from __future__ import annotations

import shlex
from datetime import date

import httpx

from app import audit, db, engine_client, intake_service, requests_service
from app.config import settings

HELP = """Befehle
!anfrage labor "Dr. Eva Brandl" eva.brandl@labor-kanal.example Patient/maria-beispiel Grund: Gerinnung vor Eingriff
!anfrage bericht "Stefan Kern" +436600000101 Patient/maria-beispiel Grund: Entlassungsbericht
Anfrage senden: !senden <id>
Antwort nach Prüfung ablegen: !ablegen <id> · verwerfen: !verwerfen <id>
Stand einer Anfrage: !status <id>"""

DOC_LABEL = {"lab": "Laborbefund", "report": "Entlassungsbericht"}
CONTACT_LABEL = {"email": "E-Mail", "sms": "SMS"}
STATUS_LABEL = {
    "draft": "Entwurf, noch nicht gesendet", "sent": "gesendet, Link noch nicht geöffnet",
    "opened": "Link geöffnet, Identität noch nicht bestätigt", "identified": "Identität bestätigt, Antwort ausständig",
    "answered": "Antwort eingegangen, wird verarbeitet", "filed": "abgelegt", "review": "wartet auf Ihre Prüfung",
    "rejected": "Antwort betraf anderen Patienten, nicht abgelegt", "discarded": "verworfen",
    "blocked": "gesperrt (zu viele Fehlversuche)",
}


def parse_anfrage(text: str) -> dict:
    head, _, reason = text.partition("Grund:")
    parts = shlex.split(head)
    if len(parts) != 5 or parts[0] != "!anfrage":
        raise ValueError('Format: !anfrage labor|bericht "Name" Kontakt Patient/<id> Grund: …')
    _, kind, name, contact, patient_ref = parts
    if kind.lower() not in requests_service.DOC_TYPES:
        raise ValueError("Dokumentart: labor oder bericht")
    return {"doc_kind": kind, "expected_name": name, "contact": contact.replace(" ", ""),
            "patient_ref": patient_ref, "reason": reason.strip()}


def _dob(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except ValueError:
        return iso


def draft_card(req: dict) -> str:
    lines = [
        f"Anfrage {req['id']}: Entwurf, noch nicht gesendet",
        f"Patient: {req['patient_name']}, geb. {_dob(req['patient_dob'])}",
        f"Dokument: {DOC_LABEL[req['doc_type']]}",
        f"An: {req['expected_name']} per {CONTACT_LABEL[req['contact_kind']]} an {req['contact']}",
    ]
    if req["reason"]:
        lines.append(f"Grund: {req['reason']}")
    lines += [f"⚠️ Kontakt prüfen: {w}" for w in req["lint_warnings"]]
    lines.append(f"Senden: !senden {req['id']}")
    return "\n".join(lines)


def sent_card(req: dict) -> str:
    return "\n".join([
        f"Anfrage {req['id']} gesendet an {req['expected_name']}",
        f"Neutrale {CONTACT_LABEL[req['contact_kind']]} mit persönlichem Link, gültig {settings.link_ttl_hours} h",
        f"FHIR {req['task_ref']} angelegt. Sie werden hier benachrichtigt, sobald die Antwort da ist.",
    ])


def _error(e: Exception) -> str:
    """What failed, why (if known), what to do next."""
    if isinstance(e, httpx.ConnectError):
        return "FHIR-Server nicht erreichbar\nNichts wurde angelegt oder gesendet. Bitte in einer Minute erneut versuchen."
    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
        return f"Nicht gefunden auf dem FHIR-Server: {e.request.url.path.split('/fhir/')[-1]}\nBitte die Patienten-ID prüfen."
    if isinstance(e, ValueError):
        return f"Befehl nicht ausgeführt\n{e}"
    return f"Befehl nicht ausgeführt: {type(e).__name__}\n{e}"


def from_engine(res: dict, sender: str, source: str) -> str:
    """Engine result (plain text or voice) -> draft card, or a question back. Never sends anything."""
    asr = res.get("asr") or {}
    meta = {"input": source, "engine": res.get("version"), "llm": (res.get("models") or {}).get("llm"),
            "asr": asr.get("model"), "audio_sha256": asr.get("audio_sha256"), "ready": bool(res.get("ready")),
            "missing": res.get("missing", []), "flags": len(res.get("flags", [])), "timings_ms": res.get("timings_ms")}
    heard = (res.get("input") or {}).get("normalized") or asr.get("text") or ""
    flags = [f"⚠️ {f}" for f in res.get("flags", [])]
    if source == "voice" and res.get("contact"):     # speech-to-text gets addresses/numbers wrong (eval/VOICE.md)
        flags.append("⚠️ Kontakt aus Sprachnachricht erkannt: bitte Adresse/Nummer vor dem Senden Zeichen für Zeichen prüfen")
    patient = res.get("patient") or {}
    if not res.get("ready"):
        audit.log("request_parsed", None, sender, meta)
        lines = ["Anfrage noch nicht vollständig", f"Verstanden: „{heard}“", res.get("ask_de") or "Bitte genauer angeben."]
        if patient.get("status") == "ambiguous":
            lines += [f"• {c['ref']}: {c['name']}, geb. {_dob(c['dob'])}" for c in patient.get("candidates", [])[:3]]
        return "\n".join(lines + flags)
    req = requests_service.draft(doc_kind=res["doc_type"], expected_name=res["recipient"], contact=res["contact"]["value"],
                                 patient_ref=patient["ref"], reason=res.get("reason") or "",
                                 panel_loinc=(res.get("panel") or {}).get("loinc", []), source=source)
    audit.log("request_parsed", req["id"], sender, meta)
    card = draft_card(req).split("\n")
    return "\n".join(card[:-1] + flags + [f"Verstanden aus: „{heard}“", card[-1]])


def handle(text: str, sender: str) -> str:
    if sender not in settings.authorized_senders:
        return ("Keine Berechtigung\nAnfragen dürfen nur Mitglieder des Klinik-Verzeichnisses stellen. "
                "Diese Nachricht wurde nicht verarbeitet.")
    text = text.strip()
    cmd, _, arg = text.partition(" ")
    arg = arg.strip()
    try:
        if not text.startswith("!"):
            return from_engine(engine_client.request_text(text), sender, "text")
        if cmd == "!anfrage":
            return draft_card(requests_service.draft(**parse_anfrage(text)))
        if cmd == "!senden":
            return sent_card(requests_service.send(arg, actor=sender))
        if cmd == "!ablegen":
            return intake_service.confirm_review(arg, actor=sender, file_it=True)
        if cmd == "!verwerfen":
            return intake_service.confirm_review(arg, actor=sender, file_it=False)
        if cmd == "!status":
            req = db.get("requests", "id", arg)
            if not req:
                return f"Anfrage {arg} nicht gefunden\nAlle Befehle: !hilfe"
            return f"Anfrage {req['id']}: {STATUS_LABEL.get(req['status'], req['status'])}\nAn: {req['expected_name']}"
        return HELP
    except Exception as e:  # the doctor sees the error in the room instead of silence
        return _error(e)
