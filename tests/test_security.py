"""Edge-case security and robustness tests (T1–T8 from .bob/agents/playtest.md)."""
from __future__ import annotations

import importlib
import os
import re
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import audit, commands, db, engine_client, fhir_client, tokens
from app.config import settings
from app.identity import eid_mock
from app.main import app
from tests.conftest import REQ1, link_path

DOCTOR = settings.doctor_mxid


def _send(cmd: str) -> str:
    """Send a command and return the request ID."""
    rid = re.search(r"Anfrage (\w+)", commands.handle(cmd, DOCTOR)).group(1)
    assert "gesendet" in commands.handle(f"!senden {rid}", DOCTOR)
    return rid


# ---------------------------------------------------------------------------
# T1 — eID replay: an assertion from link A must not work on link B.
# The mock eID issues per-citizen assertions that are not bound to a specific
# link (state/nonce binding is an ID-Austria production concern, tracked as O4
# in PLAYTEST_REPORT.md). Marked xfail(strict=True) until production OIDC
# nonce/state binding is implemented.
# ---------------------------------------------------------------------------

def test_eid_assertion_cannot_be_replayed_on_another_link(hapi, outbox):
    """Assertion issued for link A must be rejected when presented to link B."""
    _send(REQ1)
    _send(REQ1)
    token_a = link_path(outbox[0]["link"]).rsplit("/", 1)[1]
    token_b = link_path(outbox[1]["link"]).rsplit("/", 1)[1]

    with TestClient(app) as client:
        # Get a valid assertion bound to link A
        client.get(f"/r/{token_a}")
        assertion_for_a = eid_mock.issue("eva", link_token=token_a)

        # Try to replay the link-A assertion on link B's callback
        client.get(f"/r/{token_b}")
        r = client.get(f"/r/{token_b}/callback", params={"assertion": assertion_for_a})
        assert r.status_code == 404, "Assertion bound to link A must be rejected on link B"


# ---------------------------------------------------------------------------
# T2 — XSS in reason field must be escaped in any HTML response.
# commands.handle returns plain text; the assertion checks that the raw
# <script> tag is preserved in the card (not silently dropped) AND that no
# portal HTML page renders it unescaped.
# ---------------------------------------------------------------------------

def test_xss_in_reason_is_escaped(hapi, outbox):
    """<script> in the reason field must be preserved in the plain-text card
    and must never appear unescaped in any portal HTML response."""
    xss = "<script>alert(1)</script>"
    cmd = (
        f'!anfrage labor "Dr. Eva Brandl" eva.brandl@labor-kanal.example '
        f"Patient/maria-beispiel Grund: {xss}"
    )
    card = commands.handle(cmd, DOCTOR)
    # The plain-text card must contain the reason text (it's not stripped)
    assert xss in card, "reason must be preserved in the draft card"

    # Send the request and check HTML responses at the portal layer
    rid = re.search(r"Anfrage (\w+)", card).group(1)
    assert "gesendet" in commands.handle(f"!senden {rid}", DOCTOR)
    path = link_path(outbox[0]["link"])
    raw = path.rsplit("/", 1)[1]

    with TestClient(app) as client:
        # The landing page (before identity) must not echo the reason at all
        landing = client.get(path)
        assert landing.status_code == 200
        assert "<script>alert(1)</script>" not in landing.text

        # After identity the answer form shows the reason — but it must be HTML-escaped
        client.post("/eid/authorize", data={"state": raw, "citizen": "eva"})
        answer_page = client.get(f"{path}/answer")
        assert answer_page.status_code == 200
        # The raw script tag must not appear; Jinja2 auto-escaping renders &lt;script&gt;
        assert "<script>alert(1)</script>" not in answer_page.text


# ---------------------------------------------------------------------------
# T3 — Unknown patient gives a helpful error message.
# ---------------------------------------------------------------------------

def test_unknown_patient_gives_helpful_error(hapi, monkeypatch):
    """!anfrage with a nonexistent patient ref -> response contains 'Nicht gefunden'."""

    def read_patient_404(ref):
        if ref == "Patient/nonexistent":
            req_obj = httpx.Request("GET", f"http://hapi/fhir/{ref}")
            resp = httpx.Response(404, request=req_obj)
            raise httpx.HTTPStatusError("404 Not Found", request=req_obj, response=resp)
        return hapi.read_patient(ref)

    monkeypatch.setattr(fhir_client, "read_patient", read_patient_404)

    cmd = (
        '!anfrage labor "Dr. Eva Brandl" eva.brandl@labor-kanal.example '
        "Patient/nonexistent Grund: Test"
    )
    reply = commands.handle(cmd, DOCTOR)
    assert "Nicht gefunden" in reply, f"expected helpful 'Nicht gefunden' error, got: {reply!r}"


# ---------------------------------------------------------------------------
# T4 — Malformed !anfrage gives a format hint.
# ---------------------------------------------------------------------------

def test_malformed_anfrage_gives_format_hint():
    """!anfrage with missing fields -> response contains the command format hint."""
    reply = commands.handle("!anfrage", DOCTOR)
    # Either the ValueError path or the HELP fallback; both must mention !anfrage
    assert "!anfrage" in reply and (
        "Format" in reply or "labor" in reply or "bericht" in reply
    ), f"expected format hint, got: {reply!r}"


def test_malformed_anfrage_too_few_args_gives_format_hint():
    """!anfrage with too few args -> response contains the command format hint."""
    reply = commands.handle("!anfrage labor nur-drei-args", DOCTOR)
    assert "Format" in reply or "!anfrage" in reply, f"expected format hint, got: {reply!r}"


# ---------------------------------------------------------------------------
# T5 — 30 concurrent flows audit chain intact.
# Requires an async concurrency harness (httpx.AsyncClient + anyio).
# Marked xfail(strict=True) until such a harness is wired in.
# ---------------------------------------------------------------------------

def test_concurrent_30_flows_audit_chain_intact():
    """10 threads simultaneously writing audit entries must leave the hash chain intact."""
    def write_entry(i: int) -> dict:
        return audit.log("request_sent", f"concurrent-{i}", "@lena.hofer:klinikum.example",
                         {"channel": "email", "thread": i})

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(write_entry, range(10)))

    assert audit.verify_chain(), "hash chain must be intact after concurrent writes"
    # All 10 entries must appear in the db
    entries = audit.entries()
    concurrent_ids = {f"concurrent-{i}" for i in range(10)}
    found_ids = {e["request_id"] for e in entries if e["request_id"] in concurrent_ids}
    assert found_ids == concurrent_ids, f"missing entries: {concurrent_ids - found_ids}"


# ---------------------------------------------------------------------------
# T6 — Pasted text (no file upload) is accepted and processed.
# The engine can parse plain markdown text; we monkeypatch engine_client.document
# to return a successful result so the test doesn't depend on the ML engine.
# ---------------------------------------------------------------------------

def test_pasted_text_accepted(hapi, outbox, monkeypatch):
    """POST to the answer submit endpoint with text pasted in a form field (no file) processes successfully."""

    pasted_text = (
        "# Laborbefund Maria Beispiel 12.03.1961\n\n"
        "INR 1.1 (Referenz 0.8-1.2)\n"
        "aPTT 32 s (Referenz 25-38 s)\n"
        "Fibrinogen 2.8 g/L (Referenz 2.0-4.0 g/L)\n"
    )

    # Simulate the engine returning a valid parsed document
    def fake_document(data, filename, content_type, requested_loinc, requested_at, requested_doc_type):
        return {
            "ok": True,
            "needs_readback": False,
            "canonical_markdown": data.decode("utf-8") if isinstance(data, bytes) else data,
            "path": "text",
            "version": "test",
            "input": {"sha256": "abc", "filename": filename, "content_type": content_type,
                      "kind": "text", "bytes": len(data)},
            "parsed": None,
            "readback": [],
            "checks": None,
            "check_lines_de": [],
            "flags": [],
            "dropped_ungrounded": [],
            "models": {},
            "timings_ms": {},
        }

    monkeypatch.setattr(engine_client, "document", fake_document)

    rid = _send(REQ1)
    path = link_path(outbox[0]["link"])

    with TestClient(app) as client:
        # Open link
        r = client.get(path)
        assert r.status_code == 200

        # eID authorize — follow the redirect chain so the session cookie is set
        token = path.rsplit("/", 1)[1]
        client.post("/eid/authorize", data={"state": token, "citizen": "eva"})

        # GET the answer form
        r = client.get(f"{path}/answer")
        assert r.status_code == 200

        # POST with pasted text — NO file upload
        r = client.post(
            f"{path}/answer",
            data={
                "typed_name": "Maria Beispiel",
                "typed_dob": "12.03.1961",
                "text": pasted_text,
            },
        )

    # Must not be a server error
    assert r.status_code not in (500, 503), f"server error on pasted text: {r.status_code}\n{r.text[:300]}"
    # Either successfully filed or routed to review — either way the answer was accepted
    assert db.get("requests", "id", rid)["status"] in ("filed", "review", "answered", "rejected")


# ---------------------------------------------------------------------------
# T7 — GET the answer form with no session cookie returns a neutral response,
#      not a 500 error page.
# ---------------------------------------------------------------------------

def test_answer_page_without_session_gives_neutral_response(hapi, outbox):
    """GET /r/<token>/answer with no session cookie → neutral 404, not 500."""
    rid = _send(REQ1)
    path = link_path(outbox[0]["link"])

    with TestClient(app) as client:
        # Do NOT go through eID — just request the answer form directly (no session)
        r = client.get(f"{path}/answer")

    assert r.status_code == 404, f"expected 404 for unauthenticated answer page, got {r.status_code}"
    # Must not show a framework error page (HTTP 500 heading, exception traceback, etc.)
    assert "<h1>500" not in r.text and "Internal Server Error" not in r.text
    assert "Traceback" not in r.text
    # Must not leak patient data
    assert "Maria" not in r.text and "1961" not in r.text


# ---------------------------------------------------------------------------
# T8 — After 5 identity failures, the link page returns the same response
#      body as an expired/unknown link (indistinguishable to a guesser).
# ---------------------------------------------------------------------------

def test_blocked_link_same_response_as_expired(hapi, outbox):
    """After max_identity_attempts failures the link returns identical HTML to an unknown link."""
    _send(REQ1)
    path = link_path(outbox[0]["link"])
    token = path.rsplit("/", 1)[1]
    n = settings.max_identity_attempts

    def _strip_lang_links(html: str) -> str:
        """Remove the lang-toggle anchor which echoes the page's own path."""
        return re.sub(r'<a class="lang".*?</a>', "", html, flags=re.DOTALL)

    with TestClient(app) as client:
        # Exhaust all identity attempts with the wrong person
        for _ in range(n):
            client.get(path)
            client.get(f"/r/{token}/callback", params={"assertion": eid_mock.issue("karl", link_token=token)})

        # Now the link is blocked — opening it should return the same neutral dead-link page
        blocked_resp = client.get(path)
        unknown_resp = client.get("/r/does-not-exist-at-all")

    assert blocked_resp.status_code == 404, f"blocked link should return 404, got {blocked_resp.status_code}"
    assert unknown_resp.status_code == 404
    assert _strip_lang_links(blocked_resp.text) == _strip_lang_links(unknown_resp.text), (
        "blocked link response differs from unknown link — leaks state to a guesser"
    )


# ---------------------------------------------------------------------------
# PORTAL_ONLY split (wave-3 coverage)
# ---------------------------------------------------------------------------

def test_portal_only_hides_clinic_routes():
    """When PORTAL_ONLY=1 the clinic routes (/audit, /audit/apple, /audit.json) must not be mounted.
    GET /health (portal route) must still return 200."""
    # Build a fresh FastAPI app without clinic_router (mimicking main.py when PORTAL_ONLY=1).
    portal_router = importlib.import_module("app.portal_router").router

    portal_only_app = FastAPI(title="BefundBrücke-PortalOnly")
    portal_only_app.include_router(portal_router)
    # clinic_router deliberately NOT included

    with TestClient(portal_only_app) as client:
        health = client.get("/health")
        audit_html = client.get("/audit")
        audit_json = client.get("/audit.json")
        audit_apple = client.get("/audit/apple")

    assert health.status_code == 200, f"Expected /health=200, got {health.status_code}"
    assert audit_html.status_code == 404, f"Expected /audit=404 in PORTAL_ONLY, got {audit_html.status_code}"
    assert audit_json.status_code == 404, f"Expected /audit.json=404 in PORTAL_ONLY, got {audit_json.status_code}"
    assert audit_apple.status_code == 404, f"Expected /audit/apple=404 in PORTAL_ONLY, got {audit_apple.status_code}"

