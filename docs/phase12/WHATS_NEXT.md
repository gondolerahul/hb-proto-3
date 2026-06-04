# Phase 12 — "What to Build Next" Checklist

> **Pairs with** [`HANDOFF.md`](./HANDOFF.md) (the entry point) and the eight
> [`plans/`](./plans/) files (the spec). This file sequences and prioritises the
> plan's own item IDs (C0–C13, S1–S7, V1–V6, K1–K7, P-*) by current state.
> **Last updated:** 2026-06-03 (Stage 1 de-canary + C4 Phase A landed)
> **Branch:** `phase12/stage1-consolidation`

Legend: ✅ done · ◐ partial · ❌ not started · 🚧 blocked by a hard gate

---

## 0. Current state in one paragraph

The repo is now the **GA shape**, not the canary build: Stage 0 is flipped, and
**Stage 1 consolidation is nearly complete** — `C0`-narration, `C1` (v1 critic
delete), `C3` (alias), `C5` reconcile-v2, `C6`, `C7` cost attribution, `C8`
(root-clean), `C9` (DebateExecutor + retire REFLECTION/ToT), **`C10`+`C11`
de-prefix**, and the **layout/canary lint flipped to `error` (green)** have all
landed. The big remaining deletion, **`C4` (delete legacy `execute_run`), has its
evidence gate (Phase A) green** — multi-child PROCESS parity (inline + async
suspend/resume), resumability chaos, and a cost guard — but the irreversible
deletion (Phase B) is **gated on a flag soak (G4)** that needs a live canary.
`C12` (mypy --strict) is not started; `C13` is blocked. Tracks `02` (sandbox),
`03` (video), `04` (CORTEX package), and `06`'s v5 capabilities are not started.

---

## 1. The critical path

- [x] **STAGE 0 — master switches ON** *(plan `05` §4, `08` Stage 0)* — done (dev
      mode; 30-day telemetry gate intentionally skipped). Parity gate wired + green.

- [~] **C4 — delete legacy `ExecutionEngine.execute_run`** *(`01` §4)* — **Phase A
      (the evidence gate) is DONE; Phase B (deletion) is gated.** `execute_run` is
      load-bearing (loop delegates into it; children ran via the `execute_run_fn`
      callback). The unblocking mechanism (async suspend/resume child dispatch) is
      built and **now proven end-to-end**. See
      [`designs/c4_replatforming_implementation_plan.md`](./designs/c4_replatforming_implementation_plan.md).
  - [x] **G1** multi-child PROCESS parity — inline (PR-1) + async, first E2E (PR-2).
  - [x] **G2** resumability chaos (crash → durable WAITING → recover → idempotent) (PR-3).
  - [x] **G3** cost amplification guard (async child work == inline) (PR-3).
  - [x] PR-1b — loop emits `result_data["steps"]` (fixed a real refine regression).
  - [ ] **G4 flag soak (PR-4)** — operational; needs a live canary. **Gates Phase B.**
  - [ ] **Phase B (PR-5..PR-9)** — extract `StepEngine` → drop child callback →
        re-platform `RecursiveExecutor` → loop-only entry points (incl. the
        gateway dispatcher + `process_gateway_event` that bypass the flag) →
        delete `execute_run` (**irreversible**). Then **C2**/**C3** fall out.

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
- [ ] 🚧 **C13 — drop deprecated `engine_type` & `reasoning_mode`** *(`01` §9, D-1)*
      — **blocked, not a clean cut.** `engine_type` isn't a typed field (only
      consumer is the C4-blocked `execute_run`); `reasoning_mode` is still live in
      `step_executor` (REACT vs CHAIN_OF_THOUGHT off the raw dict). A clean drop
      needs per-step reasoning routed via the Strategist's `reasoning_hint` first.
      Keep the ORM/`schemas/execution.py` `reasoning_mode` (telemetry).

### 2.4 Legacy deletions (fall out of C4 Phase B)
- [ ] 🚧 **C2** — delete `MemoryRouter` body — unblocks once `execute_run` is
      deleted (all engine MemoryRouter uses are inside `execute_run`).
- [ ] 🚧 **C3 finish** — drop the engine `MetaReviewer` use after C4; `MetaReviewer`
      itself **stays** (`critic_pipeline.py:490`).

---

## 3. Stage 2 — Tooling (Track C) — unblocks the marquee capability

`02` is a **hard dependency** of `06`'s tool synthesis.

- [ ] **02 S1–S2 — `SandboxRuntime` Protocol + `SubprocessRuntime`** *(`02` §5)*. *(M)*
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
| 01 | C4 Phase B (delete execute_run) — gated on G4 soak | 🚧 |
| 01 | C2 MemoryRouter delete — C4 fallout | 🚧 |
| 01 | C3 finish (engine MetaReviewer) — C4 fallout | 🚧 |
| 01 | C12 mypy --strict (all 6 ai/ packages clean + gated) | ✅ |
| 01 | C13 drop deprecated engine_type/reasoning_mode | 🚧 blocked |
| 02 | Sandbox runtime / container / browser | ❌ |
| 03 | Video tool split | ❌ |
| 04 | CORTEX package extraction | ❌ (A-groundwork ✅) |
| 06 | v4 board exists | ✅ |
| 06 | tool synthesis · introspection · composition graph · curator · prompt-evolution | ❌ |
| 07 | cost-attribution gate | ✅ |
| 07 | MCP adapter · trust-score learning · eval harness | ❌ |
| 07 | budget-aware REACT | ◐ |
