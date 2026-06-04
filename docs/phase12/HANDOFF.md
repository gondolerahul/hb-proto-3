# Phase 12 — Implementation Handoff

> **Read this first.** It is the single entry point for continuing Phase 12 in a
> fresh session. It captures the current state, the non-obvious findings that
> change the plan, how to verify, and the exact remaining sequence. Pair it with
> [`WHATS_NEXT.md`](./WHATS_NEXT.md) (the prioritized checklist), the eight
> [`plans/`](./plans/) files (the original spec), and the two C4 design docs in
> [`designs/`](./designs/).
>
> **Last updated:** 2026-06-03 (Stage 1 de-canary + C4 Phase A landed)
> **Branch:** `phase12/stage1-consolidation`

---

## 0. TL;DR — where things stand

- Phase 12 plans live in `docs/phase12/plans/` (8 files, `00`–`08`). The
  prioritized status is in `WHATS_NEXT.md`.
- The repo was the **Phase 11 canary build**; **Stage 1 consolidation is now
  largely done** — the canary labels are gone and the codebase is the GA shape,
  except for the one big gated deletion (C4) and a few trailing items.
- **Done & committed on the branch** (newest work first):
  - **Stage 1 de-canary**: `C3`-alias removal, `C10` backend de-prefix
    (`phase11_router` → `ai/api/admin`), `C11` frontend de-prefix, and the
    **layout/canary lint flipped to `error`** — `test_layout_lint_passes` is now
    **green** (the previously-known failure is resolved).
  - **C4 Phase A (the evidence gate)**: multi-child PROCESS parity (inline +
    **async suspend/resume, first E2E**), resumability chaos test, and a cost
    amplification guard — all green. See §3 + `designs/c4_replatforming_implementation_plan.md`.
  - Earlier: Stage 0 switch-flip, the hermetic parity gate, `C1` (v1 critic
    delete), `C9` (retire REFLECTION/ToT), the async-child-dispatch mechanism.
- **The headline constraint still holds:** **C4 (delete legacy `execute_run`) is
  a multi-PR re-platforming, not a deletion.** Its evidence gate (Phase A) is now
  green; the remaining deletion chain (Phase B) is **gated on a flag soak (G4)**
  that can only run with a live canary. See §3.
- **C13 is blocked** (not a clean cut) — see §7.
- **Nothing is in production.** Telemetry/soak gates are dev-skipped by policy;
  the two master switches default ON. All commits are **local only** (no GitHub
  creds in this env) — the human pushes.

---

## 1. CRITICAL CONTEXT — read before writing any code

1. **C4 is the only remaining gated deletion, and it is a re-platforming.** The
   AgentLoop delegates step execution into `ExecutionEngine` internals, and every
   child entity historically ran via the `execute_run` callback. The unblocking
   mechanism (async suspend/resume child dispatch) is **built and now proven E2E**
   (Phase A). The actual deletion (Phase B) is gated on a soak. Full detail in §3
   and `designs/c4_replatforming_implementation_plan.md`.

2. **The layout/canary lint is now `error` mode and green.** `CANARY_LABEL_MODE`
   in `backend/scripts/lint_ai_layout.py` is `error`; any reintroduced
   `p11/P11/phase11` identifier/filename under `backend/src/ai/**.py` fails CI.
   The `core/` size cap is **1500** (agent_loop.py is large from suspend/resume).
   Keep new files under their package cap or extract a module (as `step_results.py`
   did).

3. **Residual `phase11` strings are intentional and lint-permitted.** Only: the
   one-release redirect shims (`backend/src/main.py` and the frontend route table,
   both with a **2026-09-01 removal date**), immutable applied-migration names
   (`p11t02_*`, `p11_merge_2026_05_28`), and `docs/phase11/*` pointers in `*.md`
   READMEs (the lint scans only `*.py`). Don't "clean" these without a plan.

4. **The two master switches default ON in dev** (`agent_loop.enabled`,
   `meta_agent.board_routing`) — `backend/src/ai/core/feature_flags.py`. The
   feature-flag env-override prefix is now **`AI_FLAG_`** (was `PHASE11_FLAG_`).

5. **The parity gate is hermetic and is the C4 evidence gate.** `tests/parity/`
   runs legacy `ExecutionEngine` vs the new `AgentLoop` with a deterministic mock
   LLM + stubbed `web_search` (no API keys). It now has a **positive multi-child
   PROCESS** case and the **async-dispatch + chaos + cost** checks (§3). Embeddings
   are NOT stubbed — they hit the real Vertex endpoint (returns 200 here; cost $0
   with no SKU rows). This is parity-neutral (both engines embed).

6. **All real-DB parity checks run inside ONE event loop** (the aggregated
   `test_agent_loop_parity`). A standalone `@pytest.mark.asyncio` DB test **skips**
   with "attached to a different loop" — the global `AsyncSessionLocal` engine
   binds to the first loop it touches and asyncpg can't cross loops. **Add new
   real-DB parity checks as helper functions called from that one test**, not as
   new test functions. (PR-2/PR-3 follow this.)

7. **No LLM API keys, but DB + Redis are live** (Postgres `localhost:5433`, Redis
   `localhost:6379`). There is no live arq worker; the async child path is
   exercised hermetically via the in-process drainer `tests/parity/worker_sim.py`.

8. **The comment-narration lint is `error` mode.** Don't write comments matching
   `# Phase 12`, `# Fix X:`, `# RACE-N`, etc. in `backend/src/ai/**.py`.

---

## 2. What's DONE (committed on the branch)

Oldest → newest (this branch is ahead of `origin/phase12/stage1-consolidation`;
all local). Earlier Phase-11/Stage-0 work (`1dd336a`..`deaabba`) is unchanged.

| Commit | What |
|--------|------|
| `7b946fb` | **C3-partial** — remove the deprecated `CortexRouter` alias. |
| `7379d92` | **C10** — backend de-prefix: `ai/phase11_router.py` → `ai/api/admin.py` (`/api/v1/ai/admin/*`) + 307 redirect shim in `main.py`; decision log → `docs/DECISIONS.md`. |
| `f9343b9` | **C11** — frontend de-prefix: 7 `P11*` component pairs + sub-components renamed; `types/phase11.ts`→`agentKernel.ts`; `Phase11KPI`→`KPIDashboard`; `p11-`→`agentk-` CSS; routes `/admin/agent-kernel/*` + redirect shim. |
| `98868d4` | **de-canary** — neutralize remaining `phase11` tokens in `ai/*.py` (incl. env prefix `AI_FLAG_`); flip `CANARY_LABEL_MODE`→`error`; raise `core/` cap to 1500. `test_layout_lint_passes` green. |
| `5aa0a25` | **C4 PR-1** — multi-child PROCESS positive parity (G1 inline) + the C4 implementation plan doc. |
| `dd16a35` | **C4 PR-1b** — loop emits `result_data["steps"]` (snapshotted `AgentState.step_results`); fixes a real refine-flow regression. |
| `4b762c5` | **C4 PR-2** — async suspend/resume parity (first E2E) via `worker_sim.py`; `max_concurrent_children` cap; `CHILD_RUN_QUEUE` config. |
| `4882886` | **C4 PR-3** — resumability chaos (G2) + cost amplification guard (G3). |
| `fbfbf00` | **docs** — C4 plan Progress section. |
| `b17c803` | **C12 scaffold** — `mypy --strict` per-package gate (`scripts/typecheck_ai.py` + allowlist + `test_typecheck_passes` + CI fast lane + `[tool.mypy]`); **`governance/` strict-clean** (first package). |
| `996053b` | **C12 — ORM→`Mapped[]` + planning clean** — `orm/*` migrated to SQLAlchemy 2.0 `Mapped[]` (DDL-identical), governance de-cast, **`planning/` strict-clean** (87→0); allowlist now governance + orm + planning. |
| `4f60690` | **C12 — meta strict-clean** — **`meta/` strict-clean** (74→0); allowlist now governance + orm + planning + meta (46 files). Surfaced 3 latent meta bugs (flagged). |

**Push status:** local only.
```bash
git push origin phase12/stage1-consolidation
```

---

## 3. C4 — the keystone deletion (Phase A done, Phase B gated)

**Status: the evidence gate (Phase A) is GREEN; the deletion chain (Phase B) is
not started, gated on a flag soak.** The full, code-grounded plan is
[`designs/c4_replatforming_implementation_plan.md`](./designs/c4_replatforming_implementation_plan.md)
(builds on [`designs/async_child_dispatch.md`](./designs/async_child_dispatch.md)).

**Why C4 is not a simple deletion** (still true): `execute_run` is load-bearing —
loop executors delegate into engine step methods, and child entities ran via the
`execute_run_fn` callback. Routing children through the loop inline was tried in
Phase 11 and reverted (~$11/child amplification + worker blocking,
`execution_engine.py:97-104`). The fix is async suspend/resume child dispatch.

**Expanded caller inventory (a finding beyond the original design's 3):**
`execute_run` is also called **directly, bypassing the loop and the
`agent_loop.enabled` flag**, by the gateway dispatcher (`gateway/dispatcher.py:272`)
and the gateway-event worker (`arq_jobs.py:290`), plus `resume_execution`
(`arq_jobs.py:719`). PR-8 must re-route these too. Also note the dead
`enqueue_job("execute_run", …)` calls (`cortex_bridge.py:357`, `arq_jobs.py:801`)
reference an unregistered job name — verify/clean.

**Phase A — DONE (the gate):**
- **G1** multi-child PROCESS parity, inline (PR-1) **and async suspend/resume,
  first E2E** (PR-2). ✅
- **G2** resumability chaos: crash before resume → durable `WAITING_ON_CHILDREN`
  → fresh-worker recovery → idempotency (PR-3). ✅
- **G3** cost amplification guard: async child-execution work == inline (PR-3). ✅

**Phase B — NOT started, gated:**
- **G4 flag soak (PR-4)** — operational: `governance.async_child_dispatch` ON for
  a live canary + real telemetry. Cannot run in the keyless dev env. The human
  runs it in prod, or it is dev-skipped by explicit decision (like the Stage-0
  telemetry gate this build skipped).
- Then the irreversible chain: **PR-5** extract `StepEngine` → **PR-6** drop the
  child callback → **PR-7** re-platform `RecursiveExecutor` (the hard one) →
  **PR-8** make every entry point loop-only → **PR-9** delete `execute_run`
  (irreversible — removes the rollback flag) → **PR-10** C2 (`MemoryRouter`
  delete) → **PR-11** C3 finish. All MemoryRouter/MetaReviewer engine uses live
  *inside* `execute_run`, so deleting it unblocks C2 and reduces C3.

> Do not start Phase B without confirming the soak decision. PR-9 is irreversible.

---

## 4. The async-child-dispatch mechanism (so you don't re-learn it)

Behind `governance.async_child_dispatch` (default OFF), now **proven E2E**:

- **Status** `WAITING_ON_CHILDREN`; **marker** `ActionResult.awaiting_children`;
  **state** `AgentState.awaiting_children` + `step_results` (both snapshotted) +
  transient `suspend_requested`.
- **Dispatch** `ChildEntityExecutor._dispatch_async` creates the child run,
  enqueues `run_execution_recursive`, returns the marker. Bounded by
  `governance.max_concurrent_children` (default 8; over it → run inline).
- **Loop** `_iteration` detects the marker → suspend; `_drive` persists
  `_persist_suspended` + returns; `resume()` rehydrates, `_fold_children` folds
  terminal children (records a `step_results` entry per child),
  `_maybe_resume_parent` enqueues `resume_parent_run` on a child's finalize.
- **Jobs** `resume_parent_run` (idempotent), registered in `worker.py`.
- **Tests** units in `tests/unit/test_async_child_dispatch.py`; E2E + chaos +
  cost in `tests/parity/` (driven by `worker_sim.py`).

---

## 5. How to verify (commands that work here)

```bash
cd backend
PY=.venv/bin/python

# Full unit suite (hermetic). Expect: all pass (layout-lint now green).
$PY -m pytest tests/unit -o addopts="" -q -p no:warnings

# The parity gate + all C4 Phase-A checks (needs DB+Redis; skips if absent).
# Expect: 2 passed (sanity + the aggregated parity test running G1/G2/G3).
$PY -m pytest tests/parity -o addopts="" -q -p no:warnings

# Re-record parity goldens (hermetic; needed if you change a fixture/case).
$PY -m scripts.record_golden_runs --output tests/parity/goldens

# The layout/canary lint (now exits 0).
$PY scripts/lint_ai_layout.py

# The C12 mypy --strict gate over the clean-package allowlist (exits 0).
$PY scripts/typecheck_ai.py
```

Notes: always pass `-o addopts=""`. Parity seeds throwaway `parity-*` tenants and
does not clean them up (FK chains) — use a disposable Postgres if that matters.

---

## 6. The remaining roadmap (prioritized)

Pull per-item detail from `WHATS_NEXT.md`.

### A. Stage 1 consolidation — nearly done
- ✅ C3-alias, C10, C11, lint→error (de-canary). `grep` of `backend/src
  frontend/src` for `p11|P11|phase11` is empty except the documented shims +
  migration names + `*.md` doc pointers.
- ◐ **C12 — `mypy --strict`** per package as a CI gate. **Scaffold + 4 packages
  clean** (`b17c803`, `996053b`, `4f60690`): `scripts/typecheck_ai.py` (allowlist +
  `--follow-imports=silent`), `test_typecheck_passes`, `run_ci_matrix.sh` fast
  lane, `pyproject [tool.mypy]`. **Clean: `governance/` (32→0), `orm/`, `planning/`
  (87→0), `meta/` (74→0)** — 46 files gated. Add the next package by making
  `mypy --strict --follow-imports=silent src/ai/<pkg>` zero, then append it to
  `CLEAN_PACKAGES`. Localized remaining counts: `memory` 225, `core` ~1190 —
  incremental, not the "mechanical M" the plan billed. **The legacy-`Column` ORM cost is GONE:**
  `orm/` was migrated to SQLAlchemy 2.0 `Mapped[]` (`996053b`, DDL-identical), so
  attributes carry real types — no more `cast()`/`# type: ignore[assignment]`
  against `orm/` models. (Cross-package reads of not-yet-migrated models — e.g.
  `memory/`'s `CortexNode` — still need a `cast` until that package migrates too.)
  **Latent bugs surfaced by strict typing (all silently masked, flagged via
  spawn-tasks):** `CriticCalibrator` built `IntelligenceTreeService` without the
  required `company_id` (planning; since fixed); and in `meta/` — `curator`'s
  anti-sprawl CREATE gate calls `check_creation_allowed` with the wrong kwargs,
  `registry_search`'s `_score_io_compatibility` calls async `db.get` without
  `await` (sync method), and `platform_schema_compiler` queries
  `IntegrationRegistry` columns that don't exist. The meta ones carry a narrow
  `# type: ignore` (self-cleaning via `warn_unused_ignores` once fixed).
- 🚧 **C13 — drop deprecated `engine_type` / `reasoning_mode`** — **blocked, not a
  clean cut** (see §7). Needs per-step reasoning routed via the Strategist first,
  and the engine_type half is gated on C4.

### B. C4 (large; §3) — Phase A done
Run the **G4 soak**, then Phase B (PR-5..PR-11). This unblocks **C2** and the rest
of **C3** as fallout.

### C. The rest of Phase 12 (each its own track; see plans)
- `02` Sandbox runtime / per-tenant containers (0%; hard-dep of `06` tool synth).
- `03` Video tool split (0%). `04` CORTEX pip package (0%; Stage-A groundwork done;
  Stage B gated on C2). `06` Meta-Agent v5 capabilities (v4 board exists; v5 = 0%).
  `07` MCP adapter, budget-aware REACT, trust-score learning, eval harness.

---

## 7. Landmines / gotchas (specific, learned the hard way)

- **C13 is blocked.** `engine_type` is not a typed schema field — its only
  behavioral consumer is the C4-blocked `execute_run` (`execution_engine.py:738`).
  `reasoning_mode` is still live: `step_executor.py:841/1041` routes REACT vs
  CHAIN_OF_THOUGHT off the raw-dict value (the typed `ReasoningConfig.reasoning_mode`
  is never read via the model). A clean drop needs per-step reasoning routed via
  the Strategist's `reasoning_hint` first. The ORM/`schemas/execution.py`
  `reasoning_mode` is *execution telemetry* — keep it.
- **One-loop parity constraint** (see §1.6): add real-DB parity checks as helpers
  called from `test_agent_loop_parity`, never as standalone async tests.
- **Loop result_data shape:** the loop now emits `{"output", "steps":[...]}` to
  match legacy (`core/step_results.py` + `_persist_final`). The refine flow
  (`service.py:617`) reads `result_data["steps"]` — don't regress it.
- **Child resolver has no company filter** (`planning/child_resolver.py` Strategy 4
  name-hint lookup → `scalar_one_or_none`): seeding fixed-name children across
  runs trips `MultipleResultsFound`. Parity seeding wires `target.entity_id`
  directly (Strategy 1) to avoid this.
- **De-prefix shims carry a 2026-09-01 removal date** (`main.py` backend redirect,
  frontend route table). Don't delete early; don't forget to delete on schedule.
- **C10 left a double-`admin/` path** for the KPI/decisions/risks/tools endpoints
  (e.g. `/api/v1/ai/admin/admin/kpi/runs`) — functionally correct, cosmetic
  cleanup if desired.
- **Don't delete `MemoryRouter`, `MetaReviewer`, or `execute_run` yet** — all
  load-bearing via the legacy engine until C4 Phase B (§3). `MetaReviewer` stays
  even after C4 (`RealCriticPipeline` uses it, `critic_pipeline.py:490`).
- **Alembic revision ids ≤ 32 chars**, `p12_*` prefix; don't rename `p11t*`.
- **pytest-asyncio here ignores `loop_scope`** (old version) — the one-loop
  pattern in §1.6 is the workaround.

---

## 8. File & doc index

**Phase 12 docs (`docs/phase12/`):**
- `plans/00..08` — original spec. `WHATS_NEXT.md` — prioritized status.
- `designs/async_child_dispatch.md` — the mechanism (implemented).
- `designs/c4_replatforming_implementation_plan.md` — the C4 PR-by-PR plan +
  Progress section (Phase A done).
- `HANDOFF.md` — this file.

**Key code:**
- `backend/src/ai/core/feature_flags.py` — flags (`AI_FLAG_` env prefix).
- `backend/src/ai/core/agent_loop.py` — the loop (+ suspend/resume, step_results).
- `backend/src/ai/core/step_results.py` — per-step `result_data["steps"]` helpers.
- `backend/src/ai/core/execution_engine.py` — the legacy engine (`execute_run` is
  the C4 target; note `:97-104` and the caller inventory in §3).
- `backend/src/ai/core/executors/child_entity.py` — async dispatch + concurrency cap.
- `backend/src/ai/api/admin.py` — the de-prefixed admin router (`/api/v1/ai/admin/*`).
- `backend/src/ai/core/arq_jobs.py` + `worker.py` — dispatch, `resume_parent_run`,
  `CHILD_RUN_QUEUE`.
- `backend/tests/parity/` — the gate: `worker_sim.py` (in-process drainer),
  `test_async_child_parity.py` (G1 async helper), `c4_resumability.py` (G2/G3),
  `hermetic.py` (seeding + `child_fixtures`/`governance_overrides`), `extract.py`,
  `test_agent_loop_parity.py` (the one aggregated test).
- `backend/scripts/lint_ai_layout.py` — layout + canary (`error`) + narration lint.

**Memory notes** worth re-reading: `phase12-c4-phase-a-done`,
`phase12-stage1-decanary`, `phase12-c13-blocker`, the alembic 32-char limit, the
AgentLoop billing/planning notes.

---

## 9. Suggested first actions for the fresh session

1. Read this file, then `WHATS_NEXT.md`, then
   `designs/c4_replatforming_implementation_plan.md` (Progress + §3 + §5).
2. Run the two verify commands in §5; confirm green unit suite + 2 parity passed +
   lint exit 0.
3. Push the pending commits (or confirm the human did).
4. Pick up where it makes sense:
   - **If continuing C4:** confirm the **G4 soak** decision (run in prod, or
     dev-skip), then start Phase B at **PR-5 (extract `StepEngine`)** — a
     non-destructive, parity-guarded refactor. Hold before the irreversible PR-9.
   - **Else, independent Stage-1 trailing work:** **C12 mypy --strict** (mechanical),
     or pick a Track C/B/D item from §6.C.
   - **Do NOT** attempt C13 (blocked, §7) or the C4 deletion (PR-9) without the
     soak decision.
