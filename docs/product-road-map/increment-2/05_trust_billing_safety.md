# Increment 2 / TRUST — Billing Safety, Consent & the Economics Floor

> **Status:** ✅ **Built** — **C5** (graduated dunning + state-aware suspension), **D6** (consent registry), **C3** (per-checkpoint HITL SLAs), **B13** (platform-initiated budget class) built 2026-07-20; **E1** (idle-cost model), **E2** (free-credit abuse controls), **E4** (fee-formula guard) + both integration hookups built 2026-07-22. Migrations `trust001`–`trust004`; gates green. · **Branches:** `inc2/trust`, `inc2/trust-econ` · **Closes:** **C5 ✅**, **D6 ✅**, **C3 ✅**, **B13 ✅**, **E1 ✅**, **E2 ✅**, **E4 ✅**.
> **Design authority:** Blueprint §9.6 (compliance), §10 (economics); Technical §15.2 (suspension), §20 (governance/budget). Global-neutral (decision 5), graduated dunning (decision 6).
> **Depends on:** GOV (checkpoints/PolicyGate), LOOP+ENV (envelopes/holds/wallet_debt). Its billing-safety pieces gate GA.

---

## 1. C5 — Graduated dunning + degraded read-only mode

Today, suspension instantly kills all API access + live calls (technical §15.2). When the product *is* the tenant's operations, that's unacceptable. The graduated ladder:

`current` → **`past_due`** (dunning notifications, full function) → **`grace`** (configurable window, e.g. 7d; full function, escalating notices) → **`read_only`** (agents stop *acting* — no external effects; the tenant can read, export, and pay; protected P14/P17 keep their reserved envelope) → **`suspended`** (hard, only after read-only elapses).

* A `subscription_status` state machine on the company; the shipped `CompanySuspensionMiddleware` becomes state-aware (read-only allows GETs + billing + export; blocks agent action + external effects).
* Transitions emit signals (`billing.past_due`, `billing.grace`, …) and dunning notifications.
* The wallet-hold admission (Inc-1) already blocks new spend when funds run out; read-only mode makes the *degradation* graceful instead of a cliff.

## 2. D6 — Consent / DNC / unsubscribe (global-neutral, pluggable)

Chose global-neutral (decision 5): no single jurisdiction hard-coded. A **pluggable consent registry**:

* Tables: `consent_records` (counterparty channel-identity → status per purpose: marketing/transactional/recording), `dnc_entries` (do-not-contact), `unsubscribe_log`.
* **Registry adapters** — a `ConsentProvider` interface; the built-in adapter is tenant-managed lists; jurisdiction packs (India DND/TRAI, US TCPA, EU GDPR/CAN-SPAM) are pluggable adapters added per market later. The MVP ships the interface + the tenant-managed adapter.
* **Default posture (decision 2026-07-20): tenant-configured from day one.** The platform does not impose a global opt-in default; each tenant configures their own consent posture per purpose (marketing / transactional / recording) at onboarding, and is responsible for its lawful basis in their market. The registry *enforces* whatever the tenant sets — every KAR outbound checks it (KAR §T5) — and the onboarding wizard surfaces the posture as an explicit, logged tenant choice (so "tenant-configured" is an auditable decision, not an absence of policy). Jurisdiction packs later can *tighten* a tenant's posture but never loosen it below what they configured.
* Closes D6's "compliance promises without infrastructure" — the registry is real and the gateways honor it.

## 3. C3 — Per-checkpoint HITL SLAs

The 18 checkpoints (Inc-1) get per-checkpoint SLAs + fallbacks instead of one 24h rule: each `hitl_checkpoint_defs` row gains `sla_seconds` + `on_timeout` (`auto_park` | `auto_deny` | `escalate`). The Judgment-Desk queue (approvals console) surfaces load; a payment approval's SLA differs from a marketing email's. Auto-park re-raises on the next heartbeat; auto-deny fails safe.

## 4. B13 — Platform-initiated spend budget class

Optimizer runs, self-healing, Meta-Agent iterations, perpetual sensing burn the wallet without the tenant asking (the #1 churn driver). A **`platform_initiated` budget class**: a separate envelope (LOOP §20.4) with its own cap + tenant-visible attribution (the CostLedger already attributes; add the class) + a consent setting. `EntityBuildRun` and the sensing crons draw from it; exceeding the cap parks platform work, never tenant work.

## 5. E1 — Idle-cost model (measured, not asserted)

Takes the **measured Inc-1 tenant-DB idle cost** (per-tier, from the SCH hibernation build) as its key input, plus the always-on floor (heartbeat ≈ $0, gateways' idle poll, Chronos). Produces a per-tier idle-cost figure that validates (or corrects) the default envelope and the free-tier economics — replacing the Blueprint's asserted $2,000/month with a derived number.

## 6. E2 — Free-credit abuse controls

`$5/day free credits × every tenant` is platform COGS with no abuse controls. Add: sign-up verification gates (email/phone verification before daily credits activate), per-IP/per-device throttles on tenant creation, and a daily-credit eligibility check. Documents the COGS assumption alongside E1.

## 7. E4 — Fee formula edge cases

`max(total_billing, 0)` silently masks fee misconfiguration: log/alert on a clamped negative (a real config bug indicator); document the discount-vs-partner-fee ordering as intentional in the TB billing code.

## 8. Code Mapping

| Piece | Where |
|---|---|
| Dunning state machine | `billing/` — `subscription_status` + transitions + notifications |
| State-aware suspension | `common/middleware.py` (`CompanySuspensionMiddleware`) |
| Consent registry + adapters | `ai/solo_pack/consent.py` + `consent_records`/`dnc_entries`/`unsubscribe_log` tables |
| Checkpoint SLAs | `hitl_checkpoint_defs` columns + the approvals timeout worker |
| Platform-spend class | LOOP `budget_envelopes` (new class) + CostLedger attribution |
| Idle-cost model | `ai/trust/idle_cost.py` + [05a_idle_cost_model.md](./05a_idle_cost_model.md) |
| Abuse controls | `ai/trust/abuse_controls.py`, enforced in `auth/` sign-up + daily-credit injection |
| Fee-formula guard | `ai/trust/fee_guard.py`, wired into `billing/billing_service.py` |
| Dunning driver | `billing/cron_service.py` (`days_past_due`, `run_dunning_job`) + `ai/trust/crons.py` |

## 9. Task Plan (outline)

| # | Task | Acceptance |
|---|---|---|
| T1 | Dunning state machine + state-aware middleware (C5) | a lapsed tenant degrades to read-only, not instant shutdown; export still works |
| T2 | Consent registry + adapters + KAR outbound hook (D6) | outbound blocked for a DNC counterparty; opt-in default enforced |
| T3 | Per-checkpoint SLAs + timeout fallbacks (C3) | a checkpoint auto-parks/denies on timeout per its config |
| T4 | Platform-initiated budget class + attribution + cap (B13) | platform work parks at cap; tenant sees attributed platform spend |
| T5 | Idle-cost model (E1) + abuse controls (E2) + fee alerts (E4) | derived per-tier idle cost documented; abuse throttles live; clamped-negative alerts |

## 10. Brainstorm Decisions (Rahul, 2026-07-20)

1. **Grace window 7 days (configurable); inbound is parked, never dropped** during read-only — signals are captured and held so nothing is lost when the tenant pays. (Reuses the SIG PARKED lifecycle.)
2. **Consent is tenant-configured from day one** (§2) — no imposed global opt-in default; the tenant sets and owns their per-purpose posture, the registry enforces it, and the choice is logged at onboarding.
3. **Consent-to-record is a stub** until the voice follow-on (voice is deferred).

## 11. Build Notes — D6 consent registry (2026-07-20)

**D6 built** — the piece that makes KAR's consent seam real. What landed:

1. **A dedicated `ai/trust/` package** (added to the strict-typing allowlist) rather than overloading `solo_pack/consent.py` (which stays the KAR *seam*). `trust/models.py` holds the three control-plane tables (`consent_records`, `dnc_entries`, `unsubscribe_log`); `trust/consent_registry.py` holds the evaluation + the tenant-managed provider + the installer. Migration `trust001` (off `loop002`) creates the tables; it applies and rolls back clean.

2. **Evaluation enforces explicit signals, allows otherwise** (decision 8 — no imposed global opt-in). `evaluate_consent` denies on a DNC entry, a purpose-scoped unsubscribe, or an explicit `denied` consent record; absent all three it allows. That is exactly the tenant-managed posture; a jurisdiction pack later implements `ConsentProvider` to *tighten* it. **Identities canonicalise** (digits-only phone, lower-cased email) so any formatting of the same address matches — a real bug caught in testing: `+1 (555) 111-2222` must block `whatsapp:+15551112222`.

3. **Installed at both entry points via the seam**, no gateway call site changed: `install_consent_registry()` runs beside `register_solo_pack_tools()` in `main.py` + `worker.py`, calling KAR's `set_consent_checker`. The end-to-end test proves a DNC number is blocked through `check_outbound_consent`.

## 12. Build Notes — C3 per-checkpoint HITL SLAs (2026-07-20)

**C3 built** — the 18 checkpoints move from one global 24h rule to per-checkpoint SLAs + fallbacks:

1. **The SLA policy is data, by category.** `HITLCheckpointDef` gained `sla_seconds` + `on_timeout`; `checkpoints.py` maps each §9.3 category to a policy and stamps every seed row (migration `trust002` backfills). Money/binding (payout 4h, refund 4h, contract/vendor/price 8h, data-deletion 24h) → **`auto_deny`** (silence on money must fail safe, not proceed); outbound comms (email/public-statement/discount, 24h) → **`auto_park`** (a draft can wait, re-raise); high-stakes governance/HR (48h) → **`escalate`**.

2. **A sweep, not a per-run timer.** `governance/checkpoint_sla.py::apply_checkpoint_timeouts` joins PENDING `human_approvals` → their checkpoint def, and on an overdue row applies `on_timeout`: auto-deny sets status `TIMEOUT` + records the reason (terminal, deduped once); auto-park/escalate leave it PENDING and raise `approval.parked`/`approval.escalated` (deduped per calendar day so they resurface without spamming). Wired into the existing 60s `signal_sweeper` cron — one global pass, no new cron.

## 13. Build Notes — B13 platform-initiated budget class (2026-07-20)

**B13 built** — platform work can no longer silently drain a tenant's wallet:

1. **A class, not a new cost value.** The CostLedger already tags every `usage_logs` row with an `attribution`; B13 defines `PLATFORM_INITIATED_ATTRIBUTIONS` (meta_review, meta_spec_critic, dreaming, sandbox, test_driver) — the work the platform starts without the tenant asking. `budget_class` on `budget_envelopes` (migration `trust003`) splits a tenant's Loop envelope from a **separate platform envelope** (own cap `LOOP_PLATFORM_ENVELOPE_USD`, no reserve). The Loop rollup now *excludes* the platform attributions, and the platform envelope *includes only* them — no double-count.

2. **Admission parks platform work, never tenant work.** `loop/platform_budget.py::platform_spend_admitted` checks the platform envelope's spend against its cap; over → the caller parks the platform run. Tenant work draws from the Loop envelope + wallet holds (Inc-1), untouched. `ensure_loop_envelope` is now class-aware (returns the `tenant` row even when a platform row exists on the same Loop).

## 14. Build Notes — C5 graduated dunning + state-aware suspension (2026-07-20)

**C5 built** — a lapsed tenant degrades instead of falling off a cliff:

1. **The ladder is a pure state machine in `ai/trust/dunning.py`.** `status_for_days_past_due` maps days-overdue → `current → past_due → grace → read_only → suspended` with configurable windows (`BILLING_GRACE_DAYS`/`BILLING_READ_ONLY_DAYS`, both 7d — decision 1). `advance_dunning` moves `companies.subscription_status` (new column, migration `trust004`) and emits a `billing.*` transition signal — idempotent (only on a real change; recovery to `current` when the tenant pays). `agents_may_act` is the predicate the Loop/gateways read to stop acting.

2. **The middleware degrades access, it doesn't kill it.** `CompanySuspensionMiddleware` is now state-aware: `suspended` (or the legacy `status='suspended'`) → 403 for everything; `read_only` → **blocks agent-facing mutations but allows GETs, billing/pay, and export** so the tenant can read, export, and recover without loss. `current/past_due/grace` are full function. Inbound signals keep parking (SIG PARKED), so nothing is dropped while read-only.

**What computes `days_past_due`** — the billing/payment subsystem watching wallet/subscription lapse — is the integration that calls `advance_dunning` on a schedule; it lives in `billing/` (outside `ai/`). **Closed in §18.** The ladder, the column, the middleware enforcement, and the signals were ready.

## 15. Build Notes — E4 fee-formula guard (2026-07-22)

**E4 built.** The register described `max(total_billing, 0)` masking fee misconfiguration; the shipped code turned out to have **no clamp at all**, which is worse — a discount above break-even silently *credited* the customer and recorded a negative `BillingEvent`.

1. **The clamp is right; the silence was the bug.** `ai/trust/fee_guard.py` keeps the clamp (a config bug must never credit a customer) but makes it loud: `inspect_fee_result` returns a finding that *names* the likely culprit — a discount above the `1 + pf + spf` break-even, or a negative multiplier — rather than leaving an operator to re-derive it. `report_fee_misconfiguration` logs ERROR and raises a `billing.fee_misconfigured` signal, deduped per company per billing period so a bad config fires one card, not thousands. Wired at both paths TB reaches persistence: `compute_billed_amount` (per-call deduction) and `record_billing_event`.

2. **The ordering intent is now asserted, not implicit.** The discount is taken on the *multiplied cost* and subtracted **last** — it does not reduce the platform fee or the sales-partner fee, because a discount is the platform's concession, not the partner's. That is a business decision living inside an arithmetic expression that looks "simplifiable", so it is stated in `fee_guard.py` and pinned by `TestOrderingIntent`.

## 16. Build Notes — E2 free-credit abuse controls (2026-07-22)

**E2 built** — and per §17 it is the economics finding that actually gates GA.

1. **Three controls, one policy module.** `ai/trust/abuse_controls.py` holds the verification gate, the per-IP signup throttle, and the eligibility predicate; enforcement is wired at existing call sites — the same shape as C5 (ladder in `dunning.py`, enforcement in the middleware). The throttle needs **no new table and no Redis**: the signup IP is stamped into the company's existing `onboarding_metadata` JSONB, so the check is one time-bounded count against `companies`.

2. **The gate is at all three injection points**, because any one of them alone is bypassable: `auth.service._provision_new_tenant` (a fresh self-registered workspace starts at 0 daily credits — read from the flag, not the DB, since it runs pre-commit and must not query other tables), `credit_service.get_or_create_wallet` (the first-touch path would otherwise hand out a day of credits before the cron ever asked), and `flush_and_inject_daily_credits` (the daily cron). Verifying an email is the whole activation — no separate step.

3. **It composes with the C5 ladder.** `read_only`/`suspended` tenants draw no free credits; `grace` still does, because grace is full-function by decision 1. Settings: `TRUST_REQUIRE_VERIFIED_FOR_CREDITS`, `TRUST_SIGNUP_MAX_PER_IP_PER_DAY` (0 disables).

4. **The gate is scoped to self-service signup, and that scoping is load-bearing.** The first cut gated on "the company has no verified user", which read as equivalent but is not: it also starved **admin-provisioned** tenants (a human vouched for them), **OAuth** tenants (provider-verified, `is_verified=True` at creation), and **seeded/fixture** tenants of credits. The parity harness caught it — its fixture companies have no users at all, so every agent run failed wallet-hold admission with `insufficient_funds` and the whole suite went red. The gate now keys off `onboarding_metadata.created_via ∈ SELF_SERVICE_ORIGINS`, which is both the correct security scope (password signup is the only path an attacker drives) and the fix. Pinned by `TestSelfServiceScoping` and two DB cases so it cannot re-broaden.

## 17. Build Notes — E1 idle-cost model (2026-07-22)

**E1 built** — `ai/trust/idle_cost.py` + the derived numbers in [05a_idle_cost_model.md](./05a_idle_cost_model.md).

1. **Structure derived, rates declared.** Every component's cadence is read off the shipped code (the crons in `worker.py`, the `heartbeat_interval_s` seeded by `loop/service.py`, the hibernation window), so the model moves when the platform moves — pinned by `TestCadenceIsDerived`. Only the three `UnitRates` are inputs, named and overridable so a real invoice replaces an estimate in one line.

2. **The answer is a shape, not a number.** The floor splits into infrastructure (**$0.30/tenant/month** Solo, **$4.44** Growth on the container backend) and platform-initiated inference — and **B13 already caps the second half** at `LOOP_PLATFORM_ENVELOPE_USD`. The Blueprint's `$2,000/month` is mis-scoped: it reads as platform *fixed* cost, not per-tenant; ~6,500 idle Solo tenants would be needed to reach it. Hibernation is validated (24× on residency, 59% of Solo's floor), and `LOOP_DEFAULT_ENVELOPE_USD = $100` is confirmed sane at ~330× the idle floor.

3. **It reorders the economics work.** Free credits are **$150/month/tenant** against a $0.30 idle floor — **500×**. The free tier's entire risk is the credit grant, so **E2 is the GA-gating economics item** and E1's real contribution is ruling out the other candidate explanation. That was not obvious before the numbers existed.

## 18. Build Notes — the two integration hookups (2026-07-22)

1. **C5's driver.** `billing/cron_service.days_past_due()` is pure and needs **no new column**: a successful charge advances `next_billing_date` (→ 0, and the ladder recovers the tenant), a failed one leaves it in the past so the days accumulate by themselves. `run_dunning_job()` sweeps every non-cancelled subscription — `advance_dunning` is idempotent, so a daily re-sweep of a stable tenant base is a no-op. The arq entry point is `ai/trust/crons.py::dunning_sweep`, registered daily at 01:10 UTC (after the midnight credit job, so a ladder position reflects the day just entered); `POST /api/v1/cron/dunning` triggers it manually. **Scope is subscriptions only** — a pay-as-you-go tenant has nothing to be *past due* on: their wallet runs empty and Inc-1's wallet-hold admission already blocks spend. The ladder is about a lapsed commitment, not an empty wallet.

2. **B13's admission at the runners.** `loop/platform_budget.platform_work_admitted()` resolves the root Loop itself so a runner that knows only its company can ask; it **fails open when no Sheel is seeded** — the cap is a spend control, not a safety interlock, and missing infrastructure must not silently disable platform work. Wired into `dreaming_worker` (the 4×/day per-entity LLM burner B13 targets), which now returns `platform_budget_exhausted` and parks instead of running. `meta_agent_prompt_evolution` is deliberately left alone: its LLM "critic of critic" pass is still a stub, so there is no spend to gate — wire it when that lands.

**TRUST is complete.** All seven findings (C5, D6, C3, B13, E1, E2, E4) are closed.
