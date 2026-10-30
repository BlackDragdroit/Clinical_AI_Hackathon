# Play-test and stress-test report: outside portal

Fri 30 Oct 2026, 10:30–12:00. SWE 2 (Magomed), with Claude Code as tester and implementer.
Branch `swe2/portal-fixes` (cut from `main` at `cc11d3b`, after PR #18). Synthetic data only.

This file is for anyone, human or AI, who picks up the portal after this point. It says what was tested, how,
what was wrong, what was changed, the measurements showing each change is needed, and what is still open.

## Summary

- **The prototype is good enough to keep building on.** Request 1 (email) and request 2 (SMS) file end to end.
  M1, M2 and M3 are caught. The audit log covers 6/6 steps and its hash chain verifies. Emails and SMS carry no
  patient data. 8 simultaneous submits of one link still file once. Tests that didn't come from a real phone
  or the Docker stack are labelled as such below.
- **Five real problems in the outside portal**, all reproduced on current `main` and fixed on this branch. Each
  fix has a regression test, and every one of those tests fails on unmodified `main`:
  1. A birth date typed without dots (`12031961`) sends a correct answer to manual review.
  2. If HAPI is unreachable while an answer is filed, the sender gets a 500 error and the link stops working.
     The request is stuck at `answered` and Dr. Hofer is never told.
  3. A single upload freezes the whole portal for everyone (6 s per MB), and a 25 MB upload crashes after 97 s.
  4. (Needed because of the fix for 3) two submits of the same link at the same moment could both be filed.
  5. The wrong-patient (M3) receipt shows "✓ Danke" while the link is already dead, and Dr. Hofer isn't told
     what to do next.
- **Still open, not fixed here:** a lab request answered with a discharge report is filed (with only a ⚠️). The
  review message can hide the real reason. More items are in [Open findings](#open-findings-not-fixed-here).
  G2 (e2e on `make up`) and G3 (stopwatch on a real phone) have not been run.

## How it was tested

There was no Docker on the test machine, so the stack was replaced:

| Real stack | Used here |
|---|---|
| HAPI FHIR | In-process fake (same idea as `tests/conftest.py::FakeHapi`) with a switch that makes `$validate` or the transaction raise `httpx.ConnectError` |
| Mailpit | Emails captured in memory; the link was taken from the captured email |
| Synapse / Element | `MATRIX_ENABLED=0`: Dr. Hofer's commands went through `commands.handle`; her messages were read from the `matrix_outbox` table |
| Phone | The desktop app's built-in Chromium at 375 × 812 (phone viewport) |

The harness (a 100-line `playserver.py` plus stress scripts) lived in a scratch directory and is **not in the
repo**. The regression tests in `tests/test_flow.py` cover the same cases without it. To compare "before" and
"after", the same scripts ran against three servers at the same time:

- current `main` (`cc11d3b`)
- this branch
- this branch with the atomic link claim removed

Every "before → after" number below comes from that run, not from an older branch.

What was exercised:

- **Play-test** (by hand, phone viewport): landing → simulated ID Austria → answer form → receipt, as Dr. Brandl.
- **About 20 abuse and edge cases**, among them:
  - HAPI down at validation or at the transaction
  - lab request answered with the rehab report
  - lying form (typed Maria, document about Max, and the reverse)
  - junk text; fake PDF bytes; 3 MB and 25 MB uploads
  - 8 concurrent submits of one link
  - eID assertion replayed on another link
  - 5 wrong identities, then the real one
  - answer page without a session, or with another link's cookie
  - unauthorised Matrix sender, unknown patient, malformed commands
  - `<script>` in the reason
  - 30 full flows, 10 in parallel
  - audit chain afterwards
  - unauthenticated `/audit`, `/audit.json`, `/sms`
- **Existing suites:** `make test`, `scripts/e2e.py --local` (Playwright), `python -m metrics.eval_jury_docs`.

## Requirements check (scenario + TEAM.md gates)

| Requirement | Status | Evidence |
|---|---|---|
| Request 1 by email, filed as FHIR R4 | ✅ | e2e r1; PROGRESS: verified on the real stack Thu |
| Request 2 by SMS (simulated page) | ✅ | e2e r2 |
| Email / SMS without patient name, DOB or document type | ✅ | `tests/test_template_leak.py`; landing page checked by hand and by e2e |
| Form asks for patient name and DOB | ✅ | `answer.html` |
| M1 wrong address caught | ✅ | lint warns on the draft; identity binding → 403, nothing shown, audit `identity_checked FAILED` + `misdelivery_caught` |
| M2 forwarded request caught | ✅ | same as M1, with Karl Kollege |
| M3 wrong patient caught | ✅ | three-way Fellegi–Sunter → reject, not filed, Dr. Hofer told, no Max data in Matrix or audit |
| Audit 6/6, chain intact | ✅ | `/audit.json` after 200+ stress events: `chain_ok: true` |
| HL7 validator 0 errors | ✅ on `main` | commit `ba5127e` (MedEng); not re-run here (needs the stack) |
| Effort < 2 min for the outside person | ⚠️ | scripted 0.7 s; **human stopwatch (G3) not run**. Fix 1 removes a likely slowdown on iPhones |
| e2e on the real stack (SWE 2 G2) | ❌ | only `--local` |
| Jury documents: wrongly filed = 0 | ✅ | n = 17, wrongly filed 0. 3 cautious mismatches (jd02, jd05: file expected, got review; jd10: reject expected, got review) belong to MedEng / Biostat |
| `METRICS.md`, README answer 4, "What works / what doesn't" | ❌ | file missing; README TODOs at answer 4 and "What works" (Biostat / all) |

## Fixes, with proof that each is needed

All "before" numbers are from current `main`, measured side by side with this branch.

### 1. Birth date typed without dots

| | |
|---|---|
| **Problem** | The DOB field has `inputmode="numeric"`. On iPhones that opens a digits-only keypad with no dot, so people type `12031961`. The core date parser doesn't recognise it (`Person.from_full(..., "12031961").dob is None`), so the typed-vs-requested check can't agree and a perfect answer goes to **review**. Dr. Hofer then has to tap ✅ for nothing. |
| **Before → after** | `main`: status `review`. Branch: status `filed`. |
| **Fix** | `app/main.py::_norm_dob`: exactly 8 digits become `DD.MM.YYYY`; commas become dots (a German decimal keypad gives `12,03,1961`). Anything else is passed on unchanged. |
| **Needed?** | Yes for iPhones. The keypad behaviour is documented iOS behaviour for `inputmode="numeric"`, but it was **not tried on a real iPhone**; Android keyboards usually offer a dot. The change is narrow: only an exact 8-digit string is rewritten. A `YYYYMMDD` string like `19610312` becomes an invalid date and goes to review, exactly as before. |
| **Test** | `test_dob_typed_without_dots_is_filed` |

### 2. Processing failure kills the link

| | |
|---|---|
| **Problem** | The link was marked used **before** the answer was processed. If processing raised (HAPI unreachable, transaction rejected, engine down), the sender got a 500 and the link was dead. The request stayed at `answered` and nobody told Dr. Hofer. The only way out was a new `!anfrage`, and she didn't know one was needed. |
| **Before → after** | `main`, HAPI unreachable at `$validate`: HTTP 500, status `answered`, resubmit → 404, Dr. Hofer told: no. The same at the transaction. Branch: HTTP 503 with "Technischer Fehler, nichts wurde gespeichert … Ihr Link bleibt gültig", status back to `identified`, resubmit → 200 and `filed`, Dr. Hofer gets "⚠️ Antwort zu Anfrage … konnte nicht verarbeitet werden". |
| **Fix** | `app/main.py::_processing_failed`. If no resources were filed for the request, the link is reopened (`tokens.reopen`), the status reset and Dr. Hofer told. If resources *were* filed and a later step failed (e.g. the Task update), the link is **not** reopened, so nothing gets filed twice; Dr. Hofer is told to check the Task. An engine failure before the link is claimed now shows the same "try again" form instead of a 500. |
| **Overlap with `main`** | Commit `ac75dbc` (SWE 1) already turns a `$validate` **timeout** (HAPI cold start) into "not validated → review". That is the most likely failure in a demo, and it stays as it is. This fix covers what that commit doesn't: connection errors, a failing transaction, and an engine that raises. Both are needed. |
| **Remaining risk** | If HAPI commits the transaction but the response is lost (timeout after commit), `filed_refs` stays empty, the link is reopened and a resubmit could file twice. That's rare; a transaction `ifNoneExist` / conditional create would close it. |
| **Test** | `test_hapi_down_keeps_link_valid` |

### 3. Upload size cap

| | |
|---|---|
| **Problem** | No size limit. A 25 MB Markdown upload ran for 97 s and then crashed (`sqlite3.DataError: string or blob too big`), with the link burned and the request stuck. Even legitimate-looking sizes are slow (see fix 4). |
| **Before → after** | `main`: a 3 MB upload is accepted and blocks the portal for 21.5 s. Branch: refused in 0.2 s with "Die Datei ist zu groß (höchstens 1 MB)"; the link stays valid. |
| **Fix** | `MAX_TEXT_BYTES = 1 MiB` for `.md`/`.txt`/pasted text (the scenario documents are about 1 kB). `MAX_UPLOAD_BYTES = 10 MiB` for PDF/photo (phone photos are 2–5 MB). The file is read only up to the limit + 1 byte. |
| **Needed?** | Yes. Starlette still receives the whole request body before our check, so production also needs a body limit at the reverse proxy (e.g. nginx `client_max_body_size`). |
| **Test** | `test_oversized_text_upload_refused_link_stays_valid` |

### 4. Slow work moved off the event loop

| | |
|---|---|
| **Problem** | `answer_submit` is `async` but called the synchronous engine, core parsing and HAPI client directly. While one answer was processed, **every other request waited**: other senders, `/health`, the dashboard. The Matrix bot runs on the same event loop, so it stalled too. |
| **Before → after** | `main`: a 1 MB upload → `/health` waits 6.2 s; 3 MB → 21.5 s. Branch, 1 MB: worst `/health` 2.5 s over 23 probes. With a real HAPI (each `$validate` takes seconds) or the OCR engine over HTTP (`ENGINE_URL`), every normal submit would block everyone on `main`. |
| **Fix** | `engine_client.document` and `_finish` run via `starlette.concurrency.run_in_threadpool`, in `answer_submit` and `readback_confirm`. |
| **Remaining** | 2.5 s is not 0: the parsing is CPU-bound Python, so threads still compete for Python's interpreter lock (the GIL). The 1 MB cap bounds it. Real documents are kB-sized and don't notice. |
| **Test** | covered indirectly (the suites run through the threadpool); the timing was measured with the harness |

### 5. Atomic link claim

| | |
|---|---|
| **Problem** | Created by fix 4. On `main`, concurrent submits of one link were safe only because the blocking event loop handled them one at a time. Once the work runs in threads, two submits can both pass the "link still valid" check. |
| **Proof** | 10 trials × 8 concurrent submits of one link. `main`: 0/10 filed twice. This branch: 0/10. **This branch with `tokens.claim` replaced by the old `mark_used`: 10/10 filed more than once.** |
| **Fix** | `app/tokens.py::claim` (`UPDATE … SET used_at = ? WHERE … AND used_at IS NULL`, true for exactly one caller) and `reopen` for fix 2. `mark_used` is kept for existing callers and tests. |
| **Test** | `test_link_claim_is_atomic` |

### 6. Wrong patient (M3): receipt and next step

| | |
|---|---|
| **Problem** | The sender saw "✓ Danke" followed by "Bitte prüfen Sie, ob Sie das richtige Dokument gewählt haben", but the link was already used, so following that advice was impossible. Dr. Hofer was told the document didn't fit, but not that she must send a new request to get the right one. |
| **Fix, sender** | `receipt.html` shows "Nicht zugeordnet" with no tick, in an alert style. The text says the document was not saved and the clinic will get back to the sender. The receipt text now comes from `app/i18n.py` per decision (`portal.done_file / done_review / done_reject`), so it also works in English (it used to be German only). |
| **Fix, Dr. Hofer** | In the running stack, `app/status_message.py` **suppresses** the outbox text for M3 and posts its own card ping. So the hint had to go into that ping: "⛔ … Nicht abgelegt. Link verbraucht – für das richtige Dokument neue Anfrage stellen." The same hint is also in the outbox text in `app/intake_service.py`, which is what you see with `MATRIX_ENABLED=0` (console) and in tests. |
| **Needed?** | It's UX, not safety: M3 was already caught. It prevents a dead end in the demo story ("what does Dr. Brandl do now?"). An alternative, keeping the link valid after a reject so the verified sender can upload the right file, would match the Task going back to `in-progress`. It is a bigger change, so it is left as a team decision. |
| **Tests** | `test_m3_receipt_has_no_tick_and_doctor_gets_next_step`; `tests/test_status_message.py` (ping text updated) |

## Files changed on this branch

| File | Owner (TEAM.md) | Change |
|---|---|---|
| `app/main.py` | SWE 2 | fixes 1–4, receipt per decision, `_form_error` / `_processing_failed` helpers |
| `app/tokens.py` | SWE 2 | `claim`, `reopen` |
| `app/templates/receipt.html` | SWE 2 | heading and alert style depend on the decision |
| `app/i18n.py` | MedEng (shared catalogue) | new keys `portal.err_too_big`, `portal.err_tech`, `portal.done_file/review/reject`, `portal.reject_h` |
| `app/intake_service.py` | **MedEng** | M3 outbox text gets the next step (one line) |
| `app/status_message.py` | **SWE 1** | M3 card ping gets the next step (one line) |
| `tests/test_flow.py` | — | 5 regression tests |
| `tests/test_status_message.py` | SWE 1 | expected ping text updated |
| `PROGRESS.md` | all | milestone entry |

No shared contract changed: the database schema, the `audit.log` events, `Channel.send`, `EidAssertion` and the
`process_answer` signature are all unchanged.

## Open findings (not fixed here)

| # | Finding | Evidence | Suggested owner / next step |
|---|---|---|---|
| O1 | **A lab request answered with a discharge report is auto-filed**; only a ⚠️ flag from `engine/checks.py` is added. The sender organisation in Dr. Hofer's message is also taken from the document, not verified ("Eva Brandl (Reha Waldblick)"). | Stress test: status `filed`, 1 bundle | MedEng: downgrade to `review` when `checks.doc_type` reports a mismatch (one condition in `intake_service.process_answer`) |
| O2 | The review message can hide the reason. With an unparseable typed DOB it lists only requested-vs-document ("Nachname stimmt überein, … Geburtsdatum stimmt überein"), so Dr. Hofer can't see why she is asked. | Play-test with `12031961` before fix 1 | MedEng / core: name the leg that failed (typed vs. document) |
| O3 | Junk content ("hallo", or PDF bytes on the old path) goes to review, and `!ablegen` then files it as 5 FHIR resources. The review ping shows no summary of what was received. | Stress tests E, F, S | MedEng: refuse at the form when nothing was parsed; or show the parsed row count in the 🔍 ping |
| O4 | The mock eID assertion isn't tied to the link: any valid assertion (5 min TTL) works on any link's callback. It also travels in the URL query. | Stress test I | Mock only. The real ID Austria OIDC adapter must use the authorization-code flow with `state` + `nonce` bound to the link (note for README answer 5 / production) |
| O5 | `/audit`, `/audit.json` and `/sms` are public. No patient names show there, but `/sms` lists live links (identity is still required). | Stress test P | Known; the footer says "behind clinic login in production". Keep it on the "what doesn't work" list |
| O6 | 5 failed identity attempts → 5 ⚠️ pings + 1 🔒 in Matrix. | Stress test J | SWE 1: one ping per request with a counter |
| O7 | The simulated ID Austria page preselects Eva Brandl. Convenient for the stopwatch test, but during an M1/M2 demo the presenter must remember to pick the stranger. | Play-test | Demo script note |
| O8 | 1 MB text uploads still slow other requests by up to 2.5 s (GIL). | Fix 4 measurement | Fine for the prototype; production: parse in a process pool or in the engine service |
| O9 | The sender message for review/file was German-only in core (`sender_message_de`). The portal now uses its own DE/EN texts, so `sender_message_de` is no longer shown in the portal. | — | Nothing to do; noted so nobody wonders why the core text isn't on the receipt |
| O10 | G2 (e2e on `make up`) and G3 (stopwatch on a phone) not run. | — | Someone with Docker: `uv run python scripts/e2e.py`; Biostat: stopwatch with this branch |

## What held up (no change needed)

- 8 concurrent submits of one link → filed once (on `main` thanks to the blocking event loop; on this branch thanks to the claim).
- 30 full flows, 10 in parallel → all filed; audit chain intact after 200+ events.
- Brute force: after 5 failed identities the link is blocked; the real person also gets the neutral page; Dr. Hofer is alerted.
- No session cookie, or another link's cookie → the same neutral 404 page.
- `<script>` in the request reason → escaped on the answer page.
- Unauthorised Matrix sender → "Keine Berechtigung". Unknown patient → "Nicht gefunden auf dem FHIR-Server". Malformed `!anfrage` → format hint.
- Lying form (typed Maria + Max document, or typed Max + Maria document) → rejected in both directions.
- Unknown, expired, used and blocked links all look identical to a guesser.

## Branch history (why `swe2/portal-fixes` exists)

1. `swe2/portal-mobile-i18n` was 20 commits behind `main`. A local merge (`4fcb1ba`) and the fixes (`b039586`) were
   made on it, but the push was rejected. A teammate had already merged `main` into that branch at 10:44 and merged
   it into `main` as PR #18, resolving the same conflicts the same way.
2. So the fixes were cherry-picked onto a fresh branch from current `main`: `swe2/portal-fixes`. The local
   `swe2/portal-mobile-i18n` with the two unpushed commits is obsolete and can be deleted.

## How to verify

```
make test                                   # 185 passed on this branch
uv run python scripts/e2e.py --local        # 5/5, request 1 wall time 0.7 s
uv run python -m metrics.eval_jury_docs     # n=17, wrongly filed = 0
uv run pytest -q tests/test_flow.py -k "dob or hapi_down or oversized or claim or m3_receipt"
```

To see that the fixes are needed, copy this branch's `tests/test_flow.py` into a checkout of `main` and run it:
the five new tests fail there.
