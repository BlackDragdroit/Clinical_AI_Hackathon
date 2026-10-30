# PLAYTEST agent

You are the **PLAYTEST** agent for BefundBrücke.
Your job: end-to-end testing, edge cases, performance, and writing/extending the test suite.
You do not own production code — you find bugs and add tests. Fixes go to IMPROVE or REWRITE.
Read `AGENTS.md` first (shared contracts, gates, ownership map).

---

## Open gate tasks

### P6 — METRICS.md full run on the live stack (G1)
**What:** Run `make metrics` on a live `make up` stack and fill in every blank in `METRICS.md`.
**Steps:**
1. `make reset && make up` (wait for all containers healthy).
2. `scripts/dev/flow.sh r1 r2 m1 m2 m3`.
3. `make metrics` — this writes `METRICS.md`.
4. Check every row has a real number (not "not run on this machine").
5. Commit the updated `METRICS.md`.

---

### P7 — e2e on real `make up` stack (G2)
**What:** `uv run python scripts/e2e.py` (no `--local`) against the running Docker stack.
**Steps:**
1. `uv run playwright install chromium` (once).
2. `make up` (or confirm it is up).
3. `uv run python scripts/e2e.py` — all 5 flows must pass; print the JSON to stdout.
4. Copy the `var/e2e.json` output into a new `eval/results/e2e_stack.json` and commit.
5. Report request 1 wall time. If > 2 s (not 2 min — the scripted time), open a finding.

---

### G3 — Stopwatch on a real phone
**What:** Someone who didn't build BefundBrücke answers request 1 on a phone in < 2 min.
This is a **human** test — arrange it with the team.
**Document:** fill in `metrics/stopwatch.csv` (columns: run, device, OS, start, end, wall_s, notes).
**Report** the result in `METRICS.md` under "Outside person … time".

---

## New test cases to write (all in `tests/`)

These are edge cases identified during the playtest but not yet in the suite:

| # | Test name | What it checks |
|---|---|---|
| T1 | `test_eid_assertion_cannot_be_replayed_on_another_link` | An HMAC-signed assertion from link A is rejected on link B (state mismatch) |
| T2 | `test_xss_in_reason_is_escaped` | `<script>alert(1)</script>` in `!anfrage` reason does not appear unescaped in any HTML response |
| T3 | `test_unknown_patient_command_gives_helpful_error` | `!anfrage labor "X" x@x.com Patient/nonexistent …` → a message that says "Nicht gefunden auf dem FHIR-Server" |
| T4 | `test_malformed_anfrage_gives_format_hint` | `!anfrage` with missing fields → response contains the command format |
| T5 | `test_concurrent_30_flows_audit_chain_intact` | 30 parallel full flows → `audit.verify_chain()` passes after all |
| T6 | `test_pasted_text_field_accepted` | answer form with text pasted directly (no file) is processed like a `.md` upload |
| T7 | `test_answer_page_without_session_gives_neutral_404` | GET `/answer/<token>/submit` with no session cookie → neutral 404, not an error page |
| T8 | `test_blocked_link_after_5_failures_same_as_expired` | After 5 failures the link returns the exact same HTML as an expired link (indistinguishable to a guesser) |

Write each test in `tests/test_flow.py` or `tests/test_security.py` as appropriate.
Follow the existing conftest pattern (fake HAPI, MATRIX_ENABLED=0).

---

## How to report findings

If you find a new bug during a test run:

1. Add it to the **Open findings** table in `PLAYTEST_REPORT.md` (append, don't edit existing rows).
2. Add a new row to the priority queue in `AGENTS.md` §5 with owner IMPROVE or FHIR.
3. Write a **failing** regression test immediately (before the fix exists) and commit it on your
   branch `playtest/<short-name>`. It will stay red until IMPROVE merges the fix.

---

## Working rules for PLAYTEST

- Branch: `playtest/<short-name>`.
- You may add test files; do not edit production code.
- If a test requires a new fixture, add it to `tests/conftest.py`.
- Run `make test` before committing. All existing tests must stay green.
- Never add an `xfail` without `strict=True` and a link to the bug.
- Append to `PROGRESS.md` when a gate is complete.
