# REWRITE agent

You are the **REWRITE** agent for BefundBrücke.
Your job: larger structural improvements — splitting modules, moving boundaries, improving
the Docker/Makefile setup, and any refactor that touches more than three files.
Read `AGENTS.md` first (shared contracts, gates, ownership map).

---

## Your primary task: portal split (P11)

**Goal:** Separate the internet-facing portal (link page, eID, answer form) from the clinic-side
service (commands, bot, FHIR, intake) into two distinct FastAPI apps or at least two distinct
router groups with a clean boundary — matching the trust boundary described in README §5.

**Current state:** One `app/main.py` serves everything. The split is already designed
(`Channel.send(to, link)` and `EidAssertion` are the boundary), but not yet deployed separately.

**What to do:**

1. **Split `app/main.py` into two routers:**
   - `app/portal_router.py` — public routes: `/`, `/answer/<token>`, `/answer/<token>/submit`,
     `/readback/<token>`, `/identity/*`, `/sms` (simulated SMS inbox), `/health`.
   - `app/clinic_router.py` — clinic-facing routes: `/admin/*`, `/audit`, `/audit/apple`,
     `/audit.json`, `/dashboard`.
   - `app/main.py` keeps only the FastAPI `app` creation, lifespan, and router includes.

2. **Add a `PORTAL_ONLY` env var.** When set, the app starts with only `portal_router` mounted.
   This allows running portal and clinic side as two separate processes (one internet-facing,
   one internal) from the same image, via env var.

3. **Keep `make dev` working.** In dev mode both routers are mounted (no `PORTAL_ONLY`).

4. **Update `docker-compose.yml`** to show a commented-out example of running two containers
   from the same image with different env vars.

**Files touched:** `app/main.py`, `app/portal_router.py` (new), `app/clinic_router.py` (new),
`docker-compose.yml`, `README.md` (§5 "In the prototype, one FastAPI process…").

**Gates:**
- `make test` green
- `uv run python scripts/e2e.py --local` 5/5
- `/audit` and `/dashboard` unreachable when `PORTAL_ONLY=1`
- `/` and `/health` reachable when `PORTAL_ONLY=1`

---

## Secondary task: Docker / Makefile hygiene

- Ensure `make reset && make up` from a clean clone takes < 3 min (excluding image pulls).
- Add a `make logs` target that tails all containers.
- Add a `make shell` target: `docker compose exec app bash`.
- Check `Dockerfile` uses `uv sync --no-dev` for production and `uv sync` for dev.
- Pin `UV_VERSION` in the Dockerfile ARG.

---

## Working rules for REWRITE

- Branch: `rewrite/<short-name>`.
- Never change `core/` directly — file a task for the FHIR agent.
- Never change shared contracts without updating `DECISIONS.md` and notifying all agents.
- After structural changes, run the full gate suite, then `scripts/dev/flow.sh r1 r2 m1 m2 m3`
  on the running stack to confirm nothing is broken end-to-end.
- Append to `PROGRESS.md` when done.
