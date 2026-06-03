# Phase 12 — "What to Build Next" Checklist

> **Derived from:** a code audit of `backend/src/ai/`, `frontend/src/`,
> `backend/migrations/`, and `backend/tests/` against the eight plan files in
> [`plans/`](./plans/).
> **Audit date:** 2026-06-03 · **Branch audited:** `phase12/stage1-consolidation`
> **Plan IDs** (C0–C13, S1–S7, V1–V6, K1–K7, P-*) are the plan's own; this file
> only **sequences and prioritises** them by current implementation state.

Legend: ✅ done · ◐ partial · ❌ not started · 🔒 blocked by a hard gate

---

## 0. Current state in one paragraph

The repo is the **Phase 11 canary build** plus a **partial slice of Phase 12
Stage 1**. Already landed: `C0`-narration, `C5` reconcile-v2, `C7` cost
attribution, `C8` tools subgrouping (partial), `C9` DebateExecutor + reasoning
hints. **Stage 0 has not run** — both master switches are still `OFF`
(`agent_loop.enabled`, `meta_agent.board_routing`), which **blocks every legacy
deletion** (`C1`–`C4`) and the CORTEX cutover. Files `02` (sandbox runtime),
`03` (video split), `04` (CORTEX package), and all of `06`'s v5 capabilities are
**not started**.

---

## 1. The critical path (do these in order)

These are gating: nothing downstream can complete until each is done.

- [x] **STAGE 0 — flip the master switches** *(plan `05` §4, `08` Stage 0)*
      **DONE (dev mode).** Pre-production build: the 30-day canary-telemetry
      gate is **intentionally skipped** (nothing ships to prod).
  - [x] `agent_loop.enabled` default flipped **ON** (`core/feature_flags.py`).
  - [x] `meta_agent.board_routing` default flipped **ON** (both alias + canonical).
  - [x] Feature-flag unit tests updated to the new defaults; suite green.
  - [ ] *(follow-up)* Verify `meta_cognition_migration` ran in all tenants (`06` §1).
  - [x] **Parity gate wired + green** — `tests/parity/` now runs the legacy
        `ExecutionEngine` vs the new `AgentLoop` hermetically (deterministic
        mock LLM + stubbed tools, no API keys). Goldens recorded for 3 cases;
        `pytest tests/parity` passes. This is the `loop ≈ legacy` evidence
        required before the C4 deletion. See `backend/tests/parity/README.md`.
  - **Note:** because telemetry is skipped, the gated legacy deletions (C1–C4)
        are now unblocked by policy — and the parity gate is green, so C4 has
        its evidence. Strengthen with more positive PROCESS cases before C4.

- [ ] **🔒 C4 — delete legacy `ExecutionEngine.execute_run` monolith** *(keystone,
      `01` §4)* — `core/execution_engine.py` is still ~1288 LoC. **Gated on
      Stage 0's 30-day clock + green parity corpus.** Highest-risk single PR.

---

## 2. Stage 1 — finish consolidation (Track A)

Ordered by *value now / lowest risk first*. Items 2.1–2.3 are **not gated** and
can start immediately; 2.4 is gated on Stage 0.

### 2.1 Not gated — do now
- [ ] **C6 / P-F4 — REACT-AFC adopts `ToolResilience.run`** *(`01` §6.2)*
      `core/reasoning/react.py` still calls `execute_tool_fn` directly; route the
      inner `_execute_thought` closure through `ToolResilience` so REACT heals
      tool failures like direct TOOL_CALL. *(M)*
- [ ] **C8 finish — tools/ layout to spec + social audit** *(`01` §5)*
      Subgroups exist but plan's `integrations/{social,ads}/` wrapper, `ads/`,
      and `management/` are missing; `social/` sits at top level. Move them, then
      **tag the 17 social tools ACTIVE / EXPERIMENTAL / DEAD** and gate/delete
      accordingly. Refresh subdomain READMEs. Flip lint rule
      "no loose tool files at `tools/` root." *(M)*
- [ ] **Finish C9 cleanup (D-3)** *(`01` §8.3)* — DebateExecutor + `reasoning_hint`
      shipped, but `core/reasoning/reflection.py` and `tree_of_thoughts.py`
      **still exist**; remove the retired per-entity Reflection/ToT modules now
      that the strategist routes around them (the `p12_retire_reasoning_modes`
      data migration is already present). *(S)*

### 2.2 De-prefix (do after C1–C7 land; ship with redirect shims)
- [ ] **C10 — backend de-prefix** *(`01` §2, §7)*
      `ai/phase11_router.py` → `ai/api/admin.py` (`/api/v1/ai/admin/*`); keep an
      alias/redirect shim for one release with a removal date. *(M)*
- [ ] **C11 — frontend de-prefix** *(`01` §7)*
      Rename all **14 `P11*` components** + `types/phase11.ts` →
      `types/agentKernel.ts`; update `router/index.tsx`, `MainLayout.tsx`,
      `meta.service.ts`, `kpi.service.ts`. Keep `/admin/phase11/*` redirect for
      one release. Verify `services/events.ts` reducer is exhaustive (P-O4). *(M)*
- [ ] **Flip `CANARY_LABEL_MODE` warn → error** in `lint_ai_layout.py` once
      `grep -rn 'p11|P11|phase11' backend/src frontend/src` is empty *(`01` §3)*. *(S)*

### 2.3 Quality lock-in (trailing, low risk)
- [ ] **C12 — `mypy --strict` series** *(`01` §6.4, P-M1)* — one PR per package
      (`core/ → planning/ → memory/ → meta/ → governance/`); add as required CI
      check. *(M)*
- [ ] **C13 — drop deprecated `engine_type` & `reasoning_mode` fields** *(`01` §9,
      D-1)* — minor-version schema bump; depends on C5 + C9. *(M)*

### 2.4 🔒 Gated legacy deletions (after Stage 0's 30-day clock)
- [ ] **C1** delete critic v1 `_review_step_output` body + retire `critic_pipeline.v1_compat`.
- [ ] **C2** delete `MemoryRouter` body; assembler v2-only (**keep** `LegacyEpisodicReader`).
- [ ] **C3** delete `MetaReviewer` shim + `CortexRouter` alias.
- [ ] Prune retired keys from `feature_flags.py::DEFAULTS` (flag count down ~6).

---

## 3. Stage 2 — Tooling (Track C) — unblocks the marquee capability

`02` is a **hard dependency** of `06`'s tool synthesis, so prioritise it.

- [ ] **02 S1–S2 — `SandboxRuntime` Protocol + `SubprocessRuntime`** *(`02` §5)*
      New `ai/sandbox/` package; refactor the 3 tools (`sandbox_executor`,
      `terminal_tool`, `browser_tool`) into thin front-ends; zero behaviour
      change; stays the dev/CI/rollback default. **None of this exists yet.** *(M)*
- [ ] **02 S3–S4 — `hb-sandbox` image + `ContainerRuntime` / `TenantSandboxManager`**
      *(`02` §3)* — persistent per-tenant container, `/workspace` volume,
      non-root + cap-drop + default-deny-net, quotas, reaper TTLs. Flag
      `sandbox.container_runtime_enabled` (OFF). **Needs a security review gate.** *(XL)*
- [ ] **02 S5 — persistent browser sessions** (container Chromium + CDP) *(`02` §3.3)*. *(L)*
- [ ] **02 S6 — sandbox cost attribution** → add `SANDBOX` to `CostAttribution`
      enum (`services/cost_attribution.py`) and meter per-call. *(S)*
- [ ] **03 V1–V5 — split `video_generation`** *(`03` §4)* — currently one
      ~590-LoC mega-tool. Create `tools/media/video/` + `_ffmpeg.py`; produce
      `video_generate` / `video_edit` / `video_add_sound`; keep a deprecated
      `video_generation` shim for one release; route ffmpeg through `02`. *(L)*

---

## 4. Stage 2 — Meta-Agent v5 (Track B)

The v4 board exists (`meta/board/` 7 roles, intelligence tree, skill library);
**all v5 capabilities are unbuilt.** Order by leverage.

- [ ] **06 §3 — board GA on the AgentLoop + introspection tools** *(after C4)* —
      re-platform board roles as executor/strategist moves; **build the two
      missing tools** `tools/meta/agent_introspect.py` + `agent_reflect.py`. *(L)*
- [ ] **06 §5 — intelligence → planner wiring + rule lifecycle** — confirm
      IntelligenceTree rules reach the planner prompt post-reconcile-v2; enforce
      `candidate → confirmed → retired` lifecycle (only `confirmed` enter prompts).
      Evaluate `task_classifier.v2_enabled` A/B (P-F7). *(M)*
- [ ] **06 §4 — close the learning loop**
  - [ ] Turn `meta_agent.curator_consolidation_enabled` **ON** (P-F8); wire merge
        proposals (HITL + audit).
  - [ ] **Build the cross-entity composition graph** (`composed_with`,
        `outcome_score` CORTEX edges) — currently **absent**. *(L)*
- [ ] **06 §6 — Meta-Agent self-modification**
  - [ ] Build the prompt-evolution **LLM critic-of-critic diff** (P-F2; cron
        plumbing exists, diff is stubbed).
  - [ ] Wire `reseed_meta_agent.py` (P-F1; the script exists at
        `backend/scripts/migrations/` — needs UI + content review). *(L)*
- [ ] **🔒 06 §2 — TOOL SYNTHESIS (marquee feature)** — **blocked by `02` S4.**
      Build `ToolSpec` schema, `meta/board/tool_smith.py`, `tools/meta/tool_synthesis.py`,
      `ToolValidator` (AST + LLM red-team), DRAFT/trust gating, kill switch
      `meta_agent.tool_synthesis_enabled` (OFF). Container-only exec; HITL
      promotion; Meta-Agent-only. **Nothing exists yet.** *(XL)*
- [ ] **06 §3.2 — LLM-Strategist pilot** behind `agent_loop.llm_strategist_enabled`,
      Meta-Agent only. *(M)*

---

## 5. Stage 3 — CORTEX extraction (Track D, parallel)

Not started; Phase 11 already did "Stage-A-worth" of decoupling (domains/,
scope_policy, Provenance, `resolve_embedding_model`, nullable entity FK).

- [ ] **Stage A — Protocols in place** *(`04` §5)* — add `LLMProvider`/
      `EmbeddingProvider`/`UsageReporter`/`RunRegistry` Protocols; make
      `cortex_bridge` implement them. No host break. *Can start now.* *(L)*
- [ ] **🔒 Stage B — package skeleton + move code + 1-day cutover** — **gated on
      `01` §4 (C2 MemoryRouter deletion)** so the package isn't built around dead
      v1 code. *(XL)*
- [ ] **Stage C — docs/examples/≥85% coverage/CI → publish `cortex-memory` v0.1.0
      (Apache-2.0) on PyPI**; host pins the version. *(L)*
- [ ] Lock decisions K1–K7 (`04` §4) and update `CORTEX_Implementation_Plan.md`
      §3/§4/§6/§19. *(S)*

---

## 6. Stage 4 — Hardening / KPI / DX (Track E, trailing)

- [ ] **07 §5 — real A/B / eval harness** (`tests/eval/`) — seeds exist
      (`tests/parity/`, `tests/regression/`); build the replay-corpus + delta
      report. Also de-risks the C4 deletion. *(M)*
- [ ] **07 §1 — MCP tool adapter** (`MCPToolAdapter`, read-only, per-company
      allow-list, `MCP` cost attribution) — **not present.** *(L)*
- [ ] **07 §2 — budget-aware REACT** — thread `Budget.pressure>0.7` into the
      Strategist/REACT prompt as a soft constraint (field + plumbing already
      exist; prompt-threading does not). *(S)*
- [ ] **07 §3 — provenance trust-score learning** (in-tenant; `trust_score` field
      exists, learning loop does not). *(M)*
- [ ] **P-O1** Grafana/Metabase panel JSON (SQL already shipped). *(M)*
- [ ] **07 §6 smalls** — CSAT capture (P-O2), resumability CI test,
      `INTERNAL_KEYS.md` doc-enforcement test, seed-hygiene verification,
      SSE-narrative streaming check, embedding single-source-of-truth unit test. *(S each)*
- [ ] **P-O3** frontend Storybook / Lighthouse CI / Playwright nightly. *(M)*

---

## 7. Recommended ordering (the 6-week minimal path, from `08` §5)

1. **Stage 0** — flip switches, start telemetry clock, stand up parity corpus. *(§1)*
2. **C6, C8-finish, C9-cleanup** + (after clock) **C1–C3** — pay down canary debt. *(§2)*
3. **06 board GA + intelligence→planner + Curator-ON** — compounding lift, mostly flip+wire. *(§4)*
4. **02 S1–S4 + 06 tool-synthesis canary** — the one true new capability, safely sandboxed. *(§3, §4)*

`03` (video split) and `04` (CORTEX extraction) are valuable but independently
schedulable — defer to the back half without blocking the above.

---

## 8. Quick status table (audit snapshot)

| Plan | Item | Status |
|------|------|:------:|
| 01 | C0 narration sweep + lint→error | ✅ |
| 01 | C5 reconcile-v2 + static-as-prior (D-2) | ✅ |
| 01 | C7 cost attribution + flag ON (P-F3/F6) | ✅ |
| 01 | C9 DebateExecutor + reasoning_hint (D-3) | ✅ |
| 01 | C8 tools/ subgrouping | ◐ |
| 01 | C6/P-F4 REACT ToolResilience closure | ❌ |
| 01 | C10/C11 backend+frontend de-prefix | ❌ |
| 01 | C12 mypy --strict · C13 drop deprecated fields | ❌ |
| 01 | C1–C4 legacy deletions | 🔒 (Stage 0) |
| 05 | Stage 0 master-switch flip (dev mode, telemetry skipped) | ✅ |
| 02 | Sandbox runtime / container / browser | ❌ |
| 03 | Video tool split | ❌ |
| 04 | CORTEX package extraction | ❌ (A-groundwork ✅) |
| 06 | v4 board exists | ✅ |
| 06 | tool synthesis · introspection tools · composition graph · curator-ON · prompt-evolution LLM | ❌ |
| 07 | cost-attribution gate | ✅ |
| 07 | MCP adapter · trust-score learning · eval harness | ❌ |
| 07 | budget-aware REACT | ◐ |
