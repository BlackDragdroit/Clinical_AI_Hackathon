# Progress

Append after each milestone: what works, what's next, known issues.

## Setup (Thu evening)
- Works: repo skeleton, shared contracts, thin slice in tests with a fake HAPI (request 1 email, request 2 SMS, M1–M3, audit chain). `make test`: 26 passed, 4 xfailed (address lint, owner MedEng).
- Next: M0 `make up` against the real images (SWE 1).
- Known issues: setup_synapse.sh, the bot and fhir_client have not been run against real Synapse/HAPI yet. The validator has not been run.

## M0 stack (Thu evening): verified on the real stack
- `make up` from scratch: Synapse (users + room + bot), Element, HAPI seeded, Mailpit, app container.
- Request 1 by email: Matrix `!anfrage` → `!senden` → neutral Mailpit email → eID (Eva) → upload → filed. On HAPI: 4 Observation, DiagnosticReport, DocumentReference, Provenance; Task completed; ✅ message in Matrix with HAPI links.
- Request 2 by SMS (/sms page) → eID (Stefan) → filed; ✅ in Matrix.
- M1 (labor-kanaI, stranger) and M2 (Karl Kollege): 403, nothing shown, identity FAILED + misdelivery_caught logged, ⚠️ in Matrix.
- M3 (Max document): not filed (Observation count unchanged), sender gets the neutral error, ⚠️ in Matrix without the other patient's name.
- Audit 6/6, hash chain intact.
- Fixed while bringing it up: .env quoting, Synapse start order, homeserver.yaml append (no trailing newline), Synapse login rate limit, empty sender organisation in the Matrix message.
- NOT run yet: HL7 validator (`make validate`, downloads validator_cli.jar). Owner MedEng.
- Known issues: the address lint is still a stub, so M1 is caught only by the identity binding and there's no warning before sending. The audit label is 'M1/M2' until classify_identity_failure is done.

## SWE 1 TODOs (Thu evening)
- Bot accepts commands only from AUTHORIZED_SENDERS (default DOCTOR_MXID). Replies are structured cards (headline, one fact per line, exact next command), sent as Matrix HTML with clickable FHIR links. Errors say what failed and what to do.
- Task: executionPeriod (start on send, end on close), requested document type as a LOINC-coded input (11502-2 lab / 18842-5 discharge summary). HAPI $validate on the live Task: 0 errors (1 dom-6 narrative warning).
- README: Architecture (component table, flowchart, sequence diagram, trust boundaries) and "every component is replaceable".
- FTAPI: no public API reference (ftapi.com says a REST API exists, licence-gated). The adapter stays a stub, and its docstring lists what to ask FTAPI on site.
- Verified on the live stack: card → send → answer → filed → Task completed with executionPeriod.end, ✅ message with links. `make test`: 33 passed, 4 xfailed.

## SWE 1 done (Thu 21:50): clean-clone check
- G1: `make reset`, fresh `git clone`, `make install && make up` with no manual steps → Synapse + users + room, HAPI seeded (Patient/maria-beispiel), Element on :8080, app on :8000.
- G2 and the misdelivery tests on that clean stack, via `scripts/dev/flow.sh r1|r2|m1|m2|m3`: r1 and r2 filed with a ✅ in Matrix; m1 and m2 got a 403 with nothing shown, identity FAILED + misdelivery_caught; m3 not filed (Observation count unchanged), with ⚠️ in Matrix. Audit 6/6, chain intact.
- FTAPI is deliberately not used; the README says so (tagline, trust boundaries, replaceability table).
- Still open (not SWE 1): HL7 validator run (`make validate`, MedEng); the address lint (MedEng) still runs as a stub, so the M1 audit label reads "M1/M2".

## MedEng: address lint + DE/EN texts (Thu evening)
- Works: `lint_address` warns on the draft card before `!senden`, covering look-alikes (I/l/1, O/0, rn/m, vv/w), uppercase in the domain, non-ASCII characters, edit distance ≤ 2 to a known domain, and phone numbers (no +43, foreign, landline, wrong length). `classify_identity_failure` returns M1 (the contact had warnings) or M2. New `app/i18n.py` holds the DE/EN catalogue, `t()`, language resolution (?lang= > cookie > Accept-Language) and Jinja `install()`. `make test`: 57 passed, 0 xfailed.
- Next: HL7 validator run; the audit page (uses `i18n` + `misdelivery_label`); SWE 2 can wire the portal EN toggle with the 2 lines in the `i18n.py` docstring.
- Known issues: on Windows, core's `ZoneInfo("Europe/Vienna")` needs the `tzdata` package (not in pyproject); tests ran with `uv run --with tzdata`. Not yet run on the live stack.

## MedEng: first HL7 validator run (Fri 00:40)
- Works: `make validate` on bundles built by core for request 1 (lab, 4 Observations + DiagnosticReport + DocumentReference + Provenance) and request 2 (rehab DocumentReference + Provenance): TOTAL_ERRORS=0. The only error before was Provenance.policy on example.org (fixed in core/fhir_build.py, Biostat informed via PR).
- Next: rerun on bundles filed through the live stack (G2); optional: narrative (dom-6 warnings, 10 + 6, best practice only).
- Known issues: first validator run needs ~8 min to download packages and 3 GB RAM; on Windows `core/intake.py` needs PYTHONIOENCODING=utf-8 to print the ✅ message.

## Engine slice 1 (Thu night, AI)
- Works: `engine/` request job (rules + optional model, grounding, patient lookup) and document job (Markdown, PDF text layer, OCR + read-back, checks); plain-German and voice requests in commands/bot; portal accepts PDF and photos with a read-back page. `make test`: 54 passed, 4 xfailed.
- Next: GPU box (vLLM: NuExtract3, Qwen3-ASR, PaddleOCR-VL), test data (Synthea patients, rendered documents, held-out requests), eval harness with CIs.
- Known issues: models not yet run for real (no GPU yet); OCR prompts and NuExtract template format unverified.

## Engine slice 2 (Fri 00:00–05:00, AI)
- Works: test data (Synthea v4.0.0: 442 patients with planted namesakes/near-twins; 600 dev requests; 300 held-out requests written without the engine code; 120 documents rendered as Markdown/PDF/scan/photo), eval harness with exact CIs (eval/RESULTS.md), voice eval on CPU (eval/VOICE.md), real reference data (eval/REAL_DATA.md), GPU runbook (deploy/gpu/RUNBOOK.md).
- Numbers (held-out 300): rules 69.7 % fully correct; rules + Qwen3-1.7B on CPU (v2) 81.7 %; wrong patient picked 0/300 in every rung; silent errors 5/300. Documents: Markdown and PDF 120/120, 0 wrong values filed, 16/16 wrong-patient documents rejected.
- Next: NuExtract3 and Ministral 3 rungs (CPU, running), app-side patient lookup when the engine runs remotely, ELGA names into the lexicon, GPU rungs once the A5000 is up.
- Known issues: dictated lowercase requests are the weak spot of the rules; CPU speech-to-text loses most e-mails/phones (fails safe, one wrong number); OCR not measured without GPU.

## MedEng: jury documents + name rule (Fri)
- 14 jury documents in `metrics/jury_docs/` (EN/DE, other labs, date formats, LOINC errors, wrong patient, namesake, typo, swapped DOB, sibling, German rehab report): wrongly filed = 0 of 17; 3 mismatches, all to the safe side (jd02 separate 'Geburtsdatum:' line and jd05 '12.3.61' not parsed -> review; jd10 namesake *1985 -> review at W -3.75, expected reject).
- `names_match`: hyphen = space, extra eID given names allowed, family name exact, family-only never matches; 21 new cases in tests/test_policy.py. `make test`: 54 passed, 4 xfailed.
- Broken / for MedEng + Biostat: a valid LOINC code that is not in the local table is filed unchecked (jd08: D-Dimer row coded 2276-4 = ferritin); German 'Probenentnahme'/'Befunddatum' keys are not read, so effectiveDateTime/issued are lost (jd02). Validator not yet run on the jury bundles.

## MedEng: README answers 1, 3, 5 (Fri)
- Works: README answers 1 (identity without a directory), 3 (two Mermaid diagrams + resource table, from bundles generated by `core/intake.py`), 5 (where it runs + GDPR), MedEng bullets in "What works / what doesn't", and `DEMO_CLINICAL_STORY.md` (DE/EN voice-over + shot list). HL7 validator rerun on fresh bundles: 1 error each as-is (Provenance.policy on example.org), 0 errors with the `medeng/validator-zero` fix.
- Next: merge `medeng/validator-zero` and `medeng/address-lint` before the video (the M1 shot needs the lint); rerun `make validate` on bundles filed through the live stack.
- Known issues: no retention/deletion of stored answers; Practitioner/Organization created per answer without identifier; name check blocks double names; on Windows `core/intake.py --out` and `_file()` write JSON in the locale encoding (cp1252), not UTF-8.

## MedEng: audit page (Fri)
- Works: `/audit` shows the hash-chain badge (intact, or "verletzt ab Eintrag #N" via `audit.first_broken()`), coverage of the 6 required steps (6/6 after request 1 + M1–M3), the request list (masked contact, status, x/6, M1/M2/M3 marker, click to filter), a Vienna-time timeline with one plain DE/EN sentence per event (`audit.describe`, incl. the extras and request_parsed / readback_*; unknown events fall back), raw JSON + row hash per entry, and an M1/M2/M3 panel. DE default, EN toggle; `/audit.json` keeps its keys and adds first_broken, last_hash, requests, misdelivery. Tests: 70 passed (15 in test_audit.py, 13 of them new, incl. M3 privacy: no "Max"/"1960" in /audit or /audit.json).
- Next: put `/audit` behind the clinic login in production (footer says so); show the page in the demo video after M3; once the parsing/read-back branch lands, add its events to `EVENTS` (sentences already exist).
- Known issues: not run on the live stack yet, only with the fake HAPI. The page is standalone (it doesn't extend base.html, because base.html is the narrow outside portal). Times fall back to UTC if tzdata is missing (Windows without `--with tzdata`).

## MedEng: audit page, Apple-HIG variant (Fri)
- Works: `/audit/apple` (same `request_id` / `lang` params, same `audit.view()` data and texts) shows the same page in a macOS/iPadOS inspector style: grouped inset sections, Settings-style icon tiles (colour = outcome, glyph = event), a hash-chain strip (one link per entry, broken link drawn split, request's links filled), a macOS-style requests table with accent-filled selection (a cell list at phone width), disclosure triangles for raw data + hash, a DE/EN segmented control. Light/dark, no JS, no horizontal scroll at 375 px. "Design: Standard / Apple" switch on both pages keeps filter and language. Tests: 75 passed (5 new in test_audit.py).
- Next: team picks one design for the jury video; the other can stay as a route or be dropped (its files are self-contained).
- Known issues: headless Chrome won't lay out below 512 px, so the 375 px check ran in a 375 px iframe. English column headings stay sentence case (shared keys with `/audit`), not Apple's title case.
- Apple variant simplified: no chain strip, coverage as a plain checklist with the score beside the heading, no 'created' column or channel suffix in the requests table (table from 1100 px, list below), no timeline column header, no misdelivery explanation text, routine timeline steps without a coloured tile. 78 tests pass.
- `/audit/apple` restyled as a formal audit record: "Audit-Protokoll" header with clinic / scope / entries / time zone / classification, "Hash-Kette geprüft: intakt – N Einträge, letzter Hash …", "Pflichtschritte: 6 von 6 protokolliert" as a step/status table, M1–M3 as a type/status/time/request table, plain requests table (navy rule on the selected row), timeline as a ledger (# · time · event · actor · request) with a small "Details" toggle; no icon tiles, shadows or pills; DE | EN as plain text; no horizontal scroll at 375 px.
- Light/dark/system switch removed again (app/theme.py deleted, theme.* keys and tests gone); both audit pages light only, design switch small in the footer. Tests: 78 passed (2 theme tests out, light-only + footer-switch tests in).

## SWE 2 portal (Fri morning)
- Works: mobile-first portal with step bar (identity → send → done), DE/EN toggle (German default; the neutral sentence is unchanged and tested), simulated ID Austria page with a SIMULATION banner, `secure` cookies when `BASE_URL` is https. Blocking: when identity attempts run out the request becomes `blocked`, that attempt and every later visit get the neutral dead-link page, Dr. Hofer is alerted once.
- e2e: `scripts/e2e.py` (Playwright, phone viewport) runs r1, r2 (via /sms), M1, M2, M3 and prints JSON for Biostat (`var/e2e.json`). `--local` passes 5/5 without Docker, request 1 wall time 0.64 s scripted. Not yet run against `make up` (no Docker on SWE 2's machine).
- Email now has an HTML part with a big "Anfrage öffnen" button (in `MESSAGE_TEMPLATES`, leak test green). README states md/txt-only upload.
- Next: e2e against the real stack, stopwatch fixes after Biostat's run, preview decision with MedEng.
- Audit: new extra event `request_blocked` in `app/audit.py` (shared contract, MedEng told). Logged once, after the last failed `identity_checked`.
- DE/EN: merged with MedEng's `app/i18n.py` (portal strings are `portal.*` keys, toggle is `?lang=`, German default, no Accept-Language).
- Known issues: the receipt text from intake_service is German only. Not yet tried on a real phone.

## SWE 2: play-test fixes (Fri 11:30)
- Works: fixes from a play/stress test of the merged portal: a birth date typed as `12031961` (phone keypad has no dot) is accepted; if processing fails (e.g. HAPI down) nothing is filed, the link stays valid, the sender sees "send again" and Dr. Hofer is told; uploads capped (1 MB text, 10 MB PDF/photo); parsing/intake runs off the event loop, and an atomic link claim keeps concurrent submits to one filing; a wrong-patient receipt no longer shows ✓, and Dr. Hofer's M3 card ping says to send a new request. Details, measurements on `main` vs. this branch and open findings: `PLAYTEST_REPORT.md`. `make test`: 185 passed; `e2e.py --local` 5/5.
- Next: e2e against `make up`; phone stopwatch test (G3). MedEng to decide: wrong document type (lab asked, report sent) is still filed with a ⚠️ only.
- Known issues: a 1 MB text upload still slows other requests for up to ~2 s (CPU-bound parsing shares the GIL). `/audit` and `/sms` are public; the mock eID assertion is not bound to the link.

## FHIR: P14 — name policy double given names (fhir/name-policy)
- Investigated `app/identity/policy.py::names_match` and all existing test cases.
- Finding: the implementation already correctly handles extra eID given names (the `iter(given)` ordered-subsequence logic allows Dr. Hofer to type fewer given names than the eID carries). The existing test `("Dr. Eva Brandl", "Eva Maria", "Brandl")` already covered the main reported case and passed.
- No change to `policy.py` was required; the rule in DECISIONS.md ("every given name she typed must be on the eID in order, extra eID given names are allowed") is faithfully implemented.
- Added `test_eid_extra_given_name_allowed` in `tests/test_policy.py` with 5 assertions covering: title + first given only (True), no title + first given only (True), exact match both given names (True), second given name only in order (True), eID has no given name → no match (False).
- `make test`: 199 passed, 2 xfailed. P14 closed. — FHIR

## IMPROVE P1 — doc-type mismatch → review (improve/doc-type-mismatch)
- **What changed:** `app/intake_service.py` — added `doc_type_mismatch: dict | None` parameter to `process_answer`. When the engine's `checks.doc_type` reports a mismatch (e.g. a lab request answered with a discharge report), `decision` is downgraded from `file` to `review` before storing and routing. Dr. Hofer's Matrix notification includes `⚠️ Falscher Dokumenttyp: angefragt Laborbefund, erhalten Bericht.` The audit entry for `review_requested` now carries `doc_type_mismatch` in its details. `app/main.py` — `_finish()` passes `doc_type_mismatch=(eng.get("checks") or {}).get("doc_type")` to `process_answer`.
- **Test that proves it:** `tests/test_flow.py::test_wrong_doc_type_goes_to_review` — makes a `labor` (doc_type=lab) request, submits `rehab-report-maria-beispiel.md` (doc kind=report), asserts `request.status == "review"`, nothing posted to HAPI, and Dr. Hofer's Matrix message contains the mismatch reason.
- **Caveats:** The mismatch check only fires when `engine/checks.py::run()` can determine `doc.kind` (i.e. the document was successfully parsed as `lab` or `report`). An unparseable document follows the existing "unreadable" path and never reaches this check. Downgrading a `reject` is not done (wrong-patient documents are still quarantined regardless of doc type).
- `make test`: 199 passed, 2 xfailed. P1 closed. — IMPROVE

## Multi-agent wave 1–3 (Fri 30 Oct, Bob swarm)

**Wave 1 (5 parallel agents):**
- IMPROVE P1: lab request answered with a discharge report now goes to `review` instead of `file`. Test: `test_wrong_doc_type_goes_to_review`.
- PLAYTEST T2–T8: 7 new security/edge-case tests in `tests/test_security.py` (XSS escaping, unknown patient, malformed command, pasted text, session-less access, blocked==expired link). T1 (eID replay) added as xfail stub, fixed in wave 3.
- DOCS P4/P5: README answer 4 (misdelivery: lint + identity binding + Fellegi-Sunter) and "What works / what doesn't" completed with AI engine and portal bullets.
- FHIR P14: confirmed `names_match` already handles extra eID given names; 5 new test cases added.
- ENGINE P16: 122 ELGA Austrian lab parameter LOINC aliases added to `engine/lexicon.py`. `eval/RESULTS.md` summary table added; `deploy/gpu/RUNBOOK.md` model verification section added.

**Wave 2 (4 parallel agents):**
- IMPROVE P2: review ping to Dr. Hofer now includes parsed row count and "möglicherweise kein gültiges Dokument" for junk.
- IMPROVE P3: identity failure pings deduplicated — only first failure and block ping sent to Dr. Hofer (not all 5).
- IMPROVE P13: `AUDIT_TOKEN` env var added; `/audit`, `/audit/apple`, `/audit.json` return 403 when token is set and missing.
- REWRITE P11: `app/main.py` split into `app/portal_router.py` (9 public routes) + `app/clinic_router.py` (3 internal routes). `PORTAL_ONLY=1` omits the clinic router for internet-facing deployments. `app/main.py` is now 39 lines.
- FHIR P12: Practitioner and Organization resources now carry a slug-based identifier (`urn:befundbruecke:sender` / `urn:befundbruecke:org`) + `ifNoneExist` conditional-create so HAPI deduplicates repeat filings.
- DOCS: DEMO_CLINICAL_STORY.md "Demo tips" section added (M1/M2/M3 shot instructions, cut-if-short table, common mistakes).

**Wave 3 (4 parallel agents):**
- IMPROVE P17: `POST /admin/purge` endpoint + `QUARANTINE_TTL_DAYS`/`TOKEN_TTL_DAYS` config. Deletes old quarantined answers and used/expired tokens; audit log untouched. Test: `tests/test_purge.py`.
- IMPROVE P20: mock eID assertion now bound to the link token (HMAC payload includes `lt` field). T1 xfail → real passing test. `e2e.py --local` 5/5.
- DOCS P15/P18/P19: README "Production deployment" section (env vars table, PORTAL_ONLY Docker example); eID OIDC production callout; DECISIONS.md wave-1/2 entries.
- PLAYTEST: 5 new coverage tests (portal-only route hiding, Bearer audit token, FHIR identifier fields, parseable-doc review).

**Overall: 190 → 209 passed, 2 xfailed → 1 xfailed. 19 new items completed across 3 waves.**
- Next (needs Docker): P6 METRICS.md live run, P7 e2e on real stack, P8 HL7 validator on live bundles.
- Next (needs GPU): P9 NuExtract3/Qwen3-ASR/PaddleOCR-VL vLLM verification.
- Known issues unchanged: no retention of audit log; `/sms` still public; GIL slowdown on large uploads (capped at 1 MB).
