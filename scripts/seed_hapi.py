"""Load scenario/patient.json into HAPI (PUT, so the id stays maria-beispiel). Owner: SWE 1."""
import json
import time
from pathlib import Path

import httpx

from app.config import settings

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    patient = json.loads((ROOT / "scenario" / "patient.json").read_text())
    for _ in range(90):          # HAPI needs ~1 min on first start
        try:
            httpx.get(f"{settings.hapi_url}/metadata", timeout=5).raise_for_status()
            break
        except httpx.HTTPError:
            print("waiting for HAPI …", flush=True)
            time.sleep(3)
    r = httpx.put(f"{settings.hapi_url}/Patient/{patient['id']}", json=patient,
                  headers={"Content-Type": "application/fhir+json"}, timeout=20)
    r.raise_for_status()
    print("seeded", f"Patient/{patient['id']}", r.status_code)
