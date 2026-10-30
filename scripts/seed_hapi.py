"""Load scenario/patient.json into HAPI (PUT, so the id stays maria-beispiel), then warm up $validate. Owner: SWE 1."""
import json
import time
from pathlib import Path

import httpx

from app.config import settings

ROOT = Path(__file__).resolve().parent.parent
# A fresh HAPI loads its validator (LOINC, UCUM, profiles) on the first $validate, which took longer than the
# upload's timeout in the playtest. One realistic bundle here pays that cost before anyone uploads.
WARMUP = {"resourceType": "Bundle", "type": "transaction", "entry": [
    {"fullUrl": "urn:uuid:9b1c5c1e-0000-4000-8000-000000000001", "request": {"method": "POST", "url": "Observation"},
     "resource": {"resourceType": "Observation", "status": "final",
                  "code": {"coding": [{"system": "http://loinc.org", "code": "6301-6"}]},
                  "subject": {"reference": "Patient/maria-beispiel"},
                  "valueQuantity": {"value": 1.0, "system": "http://unitsofmeasure.org", "code": "{INR}"}}},
    {"fullUrl": "urn:uuid:9b1c5c1e-0000-4000-8000-000000000002", "request": {"method": "POST", "url": "DiagnosticReport"},
     "resource": {"resourceType": "DiagnosticReport", "status": "final",
                  "code": {"coding": [{"system": "http://loinc.org", "code": "11502-2"}]},
                  "subject": {"reference": "Patient/maria-beispiel"},
                  "result": [{"reference": "urn:uuid:9b1c5c1e-0000-4000-8000-000000000001"}]}}]}

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
    t0 = time.monotonic()
    r = httpx.post(f"{settings.hapi_url}/Bundle/$validate", json=WARMUP,       # the verdict does not matter here
                   headers={"Content-Type": "application/fhir+json"}, timeout=300)
    print(f"HAPI $validate warmed up in {time.monotonic() - t0:.0f} s (HTTP {r.status_code})")
