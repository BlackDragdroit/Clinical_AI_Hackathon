# Clinical_AI_Hackathon

Skeleton for the Clinical AI Hackathon Vienna (29-30 Oct 2026): a minimal, runnable CSV -> FHIR pipeline with fixed interfaces. Preferred track: Health Data Interoperability (HL7 / FHIR). The concrete use case is announced on site and will be built on this skeleton.

**Synthetic or de-identified data only. Never commit real patient data.**

## Setup

Python >= 3.11.

PowerShell (Windows):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Run

```powershell
# Pipeline: CSV -> Bundle -> validation -> out/bundle.json  (add --push to send it to FHIR_BASE_URL)
python scripts/run_pipeline.py data/synthetic/patients_sample.csv

# API (http://127.0.0.1:8000/docs)
uvicorn hackathon.api.main:app --reload

# Streamlit demo
streamlit run src/hackathon/ui/app.py
```

## Tests and lint

```powershell
pytest                    # unit tests (integration tests are skipped by default)
pytest -m integration     # needs network: posts synthetic data to the public HAPI server
ruff check .
ruff format .
```

## Synthea (optional synthetic FHIR data)

Needs Java 11+. Downloads the pinned Synthea release (about 200 MB) and generates 20 patients into `data/synthetic/synthea/` (gitignored):

```powershell
python scripts/generate_synthea.py
```

If Java is missing, skip this; the CSV sample is enough for the skeleton. A tiny fixture may be committed under `tests/fixtures/`.

## Structure

```
CLAUDE.md, AGENTS.md    rules for agents (CLAUDE.md is authoritative)
src/hackathon/          ingest, mapping, validation, fhir_client, api, ui, pipeline.py
tests/                  unit/, integration/
data/synthetic/         synthetic sample data only
scripts/                run_pipeline.py, generate_synthea.py
docs/                   architecture, data ethics, pitch, submission, devin/
.github/                PR/issue templates, CI
```

## Team workflow

Issue (task template) -> branch (`devin/<issue-nr>-<name>` or `claude/<issue-nr>-<name>`) -> PR (template) -> review by Claude Code against the checklist in `CLAUDE.md` -> merge. Last merge by Friday 14:00, submission 15:00, pitch 16:00.
