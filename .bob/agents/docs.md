# DOCS agent

You are the **DOCS** agent for BefundBrücke.
Your job: README, METRICS.md, DECISIONS.md, and the two open TODO sections in the README.
Read `AGENTS.md` first (shared contracts, gates, ownership map).

---

## Open tasks

### P4 — README answer 4: how we notice a misdelivery  ← start here
**Location:** `README.md`, under `### 4. How do we notice a misdelivery?`
The current content is only a `<!-- TODO(Biostat) -->` comment.

**Write the answer.** Cover all three mechanisms in order:

1. **Address lint (M1 pre-check).** `app/misdelivery.lint_address` warns before `!senden` about
   homoglyphs (I/l/1, O/0, rn/m), uppercase in the domain, non-ASCII, edit distance ≤ 2 to
   `KNOWN_DOMAINS`, and phone format. Source: `app/misdelivery.py`.

2. **Identity binding (M1/M2 runtime).** The eID name must match the named person exactly
   (`policy.names_match`). On a mismatch: 403, nothing revealed, `identity_checked FAILED` +
   `misdelivery_caught` in the audit log, ⚠️ to Dr. Hofer. The `classify_identity_failure`
   function distinguishes M1 (the contact had lint warnings) from M2 (it was clean — likely
   forwarded). Source: `app/misdelivery.py`, `app/identity/policy.py`.

3. **Three-way Fellegi–Sunter patient check (M3).** The patient check runs three comparisons:
   requested ↔ typed-by-sender ↔ document. A Fellegi–Sunter score below `t_reject` (–6 bits
   by default) quarantines the answer; between `t_reject` and `t_file` (4 bits) goes to review;
   above `t_file` files. Source: `core/fs_matcher.py`, `core/weights.json`.
   Include the numbers from `METRICS.md` (3/3 misdeliveries caught, 0 harm events).

Include a one-sentence note: "Every misdelivery event is logged in the audit log with who,
what, when, and the M1/M2/M3 classification."

---

### P5 — README "What works / what doesn't" — complete the section
**Location:** `README.md`, under `## What works / what doesn't`
The current MedEng bullets are present. Add bullets for:
- **AI engine** (from PROGRESS.md "Engine slice 2"): 81.7 % fully correct requests,
  0 wrong patients picked in 300 held-out requests, 120/120 Markdown/PDF answers read correctly.
- **Portal / SWE 2**: mobile-first portal working; 5 playtest fixes in `PLAYTEST_REPORT.md`;
  G2 (e2e on real stack) and G3 (stopwatch) not yet run.
- **Open findings** (from PLAYTEST_REPORT.md O1–O10): list the ones still open as bullets
  under a "Still open" sub-heading.

---

### P15 — O4: production eID note (state + nonce)
**Location:** `README.md` §5 "Where does the service run?" or a new "Production notes" section.
**Write a short paragraph** (3–5 sentences) noting:
- The mock eID assertion is not bound to the link in the prototype (O4 from PLAYTEST_REPORT).
- Production must use the ID Austria OIDC authorization-code flow.
- The `state` parameter must encode the link token (or a PKCE verifier bound to the link).
- `nonce` must be single-use and tied to the session.
- This is a note for whoever wires `eid_mock.py` → the real OIDC library.

---

### DECISIONS.md maintenance
After every agent merge, scan `git log --oneline -20` for changes to shared contract files.
If a contract changed without a `DECISIONS.md` entry, add one now:
`- <what changed> — <why> — <who>`.

---

### METRICS.md update template
`make metrics` writes the file, but it may not have all rows. After every full stack run,
ensure every row in the table has a measured number (not "not run"):

| Metric | Expected source |
|---|---|
| FHIR validation | `make validate` → TOTAL_ERRORS=0 |
| Outside person effort | `metrics/stopwatch.csv` |
| Misdeliveries | `scripts/dev/flow.sh m1 m2 m3` |
| Audit coverage | `/audit.json` → `chain_ok: true`, `coverage: 6` |
| Patient data in email/SMS | `tests/test_template_leak.py` |
| Jury documents | `metrics/eval_jury_docs.py` |

---

## Working rules for DOCS

- Branch: `docs/<short-name>`.
- Only edit `.md` files and `METRICS.md`. Never edit Python files.
- Run `make test` after any METRICS.md change to confirm the test suite still expects the
  same format (there are tests that parse METRICS.md).
- Append to `PROGRESS.md` when a section is done.
- Keep the existing Mermaid diagrams intact. If you add a new one, test it renders in GitHub.
