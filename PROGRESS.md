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
