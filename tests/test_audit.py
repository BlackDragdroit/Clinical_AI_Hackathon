import json
import re

import pytest
from fastapi.testclient import TestClient

from app import audit, db
from app.main import app
from tests.conftest import REQ1, link_path
from tests.test_flow import _answer, _send


def test_chain_verifies_and_detects_tampering():
    audit.log("request_sent", "r1", "@lena.hofer:klinikum.example", {"x": 1})
    audit.log("link_opened", "r1", "link ip=1.2.3.4", {})
    assert audit.verify_chain()
    with db.conn() as c:
        c.execute("UPDATE audit SET actor = 'someone else' WHERE seq = 1")
    assert not audit.verify_chain()


def test_unknown_event_is_rejected():
    with pytest.raises(ValueError):
        audit.log("request_snet", "r1", "x", {})


# --- first_broken -------------------------------------------------------------------------------

def test_first_broken_none_when_intact_and_seq_after_tampering():
    assert audit.first_broken() is None                       # empty log
    for ev in ("request_drafted", "request_sent", "link_opened", "identity_checked"):
        audit.log(ev, "r1", "system:test", {"result": "OK"})
    assert audit.first_broken() is None and audit.verify_chain()
    with db.conn() as c:
        c.execute("UPDATE audit SET details = '{\"result\": \"FAILED\"}' WHERE seq = 3")
    assert audit.first_broken() == 3
    assert not audit.verify_chain()


def test_first_broken_finds_a_deleted_row():
    for ev in ("request_drafted", "request_sent", "link_opened"):
        audit.log(ev, "r1", "system:test", {})
    with db.conn() as c:
        c.execute("DELETE FROM audit WHERE seq = 2")
    assert audit.first_broken() == 3                           # row 3 no longer links to row 1


# --- describe / actor_label ---------------------------------------------------------------------

def test_actor_label():
    assert audit.actor_label("@lena.hofer:klinikum.example") == "Dr. Hofer"
    assert audit.actor_label("@max.muster:klinikum.example") == "Max Muster"
    assert audit.actor_label("link ip=10.0.0.7") == "Link (IP 10.0.0.7)"
    assert audit.actor_label("eid:bpk-0123456789abcdef Eva Brandl") == "eID: Eva Brandl"
    assert "bpk-" not in audit.actor_label("eid:bpk-0123456789abcdef Eva Brandl")
    assert audit.actor_label("system:befundbruecke", "en") == "System"


def test_describe_sentences_de_en():
    failed = {"event": "identity_checked", "details": {"result": "FAILED", "attempt": 1}}
    assert audit.describe(failed) == "Identität geprüft: fehlgeschlagen (Versuch 1)"
    assert audit.describe(failed, "en") == "Identity checked: failed (attempt 1)"
    m2 = {"event": "misdelivery_caught", "details": {"type": "M2", "verified": "Karl Kollege", "expected": "Dr. Eva Brandl"}}
    assert audit.describe(m2) == "M2 – wahrscheinlich weitergeleitet – verifiziert: Karl Kollege ≠ erwartet: Dr. Eva Brandl"
    filed = {"event": "answer_filed", "details": {"resources": ["Observation/1", "Observation/2", "Provenance/3"], "task": "Task/1"}}
    assert audit.describe(filed) == "In FHIR abgelegt: 3 Ressourcen, Task/1 abgeschlossen"
    assert audit.note(filed) == "2× Observation · Provenance"
    sent = {"event": "request_sent", "details": {"channel": "email", "contact": "e***@labor-kanal.example",
                                                 "to": "Dr. Eva Brandl", "ttl_h": 72}}
    assert "e***@labor-kanal.example" in audit.describe(sent) and "E-Mail" in audit.describe(sent)


def test_describe_never_crashes_and_knows_later_events():
    for ev in audit.EVENTS + audit.LATER:
        assert audit.describe({"event": ev, "details": {}}, "en")
        assert not audit.describe({"event": ev, "details": {}}).startswith("Ereignis „")   # each has its own sentence
    assert audit.describe({"event": "mystery", "details": {}}) == "Ereignis „mystery“ (ohne Beschreibung)"
    assert audit.describe({"event": "answer_filed", "details": {"resources": 5}}).startswith("Ereignis")  # odd details
    assert audit.describe({"event": "answer_sent", "details": "not a dict"})


def test_local_time_is_vienna():
    assert audit.local_time("2026-10-30T12:00:00+00:00").strftime("%H:%M") == "13:00"   # CET
    assert audit.local_time("2026-07-01T12:00:00+00:00").strftime("%H:%M") == "14:00"   # CEST


# --- the page -----------------------------------------------------------------------------------

def _scenario(outbox) -> dict[str, str]:
    """Request 1 (filed), M1 (wrong address), M2 (forwarded), M3 (other patient's document)."""
    ids = {}
    with TestClient(app) as client:
        ids["r1"] = _send(REQ1)
        _answer(client, link_path(outbox[-1]["link"]), "eva", "lab-result-maria-beispiel.md")
        ids["m1"] = _send(REQ1.replace("labor-kanal", "labor-kanaI"))
        _answer(client, link_path(outbox[-1]["link"]), "unbekannt", "lab-result-maria-beispiel.md")
    with TestClient(app) as client:
        ids["m2"] = _send(REQ1)
        _answer(client, link_path(outbox[-1]["link"]), "karl", "lab-result-maria-beispiel.md")
    with TestClient(app) as client:
        ids["m3"] = _send(REQ1)
        _answer(client, link_path(outbox[-1]["link"]), "eva", "lab-result-max-beispiel.md",
                typed=("Max Beispiel", "01.01.1960"))
    return ids


def _visible(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def test_page_shows_full_coverage_after_scenario(hapi, outbox):
    ids = _scenario(outbox)
    with TestClient(app) as client:
        r = client.get("/audit")
    assert r.status_code == 200
    html = r.text
    assert "Hash-Kette intakt" in html
    assert re.search(r'class="num">6</span><span class="of">/ 6', html)
    for label in ("Anfrage gesendet", "Link geöffnet", "Identität geprüft", "Antwort übermittelt", "In FHIR abgelegt",
                  "Fehlzustellung erkannt"):
        assert label in html
    for rid in ids.values():
        assert f"/audit?request_id={rid}" in html
    assert "M1 – wahrscheinlich falsche Adresse" in html and "M2 – wahrscheinlich weitergeleitet" in html
    assert "verifiziert: Karl Kollege ≠ erwartet: Dr. Eva Brandl" in html
    assert "Identität geprüft: fehlgeschlagen (Versuch 1)" in html
    assert "Laborbefund" in html and "Abgelegt" in html and "Abgewiesen, Quarantäne" in html
    # patients by reference, contacts masked
    assert "Patient/maria-beispiel" in html and "Maria Beispiel" not in html
    assert "e***@labor-kanal.example" in html and "eva.brandl@" not in html
    assert "Klinikintern – in Produktion hinter Klinik-Login" in html
    # pseudonym only in the raw <details>, not in the "who" line
    assert "eID: Eva Brandl" in html
    assert not re.search(r'class="ev-who">[^<]*bpk-', html)
    # every entry has a row hash
    for e in audit.entries():
        assert e["hash"] in html


def test_filtered_view_and_english(hapi, outbox):
    ids = _scenario(outbox)
    with TestClient(app) as client:
        r = client.get(f"/audit?request_id={ids['r1']}&lang=en")
        assert r.cookies.get("lang") == "en" or "lang=en" in r.headers.get("set-cookie", "")
    html = r.text
    assert '<html lang="en">' in html
    assert "Hash chain intact" in html and "Filed in FHIR" in html and "Request sent" in html
    assert "Identity checked: confirmed" in html and "lab result" in html
    assert "Hash-Kette" not in html
    assert re.search(r'class="num">5</span><span class="of">/ 6', html)          # no misdelivery in request 1
    assert "none in this request" in html
    assert f'href="/audit?request_id={ids["r1"]}&amp;lang=de"' in html                # toggle keeps the filter
    assert f'href="/audit.json?request_id={ids["r1"]}"' in html
    assert ids["m2"] not in _visible(html.split('id="timeline"', 1)[1])            # timeline is filtered
    assert "Clinic-internal" in html


def test_m3_page_never_shows_the_other_patient(hapi, outbox):
    _scenario(outbox)
    with TestClient(app) as client:
        pages = [client.get("/audit").text, client.get("/audit?lang=en").text, client.get("/audit.json").text]
        rid = db.query("SELECT id FROM requests WHERE status = 'rejected'")[0]["id"]
        pages += [client.get(f"/audit?request_id={rid}").text, client.get(f"/audit.json?request_id={rid}").text]
    assert "M3 – Dokument betrifft anderen Patienten" in pages[0]
    for text in pages:
        assert not re.search(r"\bMax\b", text)
        assert not re.search(r"\b1960\b", text)
        assert "01.01.1960" not in text and "1960-01-01" not in text


def test_unknown_event_renders_with_generic_sentence():
    audit.log("request_sent", "r9", "@lena.hofer:klinikum.example", {"channel": "email"})
    prev = audit.head()
    ts, det = db.now(), json.dumps({"foo": 1})
    h = audit._digest(prev, ts, "mystery_event", "r9", "system:other", det)
    with db.conn() as c:   # another branch wrote an event this one does not know
        c.execute("INSERT INTO audit (ts, event, request_id, actor, details, prev_hash, hash) VALUES (?,?,?,?,?,?,?)",
                  (ts, "mystery_event", "r9", "system:other", det, prev, h))
    assert audit.verify_chain()
    with TestClient(app) as client:
        r = client.get("/audit")
        en = client.get("/audit?lang=en")
    assert r.status_code == 200 and "Ereignis „mystery_event“ (ohne Beschreibung)" in r.text
    assert en.status_code == 200 and "Event “mystery_event” (no description)" in en.text


def test_page_shows_broken_chain():
    for ev in ("request_drafted", "request_sent", "link_opened"):
        audit.log(ev, "r1", "system:test", {})
    with db.conn() as c:
        c.execute("UPDATE audit SET actor = 'mallory' WHERE seq = 2")
    with TestClient(app) as client:
        html = client.get("/audit").text
        data = client.get("/audit.json").json()
    assert "Hash-Kette verletzt ab Eintrag #2" in html and "Hash stimmt nicht" in html
    assert data["chain_ok"] is False and data["first_broken"] == 2


def test_audit_json_backward_compatible(hapi, outbox):
    _scenario(outbox)
    with TestClient(app) as client:
        data = client.get("/audit.json").json()
    assert {"chain_ok", "coverage", "entries"} <= set(data)
    assert data["chain_ok"] is True and all(data["coverage"].values())
    assert data["entries"] == json.loads(json.dumps(audit.entries()))
    assert all("@" not in r["contact"] or "***@" in r["contact"] for r in data["requests"])


def test_empty_log_and_unknown_request_render():
    with TestClient(app) as client:
        assert "Noch keine Einträge" in client.get("/audit").text
        r = client.get("/audit?request_id=nope<script>")
    assert r.status_code == 200 and "nope&lt;script&gt;" in r.text and "<script>" not in r.text


# --- /audit/apple: the same page in a second (Apple HIG) design ------------------------------------

def test_apple_page_shows_full_coverage_after_scenario(hapi, outbox):
    ids = _scenario(outbox)
    with TestClient(app) as client:
        r = client.get("/audit/apple")
    assert r.status_code == 200
    html = r.text
    assert "Hash-Kette geprüft: intakt" in html
    assert re.search(r"Hash-Kette geprüft: intakt.*?\d+ Einträge, letzter Hash</span>\s*<code class=\"hash\"", html, re.DOTALL)
    assert "Pflichtschritte: 6 von 6 protokolliert" in html
    assert html.count(">protokolliert<") == 6 and ">fehlt<" not in html   # each step in words
    assert "Klinik</dt>" in html and re.search(r"Umfang</dt>\s*<dd>Alle Anfragen</dd>", html)   # document header
    assert 'class="c-seq r">#</th>' in html and 'scope="rowgroup"' in html     # the timeline is a ledger table
    assert "tile" not in html and "segment" not in html                 # no icon tiles, no pill controls
    for label in ("Anfrage gesendet", "Link geöffnet", "Identität geprüft", "Antwort übermittelt", "In FHIR abgelegt",
                  "Fehlzustellung erkannt"):
        assert label in html
    for rid in ids.values():                                   # filter links stay on the Apple design
        assert f"/audit/apple?request_id={rid}" in html
        assert f'href="/audit?request_id={rid}' not in html
    assert "M1 – wahrscheinlich falsche Adresse" in html and "M3 – Dokument betrifft anderen Patienten" in html
    assert "verifiziert: Karl Kollege ≠ erwartet: Dr. Eva Brandl" in html
    assert "Patient/maria-beispiel" in html and "Maria Beispiel" not in html
    assert "e***@labor-kanal.example" in html and "eva.brandl@" not in html
    assert "Klinikintern – in Produktion hinter Klinik-Login" in html
    assert 'href="/audit?lang=de"' in html                      # design switch back to the standard page
    assert "<script" not in html                                # works without JavaScript
    for e in audit.entries():
        assert e["hash"] in html


def test_apple_page_english_toggle_keeps_filter(hapi, outbox):
    ids = _scenario(outbox)
    with TestClient(app) as client:
        r = client.get(f"/audit/apple?request_id={ids['r1']}&lang=en")
    html = r.text
    assert '<html lang="en">' in html and "Hash chain verified: intact" in html and "Hash-Kette" not in html
    assert "Required steps: 5 of 6 logged" in html and "none in this request" in html
    assert ">Deutsch</a>" in html and ">English</a>" in html                       # plain text language switch
    assert "Show all requests" in html and "Clinic-internal" in html
    assert f'href="/audit/apple?request_id={ids["r1"]}&amp;lang=de"' in html        # DE segment keeps the filter
    assert f'href="/audit/apple?request_id={ids["r1"]}&amp;lang=en"' in html        # EN segment (current)
    assert f'href="/audit?request_id={ids["r1"]}&amp;lang=en"' in html              # design switch keeps both
    assert f'href="/audit.json?request_id={ids["r1"]}"' in html
    assert ids["m2"] not in _visible(html.split('id="timeline"', 1)[1])


def test_apple_page_m3_never_shows_the_other_patient(hapi, outbox):
    _scenario(outbox)
    rid = db.query("SELECT id FROM requests WHERE status = 'rejected'")[0]["id"]
    with TestClient(app) as client:
        pages = [client.get(u).text for u in ("/audit/apple?lang=de", "/audit/apple?lang=en",
                                              f"/audit/apple?request_id={rid}&lang=de",
                                              f"/audit/apple?request_id={rid}&lang=en")]
    assert "M3 – Dokument betrifft anderen Patienten" in pages[0] and "M3 – document is about another patient" in pages[1]
    for text in pages:
        assert not re.search(r"\bMax\b", text)
        assert not re.search(r"\b1960\b", text)
        assert "01.01.1960" not in text and "1960-01-01" not in text


def test_apple_page_broken_chain_and_empty_states():
    with TestClient(app) as client:
        assert "Noch keine Einträge" in client.get("/audit/apple").text
        r = client.get("/audit/apple?request_id=nope<script>")
    assert r.status_code == 200 and "nope&lt;script&gt;" in r.text and "<script" not in r.text
    for ev in ("request_drafted", "request_sent", "link_opened"):
        audit.log(ev, "r1", "system:test", {})
    with db.conn() as c:
        c.execute("UPDATE audit SET actor = 'mallory' WHERE seq = 2")
    with TestClient(app) as client:
        html = client.get("/audit/apple").text
    assert "Hash-Kette verletzt ab Eintrag #2" in html and "Hash stimmt nicht" in html
    assert 'href="#e2"' in html


def test_standard_page_only_gains_the_design_switch(hapi, outbox):
    ids = _scenario(outbox)
    with TestClient(app) as client:
        html = client.get(f"/audit?request_id={ids['r1']}&lang=en").text
    switch = re.search(r'<nav class="design-switch".*?</nav>', html, re.DOTALL)
    assert switch and f'href="/audit/apple?request_id={ids["r1"]}&amp;lang=en"' in switch.group(0)
    rest = html.replace(switch.group(0), "")
    assert "/audit/apple" not in rest                           # every other link still points at /audit
    assert 'class="num">5</span><span class="of">/ 6' in rest and "_audit_apple" not in rest


@pytest.mark.parametrize("page", ["/audit", "/audit/apple"])
def test_audit_pages_are_light_only(page):
    with TestClient(app) as client:
        for url in (page, f"{page}?lang=en", f"{page}?theme=dark"):
            html = client.get(url).text
            assert "data-theme" not in html and "prefers-color-scheme: dark" not in html
            assert '<meta name="color-scheme" content="light">' in html and "color-scheme: light dark" not in html
            assert "theme=" not in html                                     # no appearance switch left


def test_design_switch_sits_in_the_footer(hapi, outbox):
    ids = _scenario(outbox)
    with TestClient(app) as client:
        for url, other in ((f"/audit/apple?request_id={ids['r1']}&lang=en", "/audit?"),
                           (f"/audit?request_id={ids['r1']}&lang=en", "/audit/apple?")):
            html = client.get(url).text
            footer = html.split("<footer", 1)[1]
            assert 'class="design-switch"' in footer and 'class="design-switch"' not in html.split("<footer", 1)[0]
            assert f'href="{other}request_id={ids["r1"]}&amp;lang=en"' in footer
