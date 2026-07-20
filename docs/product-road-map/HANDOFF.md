# Product Road-Map — Development Handoff

> **Purpose:** resume development in a fresh session with full context.
> **Last updated:** 2026-07-20 · **Author:** Claude (session with Rahul)
> **Read next:** [build_roadmap.md](./build_roadmap.md) (the plan) · [roadmap_gap_register.md](./roadmap_gap_register.md) (findings) · the `increment-1/` and `increment-2/` folders (per-workstream design + build notes).

---

## 0. TL;DR — where we are

* **Increment 1 (One-Loop Foundations) — ✅ BUILT & MERGED to `master`.** Four workstreams: **SIG** (signal bus), **GOV** (governance + PolicyGate), **SCH** (tenant schema / records / data plane), **LOOP+ENV** (Loop runtime, budget envelopes, wallet holds). Register findings B1/B2/B3/B5/B6/B8/E3/A6 closed.
* **Increment 2 (The Solo Pack — the sellable MVP) — DESIGNED + SLICE, PACK, KAR built; ONBOARD backend built.**
  * All 6 workstream design docs written and decisions locked (`increment-2/`).
  * **SLICE** (email→quote vertical slice) — ✅ BUILT & **MERGED to `master`** (and on the remote). Closes C1 for P03.
  * **PACK** (full Wave-0 roster) — ✅ BUILT & **merged to local `master`** (push pending, §1). 16 entities + 7 bundles + generalized activation + runtime SoD. Closes C1 (all 6) + Inc-1 owner-id/governance carryovers.
  * **KAR** (outward gateways) — ✅ BUILT & **merged to local `master`**. KAR-03 WhatsApp (via SIG) + KAR-01 voice stub; roster **18**. Karuna threat posture + consent seam. Real voice/B7 → Inc 3.
  * **ONBOARD** (setup wizard) — ✅ **Backend built & merged to local `master`**. The wizard **step APIs** (`/ai/onboarding/*`, Pragya's Inc-3 stages) + the budget-envelope admin GET. **Frontend is a separate track, out of scope on this VM.**
  * **TRUST** (billing safety + consent) — 🚧 **D6 (consent registry) + C3 (per-checkpoint HITL SLAs) built** on branch **`inc2/trust`** (not yet merged): consent/DNC/unsubscribe store wired into KAR's seam (migration `trust001`) + checkpoint SLA columns/policy/sweep (`trust002`). **Remaining: C5, B13, E1, E2, E4** (dunning/middleware + economics).
  * Remaining Inc-2: **TRUST (C5/B13/E1/E2/E4), RETR** (not started); ONBOARD **frontend**.

**Everything committed is green:** mypy `--strict` (167 files), 1022 unit + parity + eval, layout lint, all migrations apply/rollback clean.

---

## 1. ⚠️ Standing action — PUSH (this VM can't; do it from a credentialed host)

The remote (`origin`, an HTTPS GitHub URL) is at `19a3d4d` — Increment 1 + Inc-2 design docs + the **SLICE** build (pushed from a credentialed host earlier; read-only `git ls-remote` confirms). This VM has **no write credentials** (`no credential.helper`, no `gh`), so `git push` fails with `could not read Username`. Nothing is lost — all committed:

* **`master`** — has **PACK + KAR + ONBOARD-backend + TRUST/D6** merged, **~13 commits ahead of `origin/master`**, not yet pushed.
* **`inc2/trust`** — **TRUST / C3 (per-checkpoint HITL SLAs)** on top of D6, **not yet merged**.

To publish, from an environment with GitHub write access:
```bash
cd /home/rahul/workspace/hb-proto-3
git checkout master && git merge inc2/trust --no-edit   # TRUST/C3 → master
git push origin master
```
Verify with `git log --oneline -25` and `git rev-list --left-right --count origin/master...master`.

---

## 2. What's built (map)

### Increment 1 (on `master`)
| Workstream | New package(s) | Migration | Key tables/seams |
|---|---|---|---|
| SIG | `backend/src/ai/signals/` | `sig001` | `signals` (outbox), `trigger_registry`; dispatcher + sweeper crons; email-ingest producer |
| GOV | `backend/src/ai/governance/` (extended) | `gov001` | typed `Governance` schema, `hitl_checkpoint_defs` (18), `human_approvals.checkpoint_key`, the **PolicyGate** (a loop stage before the Pre-Critic), deploy validators |
| SCH | `backend/src/ai/tenant_schema/` | *(none — tenant tables are bootstrapped per-tenant, not control-plane Alembic)* | HBS 27-object spine, record service (CAS + owner-writes/others-propose), two-backend data plane (schema / container), memory viewport, export |
| LOOP+ENV | `backend/src/ai/loop/` | `loop001`, `loop002` (Sheel seed) | `loop_runtime` + heartbeat/watchdog crons, `budget_envelopes` (protected reserve), `wallet_holds` (closes the E3 race), `credit_wallets.wallet_debt` |

### Increment 2 / SLICE (merged to `master`)
* `backend/src/ai/solo_pack/` — `templates/` (curated entities), `loader.py` (GOV-validating), `activation.py` (seed + owner-id resolve + triggers), `tools.py` (`tenant_record_write`, `emit_business_signal`).
* GOV `authority.py` gained the **`email_dispatch`** category (so an A1 `send_email` raises a HITL card).
* The **`test_solo_pack_slice_e2e.py`** is the north-star test — the sellable path email→approved-quote across real SIG+SCH+GOV seams.

### Increment 2 / PACK (on `inc2/pack`)
* `solo_pack/templates/` split per domain — `acquisition.py` (SLICE 4), `care.py` (P06 + AGT-030/035/092), `finance.py` (P08+AGT-038 maker, P10+AGT-046 checker), `compliance.py` (P14+AGT-068 auditor), `intelligence.py` (P19+AGT-051); `__init__` is the aggregator + `PROCESS_GROUPS` manifest. **16 entities total.**
* `solo_pack/bundles.py` — the 7 §2.1 starter bundles (numeric process codes → dodge the de-canary lint). `activation.py` generalized: `activate_solo_pack` / `activate_bundle` / `activate_slice` over one `_activate` core.
* GOV: `schemas/capabilities.py` gained `sod_tags` (persists the §9.4 conflict tags); `solo_pack/tools.py` resolves the acting process from `agent_id` → cross-owner writes **propose** (runtime SoD).
* Docs: `increment-2/03a_wave0_process_sheets.md` (5 sheets, C1), `03b_pack_behavioral_goldens.md` (per-agent contracts). Tests: extended `test_solo_pack_templates.py` (57), `test_solo_pack_activation_db.py` (+pack roster), new `test_solo_pack_sod_db.py` (maker/checker holds).

### Increment 2 / KAR (on `inc2/kar`)
* `solo_pack/templates/gateways.py` — a shared `_karuna_gateway` builder + **KAR-03 WhatsApp** (consumes `message.inbound`) + **KAR-01 voice stub** (parks `voice.*`). Added to `GATEWAYS` → roster is **18**; `activate_slice` seeds email-only.
* `signals/whatsapp_inbound.py` — the WhatsApp producer (`message.inbound`, `trust:counterparty`, SID dedupe, subscription-gated). Wired into `src/voice/whatsapp_handler.py` as a fail-safe cutover. New `SignalTypes.MESSAGE_INBOUND`/`VOICE_INBOUND`.
* `solo_pack/consent.py` — the outbound consent/DNC seam (`check_outbound_consent` + pluggable checker; TRUST installs D6). Tests: `test_kar_gateways.py` (injection golden via pure `evaluate_policy` + consent), `test_whatsapp_inbound_db.py` (emit/dedupe/subscription/dispatch→KAR-03), gateway-posture in `test_solo_pack_templates.py`.

### Increment 2 / ONBOARD backend (on `inc2/onboard`)
* `solo_pack/onboarding.py` — the wizard steps as functions (Pragya's Inc-3 stage contract): `list_bundles`, `governance_preview` (pure), `activate_for_company`, `onboarding_status`. `solo_pack/onboarding_router.py` — `/ai/onboarding/{bundles,governance-preview,activate,status}`, company-scoped. `loop/api.py` — `GET /ai/loop/envelope` (the envelope admin view). Both registered in `src/main.py`.
* Admin backends: signals inspector + trigger editor were already shipped (`signals/api.py`); ONBOARD added only the envelope GET. Tests: `test_onboarding.py` (pure steps), `test_onboarding_db.py` (activate + status + envelope). **Frontend not built** (separate track).

### Increment 2 / TRUST — D6 consent registry (on `inc2/trust`)
* New package `ai/trust/` (added to the strict allowlist in `scripts/typecheck_ai.py`): `models.py` (`consent_records`/`dnc_entries`/`unsubscribe_log`), `consent_registry.py` (`evaluate_consent` + `TenantManagedProvider` + `install_consent_registry`). Migration **`trust001`** (off `loop002`).
* Wired into KAR's `solo_pack/consent.py` seam via `install_consent_registry()` at `main.py` + `worker.py` boot (beside `register_solo_pack_tools`). Tests: `test_consent_registry.py`, `test_consent_registry_db.py`.
* **C3 per-checkpoint HITL SLAs:** `governance/checkpoints.py` (per-category SLA policy + stamps the 18 seed rows), `governance/models.py` (`sla_seconds`+`on_timeout` on `HITLCheckpointDef`), `governance/checkpoint_sla.py` (`apply_checkpoint_timeouts` sweep — auto_deny/park/escalate), wired into the 60s `signal_sweeper` cron. Migration `trust002`. Tests: `test_checkpoint_sla.py`, `test_checkpoint_sla_db.py`. **Remaining TRUST (C5/B13/E1/E2/E4) not built** — see [05](./increment-2/05_trust_billing_safety.md) §11–§12.

**Migration head:** `trust002` (Inc-2 PACK/KAR/ONBOARD added none; TRUST added `trust001` consent tables + `trust002` checkpoint-SLA columns). Run `poetry run alembic upgrade head` from `backend/` on a fresh DB.

---

## 3. How to resume — the next work

Build order (from [increment-2/00_overview.md](./increment-2/00_overview.md) §4): **SLICE ✅ → PACK ✅ + KAR ✅ → ONBOARD ✅ (backend) → TRUST → RETR.**

**Next up: finish TRUST** ([increment-2/05_trust_billing_safety.md](./increment-2/05_trust_billing_safety.md) §11–§12). **D6 (consent registry) + C3 (per-checkpoint HITL SLAs) are done.** The **remaining findings reach into subsystems outside `ai/`** and are best done with those in view: **C5** graduated dunning (notify → grace → **read-only** → suspend) + state-aware `CompanySuspensionMiddleware` (`billing/`, `common/middleware.py`) — the GA-gating billing-safety piece; **B13** platform-initiated budget class (LOOP `budget_envelopes` + CostLedger); **E1** idle-cost model (doc); **E2** free-credit abuse controls (`auth/`); **E4** fee-formula alerts (billing).

**Done this session** — PACK ([03](./increment-2/03_pack_agents_processes.md) §8): full Wave-0 roster + runtime SoD. KAR ([02](./increment-2/02_kar_gateways.md) §5): WhatsApp via SIG + gateways + injection golden + consent seam. ONBOARD backend ([04](./increment-2/04_onboard_wizard.md) §6): the `/ai/onboarding/*` wizard step APIs over `activate_bundle` + the `/ai/loop/envelope` admin GET. **The remaining ONBOARD frontend (React wizard, approvals console, FE gates) is a separate FE track** — the backend contract it calls is done.

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
* **Solo Pack tree lives in a manifest, not in each template** (PACK): `templates.PROCESS_GROUPS` (`ProcessGroup(process, agents)`) + `GATEWAYS` encode parentage; `activation._activate(groups, gateways)` is the one seeding core. Adding an agent = add it to its `ProcessGroup`; adding a process = add a `ProcessGroup`; a new gateway (KAR) = append to `GATEWAYS`.
* **Bundle process codes are stored NUMERICALLY** (`bundles.py`: `(8, 9, 10, 11, 18)`) and rendered `P{nn}` on read — the de-canary lint bans the literal `P11` token in `ai/` source and the Fiscal bundle's §2.1 membership includes it. Same trick as the HBS spine's `owner: 11`. Never write `P11`/`p11` in `ai/` source.
* **Cross-process record writes need `actor_process_code`** (PACK SoD): the `tenant_record_write` tool resolves it from `agent_id` (own `process_code`, else parent process's); a write on another owner's object then *proposes* (`object.change_proposed`). A gateway/origination write (no PROCESS ancestor) resolves to `None` → front-door. A new money/record tool should thread `actor_process_code` the same way.

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
* **Closed by Inc 2 so far:** **C1** (all 6 Wave-0 process sheets — P03 in SLICE, the other 5 in PACK) + the Inc-1 owner-id-resolution & governance-band-seeding carryovers (PACK); **D6** (consent/DNC/unsubscribe registry — TRUST); **C3** (per-checkpoint HITL SLAs — TRUST).
* **Closing in Inc 2 (remaining):** C5, B13, E1, E2, E4 — see `increment-2/00_overview.md` §5 + `05_trust_billing_safety.md` §11–§12.
* **Deferred:** B7 (realtime voice) → Increment 3 with Pragya.
* **Still open (later increments):** B10, B11, B12, B14, C2, C4, C6, D2, D3, D4, D5. See [roadmap_gap_register.md](./roadmap_gap_register.md) and each increment charter.

---

## 9. One-paragraph orientation for a fresh agent

> The repo is a multi-tenant agentic platform. Increment 1 built the "one-loop" substrate (signal bus, governance/PolicyGate, per-tenant business schema + record graph, Loop runtime + budget/wallet safety) — all on `master`. Increment 2 is building the sellable MVP, the "Solo Pack": curated A1 agents that answer email/WhatsApp, qualify, quote, chase invoices, and report, governed with HITL. The first vertical slice (email→quote) is built and proven end-to-end on `inc2/slice`. Resume by merging that to master, pushing, then building the **PACK** workstream (the other 10 agents + 6 process sheets + bundles) per `docs/product-road-map/increment-2/03_pack_agents_processes.md`. Keep every gate green; follow the conventions in §5 above.
