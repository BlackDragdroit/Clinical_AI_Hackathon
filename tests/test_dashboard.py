"""Clinic dashboard: shows patient data only with the widget's signed key."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import commands, dashboard
from app.config import settings
from app.main import app
from app.security import sign
from tests.conftest import REQ1


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
        for path in ("/dashboard", "/dashboard?k=", "/dashboard?k=abc.def", f"/dashboard?k={portal_cookie_key}"):
            r = client.get(path)
            assert r.status_code == 404, path
            assert "Maria" not in r.text
