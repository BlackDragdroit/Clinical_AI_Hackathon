# BefundBrücke. `make help` lists targets.
SHELL := /bin/bash
.DEFAULT_GOAL := help
RUN := uv run --no-sync

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

env:             ## create .env from .env.example (once)
	@test -f .env || cp .env.example .env

install: env     ## python deps into .venv
	uv sync

test:            ## unit + flow tests (no Docker needed)
	$(RUN) pytest -q

dev: env         ## app locally on :8000 with reload; Matrix off unless MATRIX_ENABLED=1 in your shell
	set -a; source .env; set +a; MATRIX_ENABLED=$${MATRIX_ENABLED_DEV:-0} $(RUN) uvicorn app.main:app --reload --port 8000

up: env          ## whole stack: synapse+users+room, hapi seeded, mailpit, element, app
	docker compose up -d hapi mailpit element   # synapse starts in setup_synapse.sh once its config exists
	./scripts/setup_synapse.sh
	$(RUN) python -m scripts.seed_hapi
	docker compose up -d --build app
	@echo "Element  http://localhost:8080  (lena.hofer / see .env)"
	@echo "Mailpit  http://localhost:8025   SMS http://localhost:8000/sms   Audit http://localhost:8000/audit"

public:          ## share the running stack through one public address: make public URL=https://<tunnel> (URL=--off to undo)
	./scripts/public_up.sh $(URL)

down:            ## stop the stack (keeps volumes)
	docker compose down

reset:           ## stop the stack AND delete its volumes (synapse users, hapi data, app db)
	docker compose down -v

logs:            ## follow app logs
	docker compose logs -f app

seed:            ## (re)load the scenario patient into HAPI
	$(RUN) python -m scripts.seed_hapi

validate:        ## official HL7 validator on every filed bundle -> error count
	./scripts/validate_all.sh

metrics:         ## build METRICS.md from the running stack
	$(RUN) python -m scripts.run_metrics

jury-eval:       ## core decisions on metrics/jury_docs vs expected
	$(RUN) python -m metrics.eval_jury_docs

engine:          ## AI engine locally on :8100 (models via ENGINE_*_URL; without them: rules + CPU fallbacks)
	$(RUN) uvicorn engine.api:app --reload --port 8100

gpu-up:          ## on the A5000 VM: vLLM (text, speech, OCR) + engine on :8100
	docker compose -f deploy/gpu/docker-compose.yml up -d --build

gpu-smoke:       ## check every model answers: ENGINE=http://<vm>:8100 make gpu-smoke
	$(RUN) python -m scripts.gpu_smoke --engine $${ENGINE:-http://localhost:8100}

LLAMA ?= $(HOME)/.cache/befundbruecke
cpu-llm:         ## small model on this laptop's CPU (llama.cpp b11985): MODEL=NuExtract3|Qwen3-1.7B -> http://localhost:8011/v1
	$(LLAMA)/llama/llama-server -m $(LLAMA)/models/$${MODEL:-NuExtract3}-Q4_K_M.gguf --jinja -c 8192 --port 8011 -t $$(nproc)

engine-data:     ## build the engine test sets (patients, requests, documents) under eval/data
	$(RUN) python -m eval.build_data

engine-eval:     ## run the engine on the test sets -> eval/RESULTS.md (CIs, model ladder)
	$(RUN) python -m eval.run_eval

.PHONY: help env install test dev up public down reset logs seed validate metrics jury-eval engine gpu-up gpu-smoke engine-data engine-eval
