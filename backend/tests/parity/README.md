# backend/tests/parity/

Parity = "the new `AgentLoop` produces functionally-equivalent output to
the legacy `ExecutionEngine`." This is the evidence gate that must be
**green before the C4 legacy-deletion** (plan `docs/phase12/plans/01` §4;
risk R1 in `08`): once the legacy engine is deleted there is no fallback,
so we prove equivalence first.

## The gate is hermetic (no API keys, no network)

Both engines run under deterministic patches so the gate is reproducible
in CI and on a dev box with **no LLM keys**:

* `hermetic.py::DeterministicAdapter` replaces `LLMRouter._resolve_adapter`,
  so every `call_llm` / `call_llm_react` returns canned, fixed-token
  responses while the real tracing / usage / cost code still runs.
* the network-bound `web_search` tool is stubbed with a fixed result.

Because the LLM is held constant, any parity violation is attributable to
the **engine** (planning / orchestration / critics) — exactly what gates
C4. Wall-clock time is disabled in the comparison
(`ParityTolerance.hermetic`) because mock timing is infra-noise; status,
cost band, step-count delta and output cosine are enforced.

## Running the gate

```bash
cd backend
# 1. record goldens from the LEGACY engine (hermetic auto-on with no key)
.venv/bin/python -m scripts.record_golden_runs --output tests/parity/goldens
# 2. run the gate (candidate AgentLoop vs goldens)
.venv/bin/python -m pytest tests/parity -o addopts="" -q
```

The gate **skips cleanly** when there are no goldens, or when Postgres /
Redis are unreachable (see the `db` / `redis_client` fixtures in
`conftest.py`). With a real LLM key present, pass `--no-hermetic` to the
recorder to record from live provider runs instead.

## How it fits together

| Piece | Role |
|-------|------|
| `hermetic.py` | `DeterministicAdapter`, `hermetic_llm_and_tools()` context, `seed_parity_run()` (shared by recorder + tests) |
| `extract.py` | builds a `RunResult` from a finished `ExecutionRun`; engine-fair `execution_time_ms` (timestamp fallback) and step-count |
| `harness.py` | `run_parity_case()` — seed → run candidate → extract → `compare_run_results` |
| `conftest.py` | engine adapters + DB/Redis fixtures + autouse hermetic patches |
| `test_agent_loop_parity.py` | the gate: every golden vs a fresh AgentLoop run, aggregated in one event loop |
| `goldens/*.json` | checked-in legacy snapshots (one per regression case) |

> All cases run inside a **single event loop** on purpose: the kernel's
> global `AsyncSessionLocal` engine binds to the loop it is first used on
> and asyncpg connections cannot cross loops, so one-test-per-loop
> parametrisation trips "attached to a different loop." The test iterates
> internally and aggregates per-case results instead.

## Current cases

Recorded from `tests/regression/cases/*.yaml`:

* `simple_skill_topic_easy` — the strong positive case: both engines
  COMPLETE with matching cost/steps/output.
* `research_agent_brief` — AGENT; both COMPLETE.
* `research_process_pipeline` — multi-child PROCESS; under the mock both
  engines fail **identically** (a valid agreement signal, but a weaker
  case — extend with richer child-entity fixtures for a positive check).

## Known limitations / TODO

* Seeded rows are throwaway (`parity-*` tenants) but are **not** torn down
  (the run spawns cortex nodes/trees with FK chains). Use a disposable
  test Postgres, or add a cascading cleanup fixture.
* Add more positive cases (esp. a PROCESS that completes under the mock).
