# Increment 5 — The Intelligence Engine: Overview

> **Document Class:** Increment Design & Implementation Plan (index)
> **Author:** Buddha Cognitive Lab (drafted by Claude, decisions by Rahul)
> **Created:** 2026-07-23 · **Status:** Design — seam locked, four decisions taken (§2); no code yet
> **Parent:** [build_roadmap.md](../build_roadmap.md) §4 (Increment 5, L) · [00_charter.md](./00_charter.md)
> **Prerequisite:** Increment 2 (traffic to learn from) + Increment 4 complete on `master`. EVX builds on the shipped eval harness (`tests/eval/`, `tests/parity/`).
> **Read next:** [01_model_registry.md](./01_model_registry.md) (REG/B12) · [02_router.md](./02_router.md) (RTR v1+v2) · [03_fleet_expansion.md](./03_fleet_expansion.md) (FLEET/D5) · [04_eval_extensions.md](./04_eval_extensions.md) (EVX/§22.2–.4).

---

## 1. The goal, stated once

> Make the §3.3 cost story **real and auditable**: complexity-scored, wallet-aware model routing over a **governed fleet**, with the eval harness as the admission gate.

Today `ai/llm/router.py` does *configuration lookup* — it resolves the one model a company configured for a task type and dispatches to an SDK adapter. There is no fleet catalog with versions/regions/effective-dated prices (B12), no complexity scoring, no wallet-aware downshift, no per-decision audit trail, and every provider is allowed by default (D5). Increment 5 closes that gap without moving the call seam every agent already uses.

**The one non-obvious fact that shapes the whole increment:** the router placement decision (§2.2) means the router is reached *through* the shipped `LLMRouter.call_llm(task_type=…)` seam, not from inside the planner. So the router scores from the signals available **at that seam** — task type, company, model override, wallet state, and optional caller hints — not from a full `PlanStep`. That is a deliberate, documented consequence, and it is enough for v1 and v2. A future planner-stage enrichment can add per-step signals *without moving the router*, because the logic lives in its own package.

## 2. Decisions Taken (Rahul, 2026-07-23 — do not re-open during build)

1. **Model registry = global catalog + per-company binding (B12).** A new **control-plane** `model_registry` (versioned, region-tagged, effective-dated pricing, `capability_profile`) is the fleet catalog. The existing per-company `IntegrationRegistry` keeps credentials and *references* a catalog row. Reproducible billing and a single fleet source for the router's eligibility query; the cost is a bigger migration and a join. Full design: [01](./01_model_registry.md).
2. **Router lives in a new `ai/intelligence/` package; `LLMRouter` delegates to it.** Routing logic + registry live in `ai/intelligence/router.py` matching the §3.3 target path. The shipped `LLMRouter.call_llm` seam delegates when routing is active, so **no agent call site changes**. This isolates complexity scoring from SDK dispatch. Full design: [02](./02_router.md).
3. **RTR v2 complexity scoring is heuristic-first.** Score from step attributes already available at the call seam (task-type class, entity tier, reasoning mode, tool use, context tokens). Deterministic, no per-step cost or latency, testable with a routing golden set. A small-model classifier is admitted *later, only if the heuristics underperform on the goldens* — never as the v2 default. Full design: [02](./02_router.md) §5.
4. **Fleet default is conservative; GLM/Qwen/Kimi are opt-in with disclosure (D5).** The default allow-list is the providers already in use (Anthropic / Google / OpenAI / Azure). GLM (Zhipu), Qwen (Alibaba) and Kimi (Moonshot AI) are **registered but OFF by default**, opt-in per tenant with a recorded data-flow disclosure. *(Updated 2026-07-23: Kimi replaces the originally-scoped Mistral, so all three fleet-expansion providers are China-hosted and opt-in — no default-allowed EU provider, a strictly more conservative posture.)* Directly closes D5. Full design: [03](./03_fleet_expansion.md).

**Two working assumptions carried from the Inc-4 precedent (state them, don't re-litigate):**

* **Fleet expansion ships as a *tested seam*, not live wire-level calls.** Catalog rows + an OpenAI-compatible adapter over an *injectable transport* (the Zoho pattern) + the allow-list + the eval gate — proven against fakes. No live GLM/Qwen/Kimi call is made; live binding is activation-time ops, the same discipline voice go-live and the Zoho connector carry. See [03](./03_fleet_expansion.md) §7.
* **BabyBuddha / OmniBuddha stays out (Inc 7).** Inc 5 leaves a **registry-row-shaped hole** it drops into — `internal` provider, `capability_profile`, admission through the same EVX gate as any vendor model. Nothing here builds toward a training run.

## 3. Workstreams

| # | Doc | Workstream | Closes | Depends on |
|---|---|---|---|---|
| 1 | [01_model_registry.md](./01_model_registry.md) | **REG** — the global `model_registry` + effective-dated `model_prices`; `IntegrationRegistry` binds to it | **B12** | Inc-1 billing/config |
| 2 | [02_router.md](./02_router.md) | **RTR v1** — registry + static rules + `routing_decisions` attribution, reproducing current defaults | (B12 audit half) | REG |
| 3 | [02_router.md](./02_router.md) | **RTR v2** — heuristic complexity scoring + wallet-aware downshift + fallback | — | RTR v1, Inc-1 ENV/wallet-holds |
| 4 | [04_eval_extensions.md](./04_eval_extensions.md) | **EVX** — independent-suite rule, canary rollout, model-change regression gate (§22.2–.4) | **B9** docs+build side | shipped `tests/eval`, `tests/parity` |
| 5 | [03_fleet_expansion.md](./03_fleet_expansion.md) | **FLEET** — GLM/Qwen/Kimi adapter seam + conservative default allow-list + data-flow disclosure | **D5** | REG, RTR, **EVX (the gate)** |

## 4. Build Order

**REG → RTR v1 → RTR v2 → EVX → FLEET.**

The order is a dependency chain, not the charter's listing order — and the one reversal is deliberate:

* **REG first** — the router is blind without a fleet catalog to select from (charter §1). Everything downstream reads it.
* **RTR v1 before v2** — v1 introduces the router + `routing_decisions` + static rules that **reproduce the current per-company defaults** (non-inferior by construction, §22.4). v2 then adds scoring and downshift *on top of* a proven-neutral baseline, so a routing regression is attributable to the scorer alone.
* **EVX before FLEET *activation*.** The charter lists EVX last because it is "wired as the admission gate for every fleet change." Logically the gate must exist before any provider is flipped `active`. So FLEET's *adapters and catalog rows* land default-OFF, and **no provider goes `active` except through the EVX admission check.** EVX and FLEET therefore build as a co-dependent pair, EVX being the gate FLEET must pass. See [04](./04_eval_extensions.md) §2 and [03](./03_fleet_expansion.md) §6.

Each workstream: branch `inc5/<workstream>`, build task-by-task, keep every gate green (§6), add a §N build-note delta log + flip maturity tags (⬜→◐→✅) on merge.

## 5. Register Findings — where each closes

| Finding | Workstream | Note |
|---|---|---|
| **B12** model registry too coarse | REG | New control-plane `model_registry` carries version + region + effective-dated price + `capability_profile`; billing becomes reproducible against a point-in-time price. |
| **D5** data-flow disclosure / sovereignty | FLEET | Conservative default allow-list; GLM/Qwen opt-in per tenant with a recorded disclosure; a subprocessor / data-region / training-data disclosure doc ([03a](./03_fleet_expansion.md#3a)) published. |
| **B9** (EVX docs+build side) | EVX | The shipped eval layer's three missing pieces — independent-suite rule (§22.2), canary rollout (§22.3), model-change regression gate (§22.4) — built and wired to every fleet change. B9's design was resolved in Inc 2 docs; this is its build. |

**Still open after Inc 5** (unchanged homes): B10, B11, D3 (Inc 6); B14, D4 (Inc 7); C2, D2 (deferred within Inc 4).

## 6. Standing Rules (carried forward)

1. **Metered *and* attributed.** Every model call already writes `usage_logs`; Inc 5 adds that every *routed* call also carries a `routing_decisions` row (which model, why, wallet state, fallback). A call the audit trail can't explain is the B12 gap rebuilt. The **parity suite is the canary** for any change on the LLM cost path — run `tests/parity tests/eval` before believing a routing change is safe.
2. **No behavior change without the gate.** A model-fleet change — new model, version bump, provider flip to `active`, or a routing rule that would select differently — is a §22.4 event: it runs the eval-harness delta against the incumbent on the affected task classes and admits only on **non-inferiority within cost budget**. Router preference *never* overrides a failed admission.
3. **Conservative by default, opt-in with disclosure.** A provider off the default allow-list is never selected until the tenant opts in and the disclosure is recorded. The allow-list filters candidates *before* scoring, so a disallowed provider is never even a candidate.
4. **Platform-initiated spend stays off the tenant budget (B13).** EVX admission runs eval-harness calls; that spend is `MODEL_ADMISSION`, a `PLATFORM_INITIATED` attribution. A new `usage_logs` attribution must be classified (the §5 convention).
5. **Docs move with code** — maturity tags in the target-state docs (§2.4/§3/§22) + §N build-note delta logs per workstream on merge.
