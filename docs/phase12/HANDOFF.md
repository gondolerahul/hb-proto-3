# Phase 12 — Implementation Handoff

> **Read this first.** It is the single entry point for continuing Phase 12 in a
> fresh session. It captures the current state, the non-obvious findings that
> change the plan, how to verify, and the exact remaining sequence. Pair it with
> [`WHATS_NEXT.md`](./WHATS_NEXT.md) (the prioritized checklist) and the eight
> [`plans/`](./plans/) files (the original spec).
>
> **Author:** prior implementation session · **Date:** 2026-06-03
> **Branch:** `phase12/stage1-consolidation`

---

## 0. TL;DR — where things stand

- Phase 12 plans live in `docs/phase12/plans/` (8 files, `00`–`08`). They are a
  **plan**, mostly not yet built. The audit + progress is in `WHATS_NEXT.md`.
- The repo is the **Phase 11 canary build** + a partial slice of Phase 12.
- **Done this far** (committed on the branch): Stage 0 switch-flip, a hermetic
  **parity gate**, **C1** (v1 critic delete), **C9** (retire REFLECTION/ToT),
  the **async-child-dispatch** mechanism (flag-gated), and the **C4 blocker
  design**. **C6** was found already-done.
- **The headline finding:** **C4 (delete legacy `execute_run`) is NOT a deletion
  — it's a multi-PR re-platforming.** The AgentLoop is built *on top of*
  `ExecutionEngine`. See §3. This blocks C2/C3/C4 and is the single most
  important thing a fresh agent must understand before touching the "legacy
  deletion" cuts.
- **Nothing is in production.** Stage 0's 30-day telemetry gate was deliberately
  skipped (dev build). The two master switches default ON.

---

## 1. CRITICAL CONTEXT — read before writing any code

These are the non-obvious facts that will cost you hours if you miss them.

1. **The whole agent kernel was uncommitted at session start.** Phase 11's code
   (agent_loop, executors, planning, memory, meta, …) landed as one big commit
   `21ea5f4`. If something looks "new/untracked," it is expected.

2. **C4 is blocked by a documented, reverted attempt.** The AgentLoop delegates
   step execution into `ExecutionEngine` internals, and **every child entity
   runs via the `execute_run` callback**. Routing children through the loop was
   tried in Phase 11 and **reverted** (~$11/child cost amplification + worker
   blocking). The evidence is verbatim in `backend/src/ai/core/execution_engine.py:97-104`.
   **Do not try to "just delete `execute_run`."** See §3.

3. **The two master switches default ON in dev** (`agent_loop.enabled`,
   `meta_agent.board_routing`) — `backend/src/ai/core/feature_flags.py`. The
   30-day telemetry gate the plans require is intentionally skipped because
   nothing ships to prod. If you ever target prod, that gate is back in force.

4. **There is a real parity gate, but it's hermetic and thin.** `tests/parity/`
   runs legacy `ExecutionEngine` vs the new `AgentLoop` with a **deterministic
   mock LLM + stubbed tools** (no API keys — there are none in this env). It has
   one *strong* positive case (`simple_skill`); the multi-child PROCESS case
   *fails identically on both engines* (weak). **Before any C4/C2/C3 deletion,
   strengthen this with a multi-child PROCESS case that completes.** See
   `backend/tests/parity/README.md`.

5. **No LLM API keys, but DB + Redis are live** in this environment
   (Postgres `localhost:5433`, Redis `localhost:6379`). That's why the parity
   gate and any execution test must be hermetic (mock LLM). Don't assume a key.

6. **`mypy --strict` (C12) is NOT set up; the layout lint has one known-failing
   test.** `tests/unit/test_layout.py::test_layout_lint_passes` fails on HEAD —
   this is **pre-existing de-canary debt** (the `phase11_router.py` filename +
   the `as CortexService` alias). It goes green only after C10 (de-prefix) and
   the `CortexRouter` alias removal. Treat that one failure as expected until
   then; everything else is green.

---

## 2. What's DONE (committed on the branch)

Commits ahead of `origin/phase12/stage1-consolidation` (oldest → newest):

| Commit | What |
|--------|------|
| `1dd336a` | **Stage 0** — flip `agent_loop.enabled` + `meta_agent.board_routing` ON (dev mode; telemetry gate skipped). Tests updated. |
| `3051651` | **Parity gate** — hermetic legacy-vs-AgentLoop harness + recorded goldens (`tests/parity/`). The `loop ≈ legacy` evidence tool. |
| `d70912a` | **C9** — retire `REFLECTION` + `TREE_OF_THOUGHTS` reasoning modules (D-3). Registry now REACT + CHAIN_OF_THOUGHT only. |
| `a10130e` | **C1** — delete v1 critic body (`_review_step_output`) + retire dead `critic_pipeline.v1_compat`. |
| `bcf2911` | **C4 design** — `designs/async_child_dispatch.md` + recorded the C4 blocker in `WHATS_NEXT.md`. |
| `deaabba` | **Async child dispatch** — suspend/resume implementation behind `governance.async_child_dispatch` (default OFF). 11 unit tests. |

Also verified **already-done** (no commit needed): **C6** (REACT routes through
`ToolResilience` in `step_executor.py`), **C7** (cost attribution + flag ON),
**C5** (`reconcile`→v2 + static-plan-as-prior), **C8** root-layout criterion.

**Push status:** these 6 commits are **local only** — the environment has no
GitHub credentials. The human pushes from their own machine:
```bash
git push origin phase12/stage1-consolidation
```

---

## 3. The C4 blocker, in full (the thing not to re-derive)

Plan `01` §4 assumes deleting `execute_run` is safe once the loop is the default.
**It is not, in this codebase.** Three couplings:

1. **arq dispatch** routes non-loop companies to `execute_run` (removable).
2. **Loop executors delegate into engine internals:**
   `single_step`→`_execute_step_wrapper`, `dag`→`_execute_steps_dag`,
   `child_entity`→`_execute_step_wrapper`, `recursive`→`execute_run`.
3. **Child entities execute via the `execute_run_fn` callback**
   (`execution_engine.py:79,93` → `step_executor.py`), and routing them through
   the loop was tried + reverted (cost amplification / worker blocking).

**The unblock path (designed + partly built):**
[`designs/async_child_dispatch.md`](./designs/async_child_dispatch.md) — a
suspend/resume mechanism so children run as isolated jobs instead of inline.
**It is now implemented behind `governance.async_child_dispatch` (default OFF).**

**The remaining deletion chain (do strictly in order):**
```
1. Strengthen parity: a multi-child PROCESS case that COMPLETES (record golden).
2. Resumability chaos test: kill worker mid-WAITING_ON_CHILDREN → new worker resumes.
3. Flip governance.async_child_dispatch ON (canary), soak, cost-regression guard green.
4. Drop the execute_run_fn child callback (execution_engine.py:79,93).
5. Extract StepEngine (step methods) out of ExecutionEngine; loop executors use it.
6. Re-platform RecursiveExecutor off execute_run.
7. Make arq dispatch loop-only (remove the legacy branch).
8. Delete execute_run (+ subclass).  ← this is the real "C4"
9. C2 falls out: delete MemoryRouter (its only remaining caller was execute_run).
10. C3: MetaReviewer STAYS (RealCriticPipeline uses it, critic_pipeline.py:490);
    only the CortexRouter alias (cortex_service.py:1199) is safe to remove.
```

> Steps 1–3 are the gate. **Do not do 4–8 until the parity multi-child case is
> green and the flag has soaked.** This is irreversible and was reverted once.

---

## 4. What's the async-child-dispatch mechanism (so you don't re-learn it)

Implemented in `deaabba`, behind `governance.async_child_dispatch` (OFF):

- **Status:** `WAITING_ON_CHILDREN` (`schemas/enums.py`).
- **Marker:** `ActionResult.awaiting_children` (`core/executors/base.py`).
- **State:** `AgentState.awaiting_children` (snapshotted) + transient
  `suspend_requested` (`core/agent_state.py`).
- **Trigger:** `ChildEntityExecutor._dispatch_async` creates the child run
  (`StepExecutorService.create_child_run`), enqueues `run_execution_recursive`,
  returns the marker (`core/executors/child_entity.py`).
- **Loop:** `_iteration` detects the marker → `suspend_requested`; `_loop`
  breaks; `_drive` (shared run/resume tail) persists `_persist_suspended` +
  returns. `resume()` rehydrates from the snapshot, `_fold_children` folds
  terminal children, continues. `_maybe_resume_parent` nudges the parent on a
  child's finalize (`core/agent_loop.py`).
- **Job:** `resume_parent_run` (`core/arq_jobs.py`, registered in `worker.py`).
  Idempotent — no-op unless the parent is `WAITING_ON_CHILDREN`.
- **Tests:** `tests/unit/test_async_child_dispatch.py` (11; units only).
- **NOT YET VALIDATED end-to-end** (needs a live arq worker + multi-child
  fixture). That is the §3 step-1/2 gate.

---

## 5. How to verify (commands that actually work here)

```bash
cd backend
# Python is in the venv (no system `python`):
PY=.venv/bin/python

# Full unit suite (fast, hermetic). Expect: 1 failed (layout lint, pre-existing).
$PY -m pytest tests/unit -o addopts="" -q -p no:warnings

# The parity gate (needs DB+Redis; skips cleanly if absent). Expect: 2 passed.
$PY -m pytest tests/parity -o addopts="" -q -p no:warnings

# Re-record parity goldens (hermetic auto-on with no LLM key):
$PY -m scripts.record_golden_runs --output tests/parity/goldens

# The layout/canary lint (currently exits 1 — known pre-existing debt):
$PY scripts/lint_ai_layout.py
```

Notes:
- Always pass `-o addopts=""` — the repo's default addopts can interfere.
- `-p no:warnings` just trims deprecation noise.
- The DB has live data; parity seeds throwaway `parity-*` tenants and does **not**
  clean them up (FK chains). Use a disposable Postgres if that matters.

---

## 6. The remaining roadmap (prioritized)

Pull the full per-item detail from `WHATS_NEXT.md`. The high-value order:

### A. Finish the safe, unblocked Stage 1 cuts (no re-platforming needed)
- **C10 — backend de-prefix:** `ai/phase11_router.py` → `ai/api/admin.py`
  (`/api/v1/ai/admin/*`) + a redirect shim for one release. *(M)*
- **C11 — frontend de-prefix:** rename the **14 `P11*` components** +
  `types/phase11.ts` → `types/agentKernel.ts`; update `router/index.tsx`,
  `MainLayout.tsx`, `meta.service.ts`, `kpi.service.ts`; route shim. *(M)*
- **C3-partial — remove the `CortexRouter` alias** (`cortex_service.py:1199`;
  pure rename shim; update the 2 importers). *(S)*
- **After C10 + alias removal:** flip `CANARY_LABEL_MODE` → `error` in
  `scripts/lint_ai_layout.py`; the layout-lint test goes green. *(S)*
- **C13 — drop deprecated `engine_type` / `reasoning_mode` fields** (schema minor
  bump; depends on C5 + C9, both done). *(M)*
- **C12 — `mypy --strict`** per package (`core/ planning/ memory/ meta/
  governance/`) as a CI gate. *(M, mechanical)*

### B. The C4 chain (large; §3) — only when ready
Strengthen parity → chaos test → flip async flag → re-platform → delete
`execute_run` → C2 → C3 MetaReviewer-in-engine removal.

### C. The rest of Phase 12 (each its own track; see plans)
- **`02`** Sandbox runtime / per-tenant containers (0% — XL).
- **`03`** Video tool split (0%).
- **`04`** CORTEX pip package extraction (0%; P11 did Stage-A groundwork).
- **`06`** Meta-Agent v5 capabilities (v4 board exists; tool synthesis,
  introspection tools, composition graph, prompt-evolution LLM, etc. = 0%).
  Note: tool synthesis (`06` §2) hard-depends on `02`.
- **`07`** MCP adapter, budget-aware REACT, trust-score learning, eval harness.

---

## 7. Landmines / gotchas (specific, learned the hard way)

- **Don't delete `MemoryRouter`, `MetaReviewer`, or `execute_run` yet** — all are
  load-bearing via the legacy engine the loop still uses (§3).
- **`MetaReviewer` is not a shim to delete** — `RealCriticPipeline` (the loop's
  own critic) uses it (`critic_pipeline.py:490`). Plan `01` §4 is wrong on this.
- **The narration lint is `error` mode** (`COMMENT_NARRATION_MODE`). Comments
  matching `#\s*Phase\s+\d+`, `# Fix X:`, `# RACE-N`, etc. **fail the lint.** When
  you add comments, avoid those patterns (write invariant comments instead). This
  bit the Stage 0 commit.
- **Alembic revision ids ≤ 32 chars** (memory note). New migrations use a `p12_*`
  prefix; don't rename applied `p11t*` migrations.
- **pytest-asyncio here ignores `loop_scope`** (old version — see the "Unknown
  config option" warnings). Parametrized async tests each get their own event
  loop, and the global `AsyncSessionLocal` engine binds to the first loop →
  "attached to a different loop." The parity test iterates cases in **one**
  test/loop on purpose. Keep that pattern for anything that drives the engine.
- **The kernel opens its own `AsyncSessionLocal` sessions internally** (final
  persist, child runs). You cannot wrap engine runs in a rolled-back savepoint
  for test isolation — they commit. Seed throwaway tenants instead.
- **Frontend de-prefix needs route/redirect shims** (`/admin/phase11/*` →
  `/admin/agent-kernel/*`) for one release so bookmarks don't 404.

---

## 8. File & doc index

**Phase 12 docs (`docs/phase12/`):**
- `plans/00..08` — the original spec (read order: 00 → 05 → 01 → 06 → 02/03/04 → 07 → 08).
- `WHATS_NEXT.md` — prioritized, checkbox status of every cut/item.
- `designs/async_child_dispatch.md` — the C4-unblocking mechanism (implemented).
- `HANDOFF.md` — this file.

**Key code:**
- `backend/src/ai/core/feature_flags.py` — flag defaults (master switches ON).
- `backend/src/ai/core/agent_loop.py` — the loop (+ suspend/resume).
- `backend/src/ai/core/execution_engine.py` — the legacy engine (still the
  step-execution substrate; see the note at lines 97-104).
- `backend/src/ai/core/executors/` — loop executors (delegate into the engine).
- `backend/src/ai/step_executor.py` — step + child-run execution.
- `backend/src/ai/core/arq_jobs.py` + `worker.py` — job dispatch + registration.
- `backend/tests/parity/` — the legacy-vs-loop gate (+ `README.md`).
- `backend/scripts/lint_ai_layout.py` — layout + canary-label + narration lint.
- `backend/scripts/record_golden_runs.py` — parity golden recorder (hermetic).

**Memory notes (`~/.claude/.../memory/`)** worth re-reading: the Phase 12 plan
index, the alembic 32-char limit, the AgentLoop billing/planning notes, and the
C9 DebateExecutor note.

---

## 9. Suggested first actions for the fresh session

1. Read this file, then `WHATS_NEXT.md`, then skim `plans/01` and `plans/08`.
2. Run the two verify commands in §5; confirm you see the expected green +
   the single known layout-lint failure.
3. Push the 6 pending commits (or confirm the human did).
4. Pick the next cut from §6.A (recommended start: **C10 + CortexRouter alias +
   flip the canary lint to error** — this finally makes the layout-lint go green
   and is the visible "de-canary" win, no re-platforming risk).
5. For anything touching the legacy engine / child execution, re-read §3 first.
