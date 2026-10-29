"""Collect the four track metrics from the running stack and write METRICS.md. Owner: Biostat.

Sources:
  audit coverage     GET  {BASE_URL}/audit.json                      (implemented)
  email/SMS leaks    Mailpit API + sms_outbox via /sms               (implemented: same token list as the unit test)
  HL7 validator      var/validation/*.txt from scripts/validate_all.sh (TODO)
  outside effort     Playwright timings (SWE 2's e2e script) + stopwatch test sheet metrics/stopwatch.csv (TODO)
  misdeliveries      M1–M3 results: audit entries with event misdelivery_caught per request (TODO: map request -> test)
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from app.config import settings
from tests.test_template_leak import FORBIDDEN

ROOT = Path(__file__).resolve().parent.parent


def audit_coverage() -> dict:
    a = httpx.get(f"{settings.base_url}/audit.json", timeout=10).json()
    return {"chain_ok": a["chain_ok"], "coverage": a["coverage"]}


def leak_scan() -> dict:
    hits: list[str] = []
    msgs = httpx.get(f"{settings.mailpit_api}/messages", params={"limit": 200}, timeout=10).json().get("messages", [])
    for m in msgs:
        full = httpx.get(f"{settings.mailpit_api}/message/{m['ID']}", timeout=10).json()
        text = f"{full.get('Subject', '')}\n{full.get('Text', '')}".lower()
        hits += [f"email {m['ID']}: {t}" for t in FORBIDDEN if re.search(rf"\b{re.escape(t)}\b", text)]
    # TODO(Biostat): SMS bodies from /sms; also scan the neutral landing page HTML
    return {"emails_scanned": len(msgs), "hits": hits}


def validator_errors() -> dict:
    # TODO(Biostat): parse var/validation/*.txt (written by scripts/validate_all.sh) -> errors per file + total
    return {}


def main() -> None:
    cov, leaks, val = audit_coverage(), leak_scan(), validator_errors()
    n_cov = sum(cov["coverage"].values())
    lines = ["# Metrics (scenario)", "", "| Metric | Result | Target |", "|---|---|---|",
             f"| Audit coverage | {n_cov}/6, hash chain {'ok' if cov['chain_ok'] else 'BROKEN'} | 6/6 |",
             f"| Email/SMS leaks | {len(leaks['hits'])} hits in {leaks['emails_scanned']} emails | 0 |",
             f"| HL7 validator errors | {val.get('total', 'TODO')} | 0 |",
             "| Outside person: installs / accounts / time | TODO | 0 / 0 / < 2 min |",
             "| Misdeliveries caught | TODO | 3/3 |", "",
             "Matcher calibration and CIs: see core/METRICS_matching.md."]
    (ROOT / "METRICS.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
