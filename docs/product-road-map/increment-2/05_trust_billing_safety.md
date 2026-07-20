# Increment 2 / TRUST — Billing Safety, Consent & the Economics Floor

> **Status:** 🚧 **In progress** — **D6 (consent registry) ✅ built (2026-07-20)**: the jurisdiction-agnostic consent/DNC/unsubscribe store + tenant-managed provider, wired into KAR's outbound seam; migration `trust001`; gates green. **Remaining: C5, C3, B13, E1, E2, E4** (dunning/middleware + economics — see §11). · **Branch:** `inc2/trust` · **Closes:** C5, **D6 ✅**, C3, B13, E1, E2, E4.
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
| Idle-cost model | a report/doc + `E1` measurement harness reading Inc-1 tenant-DB metrics |
| Abuse controls | `auth/` sign-up + daily-credit eligibility |

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

**Remaining TRUST (not built this session):** **C5** dunning + state-aware `CompanySuspensionMiddleware` (touches `billing/` + `common/middleware.py`), **C3** per-checkpoint SLAs (`hitl_checkpoint_defs` columns + timeout worker), **B13** platform-initiated budget class (LOOP + CostLedger), **E1** idle-cost model, **E2** free-credit abuse controls (`auth/`), **E4** fee-formula alerts. These reach into the billing/auth/middleware subsystems outside `ai/` and are best done with that subsystem in view.
