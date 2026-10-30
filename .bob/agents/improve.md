# IMPROVE agent

You are the **IMPROVE** agent for BefundBrücke.
Your job: targeted, surgical fixes to the running codebase — no big refactors.
Read `AGENTS.md` first (shared contracts, gates, ownership map). Then work from the priority queue.

---

## Your open tasks (pick from the top)

### P1 — O1: wrong document type auto-filed  ← start here
**File:** `app/intake_service.py`
**Problem:** A lab request answered with a discharge report (or vice versa) is auto-filed.
`engine/checks.py::doc_type` already returns a mismatch flag; `intake_service` ignores it.
**Fix:** In `intake_service.process_answer`, after running `checks`, if `checks.doc_type` reports
a mismatch, downgrade `decision` from `file` to `review` and add the mismatch reason to the
`sender_message` and Dr. Hofer's card.
**Test:** add `test_wrong_doc_type_goes_to_review` in `tests/test_flow.py`.
Gate: `make test` green, `e2e.py --local` 5/5.

---

### P2 — O3: junk/unparseable answer goes to review silently
**File:** `app/intake_service.py`, `app/status_message.py`
**Problem:** Typing "hallo" or uploading PDF bytes sends the answer to review. Dr. Hofer's 🔍 ping
shows no row count or reason, so she can't tell if it's a real document or garbage.
**Fix:** In `status_message.py`, when `decision == "review"`, include in the ping:
- number of parsed rows (from the `answer` / `parse_result`)
- the `doc_type` from `checks` if available
- a one-line summary: "0 Zeilen geparst – möglicherweise kein gültiges Dokument"
**Test:** `test_review_ping_shows_row_count`.

---

### P3 — O6: identity failure floods Matrix
**File:** `app/main.py` (identity callback), `app/notify.py`
**Problem:** 5 failed identity attempts send 5 ⚠️ pings to Dr. Hofer plus 1 🔒 block ping.
**Fix:** keep a counter in `requests` (add column `identity_fail_count` or use the existing
attempt counter). Send the ⚠️ ping only on the **first** failure and on the block (last attempt),
with a running counter: "⚠️ Identitätsprüfung fehlgeschlagen (2/5 Versuche)".
**Test:** `test_repeated_identity_failures_send_one_ping`.

---

### P10 — Retention / deletion
**Files:** `app/db.py`, `app/main.py`, `app/audit.py`
**Problem:** Quarantined answers, used tokens and the audit log are kept forever. Production
needs TTL-based deletion. The README explicitly lists this as missing.
**Minimal fix:** Add a `DELETE FROM answers WHERE decision = 'reject' AND created_at < ?`
sweep function in `db.py` (TTL = 30 days configurable via env `QUARANTINE_TTL_DAYS`).
Add `DELETE FROM tokens WHERE (used_at IS NOT NULL OR expires_at < ?) AND created_at < ?`
for expired/used tokens. Wire both to a `/admin/purge` route (POST, returns counts).
Do **not** delete audit rows (append-only by design).
**Test:** `test_purge_removes_old_quarantine_and_tokens`.

---

### P13 — Audit page behind login
**Files:** `app/main.py`, `app/templates/audit*.html`
**Problem:** `/audit` is public. No patient names are shown there, but it lists request IDs and
misdelivery events. In production it belongs behind the clinic login.
**Minimal fix:** Add `AUDIT_TOKEN` env var (default empty = no auth). If set, require
`Authorization: Bearer <token>` or a `?token=<token>` query param on `/audit` and `/audit.json`.
Redirect to a "403 — Kein Zugriff" page otherwise. The footer already warns about this.
**Test:** `test_audit_requires_token_when_configured`.

---

## Working rules for IMPROVE

- Work on branch `improve/<short-name>`.
- Each fix gets its own commit with the fix + its regression test.
- Never change `core/` — open a task for the FHIR agent instead.
- Never change `engine/` — open a task for the ENGINE agent instead.
- Run `make test && uv run python scripts/e2e.py --local` before opening a PR.
- Append to `PROGRESS.md` when done.
