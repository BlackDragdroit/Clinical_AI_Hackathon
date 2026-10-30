# GPU runbook: A5000 VM → engine numbers in ~60 min

The organisers give each group an A5000 VM (24 GB) with an SSH key in the group's tutorial (#gpu-access on Discord).
Everything below runs on the VM unless it says *laptop*.

## 1. Check the box (5 min)
```
ssh -i <key> <user>@<vm>
nvidia-smi                                  # A5000, 24 GB, driver present
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi   # GPU visible inside Docker
df -h /                                     # need ~60 GB free: vLLM image ~10 GB + models ~20 GB
```
If Docker cannot see the GPU, install the NVIDIA container toolkit (`sudo apt-get install -y nvidia-container-toolkit && sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`) or ask A1 on site.

## 2. Start models + engine (20–30 min, mostly downloads)
```
git clone -b ai/engine https://github.com/BlackDragdroit/Clinical_AI_Hackathon && cd Clinical_AI_Hackathon
export HF_TOKEN=<optional, avoids rate limits>
docker compose -f deploy/gpu/docker-compose.yml up -d --build
docker compose -f deploy/gpu/docker-compose.yml logs -f llm asr ocr     # wait for "Application startup complete" x3
nvidia-smi                                                               # ~0.82 of 24 GB in use
```
Each model can be swapped without code changes (`.env` next to the compose file or inline):

| Slot | Default | EU / fallback alternative |
|---|---|---|
| text → JSON | `ENGINE_LLM_MODEL=numind/NuExtract3` `ENGINE_LLM_MODE=nuextract` | `mistralai/Ministral-3-8B-Instruct-2512` + `ENGINE_LLM_MODE=json_schema` + `LLM_EXTRA="--tokenizer-mode mistral --config-format mistral --load-format mistral"`; or `Qwen/Qwen3.5-4B` + `json_schema` |
| speech → text | `ENGINE_ASR_MODEL=Qwen/Qwen3-ASR-1.7B` | `mistralai/Voxtral-Mini-3B-2507` + the same `ASR_EXTRA` flags; `openai/whisper-large-v3` |
| image → Markdown | `ENGINE_OCR_MODEL=PaddlePaddle/PaddleOCR-VL-1.6` | `ENGINE_OCR_PROMPT` if the model wants a different prompt (PaddleOCR-VL: try `OCR:`) |

Troubleshooting:
- `unsupported architecture` → newer vLLM: `VLLM_TAG=<newer tag>` (Qwen3.5-based NuExtract3 needs ≥ 0.17, Qwen3-ASR ≥ 0.16).
- out of memory at start → lower the three `--gpu-memory-utilization` shares (they must add up to < 0.9).
- NuExtract3 returns junk in `nuextract` mode → set `ENGINE_LLM_MODE=json_schema` (works on llama.cpp too; it may normalise dates, which grounding then drops).

## 3. Smoke test (5 min) — *laptop*
```
ssh -i <key> -N -L 8100:localhost:8100 -L 8001:localhost:8001 -L 8002:localhost:8002 -L 8003:localhost:8003 <user>@<vm> &
ENGINE=http://localhost:8100 make gpu-smoke
```
Expect: `llm` model listed with no `llm_error`; PDF read via `pdf-text`; the phone photo read via `ocr` with read-back items and most of them `agree`.

## 4. Numbers for the slides (20–30 min) — *laptop*
```
L="--llm-url http://localhost:8001/v1"
uv run python -m eval.run_eval requests --set test --rung nuextract3-gpu $L --llm-model numind/NuExtract3 --llm-mode nuextract
uv run python -m eval.run_eval requests --set test --rung ministral-3-8b-gpu $L --llm-model mistralai/Ministral-3-8B-Instruct-2512 --llm-mode json_schema   # after swapping the model
uv run python -m eval.run_eval documents --forms md,pdf,scan,photo --rung gpu $L --ocr-url http://localhost:8003/v1
uv run python -m eval.voice_eval --help      # voice on the GPU ASR: see eval/VOICE.md
```
Commit `eval/results/*.json` and `eval/RESULTS.md`.

## 5. Point the app at it
App on the laptop: `ENGINE_URL=http://localhost:8100` (through the tunnel) in `.env`, restart the app. Plain-German requests,
voice notes and PDF/photo answers then use the GPU models; without `ENGINE_URL` the app runs the engine in-process on CPU.

## 6. Verification status

### What was verified on CPU (llama.cpp b11985, Q4_K_M GGUF)

| model | verified | notes |
|---|---|---|
| `numind/NuExtract3` (4B) | ✅ nuextract template mode | Verbatim-string extraction works; `json_schema` mode also works but rewrites dates (grounding drops them). Run: `make cpu-llm MODEL=nuextract3`. See DECISIONS.md. |
| `Qwen/Qwen3-1.7B` | ✅ json_schema mode | Used in all CPU eval rungs (eval/RESULTS.md). |
| `mistralai/Ministral-3-3B-Instruct-2512` | ✅ json_schema mode | CPU eval rungs present in RESULTS.md (v2-100). |
| `Qwen/Qwen3-ASR-1.7B` | ❌ not verified on CPU | Requires vLLM ≥ 0.16 for the `/v1/audio/transcriptions` endpoint; llama.cpp has no audio path. |
| `PaddlePaddle/PaddleOCR-VL-1.6` | ❌ not verified on CPU | VLM; no CPU path in this repo. Prompt format (try `OCR:` prefix) unconfirmed. |

### What still needs verification on the A5000

1. **NuExtract3 on vLLM** — vLLM ≥ 0.17 required (Qwen3.5-based architecture). Confirm `chat_template_kwargs` pass-through works in nuextract mode; if not, fall back to `json_schema`.
2. **Qwen3-ASR-1.7B on vLLM** — vLLM ≥ 0.16. Confirm `/v1/audio/transcriptions` accepts a `prompt` field as vocabulary context (Open ASR Leaderboard reports DE WER 3.97 %). Fallback: `openai/whisper-large-v3`.
3. **PaddleOCR-VL-1.6 on vLLM** — confirm the prompt format for full lab-report pages and that the model ID is accepted by vLLM's registry. Fallback: `ENGINE_OCR_PROMPT` override or dots.mocr.
4. **Three-model GPU memory budget** — shares sum to 0.82 of 24 GB (0.42 + 0.22 + 0.18). Confirm no OOM at startup with `nvidia-smi` during `docker compose up`.

### Expected smoke-test commands once the GPU is up

```bash
# 1. NuExtract3: one extraction request
curl -s http://localhost:8001/v1/models | python -m json.tool | grep id
curl -s -X POST http://localhost:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"numind/NuExtract3","messages":[{"role":"user","content":"<|input|>\nBitte Gerinnung von Maria Beispiel geb 12.3.1961 bei Dr. Eva Brandl.\n<|output|>\n"}],"max_tokens":200}' \
  | python -m json.tool

# 2. Qwen3-ASR: transcribe a WAV file (16 kHz mono)
curl -s -X POST http://localhost:8002/v1/audio/transcriptions \
  -F model=Qwen/Qwen3-ASR-1.7B \
  -F file=@/path/to/test.wav \
  -F language=de \
  | python -m json.tool

# 3. PaddleOCR-VL: describe a lab-report image
curl -s -X POST http://localhost:8003/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"PaddlePaddle/PaddleOCR-VL-1.6","messages":[{"role":"user","content":[{"type":"text","text":"OCR:"},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,<BASE64>"}}]}],"max_tokens":1000}' \
  | python -m json.tool

# 4. Full engine smoke test (after SSH tunnel, see step 3)
ENGINE=http://localhost:8100 make gpu-smoke
```
