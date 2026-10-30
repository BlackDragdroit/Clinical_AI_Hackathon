"""Browser end-to-end test of the outside portal (Playwright). Owner: SWE 2.

    uv run python scripts/e2e.py              against the running stack (make up): Matrix, Mailpit, HAPI, app
    uv run python scripts/e2e.py --local      no Docker: app in-process on a free port, fake HAPI, emails captured
    options: --flows r1,m2   --headed   --out var/e2e.json

Flows: r1 (request 1 by email, timed), r2 (request 2 via the /sms page), m1 (wrong address, stranger),
m2 (forwarded to a colleague), m3 (wrong patient's document). Dr. Hofer's side is driven like scripts/dev/flow.sh
(Matrix API, or commands.handle in --local); the outside person's side runs in a phone-sized Chromium.

stdout: one JSON object (Biostat reads it, also written to --out). Logs go to stderr. Exit 0 only if all flows pass.
request1_wall_s = opening the link -> receipt shown, as a script clicks it (a floor for the human stopwatch test).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DOCS = ROOT / "scenario" / "documents"
R1 = '!anfrage labor "Dr. Eva Brandl" eva.brandl@labor-kanal.example Patient/maria-beispiel Grund: Gerinnung vor Eingriff'
R2 = '!anfrage bericht "Stefan Kern" +436600000101 Patient/maria-beispiel Grund: Entlassungsbericht'
MARIA = ("Maria Beispiel", "12.03.1961")

# name -> (doctor command, eID test citizen, document, typed name + DOB, expected outcome)
FLOWS = {
    "r1": (R1, "eva", "lab-result-maria-beispiel.md", MARIA, "filed"),
    "r2": (R2, "stefan", "rehab-report-maria-beispiel.md", MARIA, "filed"),
    "m1": (R1.replace("labor-kanal.example", "labor-kanaI.example"), "unbekannt", "lab-result-maria-beispiel.md", MARIA,
           "identity_failed"),
    "m2": (R1, "karl", "lab-result-maria-beispiel.md", MARIA, "identity_failed"),
    "m3": (R1, "eva", "lab-result-max-beispiel.md", ("Max Beispiel", "01.01.1960"), "rejected"),
}
BEFORE_IDENTITY = re.compile(r"\b(Maria|Beispiel|1961|Labor\w*|Gerinnung|Befund|Entlassung\w*|Reha\w*)\b", re.I)


def log(*a: object) -> None:
    print(*a, file=sys.stderr, flush=True)


def _dotenv() -> dict[str, str]:
    env = {}
    p = ROOT / ".env"
    for line in p.read_text().splitlines() if p.exists() else []:
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return {**env, **os.environ}


# ---------------------------------------------------------------- Dr. Hofer's side + link delivery

class StackDriver:
    """The running stack: commands go into the Matrix room as Dr. Hofer, links come from Mailpit or /sms."""

    def __init__(self, portal: str):
        env = _dotenv()
        self.portal = portal
        self.hs = env.get("MATRIX_HOMESERVER", "http://localhost:8008")
        self.mailpit = env.get("MAILPIT_API", "http://localhost:8025/api/v1")
        self.room = quote(env["MATRIX_ROOM_ID"], safe="")
        r = httpx.post(f"{self.hs}/_matrix/client/v3/login", timeout=10, json={
            "type": "m.login.password", "identifier": {"type": "m.id.user", "user": "lena.hofer"},
            "password": env["DOCTOR_PASSWORD"]})
        r.raise_for_status()
        self.auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
        self.me = r.json()["user_id"]

    def _say(self, text: str) -> str:
        """Send as Dr. Hofer, return the first bot reply after it."""
        sent = time.time() * 1000
        httpx.put(f"{self.hs}/_matrix/client/v3/rooms/{self.room}/send/m.room.message/e2e{time.time_ns()}",
                  headers=self.auth, json={"msgtype": "m.text", "body": text}, timeout=10).raise_for_status()
        for _ in range(40):
            time.sleep(0.5)
            chunk = httpx.get(f"{self.hs}/_matrix/client/v3/rooms/{self.room}/messages", headers=self.auth,
                              params={"dir": "b", "limit": 10}, timeout=10).json()["chunk"]
            for e in reversed(chunk):
                if e["type"] == "m.room.message" and e["sender"] != self.me and e["origin_server_ts"] >= sent:
                    return e["content"]["body"]
        raise TimeoutError(f"no bot reply to {text!r}")

    def _mail_ids(self) -> set[str]:
        return {m["ID"] for m in httpx.get(f"{self.mailpit}/messages", params={"limit": 50}, timeout=10).json()["messages"]}

    def send_request(self, cmd: str) -> tuple[str, str]:
        rid = re.search(r"Anfrage ([a-z0-9]{8})", self._say(cmd)).group(1)
        email = "@" in cmd.split('"')[2]
        before = self._mail_ids() if email else set()
        reply = self._say(f"!senden {rid}")
        if "gesendet" not in reply:
            raise RuntimeError(f"!senden {rid} failed: {reply[:200]}")
        return rid, self._link_from_mail(before) if email else sms_link(self.portal)

    def _link_from_mail(self, before: set[str]) -> str:
        for _ in range(20):
            new = self._mail_ids() - before
            if new:
                text = httpx.get(f"{self.mailpit}/message/{new.pop()}", timeout=10).json()["Text"]
                return re.search(r"https?://\S+/r/[A-Za-z0-9_-]+", text).group(0)
            time.sleep(0.5)
        raise TimeoutError("no new email in Mailpit")

    def close(self) -> None:
        pass


class LocalDriver:
    """No Docker: the app runs in this process with a fake HAPI; emails are captured instead of sent."""

    def __init__(self):
        tmp = tempfile.mkdtemp(prefix="bb-e2e-")
        port = _free_port()
        os.environ.update(DB_PATH=f"{tmp}/bb.sqlite", VAR_DIR=f"{tmp}/var", MATRIX_ENABLED="0",
                          BASE_URL=f"http://127.0.0.1:{port}")
        import uvicorn

        from app import commands, fhir_client
        from app.config import settings
        from app.delivery.smtp_mailpit import SmtpMailpit
        from app.main import app
        from tests.conftest import FakeHapi

        self.portal, self.handle, self.doctor = settings.base_url, commands.handle, settings.doctor_mxid
        self.hapi, self.mails = FakeHapi(), []
        for name in ("read_patient", "create_task", "set_task_status", "validate", "post_transaction"):
            setattr(fhir_client, name, getattr(self.hapi, name))
        SmtpMailpit.send = lambda _self, to, link: self.mails.append(link) or f"<e2e{len(self.mails)}@local>"
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        threading.Thread(target=self.server.run, daemon=True).start()
        while not self.server.started:
            time.sleep(0.05)

    def send_request(self, cmd: str) -> tuple[str, str]:
        rid = re.search(r"Anfrage ([a-z0-9]{8})", self.handle(cmd, self.doctor)).group(1)
        n = len(self.mails)
        reply = self.handle(f"!senden {rid}", self.doctor)
        if "gesendet" not in reply:
            raise RuntimeError(f"!senden {rid} failed: {reply[:200]}")
        return rid, self.mails[-1] if len(self.mails) > n else sms_link(self.portal)

    def close(self) -> None:
        self.server.should_exit = True


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sms_link(portal: str) -> str:
    """Newest SMS on the simulated inbox page, the way request 2's recipient gets it."""
    return re.search(r"https?://[^\"<\s]+/r/[A-Za-z0-9_-]+", httpx.get(f"{portal}/sms", timeout=10).text).group(0)


# ---------------------------------------------------------------- the outside person's side

def run_flow(name: str, driver, browser, portal: str) -> dict:
    cmd, citizen, doc, (typed_name, typed_dob), expect = FLOWS[name]
    out: dict = {"flow": name, "expected": expect, "checks": {}}
    checks = out["checks"]
    rid, link = driver.send_request(cmd)
    url = portal + urlsplit(link).path               # the link carries BASE_URL; reach the portal we were given
    out["request_id"] = rid
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, locale="de-AT")
    page = ctx.new_page()
    try:
        t0 = time.perf_counter()
        page.goto(url)
        checks["landing_neutral"] = not BEFORE_IDENTITY.search(page.inner_text("body"))
        page.get_by_role("link", name="Mit ID Austria anmelden").click()
        page.locator(f"input[name=citizen][value={citizen}]").check()
        with page.expect_navigation():
            page.get_by_role("button", name="Freigeben und weiter").click()
        body = page.inner_text("body")
        if expect == "identity_failed":
            checks["not_for_you_page"] = "nicht für Sie bestimmt" in body
            checks["nothing_revealed"] = not BEFORE_IDENTITY.search(body)
            checks["answer_form_closed"] = page.goto(url + "/answer").status == 404
        else:
            page.get_by_label(re.compile("Name der Patientin")).fill(typed_name)
            page.get_by_label(re.compile("Geburtsdatum")).fill(typed_dob)
            page.locator("input[type=file]").set_input_files(str(DOCS / doc))
            with page.expect_navigation():
                page.get_by_role("button", name="Sicher senden").click()
            page.get_by_text("Eingangsnummer").wait_for()
            out["wall_s"] = round(time.perf_counter() - t0, 2)
            body = page.inner_text("body")
            checks["receipt_shown"] = ("sicher übermittelt" in body) if expect == "filed" else ("nicht zugeordnet" in body)
            if expect == "rejected":
                checks["other_patient_not_echoed"] = "Max" not in body and "1960" not in body
    finally:
        ctx.close()
    events = _audit(portal, rid)
    names = [e["event"] for e in events]
    if expect == "filed":
        checks["audit_answer_filed"] = "answer_filed" in names
    else:
        checks["audit_not_filed"] = "answer_filed" not in names
        checks["audit_misdelivery_caught"] = "misdelivery_caught" in names
    if expect == "identity_failed":
        checks["audit_identity_failed"] = any(e["event"] == "identity_checked" and e["details"].get("result") == "FAILED"
                                              for e in events)
    out["audit_events"] = names
    out["passed"] = all(checks.values())
    return out


def _audit(portal: str, rid: str) -> list[dict]:
    """answer_filed is written after HAPI answers; give it a moment on the real stack."""
    for _ in range(10):
        events = httpx.get(f"{portal}/audit.json", params={"request_id": rid}, timeout=10).json()["entries"]
        if any(e["event"] in ("answer_filed", "misdelivery_caught") for e in events):
            return events
        time.sleep(0.5)
    return events


def _launch(p, headed: bool):
    try:
        return p.chromium.launch(headless=not headed)
    except Exception as e:                       # no bundled browser: `uv run playwright install chromium`
        exe = shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("chromium-browser")
        if not exe:
            raise
        log(f"bundled Chromium missing ({str(e).splitlines()[0]}); using {exe}")
        return p.chromium.launch(headless=not headed, executable_path=exe)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local", action="store_true", help="run without Docker (app in-process, fake HAPI)")
    ap.add_argument("--portal", default="http://localhost:8000", help="portal URL for stack mode")
    ap.add_argument("--flows", default=",".join(FLOWS), help="comma-separated subset of " + ",".join(FLOWS))
    ap.add_argument("--headed", action="store_true", help="show the browser")
    ap.add_argument("--out", default=str(ROOT / "var" / "e2e.json"))
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    stdout, sys.stdout = sys.stdout, sys.stderr      # the in-process app prints Matrix messages; keep stdout for the JSON
    driver = LocalDriver() if args.local else StackDriver(args.portal)
    portal = driver.portal if args.local else args.portal
    results = []
    try:
        with sync_playwright() as p:
            browser = _launch(p, args.headed)
            for name in args.flows.split(","):
                log(f"[{name}] running")
                try:
                    r = run_flow(name, driver, browser, portal)
                except Exception as e:                   # a broken flow is a failed flow, the others still run
                    r = {"flow": name, "passed": False, "error": f"{type(e).__name__}: {e}"}
                log(f"[{name}] {'PASS' if r['passed'] else 'FAIL'} {r.get('wall_s', '')}"
                    f" {[k for k, v in r.get('checks', {}).items() if not v] or r.get('error', '')}")
                results.append(r)
            browser.close()
    finally:
        driver.close()

    r1 = next((r for r in results if r["flow"] == "r1"), {})
    report = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mode": "local" if args.local else "stack",
              "all_passed": all(r["passed"] for r in results), "request1_wall_s": r1.get("wall_s"), "flows": results}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, ensure_ascii=False), file=stdout)
    log(f"request 1 wall time: {report['request1_wall_s']} s · {sum(r['passed'] for r in results)}/{len(results)} flows passed"
        f" · written to {args.out}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
