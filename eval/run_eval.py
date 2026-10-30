"""Engine evaluation -> eval/results/<run>.json, then eval/RESULTS.md from all runs.

  python -m eval.run_eval requests --set dev|test|human --rung rules            (CPU, no model)
  python -m eval.run_eval requests --set test --rung nuextract3 --llm-url http://<vm>:8001/v1 \
         --llm-model numind/NuExtract3 --llm-mode nuextract
  python -m eval.run_eval documents --forms md,pdf,scan,photo --rung rules
  python -m eval.run_eval report                                                  (rebuild RESULTS.md)

Safety numbers come first and use exact (Clopper–Pearson) intervals, because with 0 events a bootstrap
collapses to [0, 0]. Accuracy uses Wilson intervals.
  silent error      the card was "ready" but a required field was wrong (Dr. Hofer still confirms, but nothing warned)
  wrong patient     the engine picked a patient other than the gold one
  wrong value filed a document took an auto-file path (Markdown, PDF text, model fallback) with a value that differs
                    from the source; OCR answers never auto-file, so for them we count values two readers agreed on
                    that were still wrong
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "eval" / "data"
RESULTS = ROOT / "eval" / "results"


# ---------------------------------------------------------------- statistics
def _binom_cdf(k: int, n: int, p: float) -> float:
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0 if k < n else 1.0
    return sum(math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * math.log(p) + (n - i) * math.log1p(-p))
               for i in range(k + 1))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    def solve(f, lo=0.0, hi=1.0):
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) else (lo, mid)
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(lambda p: 1 - _binom_cdf(k - 1, n, p) < alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: _binom_cdf(k, n, p) > alpha / 2)
    return lower, upper


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def rate(k: int, n: int, exact: bool = False) -> dict:
    lo, hi = clopper_pearson(k, n) if exact else wilson(k, n)
    return {"k": k, "n": n, "p": k / n if n else None, "lo": lo, "hi": hi}


def pct(q: list[float], p: float) -> float | None:
    if not q:
        return None
    q = sorted(q)
    return q[min(len(q) - 1, int(round(p * (len(q) - 1))))]


# ---------------------------------------------------------------- requests
def _load(name: str) -> list[dict]:
    path = DATA / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def eval_requests(items: list[dict], use_llm: bool, audio_dir: Path | None = None, use_rules: bool = True) -> dict:
    from engine import request_job
    from engine._core import norm_tokens
    from engine.backends import asr
    from engine.patients import MemoryDirectory

    directory = MemoryDirectory(json.loads((DATA / "patients.json").read_text(encoding="utf-8")))
    per, lat = [], []
    for it in items:
        g = it["gold"]
        text, asr_info = it["text"], None
        if audio_dir and (audio_dir / f"{it['id']}.wav").exists():
            r = asr.transcribe((audio_dir / f"{it['id']}.wav").read_bytes(), f"{it['id']}.wav")
            asr_info = {"text": r.text, "ms": r.ms, "error": r.error}
            text = r.text or ""
        t0 = time.perf_counter()
        res = request_job.run(text, directory, use_llm=use_llm, use_rules=use_rules)
        cached_llm = res["timings_ms"]["llm"] if res["models"].get("llm_cached") else 0   # a cached answer reports its original time
        lat.append((time.perf_counter() - t0) * 1000 + cached_llm + (asr_info or {}).get("ms", 0))
        picked = res["patient"]["ref"] if res["patient"]["status"] in ("unique", "explicit") else None
        ok = {
            "recipient": bool(res["recipient"]) and norm_tokens(res["recipient"]) == norm_tokens(g["recipient"]),
            "contact": (res["contact"] is None) if it.get("trap") == "no_contact"
                       else bool(res["contact"]) and res["contact"]["value"] == g["contact"],
            "patient": picked == g["patient_ref"],
            "doc_type": res["doc_type"] == g["doc_type"],
            "panel": ((res["panel"] or {}).get("key") == g["panel"]) if g["doc_type"] == "lab" and g["panel"] else True,
            "ready": res["ready"] == g["ready"],
        }
        required = ok["recipient"] and ok["contact"] and ok["patient"] and ok["doc_type"]
        per.append({"id": it["id"], "trap": it.get("trap", "none"), "lang": it.get("lang"), "style": it.get("style"), "ok": ok,
                    "full": ok["ready"] and (required if g["ready"] else True),
                    "silent_error": res["ready"] and not required and not res["flags"],   # wrong and nothing warned
                    "flagged_wrong": res["ready"] and not required and bool(res["flags"]),
                    "wrong_patient": picked is not None and picked != g["patient_ref"],
                    "dropped": len(res.get("dropped_ungrounded", [])), "llm_error": res["models"].get("llm_error"),
                    "asr": asr_info, "got": {"recipient": res["recipient"], "contact": res["contact"], "patient": picked,
                                             "doc_type": res["doc_type"], "ready": res["ready"], "missing": res["missing"]}})
    n = len(per)
    out = {"n": n,
           "safety": {"silent_error": rate(sum(p["silent_error"] for p in per), n, exact=True),
                      "flagged_wrong": rate(sum(p.get("flagged_wrong", False) for p in per), n, exact=True),
                      "wrong_patient": rate(sum(p["wrong_patient"] for p in per), n, exact=True)},
           "full_request": rate(sum(p["full"] for p in per), n),
           "fields": {f: rate(sum(p["ok"][f] for p in per), n) for f in ("recipient", "contact", "patient", "doc_type", "panel", "ready")},
           "by_trap": {}, "by_lang_style": {},
           "latency_ms": {"p50": pct(lat, 0.5), "p95": pct(lat, 0.95)},
           "dropped_ungrounded_values": sum(p["dropped"] for p in per),
           "llm_errors": sum(1 for p in per if p["llm_error"] and p["llm_error"] != "disabled"),
           "items": per}
    for key, field in (("by_trap", "trap"), ("by_lang_style", None)):
        groups: dict[str, list] = {}
        for p in per:
            k = p[field] if field else f"{p['lang']}/{p['style']}"
            groups.setdefault(k, []).append(p)
        out[key] = {k: rate(sum(x["full"] for x in v), len(v)) for k, v in sorted(groups.items())}
    return out


# ---------------------------------------------------------------- documents
def _render(doc: dict, form: str) -> tuple[bytes, str, str]:
    from eval.render import md_to_pdf, photo, scan
    cache = DATA / "docs"
    cache.mkdir(parents=True, exist_ok=True)
    ext = {"md": "md", "pdf": "pdf", "scan": "jpg", "photo": "jpg"}[form]
    path = cache / f"{doc['id']}.{form}.{ext}"
    if not path.exists():
        md = doc["markdown"]
        seed = int(doc["id"].split("-")[1])
        data = {"md": lambda: md.encode("utf-8"), "pdf": lambda: md_to_pdf(md),
                "scan": lambda: scan(md_to_pdf(md), seed), "photo": lambda: photo(md_to_pdf(md), seed)}[form]()
        path.write_bytes(data)
    ctype = {"md": "text/markdown", "pdf": "application/pdf", "scan": "image/jpeg", "photo": "image/jpeg"}[form]
    return path.read_bytes(), path.name, ctype


def eval_documents(docs: list[dict], forms: list[str], use_models: bool) -> dict:
    from engine import document_job
    from engine._core import parse_dob
    from app.core_bridge import Person, run_intake

    out: dict = {}
    for form in forms:
        per, lat = [], []
        for d in docs:
            data, name, ctype = _render(d, form)
            rq = d["request"]
            t0 = time.perf_counter()
            res = document_job.read(data, name, ctype, rq["requested_loinc"], datetime.fromisoformat(rq["requested_at"]),
                                    rq["doc_type"], use_models=use_models)
            lat.append((time.perf_counter() - t0) * 1000)
            g = d["gold"]
            rec = {"id": d["id"], "trap": d["trap"], "ok": res["ok"], "path": res["path"]}
            if res["ok"]:
                p = res["parsed"]
                got_rows = p["rows"]
                fields = [("patient_name", p["patient_name"], g["patient_name"]),
                          ("patient_dob", p["patient_dob"], g["patient_dob"])]
                for i, gr in enumerate(g["rows"]):
                    r = got_rows[i] if i < len(got_rows) else {}
                    for k in ("result", "unit", "reference_range"):
                        fields.append((f"rows.{i}.{k}", r.get(k, ""), gr[k]))
                wrong = [f for f, got, want in fields if (got or "") != (want or "")]
                rec.update(n_fields=len(fields), wrong=wrong, rows_got=len(got_rows), rows_want=len(g["rows"]))
                if res["needs_readback"]:
                    agreed = {i["key"]: i for i in res["readback"] if i["agree"]}
                    gold_by_key = {f: want for f, _, want in fields}
                    rec["readback_items"] = len(res["readback"])
                    rec["agreed"] = len(agreed)
                    rec["agreed_wrong"] = sum(1 for k, i in agreed.items() if k in gold_by_key and (i["value"] or "") != (gold_by_key[k] or ""))
                else:
                    rec["wrong_value_filed"] = bool(wrong)
                    typed = Person.from_full(g["patient_name"], g["patient_dob"])     # sender copies from the document
                    decision = run_intake(res["canonical_markdown"], Person.from_full(rq["patient_name"], rq["patient_dob"]),
                                          typed, rq["sender"], "", "eval", rq["patient_ref"], name).decision
                    rec["decision"], rec["decision_ok"] = decision, decision == g["decision"]
                    rec["wrongly_filed"] = decision == "file" and g["decision"] != "file"
                flags = " ".join(res["flags"])
                rec["flag_old"] = "Tage alt" in flags
                rec["flag_implausible"] = "unplausibel" in flags or "Einheit" in flags
            per.append(rec)
        n = len(per)
        auto = [p for p in per if p["ok"] and "wrong_value_filed" in p]
        ocr = [p for p in per if p["ok"] and "agreed" in p]
        planted_old = [p for p in per if p["trap"] == "old" and p["ok"]]
        planted_imp = [p for p in per if p["trap"] == "implausible" and p["ok"]]
        out[form] = {
            "n": n, "read": rate(sum(p["ok"] for p in per), n),
            "safety": {"wrong_value_filed": rate(sum(p["wrong_value_filed"] for p in auto), len(auto), exact=True),
                       "wrongly_filed_patient": rate(sum(p["wrongly_filed"] for p in auto), len(auto), exact=True),
                       "ocr_agreed_but_wrong": rate(sum(p["agreed_wrong"] for p in ocr), sum(p["agreed"] for p in ocr), exact=True)},
            "field_exact": rate(sum(p["n_fields"] - len(p["wrong"]) for p in per if p["ok"]), sum(p["n_fields"] for p in per if p["ok"])),
            "decision": rate(sum(p["decision_ok"] for p in auto), len(auto)),
            "ocr_agreement_coverage": rate(sum(p["agreed"] for p in ocr), sum(p["readback_items"] for p in ocr)),
            "checks_recall": {"old": rate(sum(p["flag_old"] for p in planted_old), len(planted_old)),
                              "implausible": rate(sum(p["flag_implausible"] for p in planted_imp), len(planted_imp))},
            "false_alarm_old": rate(sum(p.get("flag_old", False) for p in per if p["ok"] and p["trap"] != "old"),
                                    sum(1 for p in per if p["ok"] and p["trap"] != "old")),
            "paths": {k: sum(1 for p in per if p["path"] == k) for k in {p["path"] for p in per}},
            "latency_ms": {"p50": pct(lat, 0.5), "p95": pct(lat, 0.95)},
            "items": per,
        }
    return out


# ---------------------------------------------------------------- report
def _r(x: dict | None, digits: int = 1) -> str:
    if not x or x["n"] == 0 or x["p"] is None:
        return "–"
    return f"{100 * x['p']:.{digits}f} % [{100 * x['lo']:.{digits}f}, {100 * x['hi']:.{digits}f}] ({x['k']}/{x['n']})"


def report() -> None:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS.glob("*.json"))
            if p.name.startswith(("requests_", "documents_"))]          # voice_*.json: eval/VOICE.md
    lines = ["# Engine evaluation", "",
             "Generated by `make engine-eval` from `eval/results/*.json`. 95 % intervals: exact (Clopper–Pearson) for the safety "
             "rows, Wilson for accuracy. Synthetic data only; see eval/build_data.py and DECISIONS.md for how each set was made.", ""]
    req = [r for r in runs if r["task"] == "requests"]
    if req:
        lines += ["## Request job (Dr. Hofer's sentence → checked request)", "",
                  "| set | rung | n | silent error | wrong but flagged | wrong patient picked | full request correct | contact exact | patient | latency p50 / p95 |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for r in req:
            m = r["metrics"]
            lines.append(f"| {r['set']} | {r['rung']} | {m['n']} | {_r(m['safety']['silent_error'])} | {_r(m['safety'].get('flagged_wrong'))} | {_r(m['safety']['wrong_patient'])} | "
                         f"{_r(m['full_request'])} | {_r(m['fields']['contact'])} | {_r(m['fields']['patient'])} | "
                         f"{m['latency_ms']['p50']:.0f} / {m['latency_ms']['p95']:.0f} ms |")
        lines += ["", "Per trap (full request correct):", "", "| set | rung | " + " | ".join(sorted({t for r in req for t in r["metrics"]["by_trap"]})) + " |",
                  "|---|---|" + "---|" * len({t for r in req for t in r["metrics"]["by_trap"]})]
        traps = sorted({t for r in req for t in r["metrics"]["by_trap"]})
        for r in req:
            bt = r["metrics"]["by_trap"]
            lines.append(f"| {r['set']} | {r['rung']} | " + " | ".join(
                f"{100 * bt[t]['p']:.0f} % ({bt[t]['k']}/{bt[t]['n']})" if t in bt else "–" for t in traps) + " |")
        lines.append("")
    docs = [r for r in runs if r["task"] == "documents"]
    if docs:
        lines += ["## Document job (answer → canonical Markdown → core)", "",
                  "| rung | form | n | read | wrong value auto-filed | wrong patient filed | OCR: agreed but wrong | field exact | decision correct | latency p50 / p95 |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for r in docs:
            for form, m in r["metrics"].items():
                lines.append(f"| {r['rung']} | {form} | {m['n']} | {_r(m['read'])} | {_r(m['safety']['wrong_value_filed'])} | "
                             f"{_r(m['safety']['wrongly_filed_patient'])} | {_r(m['safety']['ocr_agreed_but_wrong'], 2)} | {_r(m['field_exact'])} | "
                             f"{_r(m['decision'])} | {m['latency_ms']['p50']:.0f} / {m['latency_ms']['p95']:.0f} ms |")
        lines += ["", "Checks on planted problems (recall): old sample, implausible value.", ""]
        for r in docs:
            for form, m in r["metrics"].items():
                lines.append(f"- {r['rung']} / {form}: old {_r(m['checks_recall']['old'])}, implausible {_r(m['checks_recall']['implausible'])}, "
                             f"false alarm 'old' {_r(m['false_alarm_old'])}; paths {m['paths']}")
        lines.append("")
    (ROOT / "eval" / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", choices=["requests", "documents", "report"])
    ap.add_argument("--set", default="dev")
    ap.add_argument("--rung", default="rules", help="name for this model setup; 'rules' disables all models")
    ap.add_argument("--llm-url"), ap.add_argument("--llm-model"), ap.add_argument("--llm-mode")
    ap.add_argument("--asr-url"), ap.add_argument("--ocr-url")
    ap.add_argument("--audio-dir", help="eval/data/audio/<set>: <id>.wav per request -> voice evaluation")
    ap.add_argument("--forms", default="md,pdf")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-rules", action="store_true", help="model alone (requests): ignore what the rules found")
    a = ap.parse_args()
    if a.task == "report":
        return report()
    for k, v in (("ENGINE_LLM_URL", a.llm_url), ("ENGINE_LLM_MODEL", a.llm_model), ("ENGINE_LLM_MODE", a.llm_mode),
                 ("ENGINE_ASR_URL", a.asr_url), ("ENGINE_OCR_URL", a.ocr_url)):
        if v:
            os.environ[k] = v
    use = not a.rung.startswith("rules")
    if a.task == "requests":
        items = _load(f"requests_{a.set}.jsonl")[: a.limit]
        if not items:
            sys.exit(f"no items in eval/data/requests_{a.set}.jsonl")
        metrics = eval_requests(items, use, Path(a.audio_dir) if a.audio_dir else None, use_rules=not a.no_rules)
        name = f"requests_{a.set}_{a.rung}" + ("_voice" if a.audio_dir else "")
    else:
        docs = _load("documents.jsonl")[: a.limit]
        metrics = eval_documents(docs, a.forms.split(","), use)
        name = f"documents_{a.rung}"
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps({"task": a.task, "set": a.set, "rung": a.rung, "at": datetime.now().isoformat(timespec="seconds"),
                                                      "metrics": metrics}, ensure_ascii=False, indent=1), encoding="utf-8")
    report()


if __name__ == "__main__":
    main()
