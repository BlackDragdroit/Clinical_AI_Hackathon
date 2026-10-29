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
