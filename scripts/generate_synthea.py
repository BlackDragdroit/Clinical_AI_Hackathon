"""Download Synthea (pinned release) and generate ~20 synthetic patients as FHIR R4 JSON.

Needs Java 11+ on PATH. Output goes to data/synthetic/synthea/ (gitignored).
Usage: python scripts/generate_synthea.py [--population 20]
"""

import argparse
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

SYNTHEA_VERSION = "v4.0.0"
JAR_URL = (
    "https://github.com/synthetichealth/synthea/releases/download/"
    f"{SYNTHEA_VERSION}/synthea-with-dependencies.jar"
)
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "synthetic" / "synthea" / "_tools"
OUT_DIR = ROOT / "data" / "synthetic" / "synthea"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)  # seed 42 hung with v4.0.0
    parser.add_argument("--state", default="Massachusetts", help="US state (Synthea limitation)")
    args = parser.parse_args()

    if shutil.which("java") is None:
        print("Java not found on PATH; install Java 11+ to use Synthea.", file=sys.stderr)
        return 1

    jar = CACHE_DIR / f"synthea-{SYNTHEA_VERSION}.jar"
    if not jar.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {JAR_URL} (about 200 MB) ...")
        urllib.request.urlretrieve(JAR_URL, jar)

    command = [
        "java", "-jar", str(jar),
        "-p", str(args.population),
        "-s", str(args.seed),
        "--exporter.baseDirectory", str(OUT_DIR),
        "--exporter.fhir.export", "true",
        args.state,  # Synthea only supports US states (demographics are US-based)
    ]  # fmt: skip
    print("Running:", " ".join(command))
    return subprocess.call(command)


if __name__ == "__main__":
    sys.exit(main())
