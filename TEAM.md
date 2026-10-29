# Who does what

**Deadlines:** building closes **Thu 22:00**. Submission is **Fri 15:00**: a video of at most 2 min, the public repo and the metric results. **Code freeze is Fri 13:30.**

## Where we start

The thin slice already works **in tests**, with HAPI faked: request 1 by email, request 2 by SMS, M1, M2 and M3 are all caught, the audit log covers 6 of 6 steps, and the hash chain verifies. `make test` reports 26 passed and 4 xfailed.

**M0 is done:** `make up` brings up the real stack, and request 1, request 2 and M1–M3 have been run on it. See PROGRESS.md. The HL7 validator hasn't been run yet. Each person below owns their files: make them work for real, make them good, and prove it with a gate.

```
make install && make test        # everyone, first thing
make dev                         # app on :8000 without Docker (Matrix messages print to the console)
uv run python -m app.cli '!anfrage labor "Dr. Eva Brandl" eva.brandl@labor-kanal.example Patient/maria-beispiel Grund: Gerinnung vor Eingriff'
```

## Shared contracts: don't change these without telling everyone

| Contract | File | Used by |
|---|---|---|
| SQLite schema and status lifecycle | `app/db.py` | all |
| `audit.log(event, request_id, actor, details)`: 6 required events plus the extras | `app/audit.py` | all |
| `notify.doctor(text, request_id)`: outbox that the bot or the console drains | `app/notify.py` | MedEng, SWE 2 → SWE 1 |
| `Channel.send(to, link)`: receives only the link, never patient data | `app/delivery/base.py` | SWE 2, SWE 1 |
| `EidAssertion` from `eid_mock.verify()` | `app/identity/eid_mock.py` | SWE 2, MedEng |
| `process_answer(req, …)` → decision, `sender_message_de`, `answer_id` | `app/intake_service.py` | SWE 2 → MedEng |
| `commands.handle(text, sender)` → reply (shared by the bot and the CLI) | `app/commands.py` | SWE 1 |
| `core/` is the finished matcher and FHIR builder: **import it, don't edit it** (changes go through MedEng + Biostat) | `core/`, `app/core_bridge.py` | — |

## Working rules

- Work on a branch per person (`swe1/…`, `swe2/…`, `medeng/…`, `biostat/…`). Keep PRs small. Merge to `main` only when `make test` is green.
- Never weaken a test to get green. Each `xfail(strict=True)` marks work that's owed: remove the marker when your code makes the test pass.
- Synthetic data only. Never put a patient name, birth date or document type into an email, an SMS or a URL (Hard rule 1; `tests/test_template_leak.py` checks this).
- Every `TODO(<role>)` in the code belongs to that person. Find yours with `grep -rn "TODO(SWE 1)" app scripts metrics`.
- After each milestone, add 3 lines to `PROGRESS.md`: what works, what's next, what's broken.

---

## SWE 1: stack, Matrix bot, FHIR server

**Owns:** `docker-compose.yml`, `Dockerfile`, `Makefile`, `scripts/setup_synapse.sh`, `scripts/seed_hapi.py`, `app/bot.py`, `app/commands.py`, `app/requests_service.py`, `app/fhir_client.py`, `app/config.py`, `app/delivery/ftapi_submitbox.py`, `element/config.json`.

**Status: done (Thu 21:45).** G1 and G2 are verified (see PROGRESS.md). All `TODO(SWE 1)` items are closed: real HAPI client with Task executionPeriod + input, bot limited to `AUTHORIZED_SENDERS`, HTML cards with clickable FHIR links, README Architecture + "every component is replaceable". FTAPI is deliberately not used (see DECISIONS.md).

**Friday (to 13:30): support the team**
- Keep the stack healthy for everyone. `scripts/dev/flow.sh` replays request 1 / M1–M3 against the running stack in seconds; use it after every merge to `main`.
- Help SWE 2 wire `scripts/e2e.py` (Playwright) to the same flows, and help Biostat with `make metrics`.
- Before 13:30: `make reset && make up` from a clean clone, then run `scripts/dev/flow.sh` once for each case.

**Done when**
- G1 `make up` from a clean clone (`make reset` first) ends with Element reachable and `curl -s localhost:8090/fhir/Patient/maria-beispiel` returning the patient.
- G2 Request 1 runs end to end in Element: Dr. Hofer gets the ✅ message with links, and HAPI has the Observations + DiagnosticReport + DocumentReference + Provenance + Task completed.

---

## SWE 2: outside portal (links, delivery, eID)

**Owns:** `app/main.py` (portal routes), `app/templates/*.html`, `app/templates/messages/*`, `app/tokens.py`, `app/security.py`, `app/delivery/smtp_mailpit.py`, `app/delivery/sms_inbox.py`, `app/identity/eid_mock.py`, `tests/test_template_leak.py`, `tests/test_tokens_eid.py`, Playwright scripts (new: `scripts/e2e.py`).

**Tonight**
1. Work against `make dev` + Mailpit only (`docker compose up -d mailpit`). You don't need Matrix.
2. Make the portal mobile-first and nice to use: big tap targets, clear steps (1. confirm identity → 2. upload → done), and a DE/EN toggle. The text before identity stays **exactly** neutral: "Klinikum Beispielstadt hat eine sichere Dokumentenanfrage an Sie gerichtet."
3. Make the mock eID page look like a believable ID Austria handoff, clearly labelled as a simulation.

**Friday**
- Blocking: when attempts run out, set the request to `blocked`, show the same neutral page, and alert Dr. Hofer once.
- Answer form: show a preview of what was parsed (number of rows, patient as found in the document) before final send? Decide with MedEng and keep the flow under 2 min.
- HTML email part with a big button. Add `secure=True` on the cookie behind HTTPS.
- `scripts/e2e.py` (Playwright): request 1 with wall time, request 2 via `/sms`, M1, M2, M3. Biostat reads its JSON output.
- PDF upload: decide with MedEng (text extraction vs. attachment + review). The default is md/txt only, stated in the README.

**Done when**
- G1 `make test` green, including the leak test, with every new template added to `MESSAGE_TEMPLATES`.
- G2 `uv run python scripts/e2e.py` passes all 5 flows and prints the request 1 wall time.
- G3 Stopwatch test: someone new answers request 1 on a phone in under 2 min. Biostat runs it; you fix what slows them down.

---

## SWE/MedEng: safety, misdelivery, audit, FHIR validity, clinical story

**Owns:** `app/intake_service.py`, `app/misdelivery.py`, `app/identity/policy.py`, `app/audit.py` (+ `/audit` page), `scripts/validate_all.sh`, `tests/test_misdelivery.py`, `tests/test_policy.py`, `metrics/jury_docs/*.md` (writing the documents), README design answers 1, 2, 3, 5.

**Tonight**
1. `misdelivery.lint_address`: homoglyphs, uppercase letters in the domain, edit distance ≤ 2 to known domains, phone format. Remove the `xfail` in `tests/test_misdelivery.py` once it passes.
2. `classify_identity_failure`: label M1 vs. M2 honestly ("wahrscheinlich weitergeleitet").
3. Run `scripts/validate_all.sh` **early** (it downloads the validator and needs internet). Run it on a bundle from `mkdir -p var/filed && uv run python core/intake.py scenario/documents/lab-result-maria-beispiel.md --typed-name "Maria Beispiel" --typed-dob 12.03.1961 --sender "Dr. Eva Brandl" --out var/filed/test.json`. Every error goes to you, plus the core changes agreed with Biostat.

**Friday**
- `policy.py`: a possession-only path (no eID → may answer, never auto-filed). Wire the downgrade in `intake_service.py` (the TODO). Write the per-document-type table as README answer 2.
- Audit page: filter per request, coverage badges, chain status. Check that every event has who, what and when. M3 entries must never contain the other patient.
- Write about 10 jury-style documents in `metrics/jury_docs/`: other labs, German month names, German labels, a missing LOINC, a wrong LOINC, a wrong patient, a namesake with a different birth date, a typo in the name. Add each one to `manifest.json` with its expected decision.
- README answers 1 (identity without a directory), 2 (check per document type), 3 (a Mermaid diagram: Task → DiagnosticReport/DocumentReference → Observations → Patient; Provenance → targets, entity, agents), and 5 (where it runs). Also the clinical story for the video.

**Done when**
- G1 `make test` green, with the `xfail` gone from `test_misdelivery.py`.
- G2 `make validate` prints `TOTAL_ERRORS=0` for both scenario requests filed via the real stack.
- G3 `/audit` shows 6/6 coverage after running request 1 + M1–M3.

---

## Biostat PhD: metrics and evidence

**Owns:** `scripts/run_metrics.py`, `metrics/eval_jury_docs.py`, `METRICS.md`, `core/METRICS_matching.md` (re-check), `metrics/stopwatch.csv` (new), README design answer 4, the metrics slide and the stats Q&A.

**Tonight**
1. Re-check the matcher (`core/gen_pairs.py`, `core/eval_matcher.py`, `weights.json`). `false_file 0.0000 [0, 0]` is a bootstrap artifact: with 0 events in 3000 pairs, report the rule-of-three / Clopper–Pearson upper bound (≈ 0.1 %). Add a threshold sweep (review rate vs. false reject as `t_file` / `t_reject` move) and be ready to defend 4 / −6 and the hard block (exact birth date + matching family name).
2. Design the stopwatch test: who (people who didn't build it), which device, when the clock starts and stops (opening the email → receipt shown), and how many runs. Columns go in `metrics/stopwatch.csv`.

**Friday**
- `run_metrics.py`: finish the validator parsing, SMS leak scan, M1–M3 mapping and Playwright timings (from SWE 2's `e2e.py` output). Then `make metrics` writes `METRICS.md`.
- `eval_jury_docs.py`: run it on MedEng's documents and report a confusion table plus exact CIs. The safety number is "wrongly filed". Label the small n honestly.
- README answer 4 (how we notice a misdelivery: lint + identity binding + a three-way Fellegi–Sunter check, with the numbers). Plus the metrics slide.
- Run the stopwatch test with at least 2–3 outside people (ask other teams).

**Done when**
- G1 `make metrics` on the running stack writes `METRICS.md` with all 4 track metrics filled: validator 0, effort 0/0/<2 min, misdeliveries 3/3, audit 6/6.
- G2 `make jury-eval` shows wrongly filed = 0 on ≥ 10 documents, with the CI in `METRICS.md`.

---

## Timeline

| When | SWE 1 | SWE 2 | MedEng | Biostat |
|---|---|---|---|---|
| Thu → 22:00 | M0 `make up`, Matrix room | Portal UX, eID page | Address lint, validator first run | Matcher re-check, stopwatch design |
| Fri → 11:00 | Real HAPI, bot polish | Blocking, e2e.py | Policy, audit page, jury documents | run_metrics, jury eval |
| Fri → 13:30 | README architecture | Stopwatch fixes | README answers 1–3, 5 | METRICS.md, answer 4 |
| **13:30 → 15:00** | **Freeze.** Full run from a clean clone, record the video (DEMO.md), submit. | | | |
