# CLAUDE.md

## Purpose

Skeleton repo for the Clinical AI Hackathon Vienna (29-30 Oct 2026, 24 h). Preferred track: Health Data Interoperability (HL7 / FHIR). The track and the concrete use case are announced on site, so this repo is a working end-to-end skeleton with fixed interfaces, not a finished product. Do not pick a use case on your own.

## Architecture

Data flow: `ingest` -> `mapping` -> `validation` -> `fhir_client` / `api` -> `ui`.

| Module | Role |
|---|---|
| `src/hackathon/ingest/` | read raw input (CSV now) |
| `src/hackathon/mapping/` | raw records -> FHIR resources and transaction bundles |
| `src/hackathon/validation/` | FHIR schema validation |
| `src/hackathon/fhir_client/` | REST access to a FHIR server |
| `src/hackathon/api/` | FastAPI layer |
| `src/hackathon/ui/` | Streamlit demo (fallback if the UI is built elsewhere) |
| `src/hackathon/pipeline.py` | glue: records -> Bundle + validation (used by script, API, UI) |

## Stable interfaces

These signatures are the contract between parallel work (Claude Code, Devin sessions, teammates). **Change them only after agreement in the team, never silently inside a feature PR.**

- `ingest.csv_reader.read_records(path: Path) -> list[dict[str, str]]`
- `mapping.patient.map_patient(record: dict[str, str]) -> Patient`
- `mapping.bundle.to_transaction_bundle(resources: list[Resource]) -> Bundle`
- `validation.validate.validate_resource(data: dict, resource_type: str) -> ValidationResult` (`ok: bool`, `errors: list[str]`)
- `fhir_client.client.FhirClient(base_url)` with `post_bundle(bundle) -> dict` and `search(resource_type, params) -> dict`
- API: `GET /health`, `POST /convert` (CSV upload -> `{bundle, validation}`)

New mappers, resources and endpoints are additions, not changes. Add them next to the existing ones.

## FHIR version

`fhir.resources` 8.x defaults to FHIR R5. The public HAPI test server (`https://hapi.fhir.org/baseR4`) speaks R4. We therefore use the **`fhir.resources.R4B`** subpackage (FHIR 4.3.0, wire-compatible with R4 for the resources we use). Always import from `fhir.resources.R4B...`, never from the unversioned package.

## Conventions

- Python >= 3.11, type annotations and docstrings on public functions, small functions.
- `ruff check .` and `ruff format --check .` must pass; `pytest` must pass.
- No new dependencies without a justification in the PR.
- Commands must work in PowerShell (no Makefile- or Bash-only workflows); prefer Python scripts.
- Repo language is English (code, docs, commits).

## Data rule

Only synthetic or de-identified data. Never commit real patient data. No secrets in code; use `.env` (gitignored) and `.env.example`. The public HAPI server is world-readable.

## PR review checklist

1. Does the PR solve exactly the linked issue, nothing more?
2. Interfaces unchanged, or the change is justified and agreed?
3. Tests present and green (`pytest`), lint clean (`ruff check`)?
4. Does the mapping produce valid FHIR resources (validation runs in a test)?
5. No real data, no secrets, no unnecessary dependencies?
6. Is the demo (script, API, UI) still working afterwards?
