# Product Road-Map — Development Handoff

> **Purpose:** resume development in a fresh session with full context.
> **Last updated:** 2026-07-20 · **Author:** Claude (session with Rahul)
> **Read next:** [build_roadmap.md](./build_roadmap.md) (the plan) · [roadmap_gap_register.md](./roadmap_gap_register.md) (findings) · the `increment-1/` and `increment-2/` folders (per-workstream design + build notes).

---

## 0. TL;DR — where we are

* **Increment 1 (One-Loop Foundations) — ✅ BUILT & MERGED to `master`.** Four workstreams: **SIG** (signal bus), **GOV** (governance + PolicyGate), **SCH** (tenant schema / records / data plane), **LOOP+ENV** (Loop runtime, budget envelopes, wallet holds). Register findings B1/B2/B3/B5/B6/B8/E3/A6 closed.
* **Increment 2 (The Solo Pack — the sellable MVP) — DESIGNED + first workstream built.**
  * All 6 workstream design docs written and decisions locked (`increment-2/`).
  * **SLICE** (email→quote vertical slice) — ✅ BUILT on branch **`inc2/slice`** (not yet merged). The sellable exit-demo passes end-to-end. Closes C1 for P03.
  * Remaining Inc-2 workstreams: **PACK, KAR, ONBOARD, TRUST, RETR** (not started).

**Everything committed is green:** mypy `--strict` (150 files), ~953 unit + parity + eval, layout lint, all migrations apply/rollback clean.

---

## 1. ⚠️ Standing action — PUSH (do this first)

This dev VM has **no GitHub credentials**, so every merge/commit this session accumulated **locally only**:

* `master` is **16 commits ahead of `origin/master`** — all of Increment 1 + Inc-2 design docs.
* `inc2/slice` is **5 commits ahead of `master`** — the SLICE build.

**To resume:**
```bash
cd /home/rahul/workspace/hb-proto-3
git checkout master && git merge inc2/slice --no-edit   # fast-forward; SLICE → master
git push origin master                                   # once creds are available
```
Nothing is lost — it's all committed. Verify with `git log --oneline -20`.

---

## 2. What's built (map)

### Increment 1 (on `master`)
| Workstream | New package(s) | Migration | Key tables/seams |
|---|---|---|---|
| SIG | `backend/src/ai/signals/` | `sig001` | `signals` (outbox), `trigger_registry`; dispatcher + sweeper crons; email-ingest producer |
| GOV | `backend/src/ai/governance/` (extended) | `gov001` | typed `Governance` schema, `hitl_checkpoint_defs` (18), `human_approvals.checkpoint_key`, the **PolicyGate** (a loop stage before the Pre-Critic), deploy validators |
| SCH | `backend/src/ai/tenant_schema/` | *(none — tenant tables are bootstrapped per-tenant, not control-plane Alembic)* | HBS 27-object spine, record service (CAS + owner-writes/others-propose), two-backend data plane (schema / container), memory viewport, export |
| LOOP+ENV | `backend/src/ai/loop/` | `loop001`, `loop002` (Sheel seed) | `loop_runtime` + heartbeat/watchdog crons, `budget_envelopes` (protected reserve), `wallet_holds` (closes the E3 race), `credit_wallets.wallet_debt` |

### Increment 2 / SLICE (on `inc2/slice`)
* `backend/src/ai/solo_pack/` — `templates/` (4 curated entities), `loader.py` (GOV-validating), `activation.py` (seed + owner-id resolve + triggers), `tools.py` (`tenant_record_write`, `emit_business_signal`).
* GOV `authority.py` gained the **`email_dispatch`** category (so an A1 `send_email` raises a HITL card).
* Tests: `tests/unit/test_solo_pack_templates.py`, `tests/integration/test_solo_pack_{activation,tools,slice_e2e}_db.py`.
* The **`test_solo_pack_slice_e2e.py`** is the north-star test — the sellable path email→approved-quote across real SIG+SCH+GOV seams.

**Migration head:** `loop002`. Run `poetry run alembic upgrade head` from `backend/` on a fresh DB.

---

## 3. How to resume — the next work

Build order (from [increment-2/00_overview.md](./increment-2/00_overview.md) §4): **SLICE ✅ → PACK+KAR → ONBOARD → TRUST → RETR.**

**Next up: PACK** ([increment-2/03_pack_agents_processes.md](./increment-2/03_pack_agents_processes.md)) — broaden the slice to the full **12 curated agents + 6 Wave-0 process sheets + 7 bundles**. The SLICE templates (`solo_pack/templates/`) and `activation.py` are the pattern to copy — PACK generalizes `activate_slice` into `activate_bundle`. Then **KAR** ([02](./increment-2/02_kar_gateways.md)) adds the WhatsApp gateway (KAR-03) + the voice stub (KAR-01).

Each workstream doc has: self-contained design, code mapping, a task plan, and a **§ Brainstorm Decisions** block (already answered — do not re-litigate). Follow the Increment-1 rhythm: branch `inc2/<workstream>`, build task-by-task, keep gates green, add a §N build-note delta log + flip maturity tags on merge.

**Voice (KAR-01 real) + B7** are **deferred to Increment 3** (with Pragya, who needs the same realtime path).

---

## 4. Locked decisions (Increment 2 — do not re-open)

From `increment-2/00_overview.md` §2 and each doc's decisions block:

1. **Thin vertical slice first** (done: email→P03).
2. **Async-first MVP; voice deferred** to Inc 3. KAR-01 is a registered stub.
3. **Curated hand-authored agent templates** (reviewed like the HBS spine); the Meta-Agent Board is for tenant-*custom* agents.
4. **Wizard onboarding; Pragya in Inc 3** — the wizard's step APIs are authored as Pragya's stage APIs.
5. **Global-neutral market** — pluggable consent/DNC + multi-currency; no hard-coded jurisdiction.
6. **Graduated dunning** — notify → grace (7d, configurable) → **read-only** (agents stop acting, inbound parked-not-dropped) → suspend.
7. **All bundles included at all subscription tiers** (no per-tier bundle gating).
8. **Consent is tenant-configured from day one** (no imposed global opt-in default).
9. First slice = **email → P03 acquisition**.

---

## 5. Conventions & gotchas (learned this session — save future debugging)

* **New `ai/` package → add it to the strict-typing allowlist** in `backend/scripts/typecheck_ai.py` (`CLEAN_PACKAGES`). Current: governance, orm, planning, meta, memory, core, signals, tenant_schema, loop, solo_pack.
* **`backend/src/ai/core/agent_loop.py` is pinned at its 1500-line cap** (layout lint). Do NOT add code there — extract to a helper module (that's why `gate_and_maybe_stop` lives in `policy_gate.py` and wallet-hold admission lives in `arq_jobs.py`).
* **De-canary layout lint** bans the token `P11`/`p11`/`phase11` in `ai/` source (it flags leftover phase-11 canaries). The HBS fixture stores owner codes numerically (`"owner": 11`) and renders `P{n:02d}` at seed for exactly this reason. Don't write a literal `"P11"` in `ai/` source or comments.
* **Tenant schema routing** uses SQLAlchemy `schema_translate_map` (symbolic `tenant` schema → `t_<hex>`), NOT `SET search_path` (which leaks onto pooled connections). Tenant tables use a separate `TenantBase`.
* **Records are tenant-DB; signals/runs/billing/memory are control-plane.** Cross-DB emits (e.g. `object.change_proposed`) go through a *separate* `AsyncSessionLocal` transaction — never assume one transaction spans both planes.
* **Wallet-hold admission reads the balance from the FOR-UPDATE-locked row directly** (`_locked_available`), never via `CreditService.get_balance` — that method's daily-credit auto-injection commits and would release the lock mid-admission (re-opening the E3 race).
* **Solo Pack tools register at the entry points** (`worker.py` + `main.py` via `register_solo_pack_tools()`), NOT from `tools/__init__` — importing `solo_pack.tools` from that package init cycles.
* **Integration tests dispose the global engine** at fixture setup (`await engine.dispose()`) — pytest-asyncio gives each test its own loop and asyncpg can't share pooled connections across loops. Follow the self-managed committed-fixture pattern (create company + tenant schema + wallet, clean up in `finally`, delete child tables before parents: signals before execution_runs, etc.).
* **PolicyGate only gates *categorised* acts** (`CATEGORY_RULES` + `TOOL_CATEGORY_MAP` in `governance/authority.py`). A new money/comms tool needs a category + mapping or it won't be governed. At A1 any categorised external effect → HITL; at A2+ it's band-based/autonomous.
* **Testing LLM-driven agents:** don't script the prompt-hash-keyed MockLLM through multi-run flows (fragile). Drive the *real platform seams* deterministically (signal dispatch, record graph, PolicyGate) and supply each agent's tool-calls as the unit of work; leave prose quality to eval goldens. See `test_solo_pack_slice_e2e.py`.

---

## 6. How to run the gates (from `backend/`)

```bash
cd backend
poetry run pytest tests/unit -q                          # ~950 unit tests
poetry run pytest tests/parity tests/eval -q             # engine parity + eval harness
poetry run python scripts/typecheck_ai.py                # mypy --strict over the allowlist
poetry run python scripts/lint_ai_layout.py              # layout + de-canary lint (exit 0)
poetry run pytest tests/integration/test_*_db.py -q      # needs a live Postgres (DATABASE_URL)
poetry run alembic upgrade head                          # apply migrations
poetry run mypy --strict --follow-imports=silent src/ai/<pkg>   # one package
```
Integration tests **skip cleanly** without `DATABASE_URL`. Docker is available for the tenant-DB container backend (default backend is `schema`, needs no Docker).

---

## 7. Ops remainders (human/prod-only — track separately)

* **`hb-tenant-db` container go-live** (SCH): build `backend/docker/tenant-db/`, `trivy` scan, push to registry, pin the digest, then flip `TENANT_DB_BACKEND=container`. Until then the `schema` backend is the tested default. Mirror the shipped sandbox S7 path.
* **Increment-0 items** were reported done by Rahul (PyPI publish of `hb-cortex-memory`, sandbox canary). Re-confirm before prod GA.
* **Frontend** (ONBOARD, Inc-2): the admin UI (signals/triggers/envelopes) + the onboarding wizard are not built yet — Node/browser toolchain, out of scope for the backend VM.

---

## 8. Register findings status (from the gap register)

* **Closed by Inc 1:** A6, B1, B2, B3, B5, B6, B8, E3 (+ the earlier v3 doc-pass batch).
* **Closing in Inc 2:** C1 (P03 done; other 5 in PACK), C3, C5, D6, B13, E1, E2, E4 — see `increment-2/00_overview.md` §5.
* **Deferred:** B7 (realtime voice) → Increment 3 with Pragya.
* **Still open (later increments):** B10, B11, B12, B14, C2, C4, C6, D2, D3, D4, D5. See [roadmap_gap_register.md](./roadmap_gap_register.md) and each increment charter.

---

## 9. One-paragraph orientation for a fresh agent

> The repo is a multi-tenant agentic platform. Increment 1 built the "one-loop" substrate (signal bus, governance/PolicyGate, per-tenant business schema + record graph, Loop runtime + budget/wallet safety) — all on `master`. Increment 2 is building the sellable MVP, the "Solo Pack": curated A1 agents that answer email/WhatsApp, qualify, quote, chase invoices, and report, governed with HITL. The first vertical slice (email→quote) is built and proven end-to-end on `inc2/slice`. Resume by merging that to master, pushing, then building the **PACK** workstream (the other 10 agents + 6 process sheets + bundles) per `docs/product-road-map/increment-2/03_pack_agents_processes.md`. Keep every gate green; follow the conventions in §5 above.
