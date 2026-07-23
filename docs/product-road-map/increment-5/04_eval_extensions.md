# Increment 5 / EVX — Eval Extensions: The Admission Gate (§22.2–.4)

> **Status:** ⬜ Design (self-contained) — locked before code.
> **Realizes:** technical §22.2 (independent-suite rule), §22.3 (canary rollout), §22.4 (model-change regression policy). **Builds on:** the shipped `tests/eval/` + `tests/parity/`. **Gates:** FLEET activation ([03](./03_fleet_expansion.md) §6) and any RTR rule change ([02](./02_router.md)).

---

## 1. What exists, and the three missing pieces

The platform already ships more evaluation machinery than any earlier doc admitted (§22.1): the **parity golden gate** (`tests/parity/` — hermetic engine-behavior comparison, chaos + cost-amplification checks), the **eval harness** (`tests/eval/` — pure metrics + delta reports + a DB-gated replay runner), the **Meta-Agent TestDriver** suites, the **tool-synthesis red team**, and the **static gates**. B9 was a *documentation* gap more than a code gap — but three build pieces are genuinely missing, and Inc 5 is where they earn their place because it is the first increment that **changes the model fleet**:

* **§22.2 Independent-suite rule** — the exam predates the student; nothing promotes on self-generated tests alone.
* **§22.3 Canary rollout** — promote to a slice, watch SLOs, auto-rollback, then widen.
* **§22.4 Model-change regression policy** — every fleet change runs the eval delta against the incumbent and admits only on non-inferiority within cost budget.

Per the §22 build notes: "22.2 is process plus one promotion-pipeline check; 22.3 reuses the shipped per-company canary-flag pattern; 22.4 is an eval-harness invocation wired to model-registry changes." So **EVX adds no new table** — it is code + process over the shipped harness and the existing per-company flag.

## 2. Why EVX lands before FLEET activation

FLEET makes GLM/Qwen/Mistral *reachable*; EVX decides whether any of them (or a version bump, or a routing-rule change) is *allowed to serve*. The gate must exist before the thing it gates. So EVX and FLEET are a co-dependent pair ([00](./00_overview.md) §4): FLEET's adapters + `preview` rows land, then EVX's admission check is what flips a row to `active` and rolls it out. There is no window in which a new provider serves un-gated traffic.

## 3. §22.4 — the model-change admission gate

`ai/intelligence/admission.py::admit_model_change(candidate, incumbent, task_classes) -> AdmissionResult`.

A **model-fleet change** is any of: a new `model_registry` row proposed for `active`; a `version` bump; a provider deprecation/replacement; a BabyBuddha admission (Inc 7, same gate). On such a change:

1. Determine the **affected task classes** (which `task_type`s this model would serve under the current rules).
2. Run the **eval-harness delta report** (`tests/eval/runner.py` replay) for `candidate` vs `incumbent` on those classes, over the curated corpus (§4).
3. Admit only on **non-inferiority within cost budget**: quality metric not worse than the incumbent beyond a tolerance **and** projected cost within budget. Either failing → `AdmissionResult(admitted=False, reason=…)`.
4. **Router preference never overrides a failed admission** (§22.4, hard). A model the scorer would love but that failed admission stays `preview` and is never `eligible()`.

The status flip to `active` (`RegistryService`) **calls `admit_model_change` first and refuses on failure** — the gate is in the mutation path, not a suggestion. An admission run emits `signal: model.admission_evaluated` (result + metrics) and writes its eval report as an artifact for audit.

**Cost of the gate (B13):** the admission eval makes real LLM calls against the candidate. That spend is **platform-initiated** model-change validation, not tenant work — a **new `CostAttribution.MODEL_ADMISSION`** added to `PLATFORM_INITIATED_ATTRIBUTIONS` (the §5 convention: "a new `usage_logs` attribution must be classified for B13"). It draws from the platform budget class (Inc-2 B13 machinery), never a tenant's envelope.

## 4. §22.2 — the independent-suite rule

Encoded as an **ordering check in the promotion path**, not a vibe:

`ai/intelligence/admission.py::require_independent_suites(artifact) -> None` asserts, in order, before any promotion:

1. **The incumbent's golden suite** — captured from the *current* model/rule's behavior **before** the change (the exam predates the student). For a model change this is the incumbent's recorded outputs on the corpus; for a routing-rule change it is the current rules' parity goldens.
2. **Platform curated suites** for the affected task classes — human-seeded, in `tests/eval/` (§4), never model-generated.
3. Self-generated tests — admitted only as *additional* coverage, **never as the gate**.
4. The **red-team step** — mandatory, reusing the shipped tool-synthesis adversarial reviewer where applicable.

The check refuses if (1) or (2) is absent — you cannot promote a model on a suite the model itself produced. A test asserts the guard fails when handed a self-generated-only suite.

### 4.1 The curated corpus — a routing/model golden set

New `tests/eval/routing_corpus.py` + `tests/eval/routing_metrics.py` (mirroring RETR's `retrieval_{corpus,metrics}.py`, [increment-2/06](../increment-2/06_retrieval_upgrade.md) §T5):

* **`routing_corpus`** — representative steps per task class (planning, critic, extract, format, drafting, vision, voice-turn) with a *reference* expected-quality band, human-curated. This is the "exam" a candidate model sits, and the golden set the RTR heuristic ([02](./02_router.md) §7) is scored against.
* **`routing_metrics`** — the non-inferiority metric (quality-delta vs incumbent) + a cost-delta, producing the `AdmissionResult`'s numbers. Deterministic, DB-gated replay for the model calls.

## 5. §22.3 — canary rollout

Reuses the **shipped per-company flag pattern** — no new flag machinery. `ModelTaskDefault.routing_mode` is already per-company ([02](./02_router.md) §3.3), and the sandbox runtime already ships the canary-flag pattern.

`ai/intelligence/canary.py`:

* `start_canary(change, cohort) -> None` — after admission passes, the change serves a **canary slice** first (a cohort of companies on `routing_mode='router'` with the new model `active` *for them*), the rest unchanged.
* `watch(change) -> CanaryVerdict` — compares the cohort's SLOs (the Blueprint §10.2 agent SLOs + error/cost rates from `routing_decisions` + `usage_logs`) against the baseline over a clean window.
* **Auto-rollback on SLO regression** — a regressing canary reverts (`status` back to `preview` for the cohort) and emits `signal: model.canary_rolled_back`. Full rollout (`active` for all) only after a **clean canary window**, emitting `model.canary_promoted`.

Canary state needs no table — it is the per-company `active`-for-cohort flag + the signals + the `routing_decisions`/`usage_logs` already recorded. The verdict is computed from data the router already writes.

## 6. Code Mapping

| Path | What |
|---|---|
| `ai/intelligence/admission.py` | `admit_model_change()` (§22.4) + `require_independent_suites()` (§22.2). |
| `ai/intelligence/canary.py` | `start_canary` / `watch` / rollback (§22.3). |
| `ai/intelligence/registry.py` | **edit** — the `active` flip calls `admit_model_change` first, refuses on failure. |
| `tests/eval/routing_corpus.py` | the curated routing/model golden set. |
| `tests/eval/routing_metrics.py` | non-inferiority + cost-delta metrics. |
| `ai/loop/cost_attribution.py` | **edit** — add `MODEL_ADMISSION` to the enum **and** `PLATFORM_INITIATED_ATTRIBUTIONS`. |
| `signals/*` | **edit** — new `SignalTypes.MODEL_ADMISSION_EVALUATED` / `MODEL_CANARY_PROMOTED` / `MODEL_CANARY_ROLLED_BACK`. |
| `ai/intelligence/api.py` | **edit** — `/ai/intelligence/admissions` (read the admission reports + canary state). |

**No migration** — EVX is code + process over shipped tables (§1).

## 7. Testing

* `tests/unit/test_admission.py` — a candidate that regresses quality is refused; one within tolerance+budget is admitted; **router preference cannot override a refusal** (the §22.4 hard rule, executed); the independent-suite guard fails on a self-generated-only suite.
* `tests/unit/test_canary.py` — a regressing cohort auto-rolls-back and emits the signal; a clean window promotes; the verdict is computed from `routing_decisions`/`usage_logs` alone (no new state).
* `tests/integration/test_admission_gate_db.py` — a `RegistryService` `active` flip **refuses** when admission fails and **succeeds** (emitting `model.admission_evaluated`) when it passes; the admission spend logs as `MODEL_ADMISSION` and is excluded from the tenant rollup (B13).
* `tests/eval/test_routing_goldens_db.py` — the routing corpus is the regression gate: the RTR heuristic's complexity scoring and the admission non-inferiority both run against it; a deliberately-worse candidate is caught.

## 8. Risks & gotchas

* **The gate must be in the mutation path.** If `admit_model_change` is merely *available* rather than *called by the `active` flip*, a provider can be activated un-gated. The integration test asserts the flip refuses on a failed admission — that is the load-bearing check for the whole increment.
* **Classify the admission attribution** (§5 convention) — `MODEL_ADMISSION` must be in `PLATFORM_INITIATED_ATTRIBUTIONS` or admission eval spend silently draws down a tenant's envelope and the parity suite goes red with `insufficient_funds`.
* **A curated suite that is never run is a suite that returns `True`** (the §5 T7 lesson) — the routing corpus must have a fixture the *incumbent* passes and a candidate that *fails*, and the mapping asserted total, or the gate proves nothing.
* **Canary reads live** — the verdict must reflect the current window, not a cached rollup, or a regression rides through the watch.

## 9. Task Plan

1. **T1** — `routing_corpus.py` + `routing_metrics.py` (the curated exam) + a passing-incumbent / failing-candidate fixture pair.
2. **T2** — `admit_model_change()` + `require_independent_suites()` + `MODEL_ADMISSION` attribution (B13-classified).
3. **T3** — wire the gate into `RegistryService`'s `active` flip; the refuse-on-fail integration test.
4. **T4** — `canary.py` (start/watch/rollback) over the per-company flag + the canary signals.
5. **T5** — the `/ai/intelligence/admissions` admin read; gates green; **then** FLEET activation ([03](./03_fleet_expansion.md) §6) runs through this gate.

## 10. Brainstorm Decisions (Rahul, 2026-07-23)

1. **EVX adds no table** — code + process over the shipped harness and the per-company flag (§1, §22 build notes).
2. **The gate is in the mutation path** — the `active` flip calls admission and refuses on failure; availability is not enough.
3. **Admission spend is `MODEL_ADMISSION`, platform-initiated** — B13-classified, off the tenant budget.
4. **Canary reuses `routing_mode='router'`** — one flag, live verdicts from data the router already writes.
5. **The curated routing corpus is the exam** — human-seeded, incumbent-predates-candidate, with a failing-candidate fixture so the gate is proven to bite.
