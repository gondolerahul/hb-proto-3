# Increment 2 / TRUST — E1: The Always-On Idle-Cost Model

> **Status:** ✅ **Derived** (2026-07-22) · **Closes:** **E1** · **Parent:** [05_trust_billing_safety.md](./05_trust_billing_safety.md) §5
> **Model:** `backend/src/ai/trust/idle_cost.py` · **Tests:** `tests/unit/test_idle_cost.py`
> **Design authority:** Blueprint §10.1/§15 (economics), Technical §20.4 (envelopes). Replaces the Blueprint's asserted `$2,000/month` with a derived, per-tenant number.

---

## 1. The finding

Register **E1**: *"Always-on cost floor unmodeled. 5 gateways + continuous P01 sensing + Chronos sweeps burn money at zero business volume. The $2,000/month Sheel example is asserted, not derived."*

It mattered for three decisions that were all waiting on it: what a default budget envelope should be (`LOOP_DEFAULT_ENVELOPE_USD` shipped as an explicit placeholder), whether the free tier is survivable, and how aggressive tenant-DB hibernation needs to be.

## 2. What is derived and what is input

The model separates the two so its confidence is legible:

* **Derived — the structure.** Every component's cadence is read off the shipped code, not assumed: the cron registrations in `ai/worker.py`, the `heartbeat_interval_s` seeded by `loop/service.py`, and the hibernation window in `TENANT_DB_SOLO_IDLE_SECONDS`. Change a cron and the model moves. That is regression-pinned by `test_idle_cost.py::TestCadenceIsDerived`.
* **Input — the unit rates.** `UnitRates` (`usd_per_db_query`, `usd_per_gateway_poll`, `usd_per_tenant_db_hour`) are hosting costs, defaulted to conservative small-managed-deployment figures. They are named and overridable, so swapping an estimate for a real invoice line is a one-line change, not a re-derivation.

**These are marginal, per-tenant costs** — what one additional idle tenant adds. Platform-wide fixed cost (the API process, the arq worker, the control-plane Postgres, Redis) is *not* per-tenant and is accounted separately in §5.

## 3. The derived floor

Per tenant, per month, at **zero business volume**, `TENANT_DB_BACKEND=container` (the prod backend):

| Component | Per day | Solo $/mo | Growth $/mo | Cadence source |
|---|---:|---:|---:|---|
| Loop heartbeat (6 queries/beat) | 4,320 | 0.0518 | 0.0518 | `heartbeat_interval_s` = scan × 2 = 120s |
| Loop watchdog | 720 | 0.0086 | 0.0086 | `cron(loop_watchdog)` every 2 min |
| Signal sweeper | 1,440 | 0.0173 | 0.0173 | `cron(signal_sweeper)` every minute |
| Gateway inbound poll | 720 | 0.0432 | 0.0432 | `cron(email_inbound_poll)` every 2 min |
| Chronos resume scan | 288 | 0.0035 | 0.0035 | `cron(cortex_resume_scheduled)` every 5 min |
| KPI rollup | 24 | 0.0003 | 0.0003 | `cron(kpi_rollup_refresh)` hourly |
| Tenant-DB residency | 1 h / 24 h | **0.1800** | **4.3200** | hibernation vs always-on |
| **Infrastructure total** | | **$0.30** | **$4.44** | |
| *(+ platform-inference cap, §4)* | | *10.00* | *10.00* | `LOOP_PLATFORM_ENVELOPE_USD` |
| **Ceiling** | | **$10.30** | **$14.44** | |

On the `schema` backend (dev/CI/test, no container) the infrastructure floor is **$0.12/mo** — residency is the only tier-sensitive term.

**Hibernation earns its keep.** Solo's tenant-DB residency is $0.18/mo against Growth's always-on $4.32 — a **24× reduction**, and it is 59% of Solo's total infrastructure floor. The aggressive Solo idle window (15 min, Inc-1 SCH decision) is validated: without it, every Solo tenant would cost what a Growth tenant costs.

## 4. The half that used to be unbounded — and is not any more

The floor splits in two, and only one half was ever a real risk:

* **Infrastructure** (the table above) — DB round-trips and network polls, no inference. Cents, and bounded by cron cadence.
* **Platform-initiated inference** — dreaming, meta-review, spec-critic, sandbox, test-driver, perpetual sensing. This is the expensive half and the one E1 was really worried about: work the platform starts *without the tenant asking*.

**B13 already capped it.** Those attributions draw from a separate envelope (`LOOP_PLATFORM_ENVELOPE_USD`, default $10/mo) via `loop/platform_budget.py::platform_spend_admitted`; over cap, platform work parks and tenant work is untouched. So the inference half of the idle floor has a **hard per-tenant ceiling by construction**, not by hope. E1's answer is therefore not a single number but a shape: *small infrastructure + a configurable, enforced ceiling*.

`idle_cost.measured_platform_spend(db, company_id)` is the empirical check — run it against a tenant with no business volume and it returns that tenant's actual idle inference spend, which must sit at or under the cap.

## 5. Correcting the $2,000/month assertion

The Blueprint's `$2,000/month` is not wrong so much as **mis-scoped**: it reads as a per-deployment *platform fixed* cost (API + worker processes, control-plane Postgres, Redis, observability), which does not scale per tenant. The marginal cost of one more idle tenant is **$0.30/month** (Solo, container backend).

Put the other way: **~6,500 idle Solo tenants** would be needed before marginal idle cost reached $2,000/month. Idle tenants are not the platform's cost problem.

## 6. What this validates

1. **`LOOP_DEFAULT_ENVELOPE_USD = $100/mo` is a sane default.** It is ~330× the Solo idle floor and ~10× the platform-inference cap, so an envelope is never consumed by idling — it exists to bound *tenant-initiated* work, which is correct. Pinned by `test_idle_cost.py::test_idle_ceiling_fits_inside_the_default_envelope`.
2. **The free tier's risk is free credits, not idling** — and by a wide margin. `$5/day` is **$150/month** per tenant of platform COGS, against a $0.30 idle floor: **500×**. Every dollar of free-tier risk is in the credit grant.
3. Which is precisely why **E2's abuse controls are the GA-gating economics item**, not E1. A signup farm does not cost $0.30/tenant/month; it costs $150. The verification gate and per-IP throttle ([05](./05_trust_billing_safety.md) §6) are what make the free tier survivable — E1's contribution is showing that the *other* candidate explanation (always-on burn) is a rounding error.

## 7. Sharpening it later

The structure needs no revisiting; only the three `UnitRates` do. When a real hosting invoice exists, override them and re-run:

```bash
poetry run python -c "from src.ai.trust.idle_cost import derive_idle_cost; print(derive_idle_cost('solo').as_rows())"
```

Two model simplifications worth revisiting if the numbers ever get close to mattering: Solo tenant-DB residency assumes ~4 sporadic touches/day (each holding the container up for one idle window), and the heartbeat is costed at 6 DB round-trips per beat. Both are stated in `idle_cost.py` at the point of use.
