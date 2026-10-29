# Progress

Append after each milestone: what works, what's next, known issues.

## Setup (Thu evening)
- Works: repo skeleton, shared contracts, thin slice in tests with a fake HAPI (request 1 email, request 2 SMS, M1–M3, audit chain). `make test`: 26 passed, 4 xfailed (address lint, owner MedEng).
- Next: M0 `make up` against the real images (SWE 1).
- Known issues: setup_synapse.sh, the bot and fhir_client have not been run against real Synapse/HAPI yet. The validator has not been run.

## Engine slice 1 (Thu night, AI)
- Works: `engine/` request job (rules + optional model, grounding, patient lookup) and document job (Markdown, PDF text layer, OCR + read-back, checks); plain-German and voice requests in commands/bot; portal accepts PDF and photos with a read-back page. `make test`: 54 passed, 4 xfailed.
- Next: GPU box (vLLM: NuExtract3, Qwen3-ASR, PaddleOCR-VL), test data (Synthea patients, rendered documents, held-out requests), eval harness with CIs.
- Known issues: models not yet run for real (no GPU yet); OCR prompts and NuExtract template format unverified.
