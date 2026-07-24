# Increment 6 — The Self-Improving Platform — Increment Plan

> **Document class:** increment overview — the plan the six workstream docs hang off.
> **Author:** Buddha Cognitive Lab (drafted by Claude, decisions by Rahul)
> **Created:** 2026-07-24 · **Status:** v1.0 — decisions locked, workstream docs in progress
> **Parent:** [00_charter.md](./00_charter.md) (goal, scope, the nine decisions) · [build_roadmap.md](../build_roadmap.md) §4
> **Baseline:** `master` @ `8a54c27` — Increments 1–5 merged and pushed; VG-05 hardening built.

---

## 1. What this increment is

Increment 6 is the increment that makes the platform's central claim **measurable**. Everything before it built capability; this one builds the machinery that observes capability changing — and, because measurement is worthless without history, it starts collecting on day one.

It is now **entirely backend**. GENUI left for [Increment 7](../increment-7/00_charter.md) (decision 6), which is what the charter's title always implied: *the self-improving platform*, not *the platform and its new face*.

Two things about the shape are worth stating before the workstream docs:

**This increment is mostly stores, and stores are worthless empty.** KPI history, the retrieval-usage log, the learning store, the entity version ledger, the Seasons timeline — every one is a time series whose value is a function of how long it has been running. That is why the build order front-loads them, and why a workstream that could be deferred on feature grounds may not be deferrable on *data* grounds. A KPI history started in Increment 7 cannot answer "was Week 12 better than Week 1" until Week 12 of Increment 7.

**Half of it exists because the Design Gate found it.** TWIN, STRAT, GATE and LIB were not in the road map before 2026-07-24 — they came out of walking the ratified Vihara spec against the code ([00a](./00a_genui_backend_gap_analysis.md)). They are in Increment 6 rather than Increment 7 because they are backend domain work, and Vihara should be a frontend increment with its own substrate, not a frontend increment that also has to invent a simulation engine.

## 2. The six workstreams

| # | Workstream | Closes | Doc |
|---|---|---|---|
| 1 | **LEARN** — learning store, charter tuning, B10 policy, KPI history, density store | **B10** | `01_learn.md` |
| 2 | **SEGA** — self-evolution GA, entity-change canary, version ledger, taint | **B11**, **D3** | `02_sega.md` |
| 3 | **TWIN** — the Glasshouse: twin plane, replay, forecast, honesty grading | — (VG-09/VG-10) | `03_twin.md` |
| 4 | **STRAT** — Minutes→Propositions→Resolutions→Mandates→Reviews + HBS Planning depth | — (VG-11) | `04_strat.md` |
| 5 | **GATE** — KAR-05 governed broadcast gates | — (VG-15) | `05_gate.md` |
| 6 | **LIB** — Library data layer: provenance, influence, staleness, drives | — (VG-13/VG-14) | `06_lib.md` |

Workstreams 3–6 close no *register* finding because the register predates the Design Gate. They close **gap-analysis** findings instead, and the register is not retro-fitted — the gap analysis is their register.

## 3. Build order, and why it is forced

```
LEARN ──► SEGA ──► TWIN ──► STRAT
                                       GATE  (independent, any time)
                                       LIB   (independent, start early)
```

* **SEGA before TWIN** — TWIN's promotion pipeline (diff → certified approval → Board build → canary → GA) *calls* SEGA's entity-change canary. Building a second canary inside TWIN would duplicate B11's blast-radius logic in the one place it must not be duplicated.
* **TWIN before STRAT** — STRAT's reviews show predicted-vs-realized, and "predicted" is a TWIN honesty grade. Without TWIN, a Resolution's review can only report what happened, not whether the bet was right.
* **LEARN first** — see §1: `KpiSnapshot` is the longest-lead time series in the increment and four later surfaces read it.
* **LIB early despite being independent** — the retrieval-usage log has the same problem. "This pricing sheet answered 40 customer questions this month" requires a month of logging.
* **GATE anywhere** — it touches SIG, the Karuna profile and the consent registry, none of which the other five modify.

## 4. The decisions, and what each one obliges

The nine locked decisions are in [the charter](./00_charter.md). Four of them impose obligations that must show up in code, not just in prose:

**Decision 2 (B10 split) is a schema obligation, not a query convention.** "Platform-level pools, tenant-level doesn't" is only true if the pooled path *cannot* carry tenant content. A `company_id` column that is merely left NULL is not a guarantee — it is a bug waiting for a careless insert. LEARN must make the pooled record a **different shape** from the tenant record, so that carrying business content through the pooled path is a type error rather than a policy violation. The B10 finding is about *blindspots*; a scoping rule enforced only by discipline is precisely such a blindspot.

**Decision 3 (reuse the signal bus + CORTEX) means both systems take a third job.** The signal bus was built for business events and CORTEX for agent memory. Neither was designed to be a learning store, and the risk is not capacity — it is that "which store is this row in" stops being a meaningful scoping signal, which is exactly why decision 2's guarantee has to live in the record shape (above).

**Decision 7 (twin spend is tenant-initiated) overrides the ratified spec.** Spec §12.1 says twin spend is visible under the platform-initiated budget class. That is wrong for the reason the HANDOFF convention states plainly: tenant-asked-for work in `PLATFORM_INITIATED_ATTRIBUTIONS` lets ordinary tenant activity exhaust the cap that exists to protect tenants *from* platform work. The spec will be amended. **The product consequence is real and should be designed for**: a Glasshouse that visibly costs money is a Glasshouse people use less, and TWIN's doc should say how it keeps a what-if cheap (bounded replay windows, cached baselines, no re-embedding).

**Decision 8 (pooled learning disclosed, not opt-out) is asymmetric with D5 on purpose.** D5's opt-in governs *where tenant data physically goes*; decision 8 governs aggregate telemetry that by construction contains none. If LEARN cannot hold decision 2's schema guarantee, decision 8's justification collapses with it and the question reopens. **They stand or fall together** — that dependency belongs in LEARN's doc as a stated risk.

## 5. Gates

Unchanged from Increments 1–5, run from `backend/`:

```bash
poetry run python scripts/typecheck_ai.py      # mypy --strict; ADD EACH NEW ai/ PACKAGE
poetry run python scripts/lint_ai_layout.py    # layout + de-canary lint
poetry run pytest tests/unit -q
poetry run pytest tests/parity tests/eval -q   # the billing canary — TWIN touches attribution
poetry run pytest tests/integration -q         # needs DATABASE_URL
poetry run alembic upgrade head
```

Baseline to beat: typecheck **260 files**, **1550 unit**, **16 parity/eval**, **288 integration**, migration head **`fleet001`**.

Two gate notes specific to this increment:

* **TWIN and LEARN both touch cost attribution**, so `tests/parity` is the canary for both — unit tests stay green while every agent run fails (see the HANDOFF §5 note; this has bitten before).
* **Four new `ai/` packages are expected** (`learning`, `evolution`, `twin`, `strategy` — names to be fixed in the workstream docs). Each must be added to `CLEAN_PACKAGES` in `scripts/typecheck_ai.py` or it silently escapes strict typing.

## 6. Migrations

Head is **`fleet001`**. This increment adds a lot of schema — provisionally:

| Workstream | Expected tables |
|---|---|
| LEARN | learning records (two shapes, per decision 2), `kpi_snapshots`, user preference/density |
| SEGA | `entity_versions` (the ledger), canary cohorts, taint annotations |
| TWIN | scenarios, twin runs, honesty-graded results; the twin plane is likely **not** a migration (tenant schemas bootstrap per-tenant — the Inc-4 precedent in `data_plane._sync_columns`) |
| STRAT | monuments + review schedule; **Planning HBS objects are tenant-schema seed, not Alembic** |
| GATE | none expected — gateways are templates, bindings reuse `connector_bindings` |
| LIB | `documents` provenance columns, retrieval-usage log, staleness flags |

Note the two carve-outs, both established precedent: **tenant tables are bootstrapped per-tenant, not migrated** (SCH, Inc 1), and **new HBS objects are seed data** (`tenant_schema/hbs_seed/`), so STRAT's Planning depth adds spine entries rather than a migration.

## 7. Honest risks

| Risk | Why it is real here |
|---|---|
| **The increment is the largest attempted** | Six workstreams, four of them net-new subsystems. Inc 2 (six workstreams) is the closest precedent and it was the MVP. Deferring GATE or LIB is the cheapest relief valve if it runs long — both are independent by construction (§3). |
| **TWIN has no precedent in the codebase** | Nothing simulation-shaped exists. The twin *data plane* is the risky part; `data_plane.py`'s two-backend design is the intended host but has never run a third mode. Prototype the plane before the engines. |
| **Decision 2's guarantee may not survive contact** | If the pooled/tenant split cannot be made structural, decision 8 reopens (§4). Find out in LEARN's first task, not its last. |
| **STRAT is domain modelling, not plumbing** | Minutes/Propositions/Resolutions/Mandates are business objects a tenant will *see*. They need the same review the HBS spine got (drafted, then reviewed by Rahul), not just an engineer's guess. |
| **Measuring "Week 12 > Week 1" needs Week 1** | Every deferral of LEARN pushes the first honest answer out by the same amount, and no later effort recovers it. |

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-24 | v1.0 — increment plan written after the clarifying round: six workstreams, forced build order with the reasons, the four decisions that carry code obligations, gate baseline and migration expectations, honest risks. |
