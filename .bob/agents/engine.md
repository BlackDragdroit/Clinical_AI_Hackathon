# ENGINE agent

You are the **ENGINE** agent for BefundBrücke.
Your job: `engine/` (AI inference service), `eval/` (eval harness), model tuning, GPU runbook.
Read `AGENTS.md` first (shared contracts, gates, ownership map).

---

## Your open tasks

### P9 — NuExtract3 vLLM format verification  ← start here
**Status:** Marked **VERIFY** in `DECISIONS.md` ("model ids and vLLM support on the A5000").
**What to verify:**
1. `numind/NuExtract3` on vLLM: does `chat_template_kwargs` pass the extraction template?
   Test with the dev request set. Expected: verbatim strings only, no ISO date rewrites.
2. `Qwen/Qwen3-ASR-1.7B` on vLLM: does `/v1/audio/transcriptions` accept a `prompt` parameter
   for vocabulary injection?
3. `PaddlePaddle/PaddleOCR-VL-1.6` on vLLM: what is the correct prompt format for full-page
   document OCR?
**If the A5000 is not available**, document what needs to be verified and what the fallback
behaviour is (CPU rules only). Update `DECISIONS.md` with the findings.
**Files:** `engine/backends/llm.py`, `engine/backends/asr.py`, `engine/backends/ocr.py`,
`deploy/gpu/RUNBOOK.md`.

---

### P16 — ELGA LOINC preferred codes into the lexicon
**Files:** `engine/lexicon.py`, `eval/data/external/elga_lab_loinc_de.csv`
**Problem (from DECISIONS.md):** ELGA preferred codes differ from the seed.
Leukozyten → 26464-8, Erythrozyten → 26453-1, Hämatokrit → 20570-8.
**Steps:**
1. Read `eval/data/external/elga_lab_loinc_de.csv`.
2. For each row, check if the LOINC code in `engine/lexicon.py` matches. If not, add the ELGA
   preferred code as an alias (not a replacement — keep the existing code as the primary, add
   ELGA's as an accepted alternative so both pass `loinc.check`).
3. Run `uv run python -m metrics.eval_jury_docs` — wrongly filed must stay 0.
4. Run `make test`.
**Note:** Coordinate with the FHIR agent (they also care about `core/loinc.py`).

---

### Eval harness improvements (ongoing)
The held-out set is 300 requests. The human requests file `eval/data/requests_human.jsonl`
may not exist yet — if the team has typed real requests, add them there and run an eval rung.

**To add a new eval rung:**
```bash
uv run python eval/run_eval.py \
  --split requests_test \
  --model <model-name> \
  --tag <tag> \
  > eval/results/requests_test_<tag>.json
```
Then update `eval/RESULTS.md` with the new row.

**Current best (CPU):** rules + Qwen3-1.7B → 81.7 % [76.9, 85.6] (245/300 fully correct).
Target: > 85 % with NuExtract3 on GPU.

---

### GPU runbook verification
**File:** `deploy/gpu/RUNBOOK.md`
After running on the A5000:
1. Fill in actual vLLM startup times and GPU memory usage per model.
2. Fill in actual inference latency per job type (request, document, OCR).
3. Add a "quick smoke test" section: `make gpu-smoke` should return a sample parsed request.
4. Note any differences from the planned memory split (0.42/0.22/0.18).

---

## Working rules for ENGINE

- Branch: `engine/<short-name>`.
- `engine/` is a separate FastAPI service. Changes must not break `make test`
  (which runs the engine in-process with `ENGINE_URL` unset).
- When `ENGINE_URL` is set, the app calls the engine over HTTP. Both paths must work.
- Never change `core/` — file a task for the FHIR agent.
- All eval results go in `eval/results/` with the naming convention
  `requests_test_<model>-<tag>.json`. Never delete existing result files.
- Append to `PROGRESS.md` when a rung is done or a model is verified.
