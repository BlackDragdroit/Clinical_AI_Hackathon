"""Clinic dashboard: shows patient data only with the widget's signed key; steps follow the audit log."""
from __future__ import annotations

import asyncio
import json
import re

from fastapi.testclient import TestClient

from app import commands, dashboard
from app.config import settings
from app.main import app
from app.security import sign
from tests.conftest import REQ1, link_path
from tests.test_flow import _answer, _send


def _card(rid: str) -> dict:
    return next(c for c in dashboard.snapshot()["cards"] if c["id"] == rid)


def _states(rid: str) -> list[str]:
    return [s["state"] for s in _card(rid)["steps"]]


def test_widget_key_shows_requests(hapi, outbox):
    commands.handle(REQ1, settings.doctor_mxid)
    url = dashboard.widget_url()
    assert url.startswith(f"{settings.base_url}/dashboard?k=")
    with TestClient(app) as client:
        # Element appends its own widget parameters to the URL
        r = client.get(url.removeprefix(settings.base_url) + "&widgetId=bb-dashboard&parentUrl=x")
    assert r.status_code == 200
    assert "Maria Beispiel" in r.text


def test_no_or_wrong_key_reveals_nothing(hapi, outbox):
    commands.handle(REQ1, settings.doctor_mxid)
    portal_cookie_key = sign({}, "portal", 3600)        # a valid signature for another purpose is not enough
    with TestClient(app) as client:
        for page in ("/dashboard", "/dashboard/events"):
            for k in ("", "?k=", "?k=abc.def", f"?k={portal_cookie_key}"):
                r = client.get(page + k)
                assert r.status_code == 404, page + k
                assert "Maria" not in r.text


def test_draft_then_sent(hapi, outbox):
    rid = re.search(r"Anfrage (\w+)", commands.handle(REQ1, settings.doctor_mxid)).group(1)
    assert _states(rid) == ["todo"] * 5 and _card(rid)["hint"] == f"!senden {rid}"
    commands.handle(f"!senden {rid}", settings.doctor_mxid)
    assert _states(rid) == ["done", "current", "todo", "todo", "todo"]
    assert _card(rid)["steps"][0]["ts"]


def test_happy_path_all_steps_done(hapi, outbox):
    rid = _send(REQ1)
    with TestClient(app) as client:
        _answer(client, link_path(outbox[0]["link"]), "eva", "lab-result-maria-beispiel.md")
    c = _card(rid)
    assert _states(rid) == ["done"] * 5 and c["tone"] == "ok" and not c["alerts"]
    assert all(s["ts"] for s in c["steps"])


def test_forwarded_link_marks_identity_and_alerts(hapi, outbox):
    rid = _send(REQ1)
    with TestClient(app) as client:
        _answer(client, link_path(outbox[0]["link"]), "karl", "lab-result-maria-beispiel.md")
    c = _card(rid)
    assert _states(rid) == ["done", "done", "error", "todo", "todo"]   # nothing after identity is "current"
    assert c["tone"] == "error" and "Karl Kollege" in c["alerts"][0] and "Dr. Eva Brandl" in c["alerts"][0]


def test_wrong_patient_quarantined(hapi, outbox):
    rid = _send(REQ1)
    with TestClient(app) as client:
        _answer(client, link_path(outbox[0]["link"]), "eva", "lab-result-max-beispiel.md",
                typed=("Max Beispiel", "01.01.1960"))
    c = _card(rid)
    assert _states(rid) == ["done", "done", "done", "done", "error"]
    assert c["steps"][4]["label"] == "Quarantäne" and c["tone"] == "error"
    assert "Max" not in str(c)                          # the other patient never reaches the dashboard


def test_events_stream_sends_snapshot(hapi, outbox, monkeypatch):
    commands.handle(REQ1, settings.doctor_mxid)
    monkeypatch.setattr(dashboard, "POLL_S", 0)

    class Once:                                         # the client disconnects after the first snapshot
        calls = 0

        async def is_disconnected(self):
            Once.calls += 1
            return Once.calls > 1

    async def collect():
        resp = await dashboard.events(Once(), k=sign({}, dashboard.PURPOSE, 60))
        return [chunk async for chunk in resp.body_iterator]
    chunks = asyncio.run(collect())
    assert len(chunks) == 1 and chunks[0].startswith("data: ") and "Maria Beispiel" in chunks[0]


def test_dashboard_requires_signed_key():
    """GET /dashboard without a valid ?k= returns 404 (not found / no data exposed)."""
    with TestClient(app) as client:
        r_no_key = client.get("/dashboard")
        r_empty_key = client.get("/dashboard?k=")
        r_bad_key = client.get("/dashboard?k=abc.def.ghi")
    assert r_no_key.status_code == 404
    assert r_empty_key.status_code == 404
    assert r_bad_key.status_code == 404


def test_dashboard_events_streams_json():
    """GET /dashboard/events with a valid key returns text/event-stream content-type."""
    k = sign({}, dashboard.PURPOSE, 60)
    with TestClient(app) as client:
        r = client.get(f"/dashboard/events?k={k}", headers={"Accept": "text/event-stream"})
    # StreamingResponse returns 200 with the right media type
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")


def test_dashboard_doc_labels():
    """DOC dict maps 'lab' → German label and 'report' → German label."""
    assert dashboard.DOC.get("lab") == "Laborbefund"
    assert dashboard.DOC.get("report") == "Entlassungsbericht"
