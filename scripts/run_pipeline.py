"""CSV -> FHIR Bundle -> validation -> JSON file, optionally pushed to a FHIR server.

Usage: python scripts/run_pipeline.py data/synthetic/patients_sample.csv [--out PATH] [--push]
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from hackathon.fhir_client.client import FhirClient
from hackathon.ingest.csv_reader import read_records
from hackathon.pipeline import convert_records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="input CSV file")
    parser.add_argument(
        "--out", type=Path, default=Path("out/bundle.json"), help="output JSON file"
    )
    parser.add_argument("--push", action="store_true", help="POST the bundle to FHIR_BASE_URL")
    args = parser.parse_args()

    load_dotenv()
    bundle, result = convert_records(read_records(args.csv))
    bundle_json = bundle.model_dump(mode="json", exclude_none=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bundle_json, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(bundle_json.get('entry', []))} entries)")

    if not result.ok:
        print("Validation FAILED:", *result.errors, sep="\n  ")
        return 1
    print("Validation OK")

    if args.push:
        base_url = os.getenv("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4")
        response = FhirClient(base_url).post_bundle(bundle_json)
        print(f"Pushed to {base_url}: {response.get('resourceType')} {response.get('type')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
