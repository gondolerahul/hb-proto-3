# Phase 12 — "What to Build Next" Checklist

> **Pairs with** [`HANDOFF.md`](./HANDOFF.md) (the entry point) and the eight
> [`plans/`](./plans/) files (the spec). This file sequences and prioritises the
> plan's own item IDs (C0–C13, S1–S7, V1–V6, K1–K7, P-*) by current state.
> **Last updated:** 2026-06-04 (Stage 1 COMPLETE — C4 Phase B + C2/C3/C13 landed)
> **Branch:** `phase12/stage1-consolidation`

Legend: ✅ done · ◐ partial · ❌ not started · 🚧 blocked by a hard gate

---

## 0. Current state in one paragraph

The repo is now the **GA shape** and **Stage 1 consolidation is COMPLETE.** On
top of the earlier cuts (`C0`–`C1`, `C3`-alias, `C5`–`C12`, `C10`/`C11`
de-prefix, lint→error), the keystone **`C4`** landed: the legacy
`ExecutionEngine.execute_run` plan-walker and `execution_engine.py` are deleted,
the **AgentLoop is the sole run engine**, and async suspend/resume is the only
child path (G4 soak dev-skipped by decision). Its fallout also landed: **`C2`**
(MemoryRouter retrieval body deleted, memory v2 unconditional), **`C3`-finish**
(engine MetaReviewer use gone), and **`C13`** (`engine_type` +
`RecursiveReasoningEngine` deleted; per-step reasoning routed via
`reasoning_hint`). All gates green. Remaining Phase-12 work is the new-capability
tracks: `02` (sandbox), `03` (video), `04` (CORTEX package), `06`'s v5
capabilities, `07` hardening — none started.

---

## 1. The critical path

- [x] **STAGE 0 — master switches ON** *(plan `05` §4, `08` Stage 0)* — done (dev
      mode; 30-day telemetry gate intentionally skipped). Parity gate wired + green.

- [x] **C4 — delete legacy `ExecutionEngine.execute_run`** *(`01` §4)* — **DONE.**
      Phase A evidence gate + the full Phase B deletion chain landed (G4 soak
      dev-skipped by decision, same policy as the Stage-0 telemetry gate). The
      AgentLoop is now the sole run engine. See
      [`designs/c4_replatforming_implementation_plan.md`](./designs/c4_replatforming_implementation_plan.md).
  - [x] **G1/G2/G3** parity + resumability chaos + cost guard (Phase A).
  - [x] **PR-5** extract `StepEngine`; **PR-6** async child dispatch is the loop's
        sole child path (+ parity candidate drainer-driven); **PR-7** re-platform
        `RecursiveExecutor` onto the planner; **PR-8** every entry point loop-only
        (arq dispatch, gateway dispatcher, `process_gateway_event`,
        `resume_execution`; dead `enqueue_job("execute_run")` repointed);
        **PR-9** delete `execute_run` + `execution_engine.py` + the child callback
        plumbing + the `agent_loop.enabled` switch.
  - `grep -rn 'execute_run\b' backend/src/ai` → comments/history only.

---

## 2. Stage 1 — consolidation (Track A)

### 2.1 Done
- [x] **C6 / P-F4** — REACT-AFC routes through `ToolResilience` (was already done).
- [~] **C8** — tools/ root-clean criterion satisfied; the `integrations/` wrapper +
      social audit remain deferred (low-value, high-churn).
- [x] **C9 (D-3)** — DebateExecutor + per-step `reasoning_hint`; retired
      REFLECTION/ToT (`d70912a`).
- [x] **C1** — v1 critic body + `v1_compat` flag deleted (`a10130e`).
- [x] **C3-partial** — `CortexRouter` alias removed (`7b946fb`). (The `MetaReviewer`
      half stays — `RealCriticPipeline` uses it — and is part of C4 fallout.)

### 2.2 De-prefix — DONE
- [x] **C10** — `ai/phase11_router.py` → `ai/api/admin.py` (`/api/v1/ai/admin/*`) +
      307 redirect shim in `main.py` (remove 2026-09-01); decision log →
      `docs/DECISIONS.md` (`7379d92`).
- [x] **C11** — 7 `P11*` component pairs + sub-components renamed;
      `types/phase11.ts`→`agentKernel.ts`; `Phase11KPI`→`KPIDashboard`; `p11-`→
      `agentk-` CSS; routes `/admin/agent-kernel/*` + redirect shim (`f9343b9`).
- [x] **Flip `CANARY_LABEL_MODE`→`error`** + neutralize remaining `ai/*.py` tokens
      (env prefix `AI_FLAG_`); raise `core/` cap to 1500; `test_layout_lint_passes`
      green (`98868d4`). Residual `phase11` = shims + migration names + `*.md` docs.

### 2.3 Quality lock-in (trailing)
- [x] **C12 — `mypy --strict` series** *(`01` §6.4, P-M1)* — **DONE: all six
      `ai/` packages strict-clean and gated** (`b17c803`, `996053b`, `4f60690`,
      `0c6aa5a`, `2c84a39`). `scripts/typecheck_ai.py` runs strict over the
      `CLEAN_PACKAGES` allowlist (now governance, orm, planning, meta, memory,
      core — **100 source files**) with `--follow-imports=silent`;
      `test_typecheck_passes` + the `run_ci_matrix.sh` fast lane gate it,
      `pyproject [tool.mypy]` sets the baseline. Per-package start counts: orm
      (migrated to `Mapped[]`), governance 32, planning 87, meta 74, memory 222
      (cortex_models.py also → `Mapped[]`), core 234. The **legacy-`Column` cost
      is GONE** — both `orm/` and `memory/cortex_models.py` are SQLAlchemy 2.0
      `Mapped[]` (DDL-identical, alembic-verified). **Convention:** new packages
      use real annotations + `cast()` for query-result/legacy reads;
      behaviour-preserving `# type: ignore` (not "fixes") on the C4-doomed legacy
      `ExecutionEngine` so parity goldens hold; lazily-built Optional services
      narrowed with `assert ... is not None` after their `_ensure`/`_compose`.
      **Latent bugs surfaced + fixed** along the way: `CriticCalibrator` missing
      `company_id`; meta `curator` anti-sprawl kwargs, `registry_search` missing
      `await` on async `db.get`, `platform_schema_compiler` wrong
      `IntegrationRegistry` columns; and a self-inflicted `child_entity`
      `UnboundLocalError` (inline `from uuid import UUID` shadowing) caught by the
      parity gate.
- [x] **C13 — drop deprecated `engine_type` & `reasoning_mode`** *(`01` §9, D-1)*
      — **DONE.** `engine_type`'s only consumer (`execute_run`'s RECURSIVE branch)
      died with C4; the orphaned `RecursiveReasoningEngine` was deleted (C13a).
      `step_executor` now reads per-step `PlanStep.reasoning_hint` (default REACT)
      instead of the entity-level `reasoning_config.reasoning_mode`; a PlanStep
      before-validator maps a legacy per-step `reasoning_mode` onto the hint
      (C13b). The ORM/`schemas/execution.py` run-telemetry `reasoning_mode` is
      retained.

### 2.4 Legacy deletions (fell out of C4 Phase B)
- [x] **C2** — deleted the `MemoryRouter` retrieval body (`retrieve` /
      `_load_episodic` / `format_for_prompt`) + the assembler v1 branch; v2 is now
      unconditional. `write_episodic` + `search_semantic` + `LegacyEpisodicReader`
      retained. (The loop reads CORTEX via the Perceiver with
      `memory_assembler=None`, so the legacy pipeline was fully dead.)
- [x] **C3 finish** — the engine `MetaReviewer` hook died with `execute_run`;
      `MetaReviewer` itself **stays** as `CriticPipeline.supervisor`'s
      `supervisor_v2_enabled=False` fallback (`critic_pipeline.py:489`).

---

## 3. Stage 2 — Tooling (Track C) — unblocks the marquee capability

`02` is a **hard dependency** of `06`'s tool synthesis.

- [x] **02 S1–S2 — `SandboxRuntime` Protocol + `SubprocessRuntime`** *(`02` §5)* —
      **DONE.** `tools/sandbox/runtime.py`: Protocol (exec/browser/file-ops/lifecycle)
      + `ExecResult`/`BrowserSession` DTOs + `SubprocessRuntime` (today's behavior)
      + `get_sandbox_runtime()` factory. The 3 tools delegate launch to it
      (zero behavior change; terminal/browser e2e green). Next: **S3** `hb-sandbox`
      image, **S4** `ContainerRuntime`/`TenantSandboxManager` (needs Docker + a
      security-review gate).
- [ ] **02 S3–S4 — `hb-sandbox` image + `ContainerRuntime`/`TenantSandboxManager`**
      *(`02` §3)* — needs a security review gate. *(XL)*
- [ ] **02 S5 — persistent browser sessions** *(L)*; **02 S6 — sandbox cost
      attribution** *(S)*.
- [ ] **03 V1–V5 — split `video_generation`** into `video_generate`/`video_edit`/
      `video_add_sound` *(`03` §4)*. *(L)*

---

## 4. Stage 2 — Meta-Agent v5 (Track B)

v4 board exists; all v5 capabilities unbuilt.

- [ ] **06 §3 — board GA on the AgentLoop + introspection tools** *(after C4)*. *(L)*
- [ ] **06 §5 — intelligence → planner wiring + rule lifecycle**. *(M)*
- [ ] **06 §4 — close the learning loop** (Curator-ON + composition graph). *(L)*
- [ ] **06 §6 — Meta-Agent self-modification** (prompt-evolution LLM diff + reseed). *(L)*
- [ ] 🚧 **06 §2 — TOOL SYNTHESIS (marquee)** — blocked by `02` S4. *(XL)*
- [ ] **06 §3.2 — LLM-Strategist pilot** (Meta-Agent only). *(M)*

---

## 5. Stage 3 — CORTEX extraction (Track D, parallel)

Phase 11 did Stage-A groundwork.

- [ ] **Stage A — Protocols in place** *(`04` §5)* — can start now. *(L)*
- [ ] 🚧 **Stage B — package skeleton + cutover** — gated on **C2** (MemoryRouter
      delete), i.e. on C4. *(XL)*
- [ ] **Stage C — docs/coverage/CI → publish `cortex-memory` v0.1.0**. *(L)*
- [ ] Lock decisions K1–K7 (`04` §4). *(S)*

---

## 6. Stage 4 — Hardening / KPI / DX (Track E, trailing)

- [ ] **07 §5 — A/B / eval harness** (`tests/eval/`) — seeds exist
      (`tests/parity/`, `tests/regression/`); build the replay-corpus + delta
      report. *(M)*
- [ ] **07 §1 — MCP tool adapter** *(L)*; **07 §2 — budget-aware REACT** *(S)*;
      **07 §3 — provenance trust-score learning** *(M)*.
- [ ] **P-O1** Grafana/Metabase panel JSON *(M)*; **07 §6 smalls** (CSAT,
      INTERNAL_KEYS doc-test, seed hygiene, SSE-narrative check) *(S each)*.
- [ ] **P-O3** frontend Storybook / Lighthouse / Playwright *(M)*.

---

## 7. Recommended ordering from here

1. **Decide the C4 G4 soak** (run in prod, or dev-skip). It gates the highest-value
   remaining deletion + unblocks C2 and CORTEX Stage B.
2. While that's pending, do independent low-risk work: **C12 mypy --strict**
   (mechanical), or **`04` Stage A** (non-breaking Protocols), or **`02` S1–S2**
   (the sandbox refactor that unblocks tool synthesis).
3. After the soak: **C4 Phase B** (PR-5..PR-9) → **C2/C3 fallout** → **CORTEX
   Stage B**.
4. **06 board GA + tool synthesis** (the marquee, after `02` S4).

---

## 8. Quick status table

| Plan | Item | Status |
|------|------|:------:|
| 05 | Stage 0 master-switch flip (dev mode) | ✅ |
| 01 | C0 narration sweep + lint→error | ✅ |
| 01 | C1 critic v1 body deletion | ✅ |
| 01 | C3 CortexRouter alias removal | ✅ |
| 01 | C5 reconcile-v2 + static-as-prior (D-2) | ✅ |
| 01 | C6/P-F4 REACT ToolResilience | ✅ |
| 01 | C7 cost attribution + flag ON | ✅ |
| 01 | C8 tools/ root clean (integrations/ wrapper deferred) | ◐ |
| 01 | C9 DebateExecutor + retire REFLECTION/ToT (D-3) | ✅ |
| 01 | C10 backend de-prefix (`ai/api/admin`) | ✅ |
| 01 | C11 frontend de-prefix | ✅ |
| 01 | canary lint → error (de-canary) | ✅ |
| 01 | C4 Phase A evidence gate (G1/G2/G3) | ✅ |
| 01 | C4 Phase B (delete execute_run) — G4 soak dev-skipped | ✅ |
| 01 | C2 MemoryRouter retrieval delete + v2 unconditional | ✅ |
| 01 | C3 finish (engine MetaReviewer use gone) | ✅ |
| 01 | C12 mypy --strict (all 6 ai/ packages clean + gated) | ✅ |
| 01 | C13 drop deprecated engine_type/reasoning_mode | ✅ |
| 02 | Sandbox runtime / container / browser | ❌ |
| 03 | Video tool split | ❌ |
| 04 | CORTEX package extraction | ❌ (A-groundwork ✅) |
| 06 | v4 board exists | ✅ |
| 06 | tool synthesis · introspection · composition graph · curator · prompt-evolution | ❌ |
| 07 | cost-attribution gate | ✅ |
| 07 | MCP adapter · trust-score learning · eval harness | ❌ |
| 07 | budget-aware REACT | ◐ |
