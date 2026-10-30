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

## SWE 2 portal (Fri morning)
- Works: mobile-first portal with step bar (identity → send → done), DE/EN toggle (German default; the neutral sentence is unchanged and tested), simulated ID Austria page with a SIMULATION banner, `secure` cookies when `BASE_URL` is https. Blocking: when identity attempts run out the request becomes `blocked`, that attempt and every later visit get the neutral dead-link page, Dr. Hofer is alerted once.
- e2e: `scripts/e2e.py` (Playwright, phone viewport) runs r1, r2 (via /sms), M1, M2, M3 and prints JSON for Biostat (`var/e2e.json`). `--local` passes 5/5 without Docker, request 1 wall time 0.64 s scripted. Not yet run against `make up` (no Docker on SWE 2's machine).
- Email now has an HTML part with a big "Anfrage öffnen" button (in `MESSAGE_TEMPLATES`, leak test green). README states md/txt-only upload.
- Next: e2e against the real stack, stopwatch fixes after Biostat's run, preview decision with MedEng.
- Audit: new extra event `request_blocked` in `app/audit.py` (shared contract, MedEng told). Logged once, after the last failed `identity_checked`.
- Known issues: the receipt text from intake_service is German only. Not yet tried on a real phone.
