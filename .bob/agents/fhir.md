# FHIR agent

You are the **FHIR** agent for BefundBrücke.
Your job: `core/` (parser, matcher, FHIR builder), `app/identity/policy.py`, HL7 validator, and
any FHIR R4 correctness issues.
Read `AGENTS.md` first (shared contracts, gates, ownership map).

---

## Your open tasks

### P8 — HL7 validator rerun on bundles filed through the live stack  ← start here
**Goal:** Run `make validate` on bundles that were actually filed by the app (not only the
pre-built scenario bundles), and confirm 0 errors.

**Steps:**
1. `make reset && make up`.
2. Run `scripts/dev/flow.sh r1 r2` to file both requests.
3. The app writes filed bundles to `var/filed/`. Confirm two JSON files are there.
4. Run the HL7 validator on both: `make validate` (it looks in `var/filed/`).
   If it only validates the scenario files, update `scripts/validate_all.sh` to also
   scan `var/filed/*.json`.
5. Report `TOTAL_ERRORS` for each bundle. Target: 0.
6. If errors exist, fix them in `core/fhir_build.py`.

---

### P12 — Practitioner / Organization deduplication
**File:** `core/fhir_build.py`, `app/intake_service.py`
**Problem:** Each filed answer creates a new Practitioner and Organization resource with no
identifier. The same Dr. Eva Brandl from Labor Kanalstraße gets two entries on the second filing.
**Minimal fix:** Add a `system` + `value` identifier to Practitioner and Organization using a
synthetic system URI (`urn:befundbruecke:sender`) and the sender's name + org as the value.
Use `conditional create` (`ifNoneExist`) so HAPI deduplicates on repeat filings.
**Reference:** `app/fhir_client.py` already does transactions; the `ifNoneExist` parameter goes
in the `request.ifNoneExist` field of each Bundle entry.
**Test:** `test_second_filing_does_not_duplicate_practitioner`.
**Note:** Discuss with the COORDINATOR before changing `core/` (it is the most stable module).

---

### P14 — Name policy: double given names
**File:** `app/identity/policy.py`, `tests/test_policy.py`
**Problem:** "Eva Maria Brandl" in the eID against "Dr. Eva Brandl" in the request is blocked
(the rule requires every given name Dr. Hofer typed to appear in the eID in order — which works;
but it also requires the eID given names to appear *in order* without gaps, which blocks "Eva" if
"Maria" comes between it and "Brandl"). The README lists this as a known false block.
**Current rule (from DECISIONS.md):** "every given name she typed must be on the eID in order,
extra eID given names are allowed".
**Verify** by reading `app/identity/policy.py::names_match` and the 21 test cases in
`tests/test_policy.py`. Then decide:
- If the rule already handles this correctly (extra eID names are allowed) and the bug is a
  mismatch in how names are split, fix the splitting.
- If the rule itself is wrong, fix it and update `DECISIONS.md`.
**Test:** add `test_eid_extra_given_name_allowed` covering "Eva Maria Brandl" ↔ "Dr. Eva Brandl".

---

### ELGA LOINC codes (lower priority, belongs to ENGINE too)
**File:** `engine/lexicon.py`, `core/loinc.py`
**Issue (from DECISIONS.md):** ELGA's preferred LOINC codes differ from the seed for some tests.
Examples: Leukozyten 26464-8, Erythrozyten 26453-1, Hämatokrit 20570-8.
The `eval/data/external/elga_lab_loinc_de.csv` file has the full ELGA table.
**Task:** Read the CSV, find all rows where the ELGA preferred code differs from the current
`engine/lexicon.py` entry, and update the lexicon. Run `make test` and the jury-doc eval.
Coordinate with ENGINE agent (they own `engine/lexicon.py`).

---

## What "changing core/" means

`core/` is imported by both `app/` and `eval/`. Changes ripple everywhere.
Before changing any file in `core/`:
1. Run `make test` to get a green baseline.
2. Make the change.
3. Run `make test` + `uv run python -m metrics.eval_jury_docs` + `make validate`.
4. If any test breaks, fix it before continuing.
5. Add a `DECISIONS.md` entry: what changed, why, your agent name.

Never change `core/weights.json` without also rerunning `core/eval_matcher.py` and
updating `core/METRICS_matching.md`.

---

## Working rules for FHIR

- Branch: `fhir/<short-name>`.
- Every change to `core/` must pass `make test`, the jury-doc eval and `make validate`.
- Every change to `policy.py` must add or update a test in `tests/test_policy.py`.
- Never change `app/db.py` without COORDINATOR sign-off.
- Append to `PROGRESS.md` when done.
