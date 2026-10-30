# BefundBrücke — Multi-Agent Bob Orchestration

This file is the **single source of truth** for running many Bob instances in parallel on this project.
Every agent reads this file first. After reading it they read their own task file in `.bob/agents/`.

---

## 1. Mental model

```
ORCHESTRATOR (you, human or a top-level Bob)
│
├── REWRITE      .bob/agents/rewrite.md        full codebase rewrites / refactors
├── IMPROVE      .bob/agents/improve.md        targeted improvements & open findings
├── PLAYTEST     .bob/agents/playtest.md       end-to-end testing & edge cases
├── DOCS         .bob/agents/docs.md           README, METRICS, design answers
├── FHIR         .bob/agents/fhir.md           FHIR R4 / HL7 validator / core/
├── ENGINE       .bob/agents/engine.md         AI engine, eval harness, model tuning
└── COORDINATOR  .bob/agents/coordinator.md   merges PRs, resolves conflicts, runs gates
```

Spawn one Bob per role. Each runs in its own branch (name convention below). They never edit
the same file at the same time. Conflicts go to COORDINATOR.

---

## 2. Shared contracts — never change without telling all agents

| Contract | File | Used by |
|---|---|---|
| SQLite schema & status lifecycle | `app/db.py` | ALL |
| `audit.log(event, request_id, actor, details)` — 6 required events | `app/audit.py` | ALL |
| `notify.doctor(text, request_id)` outbox | `app/notify.py` | IMPROVE, REWRITE |
| `Channel.send(to, link)` — link only, never patient data | `app/delivery/base.py` | REWRITE, IMPROVE |
| `EidAssertion` from `eid_mock.verify()` | `app/identity/eid_mock.py` | IMPROVE, PLAYTEST |
| `process_answer(req, …)` → decision | `app/intake_service.py` | IMPROVE, FHIR |
| `commands.handle(text, sender)` | `app/commands.py` | REWRITE |
| `core/` — import only, never edit without FHIR agent sign-off | `core/`, `app/core_bridge.py` | FHIR |

**Rule:** If your change touches a shared contract file, write a one-line entry to `DECISIONS.md`
and mention every agent that uses it.

---

## 3. Branch naming

| Agent | Branch prefix | Example |
|---|---|---|
| REWRITE | `rewrite/` | `rewrite/portal-split` |
| IMPROVE | `improve/` | `improve/doc-type-mismatch` |
| PLAYTEST | `playtest/` | `playtest/g2-e2e-stack` |
| DOCS | `docs/` | `docs/answer-4-misdelivery` |
| FHIR | `fhir/` | `fhir/validator-zero` |
| ENGINE | `engine/` | `engine/nuextract3-vllm` |
| COORDINATOR | `main` | — |

PRs always target `main`. COORDINATOR merges only when `make test` is green.

---

## 4. Global gates — every agent must pass before merging

```bash
make install          # first time only
make test             # must be green, 0 xfail unless marked strict=False
uv run python scripts/e2e.py --local   # 5/5 flows
uv run python -m metrics.eval_jury_docs  # wrongly filed = 0 / 17
```

If a gate fails, fix it before opening a PR. Never weaken a test.

---

## 5. Priority queue (ordered, highest first)

These are the open items from PROGRESS.md and PLAYTEST_REPORT.md as of the last full run.
Each agent picks its own items (column "Owner"). COORDINATOR updates this table after each merge.

| # | Item | Owner | Branch | Status |
|---|---|---|---|---|
| P1 | O1 — lab request answered with discharge report auto-filed (should be `review`) | IMPROVE | `improve/doc-type-mismatch` | open |
| P2 | O3 — junk/unparseable answer goes to review without a summary shown to Dr. Hofer | IMPROVE | `improve/review-summary` | open |
| P3 | O6 — 5 failed identity pings flood Matrix (deduplicate to 1 + counter) | IMPROVE | `improve/identity-ping-dedup` | open |
| P4 | README answer 4 (misdelivery numbers, Biostat TODO) | DOCS | `docs/answer-4` | open |
| P5 | README "What works / what doesn't" completion | DOCS | `docs/what-works` | open |
| P6 | METRICS.md full run on the live stack (G1) | PLAYTEST | `playtest/g1-metrics` | open |
| P7 | e2e on real `make up` stack (G2) | PLAYTEST | `playtest/g2-e2e-stack` | open |
| P8 | HL7 validator rerun on bundles filed through the live stack | FHIR | `fhir/validator-live` | open |
| P9 | NuExtract3 vLLM format verification on A5000 | ENGINE | `engine/nuextract3-vllm` | open |
| P10 | Retention / deletion of stored answers and quarantine | IMPROVE | `improve/retention` | open |
| P11 | Portal split: internet-facing vs. clinic-side (production boundary) | REWRITE | `rewrite/portal-split` | open |
| P12 | Practitioner / Organization deduplication (no identifier today) | FHIR | `fhir/practitioner-dedup` | open |
| P13 | Audit page behind clinic login | IMPROVE | `improve/audit-login` | open |
| P14 | Name check: double given names ("Eva Maria Brandl" blocked by policy) | FHIR | `fhir/name-policy` | open |
| P15 | O4 — mock eID assertion not tied to the link (state+nonce for production) | DOCS | `docs/eid-production-note` | open |
| P16 | ELGA LOINC preferred codes folded into the lexicon | ENGINE | `engine/elga-loinc` | open |

---

## 6. File ownership map

When two agents need the same file, the one listed first is the **primary owner**.
The other agent opens a PR to the primary's branch, not to main.

| File / dir | Primary | Secondary |
|---|---|---|
| `app/main.py` | IMPROVE | REWRITE |
| `app/intake_service.py` | IMPROVE | FHIR |
| `app/commands.py` | REWRITE | IMPROVE |
| `app/bot.py` | REWRITE | — |
| `app/audit.py`, `app/templates/audit*.html` | DOCS | IMPROVE |
| `app/identity/policy.py` | FHIR | IMPROVE |
| `core/` | FHIR | — |
| `engine/` | ENGINE | — |
| `eval/` | ENGINE | DOCS |
| `tests/` | PLAYTEST | ALL |
| `scripts/e2e.py` | PLAYTEST | — |
| `README.md`, `DECISIONS.md`, `METRICS.md` | DOCS | ALL |
| `PROGRESS.md` | COORDINATOR | ALL (append only) |
| `docker-compose.yml`, `Makefile`, `Dockerfile` | REWRITE | — |
| `deploy/` | REWRITE | ENGINE |

---

## 7. How to spawn an agent

Each Bob instance should be started with:

```
Read AGENTS.md first, then read .bob/agents/<your-role>.md, then begin.
```

Or, if using Bob's `spawn_subagent` tool:

```python
spawn_subagent(
    name="general",
    description="""
    You are the IMPROVE agent for BefundBrücke.
    Read /home/scrythe/projects/Clinical_AI_Hackathon/AGENTS.md first,
    then read /home/scrythe/projects/Clinical_AI_Hackathon/.bob/agents/improve.md,
    then begin work on P1 (O1 doc-type mismatch → downgrade to review).
    Branch: improve/doc-type-mismatch. Run make test before opening PR.
    """,
    fork_context=False
)
```

Replace `improve.md` and the task description with the appropriate agent file.

---

## 8. After-action protocol (COORDINATOR runs this after every merge)

1. `make reset && make up` from a clean clone.
2. `scripts/dev/flow.sh r1 r2 m1 m2 m3` — all must print ✅ / ⚠️ as expected.
3. `make metrics` → update `METRICS.md`.
4. Update the priority queue in section 5 above (mark merged items done, add new ones).
5. Append a milestone entry to `PROGRESS.md`.

---

## 9. Quick reference card

```
make install          deps
make test             unit + integration (no Docker)
make dev              app :8000, MATRIX_ENABLED=0
make up               full Docker stack
make reset            wipe volumes
make engine           engine :8100 (CPU/rules)
make validate         HL7 validator on both scenario bundles
make metrics          writes METRICS.md
make gpu-up           vLLM GPU stack (A5000)
scripts/dev/flow.sh r1|r2|m1|m2|m3   replay on running stack
scripts/e2e.py        Playwright: 5 flows, --local for no Docker
metrics/eval_jury_docs.py   n=17 jury documents
```
