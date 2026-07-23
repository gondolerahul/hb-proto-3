# Increment 5 / RTR — The Model Router (v1 + v2)

> **Status:** ✅ **BUILT** (2026-07-23, branch `inc5/rtr`) — v1 + v2, all of T1–T5, gates green. Build notes §12.
> **Realizes:** technical §3.3 (the router) + §3.4 (fallback & governance). **Depends on:** REG ([01](./01_model_registry.md)) for the catalog; Inc-1 ENV/`wallet_holds` for headroom. **Gated by:** EVX ([04](./04_eval_extensions.md)) for any rule that would select differently.

---

## 1. What exists, and the seam we keep

Every reasoning call in the platform goes through **one** method:

```python
# ai/llm/router.py  (shipped)
LLMRouter(db, company_id).call_llm(task_type=…, system_prompt=…, user_prompt=…, model_override=…)
```

`_resolve_adapter(task_type, model_override)` calls `ConfigService.resolve_model_for_task(company_id, task_type)` → the single `IntegrationRegistry` row the company configured, then dispatches to the Gemini / Anthropic / Azure adapter. `ModelTaskDefault.routing_mode` is `'single' | 'router'` — **the `'router'` value already exists and does nothing.** That stub flag is our clean opt-in.

**Decision (§2.2 of the Overview): the router lives in `ai/intelligence/router.py`; `LLMRouter` delegates to it.** The call seam every agent uses does not change. `_resolve_adapter` gains one branch: when the company's task default is `routing_mode='router'`, it asks `IntelligenceRouter.route(...)` for a `ModelBinding` and builds the adapter from that; otherwise it does exactly what it does today.

### 1.1 The consequence of this placement (stated honestly)

The §3.3 target sketch routes over a full `PlanStep` (`step.entity_tier`, `step.reasoning_mode`, `step.latency_class`, …). Those live in the planner, not at the `call_llm` seam. Because we route *through the seam*, the router's signal surface is **what the seam has**: `task_type`, `company_id`, `model_override`, wallet state, and **optional caller hints** a call site may pass. This is sufficient for v1 and v2 (§5 shows the heuristic maps task_type→complexity well). When richer per-step routing is wanted, a caller passes a `RoutingHints` object *or* a future planner stage enriches the seam — **neither requires moving the router**, because the logic is already isolated in its own package. That portability is the entire reason for the placement choice.

## 2. `ModelBinding` and `RoutingSignals` — the two data types

```python
# ai/intelligence/types.py
@dataclass(frozen=True)
class RoutingSignals:
    task_type: str
    complexity: float          # 0..1, from complexity.score() — v1 sets a fixed prior per task class
    modality: str              # "text" | "vision" | "realtime_audio"
    needs_tools: bool
    context_tokens: int        # estimate at the seam
    latency_class: str         # "strict" | "standard" | "batch"
    wallet_headroom_usd: float | None
    cost_ceiling_usd: float | None
    allow_list: list[str] | None
    pinned_model: str | None

@dataclass(frozen=True)
class ModelBinding:
    model_registry_id: UUID
    integration_id: UUID       # the per-company binding that carries credentials
    model_name: str            # the concrete SDK id handed to the adapter
    provider: str
    reason: str                # "pinned" | "rule" | "auto" | "fallback" | "downshift"
    signals: dict              # snapshot, persisted to routing_decisions
```

## 3. RTR v1 — registry + static rules + attribution

**Goal:** introduce the router, the audit trail, and static rules **that reproduce the current per-company default** — so v1 is non-inferior by construction (§22.4) and every routed call becomes auditable.

### 3.1 The `routing_decisions` table (control-plane, migration `rtr001`)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `run_id` | UUID FK → `execution_runs`, nullable | the loop run (null for Pragya/standalone calls). |
| `step_id` | String, nullable | the step signature within the run, when the caller supplies it. |
| `company_id` | UUID FK → companies | |
| `task_type` | String | |
| `model_registry_id` | UUID FK → `model_registry` | the chosen model. |
| `reason` | String | `pinned` · `rule` · `auto` · `fallback` · `downshift`. |
| `signals` | JSONB | the `RoutingSignals` snapshot — the "why". |
| `fallback_used` | Boolean | true when §6 kicked in. |
| `created_at` | DateTime | |

`usage_logs` gains a **nullable** `routing_decision_id` FK. Set when routing is active, so a billing line links directly to *which model, why*. Nullable keeps the un-routed path untouched — the reproducibility/attribution chain is `usage_log → routing_decision → model_registry (+ model_prices)`.

### 3.2 Static rules

`ai/intelligence/rules.py` — `default_binding(signals, candidates) -> CatalogModel`. v1's rule table maps `(task_type)` → the catalog model equivalent to the company's current `ModelTaskDefault`, i.e. **the seed rule reproduces today's choice.** The rule layer exists so v2's scorer has a deterministic floor to fall back to and so a company with no scorer signal still routes sanely. Pinned model and allow-list filtering wrap the rules (§4).

### 3.3 The delegation branch

```python
# ai/llm/router.py :: _resolve_adapter  (v1 edit, abridged)
task_default = await config_svc.get_task_default(company_id, task_type)
if task_default and task_default.routing_mode == "router":
    binding = await IntelligenceRouter(self.db, self.company_id).route(
        RoutingSignals(task_type=task_type, ...caller hints..., wallet_headroom_usd=await self._headroom())
    )
    integration, api_key = await config_svc.load_integration(binding.integration_id)
    effective_model = binding.model_name
    # record_routing_decision(...) written inside route()
else:
    integration, api_key = await config_svc.resolve_model_for_task(company_id, task_type)  # unchanged
```

Routing is therefore **opt-in per company via the existing `routing_mode` flag** — which is exactly EVX's canary lever (§22.3): flip a canary cohort to `'router'`, watch the SLOs, widen. No new flag machinery.

## 4. Candidate selection order (v1 and v2, §3.3/§3.4)

Same order the tech doc pins, so governance/D5 always win over cost:

1. **Filter → `RegistryService.eligible(modality, min_context=context_tokens, allow_list)`.** Allow-list and residency filter *here*, before anything is scored — a disallowed provider is never a candidate (D5).
2. **Pinned wins if eligible.** `signals.pinned_model` in the candidate set → `reason="pinned"`.
3. **Score** (v2) or **rule** (v1) picks among the remaining candidates.
4. **Record** the `routing_decision`.

## 5. RTR v2 — heuristic complexity scoring + wallet-aware downshift

**Decision (§2.3): heuristic-first.** No classifier, no per-step model call — deterministic and free.

### 5.1 `ai/intelligence/complexity.py::score(signals) -> float` (0..1)

Heuristic features, all available at the seam or from caller hints:

| Feature | Signal → contribution |
|---|---|
| **task class** | planning / critic / legal-financial drafting → high; extract / format / classify → low. A `TASK_COMPLEXITY_PRIOR` table keyed by `task_type` is the base. |
| **reasoning mode** | `debate` > `cot` > `react` > single-shot (when the caller hints it). |
| **tool use** | `needs_tools` nudges up (tool orchestration needs reliability). |
| **context size** | large `context_tokens` nudges up (long-context synthesis is harder). |
| **latency class** | `strict` (voice) *caps* the score's effect — a live turn can't wait for a reasoning model regardless of complexity (§5.3). |

The output is a single 0..1 score; the mapping is a pure function with a golden set (§7). This is the whole scorer — deliberately legible, because a routing decision that spends a customer's wallet must be explainable to that customer.

### 5.2 `ai/intelligence/scoring.py::utility(model, signals) -> float`

Scores each eligible candidate on **capability-fit vs cost vs latency**, biased by wallet:

```
fit      = capability_match(model.capability_profile, signals.complexity, signals.needs_tools, signals.modality)
cost     = effective_cost_estimate(model, signals.context_tokens)      # from model_prices
latency  = latency_penalty(model.capability_profile.latency_class, signals.latency_class)
utility  = w_fit·fit − w_cost·cost·cost_pressure(signals) − w_latency·latency
```

`cost_pressure()` rises as `wallet_headroom_usd` shrinks or `cost_ceiling_usd` tightens — so the *same step* routes to a cheaper eligible model when the wallet is tight. `best = max(candidates, key=utility)`.

### 5.3 Wallet-aware downshift (the headroom tie to Inc-1)

Headroom comes from the shipped budget machinery — `loop/envelopes.py` + `wallet_holds`. The router reads available headroom (never via `CreditService.get_balance`, which auto-injects and commits — the §5 E3-race lesson; use the envelope/hold read path). When headroom is below a configurable floor **or** the entity's `max_cost_per_step_usd` ceiling is low, the scorer's `cost_pressure` forces a **downshift to a cheaper eligible tier before failing** (§3.3 heuristic; `reason="downshift"`, recorded). Downshift is a routing choice, **not** a governance bypass — a downshifted model still passes the PolicyGate and the allow-list.

### 5.4 The routing heuristics (defaults, from §3.3)

* `complexity < 0.3` and no tools → cheapest eligible.
* planning / pre-/post-critic / legal-financial drafting → the reasoning tier (`claude-opus`, later `babybuddha-reasoning`).
* `modality == vision` → a multimodal-grounded model (`gemini`).
* `latency_class == strict` → realtime-capable profile only (§5 voice).
* wallet tight or ceiling low → downshift before failing.

## 6. Fallback & governance (§3.4)

`ai/intelligence/fallback.py` — on provider error / rate-limit, retry the **next-best eligible** model by utility; record `fallback_used=True` on the decision. Two rules hold:

* **Governance and allow-list filter before scoring**, so a fallback can never reach a disallowed provider.
* **The PolicyGate is unchanged.** The router picks *which model*; the PolicyGate still asks *may this act happen* on the categorised effect. Routing is orthogonal to governance — a cheaper model raises the same HITL card.

## 7. Testing

* `tests/unit/test_complexity_scoring.py` — the pure `score()` mapping against a **routing golden set** ([04](./04_eval_extensions.md) supplies `tests/eval/routing_corpus.py`): known steps → expected complexity band; monotonicity (adding tools/depth never lowers the score); `strict` latency caps the effect.
* `tests/unit/test_routing_rules.py` — v1 rules reproduce the current per-company default for every `task_type` (the non-inferiority floor); pinned wins; allow-list excludes.
* `tests/unit/test_scoring_utility.py` — `utility()` prefers the cheaper eligible model as `cost_pressure` rises; never selects an ineligible/disallowed candidate; downshift triggers below the headroom floor.
* `tests/integration/test_routing_decisions_db.py` — a routed `call_llm` writes exactly one `routing_decision`, `usage_log.routing_decision_id` is set, and the `usage → decision → registry → price` chain resolves. `routing_mode='single'` writes **no** decision (the un-routed path is inert).
* `tests/integration/test_router_fallback_db.py` — a faked provider error routes to the next-best and stamps `fallback_used`.
* **Parity is the canary.** Routed runs must stay behaviourally identical to single-model runs on the parity goldens when the rules reproduce the default — `tests/parity tests/eval` green before merge.

## 8. Code Mapping

| Path | What |
|---|---|
| `ai/intelligence/types.py` | `RoutingSignals`, `ModelBinding`, `RoutingHints`. |
| `ai/intelligence/router.py` | `IntelligenceRouter.route(signals) -> ModelBinding` + `record_routing_decision`. |
| `ai/intelligence/rules.py` | v1 static `default_binding()` (reproduces current defaults). |
| `ai/intelligence/complexity.py` | v2 heuristic `score()`. |
| `ai/intelligence/scoring.py` | v2 `utility()` + `cost_pressure()`. |
| `ai/intelligence/fallback.py` | next-best-eligible retry. |
| `ai/intelligence/models.py` | **edit** — add `RoutingDecision` ORM (beside REG's models). |
| `ai/llm/router.py` | **edit** — the delegation branch in `_resolve_adapter`; a `_headroom()` reader. |
| `ai/orm/usage.py` | **edit** — nullable `routing_decision_id` FK. |
| `config/service.py` | **edit** — a `load_integration(id)` helper (credentials for a chosen binding). |
| `migrations/versions/rtr001_*.py` | `routing_decisions` + the `usage_logs` FK; off `reg001`. |
| `ai/intelligence/api.py` | `/ai/intelligence/routing-decisions` (admin audit read) — registered in `main.py`. |

## 9. Risks & gotchas

* **Non-inferiority is the v1 acceptance test.** If routed runs diverge from single-model runs on parity when rules reproduce the default, the rules are wrong — v1 must be behaviourally neutral before v2 adds scoring.
* **Headroom read path** — use the envelope/hold read, never `get_balance` (re-opens the E3 race, §5).
* **No new attribution for scoring** — heuristics make no LLM call, so RTR adds no `usage_logs` attribution (contrast EVX admission, which does — [04](./04_eval_extensions.md)).
* **`routing_mode='router'` is the canary lever** — do not invent a second flag; EVX (§22.3) rides this one.

## 10. Task Plan

1. **T1 (v1)** — `types.py` + `router.py` skeleton + `rules.py` reproducing current defaults + `routing_decisions` migration `rtr001` + the `LLMRouter` delegation branch. Non-inferiority parity green.
2. **T2 (v1)** — `record_routing_decision` + the `usage_logs` FK + the attribution chain test + `/ai/intelligence/routing-decisions` admin read.
3. **T3 (v2)** — `complexity.score()` + the routing golden set + monotonicity tests.
4. **T4 (v2)** — `scoring.utility()` + `cost_pressure()` + wallet-headroom read + downshift.
5. **T5 (v2)** — `fallback.py` + the fallback test; all gates green.

## 11. Brainstorm Decisions (Rahul, 2026-07-23)

1. **Router in `ai/intelligence/`, delegated from `LLMRouter`** — Overview §2.2. The call seam does not move.
2. **Signal surface = the seam's signals + optional caller hints** — the documented, deliberate consequence (§1.1); portable to a richer surface later without moving the router.
3. **v1 reproduces current defaults; v2 adds scoring** — the non-inferiority floor (§22.4) is built in before behavior changes.
4. **Heuristic complexity scoring** — Overview §2.3; a classifier only if the goldens show the heuristic underperforming.
5. **`routing_mode='router'` is the per-company opt-in and the EVX canary lever** — one flag, not two.

## 12. Build Notes (2026-07-23) — delta log

### 12.1 What shipped
* v1: `ai/intelligence/{types,router}.py` (`IntelligenceRouter.route` reproduces the task default → non-inferior), `RoutingDecision` + migration **`rtr001`** (routing_decisions + a nullable `usage_logs.routing_decision_id`), the `LLMRouter._resolve_adapter` delegation branch (routed keys uncached — a decision per call), the usage link threaded `LLMResponse → _log_usage → log_usage`, `config.load_integration`, and `GET /ai/intelligence/routing-decisions`.
* v2: `complexity.py` (heuristic score), `scoring.py` (`Candidate`/`capability_fit`/`cost_pressure`/`utility`), the router's `_candidates`/`_wallet_headroom`/`_enrich`/`reroute`, and `fallback.py` (`is_retryable`) wired into a bounded, routed-only retry in `call_llm`.
* Tests: `test_routing_scoring.py` (unit goldens), `test_router_v1_db.py` + `test_router_v2_db.py` (delegation, scored pick, downshift, safe fallback-to-default, reroute).

### 12.2 Design deltas (decided during build)
1. **Candidates are the company's *credentialed* models, not the whole catalog.** §4/§5 read as `eligible()` over the fleet, but the router can only pick a model the tenant has an `IntegrationRegistry` (credentials) for. So `_candidates` = the company's active, catalog-bound integrations, filtered by modality/context/allow-list. A model the tenant lacks keys for is never a candidate; **no catalog-bound candidate → v1 default binding**, so router mode is always safe. `eligible()` (catalog-level) stands for admission/EVX; `_candidates` (company-level) is what routing scores.
2. **v1's single-candidate case scores through v2** (reason `auto`, same model). Once v2 landed, a company with one bound model goes through scoring — `rule` is now specifically the *no-catalog-bound* fallback. The v1 test's assertion was updated to match.
3. **Fallback is routed-only, bounded, and billing-safe.** The `call_llm` retry loop wraps `generate`; an un-routed call has no `_pending_binding`, so any error re-raises immediately (the un-routed path is byte-identical — parity held). Billing is post-return in `step_executor`, so a failed-then-retried call bills once, on success. Bounded to two fallbacks. Applied to single-turn `call_llm` only, not `call_llm_react` (whose mid-loop tool side effects must not be blindly retried).
4. **Wallet headroom is a non-locking *hint*.** `cost_pressure` reads the envelope approximately (`envelope − reserved − spent`), never the FOR-UPDATE-locked wallet-hold row — because it is a *selection* bias, not admission (the E3 lesson, HANDOFF §5). The authoritative wallet-hold admission stays downstream and unchanged.
5. **The signal surface is the seam's + internal enrichment.** The router fills in `complexity` (heuristic) and `wallet_headroom` itself; no caller passes `reasoning_mode` yet, so complexity today derives mostly from `task_type` (+ tool/context when a caller hints them). Portable to a richer surface without moving the router (§1.1).

### 12.3 Gate results
`typecheck_ai` (253 files, strict) · layout lint · **parity/eval 16** (non-inferiority — the un-routed path did not move) · **1510 unit** (+11 scoring/fallback goldens) · **20 RTR `*_db`/unit** · `rtr001` apply/rollback/re-apply. The router now selects, downshifts, and falls back — auditable per decision, safe by opt-in, and (later) gated by EVX's canary.
