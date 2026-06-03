# backend/tests/parity/

Parity = "the new agent loop produces functionally-equivalent output
to the legacy one." Tracks 2-8 each promise this property under a
per-Track cost tolerance (see `14_test_strategy.md §4.3`).

## How a parity test will look (Track 2)

```python
from tests.parity.harness import ParityCase, run_parity_case

async def test_simple_skill_parity_track2(db, redis):
    case = ParityCase(
        case_id="simple_skill_track2",
        fixture_name="simple_skill",
        input_data={"topic": "post-quantum cryptography"},
        track=2,
    )
    report = await run_parity_case(
        db, redis, case,
        golden_path="backend/tests/parity/goldens/simple_skill.json",
    )
    assert report.passed, report.summary()
```

## Required wiring (Track 2 owns this)

```python
# conftest.py for parity tests
from tests.parity.harness import register_engine_adapter

class LegacyAdapter:
    async def run(self, db, redis, run_id):
        from src.ai.core.execution_engine import ExecutionEngine
        await ExecutionEngine(db, redis).execute_run(run_id)

class CandidateAdapter:
    async def run(self, db, redis, run_id):
        from src.ai.core.agent_loop import AgentLoop      # Track 2 deliverable
        await AgentLoop(db, redis).run(run_id)

register_engine_adapter("legacy", LegacyAdapter())
register_engine_adapter("candidate", CandidateAdapter())
```

The harness intentionally STOPs at `_seed_run` until Track 2 hooks up
the real run-creation path so parity tests can't silently pass on a
half-wired engine.

## Goldens

`backend/tests/parity/goldens/` (created at first record) stores one
JSON snapshot per fixture + input combo, produced by
`backend/scripts/record_golden_runs.py`. Goldens are checked into the
repo so CI doesn't need a live LLM budget — only the candidate engine
actually executes per PR.
