"""One living card per request in the Matrix room, plus a one-line ping only when Dr. Hofer has to look. Owner: SWE 1.

The bot's answer to `!anfrage` is the card. It is edited in place as the request moves (sent, opened, identity,
answer, filed), so the room gets no message per step. A new message appears only when something is done (✅),
needs a decision (🔍, with Ablegen/Verwerfen buttons) or went wrong (⚠️/⛔). Acknowledgements of Dr. Hofer's own
actions are not posted: the card already shows them. The steps are the dashboard's (app/dashboard.py), from the
audit log.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app import audit, dashboard, db, reactions
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
# a request written or spoken in English gets its card and pings in English (requests.lang)
PHASE_EN = {
    "sent": "Sent – waiting for the link to be opened",
    "opened": "Link opened – waiting for ID Austria",
    "identified": "Identity confirmed – waiting for the document",
    "answered": "Document received – being checked",
    "filed": "Filed",
    "review": "Match uncertain – please review",
    "rejected": "Not filed – document is about another patient",
    "discarded": "Discarded",
    "blocked": "Blocked – too many failed attempts",
}
VIA_EN = {"email": "email", "sms": "SMS"}
DOC_EN = {"lab": "Lab result", "report": "Discharge report"}
_ALERT_EN = ((re.compile(r"^Dokument betrifft anderen Patienten: in Quarantäne, nichts abgelegt\.$"),
              "Document is about another patient: quarantined, nothing filed."),
             (re.compile(r"^(.*) hat den Link geöffnet, nicht (.*)\. Nichts offengelegt\.$"), r"\1 opened the link, not \2. Nothing shown."))


def _en(req: dict) -> bool:
    return (req.get("lang") or "de") == "en"


def _alert(req: dict, text: str) -> str:
    if _en(req):
        for pattern, english in _ALERT_EN:
            if pattern.match(text):
                return pattern.sub(english, text)
    return text
# notify-outbox messages the card and its pings replace (texts from core/intake.py, app/main.py, intake_service)
REPLACED = ("✅ Antwort", "🔍 ", "⚠️ Fehlzustellung", "⚠️ Antwort NICHT abgelegt: Das übermittelte")
_DRAFTED = re.compile(r"^Anfrage (\w+): Entwurf")
_CMD = re.compile(r"^!(senden|ablegen|verwerfen) (\w+)")
REVIEW_Q = "Zuordnung unsicher. Ablegen oder verwerfen?"


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
    en = _en(req)
    head = f"{DOC_EN.get(req['doc_type'], card['doc']) if en else card['doc']} · {card['patient']}"
    to = "to" if en else "an"
    if req["status"] == "draft":
        lines = [f"{head}, {'born' if en else 'geb.'} {_dob(req['patient_dob'])}", f"{to} {req['expected_name']} · {req['contact']}"]
        lines += checks if checks is not None else [f"⚠️ {'Check contact' if en else 'Kontakt prüfen'}: {w}"
                                                    for w in json.loads(req["lint_warnings"] or "[]")]
        last_line = (f"Tap „{reactions.SENDEN}“ · Request {req['id']}" if en
                     else f"„{reactions.SENDEN}“ tippen · Anfrage {req['id']}")
        return "\n".join(lines + [last_line])
    dots = "".join("●" if s["state"] == "done" else "○" for s in card["steps"])
    last = max((s["ts"] for s in card["steps"] if s["ts"]), default=None)
    phase = (PHASE_EN if en else PHASE).get(req["status"], req["status"])
    if req["status"] == "review" and not any(e["event"] == "review_requested" for e in audit.entries(req["id"])):
        phase = (f"Not filed – FHIR validation failed · retry: !ablegen {req['id']}" if en
                 else f"Nicht abgelegt – FHIR-Prüfung fehlgeschlagen · erneut prüfen: !ablegen {req['id']}")
    elif req["status"] in ("sent", "opened") and card["steps"][2]["state"] == "error":   # failed identity check
        phase = (f"Wrong person – still waiting for {req['expected_name']}" if en
                 else f"Falsche Person – wartet weiter auf {req['expected_name']}")
    via = (VIA_EN if en else VIA).get(req["contact_kind"], req["contact_kind"])
    lines = [head, f"{to} {req['expected_name']} · {via}", f"{dots}  {phase}" + (f" · {_time(last)}" if last else "")]
    if req["status"] == "filed":
        lines += _result(req)
    return "\n".join(lines + [f"⚠️ {_alert(req, a)}" for a in card["alerts"]])


def _result(req: dict, en: bool | None = None) -> list[str]:
    rows = db.query("SELECT * FROM answers WHERE request_id = ? AND filed_refs != '[]' ORDER BY received_at DESC", (req["id"],))
    if not rows:
        return []
    summary = json.loads(rows[0]["intake_json"]).get("summary") or []
    refs = json.loads(rows[0]["filed_refs"])
    main = next((r for t in ("DiagnosticReport", "DocumentReference") for r in refs if r.startswith(t + "/")), None)
    out = [" · ".join(summary)] if summary and req["doc_type"] == "lab" else []   # a report is read in full, not here
    if main:
        out.append(f"[{'Open result' if (_en(req) if en is None else en) else 'Befund öffnen'}]({settings.hapi_public_url}/{main})")
    return out


def card_text(request_id: str, reply: str | None = None) -> str:
    """The card; for a draft, `reply` (commands' draft answer) supplies the warning lines to keep."""
    checks = [line for line in reply.split("\n") if line.startswith(("⚠️", "Verstanden aus", "Understood from"))] if reply else None
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


def _head(req: dict, en: bool | None = None) -> str:
    doc = (DOC_EN if (_en(req) if en is None else en) else dashboard.DOC).get(req["doc_type"], req["doc_type"])
    return f"{doc} · {req['patient_name']}"


def recent(en: bool, n: int = 3) -> str:
    """For a chat message that is no request ("Wo ist der Befund?"): the latest requests, filed ones with their values
    and a link, in the language of the question."""
    reqs = db.query("SELECT * FROM requests WHERE status != 'draft' ORDER BY created_at DESC LIMIT ?", (n,))
    lines = ["No new request recognised. Latest:" if en else "Keine neue Anfrage erkannt. Zuletzt:"]
    for req in reqs:
        steps = dashboard.card(req, audit.entries(req["id"]))["steps"]
        last = max((s["ts"] for s in steps if s["ts"]), default=None)
        phase = (PHASE_EN if en else PHASE).get(req["status"], req["status"]).split(" – ")[0]
        line = f"{_head(req, en)} – {phase}" + (f" · {_time(last)}" if last else "")
        result = _result(req, en) if req["status"] == "filed" else []
        lines.append(line + (": " + " · ".join(result) if result else ""))
    return "\n".join(lines if reqs else lines[:1] + ["–"])


def card_event(request_id: str) -> str | None:
    """The card's event id: pings are posted as replies to it, so Element shows which request they are about."""
    row = db.get("matrix_cards", "request_id", request_id)
    return row["event_id"] if row else None


def pings() -> list[tuple[str, str, dict[str, str], int]]:
    """(request_id, one-line text, buttons, audit seq) for each event since the last ping that needs Dr. Hofer."""
    out = []
    for row in db.query("SELECT * FROM matrix_cards"):
        req = db.get("requests", "id", row["request_id"])
        head, en = _head(req), _en(req)
        decided = False
        for ev in audit.entries(row["request_id"]):
            decided = decided or ev["event"] == "review_decided"
            if ev["seq"] <= row["last_seq"]:
                continue
            d, rid = ev["details"], req["id"]
            if ev["event"] == "review_requested":
                out.append((rid, f"🔍 {head}: {'Match uncertain. File or discard?' if en else REVIEW_Q}",
                            {reactions.ABLEGEN: f"!ablegen {rid}", reactions.VERWERFEN: f"!verwerfen {rid}"}, ev["seq"]))
            elif ev["event"] == "answer_filed" and not decided:      # after a review she tapped it herself
                result = " · ".join(_result(req))     # the values and where to open it, so nobody has to ask
                out.append((rid, f"✅ {head} {'has arrived' if en else 'ist da'}" + (f": {result}" if result else "."),
                            {}, ev["seq"]))
            elif ev["event"] == "misdelivery_caught" and d.get("type") == "M3":
                out.append((rid, f"⛔ {head}: Document is about another patient. Not filed. Link used up – send a new "
                                 f"request for the right document." if en else
                                 f"⛔ {head}: Dokument betrifft anderen Patienten. Nicht abgelegt. "
                                 f"Link verbraucht – für das richtige Dokument neue Anfrage stellen.", {}, ev["seq"]))
            elif ev["event"] == "misdelivery_caught":
                who, expected = d.get("verified", "Unknown" if en else "Unbekannt"), d.get("expected", "")
                out.append((rid, f"⚠️ {head}: {who} opened the link, not {expected or 'the requested person'}. Nothing shown."
                                 if en else f"⚠️ {head}: {who} hat den Link geöffnet, nicht "
                                 f"{expected or 'die angefragte Person'}. Nichts offengelegt.", {}, ev["seq"]))
    return out


def decided(command: str) -> list[tuple[str, str]]:
    """After a successful !ablegen / !verwerfen: (event_id, new text) for the 🔍 ping it answered, so the ping
    itself shows the outcome where Dr. Hofer tapped."""
    m = _CMD.match(command.strip())
    if not m or m.group(1) == "senden" or not (req := db.get("requests", "id", m.group(2))):
        return []
    if _en(req):
        text = f"🔍 {_head(req)}: Match uncertain → {'filed' if m.group(1) == 'ablegen' else 'discarded'} · {_time(db.now())}"
    else:
        outcome = "abgelegt" if m.group(1) == "ablegen" else "verworfen"
        text = f"🔍 {_head(req)}: Zuordnung unsicher → {outcome} · {_time(db.now())}"
    rows = db.query("SELECT DISTINCT event_id FROM matrix_actions WHERE command = ?", (f"!ablegen {req['id']}",))
    return [(r["event_id"], text) for r in rows]


def pinged(request_id: str, seq: int) -> None:
    db.update("matrix_cards", "request_id", request_id, last_seq=seq)
