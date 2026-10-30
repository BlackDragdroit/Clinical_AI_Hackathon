"""First thing to run when the GPU box is up: does each model answer, and how fast?

uv run python -m scripts.gpu_smoke [--engine http://<vm>:8100]

Sends request 1 as text, request 1 as synthetic speech (if a WAV is given with --wav), the lab result as PDF
and as a rendered phone photo, and prints what came back with timings. Exit code 1 if anything is missing.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

from eval.render import md_to_pdf, photo

ROOT = Path(__file__).resolve().parent.parent
REQ1 = ("Bitte bei Dr. Eva Brandl, eva.brandl@labor-kanal.example, die aktuelle Gerinnung von Frau Maria Beispiel, "
        "geb. 12.03.1961, anfordern, vor dem geplanten Eingriff.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="http://localhost:8100")
    ap.add_argument("--wav", help="a recording of a request (German or English)")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.engine, timeout=180)
    ok = True
    print("health:", json.dumps(c.get("/health").json()))

    t = time.perf_counter()
    r = c.post("/v1/request", json={"text": REQ1}).json()
    print(f"\ntext request ({time.perf_counter() - t:.2f}s): ready={r['ready']} llm={r['models']} "
          f"recipient={r['recipient']} contact={r['contact']} flags={r['flags']} dropped={r['dropped_ungrounded']}")
    ok &= bool(r["models"].get("llm")) and not r["models"].get("llm_error")

    if a.wav:
        t = time.perf_counter()
        r = c.post("/v1/request/audio", files={"file": (Path(a.wav).name, Path(a.wav).read_bytes())}).json()
        print(f"\nvoice request ({time.perf_counter() - t:.2f}s): asr={r.get('asr')} ready={r.get('ready')}")
        ok &= bool((r.get("asr") or {}).get("text"))

    md = (ROOT / "scenario/documents/lab-result-maria-beispiel.md").read_text(encoding="utf-8")
    pdf = md_to_pdf(md)
    for name, data, ctype in (("befund.pdf", pdf, "application/pdf"), ("foto.jpg", photo(pdf, seed=1), "image/jpeg")):
        t = time.perf_counter()
        r = c.post("/v1/document", files={"file": (name, data, ctype)},
                   data={"requested_loinc": "6301-6,14979-9,777-3,3255-7", "requested_doc_type": "lab"}).json()
        rows = (r.get("parsed") or {}).get("rows", [])
        agree = [i["agree"] for i in r.get("readback", [])]
        print(f"\n{name} ({time.perf_counter() - t:.2f}s): path={r['path']} ok={r['ok']} rows={[(x['test'], x['result'], x['unit']) for x in rows]}"
              f"\n  models={r['models']} readback_agree={agree.count(True)}/{len(agree)} checks={r['check_lines_de']}")
        ok &= r["ok"]
    print("\nOK" if ok else "\nSOMETHING IS MISSING (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
