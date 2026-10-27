# AGENTS.md

Short rules for coding agents (e.g. Devin). [CLAUDE.md](CLAUDE.md) is the authoritative source; read it first.

- Implement only the linked issue. One branch, one PR per task.
- Do not change the stable interfaces listed in CLAUDE.md. Add new functions or modules instead.
- Use FHIR R4B: import from `fhir.resources.R4B`.
- Setup: `pip install -e ".[dev]"`. Before opening a PR: `ruff format .`, `ruff check .`, `pytest`.
- Write tests for new behavior; mapping tests must validate the produced resource.
- Synthetic data only. No secrets. No new dependencies without justification in the PR.
- Open the PR with the PR template and link the issue.
