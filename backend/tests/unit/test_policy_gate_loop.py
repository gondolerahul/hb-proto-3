"""Inc 1 / GOV — PolicyGate wired into the AgentLoop (technical doc §20.3).

The exit-demo scene: an A1 entity about to make a payout is paused with a HITL
card BEFORE the executor runs. Plus the hard-BLOCK abort and the PASS no-op
that keeps uncategorised work (the parity suite) untouched. No DB/Redis/LLM —
reuses the in-memory loop harness pattern.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.ai.core.agent_loop import AgentLoop
from src.ai.core.executors.base import (
    EXECUTOR_REGISTRY,
    ActionResult,
    register_executor,
)
from src.ai.core.feature_flags import FeatureFlags
from src.ai.schemas.enums import RunStatus


def _entity(governance: dict, step_target: dict):
    eid, cid = uuid4(), uuid4()
    return SimpleNamespace(
        id=eid, company_id=cid, name="pay_agent", type="AGENT",
        goal="Handle payouts", description="fake", identity=None, hierarchy=None,
        logic_gate=None,
        planning={"static_plan": {"enabled": True, "steps": [{
            "step_id": "s1", "order": 1, "name": "pay", "type": "ACTION",
            "required": True, "target": step_target,
        }]}},
        capabilities=None, governance=governance, io_contract=None,
        observability=None, metadata_extensions=None,
    )


class _FakeRun:
    def __init__(self, entity, input_data=None):
        self.id = uuid4()
        self.entity_id = entity.id
        self.company_id = entity.company_id
        self.user_id = None
        self.status = RunStatus.PENDING.value
        self.input_data = input_data or {}
        self.dynamic_plan = None
        self.result_data = None
        self.context_state = None
        self.total_cost_usd = Decimal("0")
        self.total_tokens = 0
        self.error_message = None
        self.started_at = None
        self.completed_at = None
        self.entity = entity


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        if self._value is None:
            raise LookupError("no result")
        return self._value


class _FakeDB:
    def __init__(self, run):
        self.run = run
        self.added: list = []

    async def execute(self, *_a, **_k):
        return _FakeResult(self.run)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, _obj):
        return

    def add(self, obj):
        self.added.append(obj)


class _CountingExecutor:
    name = "SingleStep"

    def __init__(self):
        self.calls = 0

    async def execute(self, move, state, db):  # noqa: ARG002
        self.calls += 1
        return ActionResult(
            output="ran", cost_usd=Decimal("0.01"), latency_ms=10, success=True,
            completed_step_ids=[str(move.plan_fragment[0]["step_id"])]
            if move.plan_fragment else [],
        )


@pytest.fixture
def counting_executor():
    original = EXECUTOR_REGISTRY.get("SingleStep")
    fake = _CountingExecutor()
    register_executor(fake)
    try:
        yield fake
    finally:
        if original is not None:
            register_executor(original)


@pytest.mark.asyncio
async def test_a1_payout_pauses_with_hitl_card_before_executor(counting_executor):
    """Exit-demo: an A1 payout raises a HITL card and pauses — executor never runs."""
    entity = _entity(
        {"autonomy_level": "A1", "max_cost_usd": 1.0},
        {"action_category": "payout", "input_parameters": {"amount": 750}},
    )
    run = _FakeRun(entity)
    db = _FakeDB(run)
    loop = AgentLoop(db=db, redis=None, feature_flags=FeatureFlags(db=None))

    outcome = await loop.run(run.id)

    assert outcome["status"] == RunStatus.PAUSED.value
    assert counting_executor.calls == 0, "executor must not run when the gate pauses"
    approvals = [a for a in db.added if type(a).__name__ == "HumanApproval"]
    assert len(approvals) == 1
    assert approvals[0].checkpoint_key == "before_outbound_payout_above_band"
    assert approvals[0].status == "PENDING"


@pytest.mark.asyncio
async def test_hard_block_aborts_before_executor(counting_executor):
    """A payout above the hard-block ceiling aborts the run deterministically."""
    entity = _entity(
        {"autonomy_level": "A2", "authority": {"payout_usd": 500},
         "max_cost_usd": 1.0},
        {"action_category": "payout", "input_parameters": {"amount": 50000}},
    )
    run = _FakeRun(entity)
    db = _FakeDB(run)
    loop = AgentLoop(db=db, redis=None, feature_flags=FeatureFlags(db=None))

    outcome = await loop.run(run.id)

    assert outcome["status"] == RunStatus.FAILED.value
    assert counting_executor.calls == 0
    assert not [a for a in db.added if type(a).__name__ == "HumanApproval"]


@pytest.mark.asyncio
async def test_counterparty_trust_blocks_payout(counting_executor):
    """A run triggered by a counterparty-trust signal cannot drive a payout (§18.6)."""
    entity = _entity(
        {"autonomy_level": "A3", "max_cost_usd": 1.0},
        {"action_category": "payout", "input_parameters": {"amount": 100}},
    )
    run = _FakeRun(entity, input_data={"signal": {"trust": "counterparty"}})
    db = _FakeDB(run)
    loop = AgentLoop(db=db, redis=None, feature_flags=FeatureFlags(db=None))

    outcome = await loop.run(run.id)
    assert outcome["status"] == RunStatus.FAILED.value
    assert counting_executor.calls == 0


@pytest.mark.asyncio
async def test_generic_step_runs_to_completion(counting_executor):
    """PASS no-op: an uncategorised step at A1 runs normally — the gate does
    not touch the parity suite's ordinary work."""
    entity = _entity(
        {"autonomy_level": "A1", "max_cost_usd": 1.0},
        {"tool_id": "web_search", "input_parameters": {"q": "hello"}},
    )
    run = _FakeRun(entity)
    db = _FakeDB(run)
    loop = AgentLoop(db=db, redis=None, feature_flags=FeatureFlags(db=None))

    outcome = await loop.run(run.id)
    assert outcome["status"] in {RunStatus.COMPLETED.value,
                                 RunStatus.PARTIAL_COMPLETE.value}
    assert counting_executor.calls >= 1
    assert not [a for a in db.added if type(a).__name__ == "HumanApproval"]
