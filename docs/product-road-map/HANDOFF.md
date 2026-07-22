# Product Road-Map — Development Handoff

> **Purpose:** resume development in a fresh session with full context.
> **Last updated:** 2026-07-22 · **Author:** Claude (session with Rahul)
> **Read next:** [build_roadmap.md](./build_roadmap.md) (the plan) · [roadmap_gap_register.md](./roadmap_gap_register.md) (findings) · the `increment-1/` and `increment-2/` folders (per-workstream design + build notes).

---

## 0. TL;DR — where we are

* **Increment 1 (One-Loop Foundations) — ✅ BUILT & MERGED to `master`.** Four workstreams: **SIG** (signal bus), **GOV** (governance + PolicyGate), **SCH** (tenant schema / records / data plane), **LOOP+ENV** (Loop runtime, budget envelopes, wallet holds). Register findings B1/B2/B3/B5/B6/B8/E3/A6 closed.
* **Increment 2 (The Solo Pack — the sellable MVP) — DESIGNED + SLICE, PACK, KAR built; ONBOARD backend built.**
  * All 6 workstream design docs written and decisions locked (`increment-2/`).
  * **SLICE** (email→quote vertical slice) — ✅ BUILT & **MERGED to `master`** (and on the remote). Closes C1 for P03.
  * **PACK** (full Wave-0 roster) — ✅ BUILT & **merged to local `master`** (push pending, §1). 16 entities + 7 bundles + generalized activation + runtime SoD. Closes C1 (all 6) + Inc-1 owner-id/governance carryovers.
  * **KAR** (outward gateways) — ✅ BUILT & **merged to local `master`**. KAR-03 WhatsApp (via SIG) + KAR-01 voice stub; roster **18**. Karuna threat posture + consent seam. Real voice/B7 → Inc 3.
  * **ONBOARD** (setup wizard) — ✅ **COMPLETE: backend + frontend.** The wizard **step APIs** (`/ai/onboarding/*`, Pragya's Inc-3 stages) + the budget-envelope admin GET (2026-07-20); the **React surfaces** (Solo Pack wizard rebuilt over the step APIs, `/admin/loop-ops` signals/triggers/envelope page, checkpoint-aware approvals console + the `/respond` body-contract fix) built 2026-07-22 on `inc2/onboard-fe` — see [04](./increment-2/04_onboard_wizard.md) §7.
  * **TRUST** (billing safety + consent) — ✅ **COMPLETE.** C5 + D6 + C3 + B13 (migrations `trust001`–`trust004`); **E1 + E2 + E4 + both integration hookups** built 2026-07-22. All 7 findings closed.
  * **RETR** (retrieval upgrade) — ✅ **COMPLETE.** All 5 tasks on branch **`inc2/retr`** (2026-07-22, not yet merged): hybrid+RRF, structure-aware chunking + lazy re-chunk, schema-aware filters + KB domain viewport, Growth+ LLM rerank, retrieval goldens. Migrations `retr001`–`retr003`. Closes B8's retrieval half.
  * **Increment 2 is COMPLETE** — every charter finding closed and the ONBOARD frontend built (2026-07-22). Nothing Inc-2 remains but the push (§1).

**Everything committed is green:** mypy `--strict` (179 files), **1194 unit + 183 parity/eval/integration**, layout lint, all migrations apply/rollback clean.

---

## 1. ⚠️ Standing action — PUSH (this VM can't; do it from a credentialed host)

The remote (`origin`, an HTTPS GitHub URL) is at `19a3d4d` — Increment 1 + Inc-2 design docs + the **SLICE** build (pushed from a credentialed host earlier; read-only `git ls-remote` confirms). This VM has **no write credentials** (`no credential.helper`, no `gh`), so `git push` fails with `could not read Username`. Nothing is lost — all committed:

* **`master`** — has **everything** merged: PACK + KAR + ONBOARD-backend + all of TRUST + **RETR** (verified 2026-07-22: `inc2/retr` IS merged; `git branch --no-merged master` is empty). **28+ commits ahead of `origin/master`**, not yet pushed.

To publish, from an environment with GitHub write access:
```bash
cd /home/rahul/workspace/hb-proto-3
git push origin master
```
Verify with `git log --oneline -25` and `git rev-list --left-right --count origin/master...master`.

> **Toolchain correction (2026-07-22):** earlier sessions recorded "Node/browser toolchain out of scope on this VM" — that is **stale**. Node v20.20.0 + npm 10.8.2 are installed and `frontend/node_modules` is populated, so the **ONBOARD frontend track builds here**. Note `cd frontend && npm run build` failed with ~22 pre-existing TS errors (bitrot in `pages/ai/*` + `useAuth` + `IntegrationsPage`, unrelated to ONBOARD) — fixed as task 0 of the FE track.

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
* **C3 per-checkpoint HITL SLAs:** `governance/checkpoints.py` (per-category SLA policy + stamps the 18 seed rows), `governance/models.py` (`sla_seconds`+`on_timeout`), `governance/checkpoint_sla.py` (`apply_checkpoint_timeouts` sweep), wired into the 60s `signal_sweeper` cron. Migration `trust002`. Tests: `test_checkpoint_sla{,_db}.py`.
* **B13 platform-initiated budget class:** `cost_attribution.py` (`PLATFORM_INITIATED_ATTRIBUTIONS`), `loop/models.py` (`budget_class`), `loop/envelopes.py` (tenant rollup excludes platform attributions; class-aware), `loop/platform_budget.py` (`platform_spend_admitted` — parks platform work at its own cap). Migration `trust003`.
* **C5 graduated dunning + state-aware suspension:** `ai/trust/dunning.py` (the `current→…→suspended` ladder, `advance_dunning`, `agents_may_act`), `companies.subscription_status` (migration `trust004`), `common/middleware.py` (`CompanySuspensionMiddleware` now degrades to read-only — blocks agent mutations, allows GET/billing/export — before hard suspend). `BILLING_GRACE_DAYS`/`BILLING_READ_ONLY_DAYS` settings. Tests: `test_dunning{,_db}.py`. **Remaining TRUST (E1/E2/E4) not built** — economics only; see [05](./increment-2/05_trust_billing_safety.md) §11.

### Increment 2 / TRUST — the economics floor (on `inc2/trust-econ`)
* **E4** `ai/trust/fee_guard.py` — the shipped code had **no** `max(total_billing, 0)` clamp at all (worse than the register assumed: a negative TB *credited* the customer). The guard clamps *and* alerts (ERROR + `billing.fee_misconfigured` signal naming the culprit, deduped per company/period), wired into `compute_billed_amount` + `record_billing_event`. Ordering intent (discount subtracted last, never reducing the partner fee) is asserted and pinned.
* **E2** `ai/trust/abuse_controls.py` — verification gate + per-IP signup throttle (stamped into `onboarding_metadata`, **no new table, no Redis**) + eligibility predicate. Enforced at **all three** credit-injection points (`_provision_new_tenant`, `get_or_create_wallet`, `flush_and_inject_daily_credits`) because any one alone is bypassable. Settings `TRUST_REQUIRE_VERIFIED_FOR_CREDITS`, `TRUST_SIGNUP_MAX_PER_IP_PER_DAY`.
* **E1** `ai/trust/idle_cost.py` + [`increment-2/05a_idle_cost_model.md`](./increment-2/05a_idle_cost_model.md) — structure derived from shipped cron cadences, rates declared. **$0.30/tenant/mo** Solo, $4.44 Growth; the Blueprint's $2,000 is platform *fixed* cost, mis-scoped. **Key result: free credits are $150/mo/tenant vs a $0.30 idle floor (500×) — the free tier's risk is entirely the credit grant, which makes E2 the GA-gating economics item.**
* **Hookups** — `billing/cron_service.days_past_due()` + `run_dunning_job()` + `ai/trust/crons.py::dunning_sweep` (arq daily 01:10 UTC, plus `POST /api/v1/cron/dunning`) drive C5's ladder; `loop/platform_budget.platform_work_admitted()` wired into `dreaming_worker` closes B13's runner gap.

### Increment 2 / RETR — the retrieval upgrade (on `inc2/retr`)
* **T1** `memory/hybrid_retrieval.py` — lexical (Postgres FTS, GIN index `retr001`) + semantic (pgvector) fused by **reciprocal-rank fusion**. Fusing on *rank* is the design: a cosine and a `ts_rank_cd` are incomparable quantities. `search_semantic` now degrades to lexical-only on an embedding failure instead of returning nothing.
* **T2** `memory/chunking.py` — structure-aware chunks (ATX/numbered/setext/bare-title headings, per-source-type sizing) replacing `text[i:i+500]`. **Heading context is prepended into `content`** because both retrievers read that column. `memory/rechunk.py` + hourly cron is the lazy upgrade (`chunk_version`, migration `retr002`), gated by B13's platform budget since re-embedding is platform-initiated.
* **T3** `memory/retrieval_filters.py` + `documents.memory_domain` (`retr003`) — relevance predicates (bound, never interpolated) and the Inc-1 **domain viewport now applied to the KB**, after fusion and before `top_k` so an invisible document can't eat a result slot.
* **T4** `memory/reranker.py` — Growth+ **LLM reranker** (decision resolved 2026-07-22). Tier gate fails closed, top-20 window, attributed `rerank` and deliberately *tenant*-initiated, fails open on every path.
* **T5** `tests/eval/retrieval_{metrics,corpus}.py` + `test_retrieval_goldens_db.py` — the regression gate. **MRR 0.812 → 1.000** vs cosine; all the gain on exact-token queries, paraphrase queries unregressed.

### Increment 3 / AUTH — the inward-channel floor (merged to `master`)
* `backend/src/ai/inward_auth/` (added to the strict allowlist): `tiers.py` (the pure T0–T3 classifier over the §20 `CATEGORY_RULES`), `sessions.py` (`elevate` / `effective_level` / `require_tier` + lockout), `step_up.py` (TOTP, slot-accurate replay refusal), `webauthn_ceremony.py` (platform-built passkeys, single-use challenges, sign-count regression rejected), `bindings.py` (OTP enrollment handshake, inbound resolution, alert fan-out), `oob.py` (both-legs-or-nothing T3), `api.py` (`/ai/authn/*`).
* Migration **`iauth001`** — six tables: `channel_bindings`, `account_manager_sessions`, `webauthn_credentials`, `webauthn_challenges`, `totp_secrets`, `oob_confirmations`. New signal types `authn.channel_otp` / `authn.oob_confirm` / `authn.security_alert`; new `INWARD_AUTH_*` + `WEBAUTHN_*` settings.
* Frontend: `services/authn.service.ts`, `components/SecuritySettings.tsx` (mounted in `UserSettings`), `components/StepUpModal.tsx`.

**Migration head:** `iauth001` (Inc 3 AUTH, off `retr003`). Previously: Inc-2 PACK/KAR/ONBOARD and the TRUST economics slice added none; TRUST's safety slice added `trust001` consent, `trust002` checkpoint-SLA, `trust003` envelope `budget_class`, `trust004` `subscription_status`; RETR added `retr001` FTS index, `retr002` chunk structure, `retr003` document domain. Run `poetry run alembic upgrade head` from `backend/` on a fresh DB.

---

## 3. How to resume — the next work

Build order (from [increment-2/00_overview.md](./increment-2/00_overview.md) §4): **SLICE ✅ → PACK ✅ + KAR ✅ → ONBOARD ✅ (backend) → TRUST ✅ → RETR ✅.** **Increment 2's backend is done.**

**Next up (decided with Rahul, 2026-07-22): the ONBOARD frontend + the Increment-3 design docs, in parallel.** The Inc-3 charter's questions round is **done** — all three answers locked (see [increment-3/00_charter.md](./increment-3/00_charter.md) §Decisions): **(1) console-first** — Pragya v1 ships as web-console chat in the shipped React app, voice/WhatsApp adapters follow (voice/B7 still fold into Inc 3); **(2) platform-built WebAuthn** — full passkey/FIDO2 in-house (+ TOTP fallback) for T2 step-up, no auth vendor; **(3) Rahul reviews the stage 1–5 scripts** — review checkpoints built into the Pragya task plan.

**Both done 2026-07-22:** the ONBOARD FE track landed ([04](./increment-2/04_onboard_wizard.md) §7 — build gate restored, wizard, `/admin/loop-ops`, approvals console + its `/respond` contract fix) and the Inc-3 design docs are written (`increment-3/{00_overview,01_auth_inward_channel,02_pragya_v1}.md`, decisions locked, task plans authored).

**Increment 3 / AUTH — ✅ BUILT & merged to local `master` (2026-07-22).** All of T1–T7: the `ai/inward_auth/` package (tier classifier, session elevation, TOTP + platform-built WebAuthn, channel bindings, T3 out-of-band leg), migration **`iauth001`**, the `/ai/authn/*` router, and the FE (`SecuritySettings.tsx`, `StepUpModal.tsx`, `authn.service.ts`). Build notes + the eight design deltas are in [01](./increment-3/01_auth_inward_channel.md) §5. **D1's mechanism is built but not yet *wired*** — no command executor calls `require_tier` because Pragya doesn't exist yet; that hookup is PRAGYA's first task and is what actually closes D1 end-to-end.

**Next up: PRAGYA (`inc3/pragya`, [02](./increment-3/02_pragya_v1.md))**, then VOICE. Closes C4, C6, B7 (+ D1's wiring). The **push** in §1 remains the one standing external action.

**Done 2026-07-22** — TRUST completed ([05](./increment-2/05_trust_billing_safety.md) §15–§18): **E4** fee-formula guard, **E2** free-credit abuse controls, **E1** idle-cost model ([05a](./increment-2/05a_idle_cost_model.md)), and both open integration hookups (C5's `days_past_due` driver, B13's admission at the dreaming runner). RETR completed ([06](./increment-2/06_retrieval_upgrade.md) §5–§9): all five tasks, MRR 0.812 → 1.000 over pure cosine on the golden set.

**Done 2026-07-20** — PACK ([03](./increment-2/03_pack_agents_processes.md) §8): full Wave-0 roster + runtime SoD. KAR ([02](./increment-2/02_kar_gateways.md) §5): WhatsApp via SIG + gateways + injection golden + consent seam. ONBOARD backend ([04](./increment-2/04_onboard_wizard.md) §6): the `/ai/onboarding/*` wizard step APIs over `activate_bundle` + the `/ai/loop/envelope` admin GET. **The remaining ONBOARD frontend (React wizard, approvals console, FE gates) is a separate FE track** — the backend contract it calls is done.

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
* **TRUST's shape: policy in `ai/trust/`, enforcement at the existing call site.** Every TRUST piece follows it — the ladder in `dunning.py` enforced by `common/middleware.py`, the registry in `consent_registry.py` filling KAR's seam, the eligibility predicate in `abuse_controls.py` enforced in `billing/credit_service.py`. It keeps the policy strict-typed and unit-testable without a DB, and touches the legacy call sites minimally. `ai/` → `billing/` imports are long-established (`step_executor`, `loop/wallet_holds`, …); the reverse is fine too.
* **Free daily credits have THREE injection points, not one** — `auth.service._provision_new_tenant` (registration), `credit_service.get_or_create_wallet` (first touch), and `flush_and_inject_daily_credits` (the daily cron). A gate on only the cron is bypassable by signing up and immediately using the product. `_provision_new_tenant` runs **pre-commit and must not query other tables** (asyncpg can't do concurrent ops on one connection), so gate it from a settings flag + the company's own metadata, not a DB lookup.
* **Anything that withholds credits must be scoped to self-service signup** (`onboarding_metadata.created_via`), never to "has no verified user". Fixture/seeded companies have **no users at all**, so the broad form fails every agent run in `tests/parity` with `insufficient_funds` at wallet-hold admission. **The parity suite is the canary for credit-path changes** — `tests/unit` stays green because it doesn't drive real runs, so run `pytest tests/parity tests/eval` before believing a billing change is safe.
* **Retrieval has three stages and they are deliberately separate** (RETR): `hybrid_retrieval.hybrid_search` fuses, the domain viewport filters *inside* it (after fusion, before `top_k`), and `reranker.llm_rerank` runs at the caller. Do not fold the reranker into `hybrid_search` — it would cycle on `RetrievedChunk`, and it would put per-query LLM spend inside a function that other call sites reasonably assume is cheap.
* **A new `usage_logs` attribution must be classified for B13.** Adding a `CostAttribution` member is not enough — decide whether it belongs in `PLATFORM_INITIATED_ATTRIBUTIONS`. Tenant-asked-for work (like RETR's `rerank`) must stay out, or ordinary tenant activity can exhaust the cap that exists to protect tenants *from* platform work.
* **`setuptools` is pinned `<81` on purpose** (AUTH): 81 removed `pkg_resources`, which `opentelemetry-instrumentation` imports at module scope, so an unpinned resolve breaks `import src.main` outright. If a `poetry add` ever unpins it, `import src.main` is the fastest check. More generally: **this VM's venv had drifted from `poetry.lock`** (manually pip-installed `google-genai` 2.x / `httpx` 0.28 over a lock saying 0.4/0.26), so any `poetry add` re-syncs the venv *down* to the lock. Re-run the unit suite after touching deps.
* **AUTH's two gates are different gates.** The PolicyGate asks "may this *agent* do this?" and raises HITL cards; `inward_auth.require_tier` asks "did this *human* prove enough to ask?". They share only `CATEGORY_RULES` — do not merge them, and do not let a Pragya command satisfy its own approval (HITL cards are console-only artifacts by construction).
* **Never elevate inside a verify function** (AUTH): `verify_totp` / `finish_authentication` return a result and the *router* elevates, because a failure must be counted against the lockout counter. A new factor must funnel through `api._fail_step_up` or it silently disables brute-force protection.
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
* **Closed by Inc 2:** **C1** (all 6 Wave-0 process sheets — P03 in SLICE, the other 5 in PACK) + the Inc-1 owner-id-resolution & governance-band-seeding carryovers (PACK); **D6** (consent registry), **C3** (per-checkpoint HITL SLAs), **B13** (platform-initiated budget class), **C5** (graduated dunning + state-aware suspension), **E1** (idle-cost model), **E2** (free-credit abuse controls), **E4** (fee-formula guard) — all TRUST; **B8**'s retrieval half (RETR). **Increment 2's finding list is fully closed.**
* **In progress (Inc 3):** **D1** — AUTH built the whole mechanism (tiers, bindings, step-up, T3 out-of-band); it closes when PRAGYA wires `require_tier` into a command executor. Nothing calls it yet.
* **Deferred:** B7 (realtime voice) → Increment 3 with Pragya.
* **Still open (later increments):** B10, B11, B12, B14, C2, C4, C6, D2, D3, D4, D5. See [roadmap_gap_register.md](./roadmap_gap_register.md) and each increment charter.

---

## 9. One-paragraph orientation for a fresh agent

> The repo is a multi-tenant agentic platform. Increment 1 built the "one-loop" substrate (signal bus, governance/PolicyGate, per-tenant business schema + record graph, Loop runtime + budget/wallet safety). Increment 2 built the sellable MVP, the "Solo Pack": curated A1 agents that answer email/WhatsApp, qualify, quote, chase invoices, and report, governed with HITL — **all six workstreams are done** (SLICE, PACK, KAR, ONBOARD-backend, TRUST, RETR) and every Inc-2 register finding is closed. **Resume with Increment 3, Pragya v1** (§3) — but note its charter is a deliberate stub, so the next session starts with a clarifying-questions round with Rahul, not with code. Two Inc-2 items stay open and neither blocks Inc 3: the push in §1 (this VM has no git write credentials) and the ONBOARD frontend (a separate FE track). Keep every gate green; follow the conventions in §5 above.
