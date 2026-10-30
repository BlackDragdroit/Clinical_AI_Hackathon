"""Clinic-side dashboard, shown inside Dr. Hofer's Matrix room as an Element widget. Owner: SWE 1.

It shows patient data, so it is never reachable through the portal's link flow: every request needs the
signed key `k` that only the room's widget URL carries (`python -m app.dashboard` prints that URL;
scripts/setup_synapse.sh pins it into the room).

Each request is a card with five steps taken from the audit log (sent, opened, identity, answer, filed).
`/dashboard/events` pushes a new snapshot over Server-Sent Events whenever anything changes, and the page
animates the difference.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app import audit, db
from app.config import settings
from app.security import sign, unsign

PURPOSE = "dashboard"
KEY_TTL_S = 30 * 24 * 3600          # re-running setup_synapse.sh issues a fresh key
POLL_S = 1.0
PING_EVERY = 15                     # polls between keep-alive comments

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

DOC = {"lab": "Laborbefund", "report": "Entlassungsbericht"}
# (key, label, audit event that completes the step)
STEPS = (("sent", "Gesendet", "request_sent"), ("opened", "Geöffnet", "link_opened"),
         ("identity", "Identität", "identity_checked"), ("answered", "Antwort", "answer_sent"),
         ("filed", "Abgelegt", "answer_filed"))
# end states that replace the last open step: (step, state, label, card tone)
ENDS = {"review": ("filed", "warn", "Prüfung", "warn"), "rejected": ("filed", "error", "Quarantäne", "error"),
        "discarded": ("filed", "error", "Verworfen", "muted"), "blocked": ("identity", "error", "Gesperrt", "error")}


def widget_url() -> str:
    return f"{settings.base_url}/dashboard?k={sign({}, PURPOSE, KEY_TTL_S)}"


def _alert(ev: dict) -> str:
    d = ev["details"]
    if d.get("type") == "M3":
        return "Dokument betrifft anderen Patienten: in Quarantäne, nichts abgelegt."
    return (f"{d.get('verified', 'Unbekannt')} hat den Link geöffnet, nicht {d.get('expected', 'die angefragte Person')}."
            " Nichts offengelegt.")


def card(req: dict, events: list[dict]) -> dict:
    done: dict[str, str] = {}
    failed_identity = False
    for ev in events:
        if ev["event"] == "identity_checked" and ev["details"].get("result") != "OK":
            failed_identity = True
            continue
        for key, _, event in STEPS:
            if ev["event"] == event:
                done.setdefault(key, ev["ts"])
    status = req["status"]
    end = ENDS.get(status)
    steps, waiting = [], status not in ("draft", "filed") and not end
    for key, label, _ in STEPS:
        step = {"key": key, "label": label, "ts": done.get(key), "state": "done" if key in done else "todo"}
        if end and key == end[0] and key not in done:
            step.update(state=end[1], label=end[2])
        elif key == "identity" and failed_identity and key not in done:
            step["state"], waiting = "error", False     # still waiting here, for the right person
        elif waiting and step["state"] == "todo":
            step["state"], waiting = "current", False
        steps.append(step)
    tone = end[3] if end else {"draft": "draft", "filed": "ok"}.get(status, "active")
    alerts = [_alert(ev) for ev in events if ev["event"] == "misdelivery_caught"]
    if alerts and tone == "active":
        tone = "error"
    hint = {"draft": f"!senden {req['id']}", "review": f"!ablegen {req['id']} / !verwerfen {req['id']}"}.get(status, "")
    return {"id": req["id"], "doc": DOC.get(req["doc_type"], req["doc_type"]), "patient": req["patient_name"],
            "to": req["expected_name"], "via": req["contact_kind"], "reason": req["reason"], "status": status,
            "source": req.get("source") or "command",
            "created": req["created_at"], "tone": tone, "steps": steps, "alerts": alerts, "hint": hint}


def cards() -> list[dict]:
    by_req: dict[str, list[dict]] = {}
    for ev in audit.entries():
        if ev["request_id"]:
            by_req.setdefault(ev["request_id"], []).append(ev)
    return [card(r, by_req.get(r["id"], [])) for r in db.query("SELECT * FROM requests ORDER BY created_at DESC")]


def snapshot() -> dict:
    cards_now = cards()
    counts = {t: sum(1 for c in cards_now if c["tone"] == t) for t in ("active", "ok", "warn", "error")}
    return {"cards": cards_now, "counts": counts, "chain_ok": audit.verify_chain()}


def _authorized(k: str) -> bool:
    return unsign(k, PURPOSE) is not None


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, k: str = ""):
    if not _authorized(k):
        return PlainTextResponse("Not found", 404)
    return templates.TemplateResponse(request, "dashboard.html", {"clinic": settings.clinic_name, "snap": snapshot()})


@router.get("/dashboard/events")
async def events(request: Request, k: str = ""):
    if not _authorized(k):
        return PlainTextResponse("Not found", 404)

    async def stream():
        last, idle = None, 0
        while not await request.is_disconnected():
            snap = json.dumps(await asyncio.to_thread(snapshot), ensure_ascii=False)
            if snap != last:
                last, idle = snap, 0
                yield f"data: {snap}\n\n"
            elif idle >= PING_EVERY:
                idle = 0
                yield ": ping\n\n"
            await asyncio.sleep(POLL_S)
            idle += 1

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    print(widget_url())
