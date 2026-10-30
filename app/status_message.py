"""One living card per request in the Matrix room, plus a one-line ping only when Dr. Hofer has to look. Owner: SWE 1.

The bot's answer to `!anfrage` is the card. It is edited in place as the request moves (sent, opened, identity,
answer, filed), so the room gets no message per step. A new message appears only when something is done (✅),
needs a decision (🔍, with ✅/❌ buttons) or went wrong (⚠️/⛔). Acknowledgements of Dr. Hofer's own actions are
not posted: the card already shows them. The steps are the dashboard's (app/dashboard.py), from the audit log.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app import audit, dashboard, db
from app.config import settings

TZ = ZoneInfo("Europe/Vienna")
PHASE = {
    "sent": "Gesendet – wartet, bis der Link geöffnet wird",
    "opened": "Link geöffnet – wartet auf ID Austria",
    "identified": "Identität bestätigt – wartet auf das Dokument",
    "answered": "Dokument eingegangen – wird geprüft",
    "filed": "Abgelegt",
    "review": "Zuordnung unsicher – bitte prüfen",
    "rejected": "Nicht abgelegt – Dokument betrifft anderen Patienten",
    "discarded": "Verworfen",
    "blocked": "Gesperrt – zu viele Fehlversuche",
}
VIA = {"email": "E-Mail", "sms": "SMS"}
# notify-outbox messages the card and its pings replace (texts from core/intake.py, app/main.py, intake_service)
REPLACED = ("✅ Antwort", "🔍 ", "⚠️ Fehlzustellung", "⚠️ Antwort NICHT abgelegt: Das übermittelte")
_DRAFTED = re.compile(r"^Anfrage (\w+): Entwurf")
_CMD = re.compile(r"^!(senden|ablegen|verwerfen) (\w+)")


def _time(ts: str) -> str:
    return datetime.fromisoformat(ts).astimezone(TZ).strftime("%H:%M")


def _dob(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except ValueError:
        return iso


def _card(request_id: str) -> tuple[dict, dict]:
    req = db.get("requests", "id", request_id)
    return req, dashboard.card(req, audit.entries(request_id))


def text(req: dict, card: dict, checks: list[str] | None = None) -> str:
    """`checks`: the draft reply's own warning lines (address lint, engine flags, what the engine heard)."""
    head = f"{card['doc']} · {card['patient']}"
    if req["status"] == "draft":
        lines = [f"{head}, geb. {_dob(req['patient_dob'])}", f"an {req['expected_name']} · {req['contact']}"]
        lines += checks if checks is not None else [f"⚠️ Kontakt prüfen: {w}" for w in json.loads(req["lint_warnings"] or "[]")]
        return "\n".join(lines + [f"✅ tippen zum Senden · Anfrage {req['id']}"])
    dots = "".join("●" if s["state"] == "done" else "○" for s in card["steps"])
    last = max((s["ts"] for s in card["steps"] if s["ts"]), default=None)
    lines = [head, f"an {req['expected_name']} · {VIA.get(req['contact_kind'], req['contact_kind'])}",
             f"{dots}  {PHASE.get(req['status'], req['status'])}" + (f" · {_time(last)}" if last else "")]
    if req["status"] == "filed":
        lines += _result(req)
    return "\n".join(lines + [f"⚠️ {a}" for a in card["alerts"]])


def _result(req: dict) -> list[str]:
    rows = db.query("SELECT * FROM answers WHERE request_id = ? AND filed_refs != '[]' ORDER BY received_at DESC", (req["id"],))
    if not rows:
        return []
    summary = json.loads(rows[0]["intake_json"]).get("summary") or []
    refs = json.loads(rows[0]["filed_refs"])
    main = next((r for t in ("DiagnosticReport", "DocumentReference") for r in refs if r.startswith(t + "/")), None)
    out = [" · ".join(summary)] if summary else []
    if main:
        out.append(f"[Befund öffnen]({settings.hapi_public_url}/{main})")
    return out


def card_text(request_id: str, reply: str | None = None) -> str:
    """The card; for a draft, `reply` (commands' draft answer) supplies the warning lines to keep."""
    checks = [line for line in reply.split("\n") if line.startswith(("⚠️", "Verstanden aus"))] if reply else None
    return text(*_card(request_id), checks)


def drafted(reply: str) -> str | None:
    """The request id if `reply` is the draft answer to `!anfrage`."""
    m = _DRAFTED.match(reply)
    return m.group(1) if m else None


def has_card(request_id: str | None) -> bool:
    return bool(request_id) and db.get("matrix_cards", "request_id", request_id) is not None


def is_ack(command: str, reply: str) -> bool:
    """True if `reply` only confirms what the card now shows (a successful !senden / !ablegen / !verwerfen)."""
    m = _CMD.match(command.strip())
    if not m or not has_card(m.group(2)):
        return False
    verb, rid = m.groups()
    return {"senden": reply.startswith(f"Anfrage {rid} gesendet"), "ablegen": reply.startswith("Abgelegt:"),
            "verwerfen": reply == f"Antwort {rid} verworfen."}[verb]


def replaced(notify_text: str, request_id: str | None) -> bool:
    return has_card(request_id) and notify_text.startswith(REPLACED)


def updates(since: str) -> list[tuple[str | None, str, str]]:
    """(event_id or None for a new card, request_id, text) for every card that must change. A request sent from
    outside Matrix (CLI) gets a new card once sent; requests sent before `since` (the bot's start) get none."""
    known = {r["request_id"]: r for r in db.query("SELECT * FROM matrix_cards")}
    reqs = {r["id"]: r for r in db.query("SELECT * FROM requests")}
    out = []
    for card in dashboard.cards():
        row, sent = known.get(card["id"]), card["steps"][0]["ts"]
        if card["status"] == "draft" or (not row and not (sent and sent >= since)):
            continue                                    # a draft card only changes once it is sent
        new = text(reqs[card["id"]], card)
        if row and row["text"] != new:
            out.append((row["event_id"], card["id"], new))
        elif not row:
            out.append((None, card["id"], new))
    return out


def saved(request_id: str, event_id: str, text_now: str) -> None:
    if db.get("matrix_cards", "request_id", request_id):
        db.update("matrix_cards", "request_id", request_id, text=text_now)
    else:
        db.insert("matrix_cards", {"request_id": request_id, "event_id": event_id, "text": text_now})


def pings() -> list[tuple[str, str, dict[str, str], int]]:
    """(request_id, one-line text, buttons, audit seq) for each event since the last ping that needs Dr. Hofer."""
    out = []
    for row in db.query("SELECT * FROM matrix_cards"):
        req = db.get("requests", "id", row["request_id"])
        head = f"{dashboard.DOC.get(req['doc_type'], req['doc_type'])} · {req['patient_name']}"
        decided = False
        for ev in audit.entries(row["request_id"]):
            decided = decided or ev["event"] == "review_decided"
            if ev["seq"] <= row["last_seq"]:
                continue
            d, rid = ev["details"], req["id"]
            if ev["event"] == "review_requested":
                out.append((rid, f"🔍 {head}: Zuordnung unsicher. Ablegen oder verwerfen?",
                            {"✅": f"!ablegen {rid}", "❌": f"!verwerfen {rid}"}, ev["seq"]))
            elif ev["event"] == "answer_filed" and not decided:      # after a review she tapped it herself
                out.append((rid, f"✅ {head} ist da.", {}, ev["seq"]))
            elif ev["event"] == "misdelivery_caught" and d.get("type") == "M3":
                out.append((rid, f"⛔ {head}: Dokument betrifft anderen Patienten. Nicht abgelegt.", {}, ev["seq"]))
            elif ev["event"] == "misdelivery_caught":
                out.append((rid, f"⚠️ {head}: {d.get('verified', 'Unbekannt')} hat den Link geöffnet, nicht "
                                 f"{d.get('expected', 'die angefragte Person')}. Nichts offengelegt.", {}, ev["seq"]))
    return out


def pinged(request_id: str, seq: int) -> None:
    db.update("matrix_cards", "request_id", request_id, last_seq=seq)
