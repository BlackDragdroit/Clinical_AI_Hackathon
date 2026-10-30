"""Collect the four track metrics from the running stack and write METRICS.md. Owner: Biostat.

Sources:
  audit coverage     GET  {BASE_URL}/audit.json
  email/SMS leaks    Mailpit API (subject + text) and the simulated SMS inbox ({BASE_URL}/sms), same tokens as the unit test
  HL7 validator      var/validation/*.txt from scripts/validate_all.sh (`make validate`)
  outside effort     metrics/stopwatch.csv: one row per new person answering request 1 (installs, accounts, seconds)
  misdeliveries      audit: per test a request with misdelivery_caught of that type, and no harm (M1/M2: nothing
                     revealed; M3: nothing filed). Run scripts/dev/flow.sh m1 m2 m3 first.
  jury documents     metrics/jury_docs/manifest.json through the core (same cases as metrics/eval_jury_docs.py)
  AI engine          eval/results/*.json (synthetic held-out set; reproduce with `make engine-eval`)
"""
from __future__ import annotations

import csv
import html
import json
import re
import statistics
from pathlib import Path

import httpx

from app.config import settings
from app.core_bridge import Person, run_intake
from tests.test_template_leak import FORBIDDEN

ROOT = Path(__file__).resolve().parent.parent
MISDELIVERY = {"M1": "wrong address (labor-kanaI)", "M2": "forwarded to a colleague", "M3": "document of another patient"}


def audit() -> dict:
    return httpx.get(f"{settings.base_url}/audit.json", timeout=10).json()


def _leaks(text: str) -> list[str]:
    text = text.lower()
    return [t for t in FORBIDDEN if re.search(rf"\b{re.escape(t)}\b", text)]


def leak_scan() -> dict:
    hits: list[str] = []
    msgs = httpx.get(f"{settings.mailpit_api}/messages", params={"limit": 200}, timeout=10).json().get("messages", [])
    for m in msgs:
        full = httpx.get(f"{settings.mailpit_api}/message/{m['ID']}", timeout=10).json()
        hits += [f"email {m['ID']}: {t}" for t in _leaks(f"{full.get('Subject', '')}\n{full.get('Text', '')}")]
    page = httpx.get(f"{settings.base_url}/sms", timeout=10).text
    sms = [re.sub(r"<[^>]+>", "", b) for b in re.findall(r'<p class="muted">An [^<]*</p>\s*<p>(.*?)</p>', page, re.S)]
    for i, body in enumerate(sms):
        hits += [f"sms {i}: {t}" for t in _leaks(html.unescape(body))]
    return {"emails": len(msgs), "sms": len(sms), "hits": hits}


def validator_errors() -> dict:
    files = sorted((ROOT / "var" / "validation").glob("*.txt"))
    per = {}
    for f in files:
        found = re.findall(r"(\d+) errors?", f.read_text(encoding="utf-8", errors="replace"))
        per[f.stem] = int(found[-1]) if found else None
    known = [n for n in per.values() if n is not None]
    return {"files": per, "total": sum(known) if known else None}


def outside_effort() -> dict:
    """metrics/stopwatch.csv: tester,installs,accounts,seconds,date,notes (time from opening the email to sending)."""
    path = ROOT / "metrics" / "stopwatch.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []
    rows = [r for r in rows if (r.get("seconds") or "").strip()]
    if not rows:
        return {"n": 0}
    secs = [float(r["seconds"]) for r in rows]
    return {"n": len(rows), "installs": max(int(r["installs"] or 0) for r in rows),
            "accounts": max(int(r["accounts"] or 0) for r in rows), "median_s": statistics.median(secs), "max_s": max(secs)}


def misdeliveries(a: dict) -> dict:
    events: dict[str, list[dict]] = {}
    for e in a["entries"]:
        if e["request_id"]:
            events.setdefault(e["request_id"], []).append(e)
    out = {}
    for code in MISDELIVERY:
        reqs = [rid for rid, evs in events.items()
                if any(e["event"] == "misdelivery_caught" and e["details"].get("type") == code for e in evs)]
        harm = "patient_revealed" if code in ("M1", "M2") else "answer_filed"
        harmed = [rid for rid in reqs if any(e["event"] == harm for e in events[rid])]
        out[code] = {"caught": len(reqs), "harmed": len(harmed)}
    return out


def jury_docs() -> dict:
    """Wrongly filed = we filed a document the manifest says must not be filed. Exact (Clopper-Pearson) 95 % upper
    bound, because with 0 events a bootstrap interval collapses to [0, 0]."""
    cases = json.loads((ROOT / "metrics" / "jury_docs" / "manifest.json").read_text(encoding="utf-8"))
    got = [run_intake((ROOT / c["file"]).read_text(encoding="utf-8"), Person.from_full(*c["requested"]),
                      Person.from_full(*c["typed"]), "Test Sender", "", "test", "Patient/test").decision for c in cases]
    n = len(cases)
    wrong = sum(1 for c, g in zip(cases, got) if g == "file" and c["expected"] != "file")
    upper = 1 - 0.025 ** (1 / n) if wrong == 0 else None
    return {"n": n, "wrongly_filed": wrong, "upper": upper, "same": sum(1 for c, g in zip(cases, got) if g == c["expected"]),
            "to_review": sum(1 for c, g in zip(cases, got) if g == "review" and c["expected"] != "review")}


def engine_results() -> list[str]:
    res = ROOT / "eval" / "results"
    ci = lambda m: f"{m['p'] * 100:.1f} % [{m['lo'] * 100:.1f}, {m['hi'] * 100:.1f}] ({m['k']}/{m['n']})"   # noqa: E731
    rows = []
    for name, label in (("requests_test_rules-v2", "Requests, rules only"),
                        ("requests_test_qwen3-1.7b-cpu-v2", "Requests, rules + Qwen3-1.7B (CPU)")):
        p = res / f"{name}.json"
        if p.exists():
            m = json.loads(p.read_text(encoding="utf-8"))["metrics"]
            wrong = sum(1 for i in m["items"] if i.get("wrong_patient"))
            rows.append(f"| {label} | {ci(m['full_request'])} fully correct · {wrong} wrong patients · "
                        f"{m['safety']['silent_error']['k']} silent errors |")
    p = res / "documents_rules.json"
    if p.exists():
        for form, m in json.loads(p.read_text(encoding="utf-8"))["metrics"].items():
            rows.append(f"| Answers as {form.upper()} (synthetic, same format as the scenario) | read {m['read']['k']}/{m['read']['n']} · "
                        f"wrong value filed {m['safety']['wrong_value_filed']['k']} · "
                        f"wrong patient filed {m['safety']['wrongly_filed_patient']['k']} |")
    return rows


def main() -> None:
    a, leaks, val, eff = audit(), leak_scan(), validator_errors(), outside_effort()
    mis, jury = misdeliveries(a), jury_docs()
    n_cov = sum(a["coverage"].values())
    caught = sum(1 for m in mis.values() if m["caught"] and not m["harmed"])
    val_txt = (f"{val['total']} errors in {len(val['files'])} filed bundles" if val["total"] is not None
               else "not run on this machine: `make validate` (MedEng: 0 errors on both scenario bundles, PR #12)")
    eff_txt = (f"{eff['installs']} / {eff['accounts']} / median {eff['median_s']:.0f} s (max {eff['max_s']:.0f} s, n={eff['n']})"
               if eff["n"] else "0 / 0 by design (link + simulated ID Austria in the browser) / time: not measured yet")
    lines = ["# Metrics (scenario)", "",
             "Measured on the running stack (`make up`, then `scripts/dev/flow.sh r1 r2 m1 m2 m3`), written by "
             "`make metrics`. Synthetic data only.", "",
             "| Metric | Result | Target |", "|---|---|---|",
             f"| FHIR validation (HL7 validator) | {val_txt} | 0 |",
             f"| Outside person: installs / accounts / time | {eff_txt} | 0 / 0 / < 2 min |",
             f"| Misdeliveries caught | {caught}/3 | 3/3 |",
             f"| Audit coverage | {n_cov}/6 steps with who, what, when; hash chain {'intact' if a['chain_ok'] else 'BROKEN'} "
             f"({a['entry_count']} entries) | 6/6 |",
             f"| Patient name, birth date or document type in email/SMS | {len(leaks['hits'])} in {leaks['emails']} emails "
             f"and {leaks['sms']} SMS | 0 |",
             f"| Jury-style documents (MedEng: other labs, wrong patient, namesake, typos) | {jury['wrongly_filed']}/{jury['n']} "
             f"wrongly filed" + (f" (95 % upper bound {jury['upper'] * 100:.1f} %)" if jury["upper"] is not None else "")
             + f"; {jury['same']}/{jury['n']} exactly as expected, {jury['to_review']} more sent to review (the safe side) | 0 wrongly filed |",
             "",
             "## Misdelivery tests (scenario/misdelivery.md, on request 1)", "",
             "| Test | Caught | Harm (M1/M2: anything shown; M3: anything filed) |", "|---|---|---|"]
    lines += [f"| {code} {MISDELIVERY[code]} | {m['caught']} runs | {m['harmed']} |" for code, m in mis.items()]
    eng = engine_results()
    if eng:
        lines += ["", "## AI engine (synthetic held-out set, see eval/RESULTS.md)", "", "| What | Result |", "|---|---|"] + eng
    if leaks["hits"]:
        lines += ["", "Leaks found:", *[f"- {h}" for h in leaks["hits"]]]
    lines += ["", "Matcher calibration and CIs: core/METRICS_matching.md. Stopwatch sheet: metrics/stopwatch.csv."]
    (ROOT / "METRICS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
