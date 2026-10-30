# SWARM — Quick-start: running many Bob instances on BefundBrücke

This file tells you exactly how to start multiple Bob instances, what to say to each one,
and how to keep them from stepping on each other.

---

## TL;DR

```
1. Open 6 Bob windows/sessions
2. Paste the matching "Start prompt" from §2 into each one
3. Each Bob reads AGENTS.md + its own .bob/agents/<role>.md and begins
4. You (or a COORDINATOR Bob) merge PRs when make test is green
```

---

## 1. Prerequisites

```bash
cd /home/scrythe/projects/Clinical_AI_Hackathon
git status          # must be clean
make install        # once
make test           # confirm green baseline (should be ~185 passed)
```

Each Bob instance works on its own branch. They never push to `main` except COORDINATOR.

---

## 2. Start prompts (copy-paste into each Bob session)

### COORDINATOR
```
You are the COORDINATOR agent for BefundBrücke.
Working directory: /home/scrythe/projects/Clinical_AI_Hackathon
Read AGENTS.md first, then read .bob/agents/coordinator.md.
Your first task: confirm the repo is clean (`git status`), run `make test`, and report
the current test count and any failures. Then update AGENTS.md §5 with the current status
of each open item by scanning PROGRESS.md and PLAYTEST_REPORT.md.
```

### IMPROVE
```
You are the IMPROVE agent for BefundBrücke.
Working directory: /home/scrythe/projects/Clinical_AI_Hackathon
Read AGENTS.md first, then read .bob/agents/improve.md.
Start with task P1 (doc-type mismatch → downgrade to review).
Branch: improve/doc-type-mismatch
When done with P1, move to P2. Run `make test` after each fix.
```

### REWRITE
```
You are the REWRITE agent for BefundBrücke.
Working directory: /home/scrythe/projects/Clinical_AI_Hackathon
Read AGENTS.md first, then read .bob/agents/rewrite.md.
Start with the portal split (P11): split app/main.py into portal_router.py and clinic_router.py.
Branch: rewrite/portal-split
Run `make test && uv run python scripts/e2e.py --local` before opening a PR.
```

### PLAYTEST
```
You are the PLAYTEST agent for BefundBrücke.
Working directory: /home/scrythe/projects/Clinical_AI_Hackathon
Read AGENTS.md first, then read .bob/agents/playtest.md.
Start by writing the 8 new test cases listed in your task file (T1–T8).
Branch: playtest/new-edge-cases
Run `make test` after adding each test. Failing tests for unfixed bugs are fine if xfail(strict=True).
```

### DOCS
```
You are the DOCS agent for BefundBrücke.
Working directory: /home/scrythe/projects/Clinical_AI_Hackathon
Read AGENTS.md first, then read .bob/agents/docs.md.
Start with P4 (README answer 4 — misdelivery). Then P5 (What works / what doesn't).
Branch: docs/readme-answers
Only edit .md files. Run `make test` after every commit.
```

### FHIR
```
You are the FHIR agent for BefundBrücke.
Working directory: /home/scrythe/projects/Clinical_AI_Hackathon
Read AGENTS.md first, then read .bob/agents/fhir.md.
Start with P8 (HL7 validator rerun on live-stack bundles).
Branch: fhir/validator-live
Run `make validate` and report TOTAL_ERRORS for each bundle.
```

### ENGINE
```
You are the ENGINE agent for BefundBrücke.
Working directory: /home/scrythe/projects/Clinical_AI_Hackathon
Read AGENTS.md first, then read .bob/agents/engine.md.
Start with P16 (ELGA LOINC codes into the lexicon) since it doesn't need the GPU.
Branch: engine/elga-loinc
Run `make test && uv run python -m metrics.eval_jury_docs` after changes.
```

---

## 3. spawn_subagent pattern (if using Bob's tool programmatically)

If you have a top-level Bob session and want to spawn sub-agents using the `spawn_subagent` tool:

```python
# Spawn all non-GPU agents in parallel (no dependencies between them at start)
spawn_subagent(name="general", description="""
    IMPROVE agent for BefundBrücke.
    Dir: /home/scrythe/projects/Clinical_AI_Hackathon
    Read AGENTS.md, then .bob/agents/improve.md.
    Work P1 (doc-type mismatch), branch improve/doc-type-mismatch.
    Report: what you changed, test count, any failures.
""")

spawn_subagent(name="general", description="""
    DOCS agent for BefundBrücke.
    Dir: /home/scrythe/projects/Clinical_AI_Hackathon
    Read AGENTS.md, then .bob/agents/docs.md.
    Work P4 (README answer 4), branch docs/readme-answers.
    Report: what sections you wrote.
""")

spawn_subagent(name="general", description="""
    PLAYTEST agent for BefundBrücke.
    Dir: /home/scrythe/projects/Clinical_AI_Hackathon
    Read AGENTS.md, then .bob/agents/playtest.md.
    Write tests T1–T8, branch playtest/new-edge-cases.
    Report: how many tests pass / xfail.
""")

spawn_subagent(name="general", description="""
    FHIR agent for BefundBrücke.
    Dir: /home/scrythe/projects/Clinical_AI_Hackathon
    Read AGENTS.md, then .bob/agents/fhir.md.
    Work P14 (name policy double given names), branch fhir/name-policy.
    Report: which test case was added, whether it passes.
""")
```

Wait for all to finish, then run COORDINATOR to merge.

---

## 4. Dependency ordering

Some tasks must be done in order:

```
P1 (IMPROVE: doc-type → review)
  └─► must be done before P7 (PLAYTEST: e2e on real stack) — e2e tests doc-type flow

P8 (FHIR: validator on live bundles)
  └─► must be done after `make up` succeeds on the current main

P11 (REWRITE: portal split)
  └─► do last — it touches app/main.py, which every other agent also reads
  └─► merge only after all other PRs targeting app/main.py are merged

P9 (ENGINE: NuExtract3 vLLM)
  └─► requires the A5000 GPU — skip if not available, document the skip
```

Safe to run in parallel:
- P1 + P4 + T1–T8 + P8 + P14 + P16

---

## 5. Keeping agents in sync

Agents don't share context windows. They share only the git repo.

**When an agent finishes a task:**
1. It appends to `PROGRESS.md`.
2. It opens a PR (or just commits to its branch).
3. It updates `AGENTS.md` §5 (priority queue) — mark the item ✅.

**When the COORDINATOR merges:**
1. It runs the full gate suite.
2. It updates `AGENTS.md` §5.
3. It appends to `PROGRESS.md`.

**When an agent discovers a new bug:**
1. It adds a row to `PLAYTEST_REPORT.md` Open findings.
2. It adds a row to `AGENTS.md` §5 with the next priority number and the suggested owner.
3. It commits a failing test (xfail) on its branch.

---

## 6. File conflict avoidance

These files are **hot** (multiple agents touch them frequently):

| File | Protocol |
|---|---|
| `app/intake_service.py` | IMPROVE edits, FHIR reviews. If both need it simultaneously, IMPROVE's branch is the base — FHIR opens a PR to IMPROVE's branch. |
| `tests/test_flow.py` | PLAYTEST owns additions. IMPROVE adds regression tests. Use different test function names (IMPROVE: `test_fix_*`, PLAYTEST: `test_edge_*`). |
| `README.md` | DOCS owns. Other agents may add a `<!-- TODO(DOCS): ... -->` comment and notify. |
| `PROGRESS.md` | Append-only. Any agent may append. Never edit existing lines. |
| `AGENTS.md` §5 | COORDINATOR owns updates. Other agents mark items ✅ in their own entry. |

---

## 7. Emergency: tests are red after a merge

```bash
git log --oneline -5        # find the bad commit
git revert HEAD             # revert it
make test                   # confirm green again
git push origin main        # push the revert
```

Then notify the agent that owns the broken file (see AGENTS.md §6 ownership map).

---

## 8. File layout reference

```
AGENTS.md                    ← master orchestration doc (read first)
SWARM.md                     ← this file (how to start)
.bob/
  agents/
    coordinator.md           ← COORDINATOR role + merge checklist
    improve.md               ← IMPROVE role + P1–P3, P10, P13
    rewrite.md               ← REWRITE role + P11, Docker/Makefile
    playtest.md              ← PLAYTEST role + G2, G3, T1–T8
    docs.md                  ← DOCS role + P4, P5, P15
    fhir.md                  ← FHIR role + P8, P12, P14, ELGA
    engine.md                ← ENGINE role + P9, P16, eval harness
```
