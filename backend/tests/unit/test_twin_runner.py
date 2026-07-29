"""GLASS X2 — the assembly, driven without an LLM or a database.

TWIN's honest limit was that the pieces were tested and the assembly was
not. These test the assembly: the order of the gates, that refusals are
rows rather than exceptions, that the loop executes **inside** the
binding, and that a leaked external effect is a failed run rather than a
tidy result.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.ai.twin import runner as rn
from src.ai.twin.binding import in_twin
from src.ai.twin.grading import Grade

COMPANY = uuid.uuid4()


class FakeDB:
    """Enough session for the runner: it adds rows and commits."""

    def __init__(self, signals=None):
        self.added: list = []
        self.commits = 0
        self._signals = signals or {}

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        for row in self.added:
            if getattr(row, "id", None) is None:
                row.id = uuid.uuid4()

    async def get(self, model, key):
        return self._signals.get(key)


def _scenario(**overrides):
    base = dict(
        id=uuid.uuid4(), company_id=COMPANY,
        scope={"objects": [], "window_days": 7}, levers={})
    base.update(overrides)
    return SimpleNamespace(**base)


def _patch_common(monkeypatch, *, available="100", admitted=True,
                  replay_result=None, estimate_usd=0.5):
    """Everything the runner reaches for, faked at its own module edge."""
    from src.ai.twin import cost as cost_module

    async def fake_estimate(company_id, scope, **kw):
        return SimpleNamespace(usd=estimate_usd, rows=10, signals=10,
                               method="declared")

    async def fake_admit(db, company_id, projected_usd):
        return SimpleNamespace(
            admitted=admitted,
            reason="within budget" if admitted else "past the daily budget")

    monkeypatch.setattr(cost_module, "estimate", fake_estimate)
    monkeypatch.setattr(cost_module, "admit", fake_admit)

    import src.ai.loop.wallet_holds as holds

    async def fake_available(db, company_id):
        from decimal import Decimal
        return Decimal(available)

    async def fake_place_hold(db, company_id, run_id, entity_type, est=None):
        return SimpleNamespace(run_id=run_id)

    async def fake_settle(db, run_id, actual):
        return None

    monkeypatch.setattr(holds, "available_for_spend", fake_available)
    monkeypatch.setattr(holds, "place_hold", fake_place_hold)
    monkeypatch.setattr(holds, "settle_hold", fake_settle)

    async def fake_materialise(company_id, scope):
        return SimpleNamespace(entity_defs=1, records=2, links=0)

    monkeypatch.setattr(rn, "materialise", fake_materialise)

    from src.ai.tools.base import ToolRegistry

    monkeypatch.setattr(
        ToolRegistry, "get_tools_for_company",
        classmethod(lambda cls, cid: {}))

    if replay_result is not None:
        async def fake_replay(db, company_id, scope, *, handler, limit=500):
            return replay_result
        monkeypatch.setattr(rn, "replay", fake_replay)


def _result(**overrides):
    base = dict(signals_replayed=3, simulated_calls=5, external_effects=0,
                by_category={"email_dispatch": 5}, truncated=False)
    base.update(overrides)
    return SimpleNamespace(**base)


# ── refusals are rows, not exceptions ────────────────────────────────────────

@pytest.mark.asyncio
async def test_over_the_daily_cap_is_a_refused_run_row(monkeypatch):
    _patch_common(monkeypatch, admitted=False, replay_result=_result())
    outcome = await rn.run_scenario(FakeDB(), _scenario())
    assert outcome.refused is True
    assert "daily budget" in outcome.run.refusal_reason
    assert outcome.run.grade == Grade.UNKNOWN
    assert outcome.run.cost_usd == 0.0


@pytest.mark.asyncio
async def test_an_unaffordable_scenario_refuses_before_spending(monkeypatch):
    _patch_common(monkeypatch, available="0.01", estimate_usd=5.0,
                  replay_result=_result())
    outcome = await rn.run_scenario(FakeDB(), _scenario())
    assert outcome.refused is True
    assert "Nothing was spent." in outcome.run.refusal_reason


@pytest.mark.asyncio
async def test_a_refused_scope_is_a_row_too(monkeypatch):
    _patch_common(monkeypatch, replay_result=_result())
    outcome = await rn.run_scenario(
        FakeDB(), _scenario(scope={"objects": [], "window_days": 9999}))
    assert outcome.refused is True
    assert "window" in outcome.run.refusal_reason


# ── the happy path writes a real, computed run ───────────────────────────────

@pytest.mark.asyncio
async def test_a_replay_writes_a_graded_run_with_its_counts(monkeypatch):
    _patch_common(monkeypatch, replay_result=_result())
    outcome = await rn.run_scenario(FakeDB(), _scenario())
    assert outcome.refused is False
    assert outcome.run.grade == Grade.REPLAY
    assert outcome.run.metrics["signals_replayed"] == 3
    assert outcome.run.metrics["simulated_calls"] == 5
    assert outcome.run.metrics["external_effects"] == 0
    assert "substituted" in outcome.run.method


@pytest.mark.asyncio
async def test_nothing_to_replay_grades_unknown_not_replay(monkeypatch):
    _patch_common(monkeypatch, replay_result=_result(signals_replayed=0))
    outcome = await rn.run_scenario(FakeDB(), _scenario())
    assert outcome.run.grade == Grade.UNKNOWN


@pytest.mark.asyncio
async def test_an_unobserved_lever_disqualifies_the_grade(monkeypatch):
    """Replaying real history through a change nothing in that history
    reflects tells you about the history, not about the change."""
    _patch_common(monkeypatch, replay_result=_result())
    outcome = await rn.run_scenario(
        FakeDB(), _scenario(levers={"unobserved": True}))
    assert outcome.run.grade == Grade.UNKNOWN


# ── the leak assertion ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_leaked_external_effect_fails_the_run_loudly(monkeypatch):
    _patch_common(monkeypatch, replay_result=_result(external_effects=1))
    outcome = await rn.run_scenario(FakeDB(), _scenario())
    assert outcome.refused is True
    assert outcome.run.refusal_reason == rn.SIMULATION_LEAKED


# ── the handler executes inside the binding ──────────────────────────────────

@pytest.mark.asyncio
async def test_the_loop_executes_inside_the_binding(monkeypatch):
    """The whole point of the assembly: the shipped loop must run with the
    substitution active. Asserted from inside the injected executor."""
    seen: list[bool] = []
    signal_id = uuid.uuid4()
    signal = SimpleNamespace(id=signal_id, type="email.inbound")

    _patch_common(monkeypatch)

    async def fake_replay(db, company_id, scope, *, handler, limit=500):
        await handler(signal_id)
        return _result(signals_replayed=1)

    monkeypatch.setattr(rn, "replay", fake_replay)

    import src.ai.signals.triggers as triggers

    async def fake_owner(db, company_id, signal_type):
        return SimpleNamespace(process_entity_id=uuid.uuid4())

    monkeypatch.setattr(triggers, "resolve_owner", fake_owner)

    async def fake_spawn(db, company_id, sig, entity_id):
        return SimpleNamespace(id=uuid.uuid4(), total_cost_usd=0.02)

    monkeypatch.setattr(rn, "_spawn_twin_run", fake_spawn)

    async def executor(db, redis, run_id):
        seen.append(in_twin())

    outcome = await rn.run_scenario(
        FakeDB(signals={signal_id: signal}), _scenario(), execute=executor)

    assert seen == [True]           # the loop ran inside the Glasshouse
    assert in_twin() is False       # and the binding did not leak out
    assert outcome.run.cost_usd == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_a_signal_with_no_owning_trigger_is_skipped_not_run(monkeypatch):
    """Parked in life, skipped in rehearsal — a signal nothing subscribes
    to must not invent an owner just because it is being rehearsed."""
    executed: list[uuid.UUID] = []
    signal_id = uuid.uuid4()
    _patch_common(monkeypatch)

    async def fake_replay(db, company_id, scope, *, handler, limit=500):
        await handler(signal_id)
        return _result(signals_replayed=0)

    monkeypatch.setattr(rn, "replay", fake_replay)

    import src.ai.signals.triggers as triggers

    async def no_owner(db, company_id, signal_type):
        return None

    monkeypatch.setattr(triggers, "resolve_owner", no_owner)

    async def executor(db, redis, run_id):
        executed.append(run_id)

    signal = SimpleNamespace(id=signal_id, type="unowned.event")
    await rn.run_scenario(
        FakeDB(signals={signal_id: signal}), _scenario(), execute=executor)
    assert executed == []
