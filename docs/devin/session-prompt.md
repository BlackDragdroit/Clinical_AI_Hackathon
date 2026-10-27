# Devin session prompt

Paste at the start of every Devin session. Replace `<issue-nr>` and `<short-name>`.

```text
You are working on the repository Clinical_AI_Hackathon.

1. Read AGENTS.md and CLAUDE.md first and follow them.
2. Implement only GitHub issue #<issue-nr>. Do nothing beyond its acceptance criteria.
3. Create the branch devin/<issue-nr>-<short-name> from main.
4. Do not change the stable interfaces listed in CLAUDE.md.
5. Write tests, then run `ruff format .`, `ruff check .` and `pytest`; all must pass.
6. Use only synthetic data. Never add secrets.
7. Open a pull request using the repo's PR template and link the issue ("Closes #<issue-nr>").
```
