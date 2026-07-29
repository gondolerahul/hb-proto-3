"""GLASS X3 — the scenario as background work.

Thin by design, so the tests are about the edges: an unknown scenario is
a clean answer rather than a traceback, a fault is logged with the
scenario named rather than lost in the worker, and an unreachable queue
is reported rather than raised.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.ai.twin import jobs


class FakeArq:
    def __init__(self, fail: bool = False):
        self.jobs: list[tuple] = []
        self.fail = fail
        self.connection_pool = object()

    async def enqueue_job(self, name, *args, **kwargs):
        if self.fail:
            raise RuntimeError("queue unreachable")
        self.jobs.append((name, args))


@pytest.mark.asyncio
async def test_no_redis_is_reported_not_raised():
    assert await jobs.enqueue_scenario_run(None, uuid.uuid4()) is False


@pytest.mark.asyncio
async def test_a_failing_queue_is_reported_not_raised():
    assert await jobs.enqueue_scenario_run(FakeArq(fail=True), uuid.uuid4()) is False


@pytest.mark.asyncio
async def test_an_unknown_scenario_answers_cleanly(monkeypatch):
    class FakeSession:
        async def get(self, model, key):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    import src.common.database as database

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: FakeSession())
    out = await jobs.twin_scenario_run({}, str(uuid.uuid4()))
    assert out["outcome"] == "not_found"


@pytest.mark.asyncio
async def test_a_fault_names_the_scenario_rather_than_killing_the_worker(
        monkeypatch):
    scenario_id = str(uuid.uuid4())

    class Boom:
        def __call__(self):
            raise RuntimeError("database gone")

    import src.common.database as database

    monkeypatch.setattr(database, "AsyncSessionLocal", Boom())
    out = await jobs.twin_scenario_run({}, scenario_id)
    assert out["outcome"] == "error"
    assert out["scenario_id"] == scenario_id


@pytest.mark.asyncio
async def test_a_run_reports_its_grade_and_outcome(monkeypatch):
    scenario = SimpleNamespace(id=uuid.uuid4(), company_id=uuid.uuid4())

    class FakeSession:
        async def get(self, model, key):
            return scenario

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    import src.common.database as database
    from src.ai.twin import runner

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: FakeSession())

    async def fake_run(db, sc, **kwargs):
        return SimpleNamespace(
            run=SimpleNamespace(id=uuid.uuid4(), grade="replay"), refused=False)

    monkeypatch.setattr(runner, "run_scenario", fake_run)
    out = await jobs.twin_scenario_run({}, str(scenario.id))
    assert out["outcome"] == "ran"
    assert out["grade"] == "replay"


def test_the_job_is_registered_with_the_worker():
    """A job the worker does not know about is a scenario that queues and
    never runs — and the failure looks exactly like a slow rehearsal."""
    import inspect

    from src.ai import worker

    source = inspect.getsource(worker)
    assert "twin_scenario_run" in source
