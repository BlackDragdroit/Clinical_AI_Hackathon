"""Clinic-side dashboard, shown inside Dr. Hofer's Matrix room as an Element widget. Owner: SWE 1.

It shows patient data, so it is never reachable through the portal's link flow: every request needs the
signed key `k` that only the room's widget URL carries (`python -m app.dashboard` prints that URL;
scripts/setup_synapse.sh pins it into the room).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from app import db
from app.config import settings
from app.security import sign, unsign

PURPOSE = "dashboard"
KEY_TTL_S = 30 * 24 * 3600          # re-running setup_synapse.sh issues a fresh key

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def widget_url() -> str:
    return f"{settings.base_url}/dashboard?k={sign({}, PURPOSE, KEY_TTL_S)}"


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, k: str = ""):
    if unsign(k, PURPOSE) is None:
        return PlainTextResponse("Not found", 404)
    rows = db.query("SELECT * FROM requests ORDER BY created_at DESC")
    return templates.TemplateResponse(request, "dashboard.html", {"clinic": settings.clinic_name, "requests": rows})


if __name__ == "__main__":
    print(widget_url())
