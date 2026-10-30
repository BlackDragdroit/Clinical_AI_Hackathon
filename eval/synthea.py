"""Synthea patients and their real lab values -> eval/data/synthea_labs.json.

Synthea (pinned v4.0.0, US demographics only) gives birth dates, sexes and LOINC-coded lab results with units and
dates. Names are replaced later by Austrian ones (eval/build_data.py); the clinical content stays Synthea's.

uv run python -m eval.synthea [--population 400] [--seed 7]      (Java 11+; the jar is cached in tools/, ~200 MB)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

VERSION = "v4.0.0"
JAR_URL = f"https://github.com/synthetichealth/synthea/releases/download/{VERSION}/synthea-with-dependencies.jar"
ROOT = Path(__file__).resolve().parent.parent
JAR = ROOT / "tools" / f"synthea-{VERSION}.jar"
OUT = ROOT / "eval" / "data" / "synthea"
LABS = ROOT / "eval" / "data" / "synthea_labs.json"


def run(population: int, seed: int) -> None:
    if shutil.which("java") is None:
        sys.exit("Java not found; install Java 11+.")
    if not JAR.exists():
        JAR.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {JAR_URL} …", flush=True)
        urllib.request.urlretrieve(JAR_URL, JAR)
    cmd = ["java", "-jar", str(JAR), "-p", str(population), "-s", str(seed), "--exporter.baseDirectory", str(OUT),
           "--exporter.fhir.export", "true", "--exporter.hospital.fhir.export", "false",
           "--exporter.practitioner.fhir.export", "false", "--generate.only_alive_patients", "true", "Massachusetts"]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def extract() -> list[dict]:
    """Per patient: birth date, sex, and lab Observations (LOINC, value, unit, effective date)."""
    out = []
    for f in sorted((OUT / "fhir").glob("*.json")):
        b = json.loads(f.read_text(encoding="utf-8"))
        pat, labs = None, []
        for e in b.get("entry", []):
            r = e["resource"]
            if r["resourceType"] == "Patient":
                pat = r
            elif r["resourceType"] == "Observation" and "valueQuantity" in r and any(
                    c.get("code") == "laboratory" for cat in r.get("category", []) for c in cat.get("coding", [])):
                coding = next((c for c in r["code"].get("coding", []) if c.get("system") == "http://loinc.org"), None)
                if coding:
                    q = r["valueQuantity"]
                    labs.append({"loinc": coding["code"], "display": coding.get("display", ""), "value": q.get("value"),
                                 "unit": q.get("unit") or q.get("code") or "", "date": (r.get("effectiveDateTime") or "")[:19]})
        if pat and labs:
            out.append({"synthea_id": pat["id"], "birthDate": pat.get("birthDate"), "gender": pat.get("gender"), "labs": labs})
    LABS.parent.mkdir(parents=True, exist_ok=True)
    LABS.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)          # seed 42 hung with v4.0.0 (team note)
    ap.add_argument("--extract-only", action="store_true")
    a = ap.parse_args()
    if not a.extract_only:
        run(a.population, a.seed)
    pts = extract()
    print(f"{len(pts)} patients with labs -> {LABS}")
