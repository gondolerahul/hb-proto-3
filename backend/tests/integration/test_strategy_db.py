"""Inc 6 / STRAT — the pipeline against a real tenant schema. ``needs_db``.

Four claims that need a database:

1. **The eight objects seed**, carry the `strategy` domain, and every ref
   resolves to a real def in the tenant's own schema.
2. **The write policy is load-bearing at its only caller.** A guarantee nothing
   routes through is not a guarantee (SEGA's B11 lesson), so the refusals are
   asserted through `RecordService`, and the mutation test uninstalls the
   policy and shows the illegal write then succeeds.
3. **The review sweep finds due mandates** through the schema-translate map —
   which is why it is ORM rather than `text()`.
4. **Predicted-vs-realized reads LEARN's history** and says `not_measurable`
   with a populated `missing` when it cannot, never zero.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.strategy.governance import (
    install_strategy_write_policy,
    strategy_write_policy,
)
from src.ai.strategy.pipeline import PLANNING_OBJECTS
from src.ai.strategy.realized import Verdict, compute_realized
from src.ai.strategy.review_sweep import due_mandates, sweep_company
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
from src.ai.tenant_schema.record_service import (
    PROPOSED,
    REFUSED,
    WRITTEN,
    RecordService,
)

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

TODAY = date(2026, 7, 26)


def _db_url():
    import os

    from src.common.config import settings
    return getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")


@pytest_asyncio.fixture
async def strat_company():
    """A provisioned tenant with the write policy installed, dropped after."""
    if not _db_url():
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine
    from src.ai.tenant_schema.write_policy import set_write_policy

    await engine.dispose()
    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"strat-test-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    install_strategy_write_policy()
    try:
        yield cid
    finally:
        set_write_policy(None)
        async with engine.begin() as conn:
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM signals WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM kpi_snapshots WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


class TestSpineSeeding:
    async def test_the_eight_planning_objects_are_seeded(self, strat_company):
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            for name in sorted(PLANNING_OBJECTS):
                assert await svc._require_def(name) is not None, name

    async def test_they_carry_the_strategy_domain_and_planning_module(
            self, strat_company):
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            for name in sorted(PLANNING_OBJECTS):
                d = await svc._require_def(name)
                assert d.domain_tag == "strategy", name
                assert d.module == "Planning", name

    async def test_the_spine_is_35_defs_in_a_real_tenant(self, strat_company):
        from src.common.database import AsyncSessionLocal

        async with tenant_data_plane.session(strat_company) as ts:
            count = (await ts.execute(text(
                f'SELECT COUNT(*) FROM "{schema_name_for(strat_company)}".'
                "tenant_entity_defs"))).scalar()
        assert count == 35


class TestWritePolicyAtItsCaller:
    """A guarantee nothing routes through is not a guarantee."""

    async def test_an_illegal_transition_is_refused_through_the_service(
            self, strat_company):
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            created = await svc.create(
                "Proposition", {"title": "try discounting", "status": "draft"})
            assert created.status == WRITTEN
            await ts.commit()

            result = await svc.update(
                created.record.id, {"status": "adopted"},
                expected_version=created.record.version)

        assert result.status == REFUSED
        assert "tabled" in result.reason

    async def test_the_legal_route_succeeds(self, strat_company):
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            created = await svc.create("Proposition", {"title": "p", "status": "draft"})
            await ts.commit()

            tabled = await svc.update(created.record.id, {"status": "tabled"},
                                      expected_version=created.record.version)
            assert tabled.status == WRITTEN
            await ts.commit()

            adopted = await svc.update(created.record.id, {"status": "adopted"},
                                       expected_version=tabled.record.version)
        assert adopted.status == WRITTEN

    async def test_a_grade_with_no_run_is_refused_at_create(self, strat_company):
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            result = await svc.create(
                "Proposition", {"title": "flattering", "honesty_grade": "replay"})
        assert result.status == REFUSED
        assert "twin_run_id" in result.reason

    async def test_a_grade_with_a_run_is_written(self, strat_company):
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            result = await svc.create("Proposition", {
                "title": "honest", "honesty_grade": "replay",
                "twin_run_id": str(uuid.uuid4())})
        assert result.status == WRITTEN

    async def test_an_agent_write_proposes_before_the_policy_is_reached(
            self, strat_company):
        """04a §7.1: the Planning owner process has no seeded agent, so the
        ownership gate turns every agent write into a proposal — the policy is
        the *second* line of defence, not the first."""
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            result = await svc.create(
                "Resolution",
                {"title": "r", "decision": "d", "adopted_on": "2026-07-26",
                 "status": "active"},
                actor_process_code="P08")
        assert result.status == PROPOSED

    async def test_a_non_planning_object_is_untouched_by_the_policy(
            self, strat_company):
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            result = await svc.create("Account", {"name": f"acme-{uuid.uuid4().hex[:6]}"})
        assert result.status == WRITTEN

    async def test_mutation_uninstalling_the_policy_lets_the_illegal_write_through(
            self, strat_company):
        """The mutation test. If this passes with the policy removed, the
        refusals above are asserting the test's own arrangement rather than a
        shipped control."""
        from src.ai.tenant_schema.write_policy import set_write_policy

        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            created = await svc.create("Proposition", {"title": "p", "status": "draft"})
            await ts.commit()

            set_write_policy(None)
            try:
                loose = await svc.update(
                    created.record.id, {"status": "adopted"},
                    expected_version=created.record.version)
            finally:
                set_write_policy(strategy_write_policy)

        assert loose.status == WRITTEN, (
            "draft→adopted succeeded only because the policy was removed — "
            "so the refusal test above is testing the shipped control")


class TestReviewSweep:
    async def _mandate(self, svc, *, review_due, status="issued", title="chase"):
        # `Mandate.resolution` is required, which is the sheet working: a
        # mandate that names no resolution cannot answer "why does this process
        # exist?", and that backward walk is half the point of the loop.
        resolution = await svc.create("Resolution", {
            "title": f"r-{title}", "decision": "do the thing",
            "adopted_on": "2026-07-01", "status": "active"})
        assert resolution.status == WRITTEN, resolution.reason
        result = await svc.create("Mandate", {
            "title": title, "review_due": review_due, "status": status,
            "resolution": str(resolution.record.id)})
        assert result.status == WRITTEN, result.reason
        return result.record

    async def test_a_due_mandate_is_found(self, strat_company):
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            await self._mandate(svc, review_due=TODAY.isoformat())
            await ts.commit()
            due = await due_mandates(ts, strat_company, today=TODAY)
        assert len(due) == 1
        assert due[0]["title"] == "chase"

    async def test_an_overdue_mandate_is_still_found(self, strat_company):
        """"On or before", not "on" — a sweep matching only today's date would
        drop every mandate whose date fell on a day the worker was down."""
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            await self._mandate(
                svc, review_due=(TODAY - timedelta(days=30)).isoformat())
            await ts.commit()
            due = await due_mandates(ts, strat_company, today=TODAY)
        assert len(due) == 1

    async def test_a_future_mandate_is_not(self, strat_company):
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            await self._mandate(
                svc, review_due=(TODAY + timedelta(days=30)).isoformat())
            await ts.commit()
            due = await due_mandates(ts, strat_company, today=TODAY)
        assert due == []

    async def test_closed_and_reviewed_mandates_are_left_alone(self, strat_company):
        """Chasing either is the kind of noise that teaches people to ignore
        the tray."""
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            for status in ("closed", "reviewed"):
                await self._mandate(svc, review_due=TODAY.isoformat(),
                                    status=status, title=status)
            await ts.commit()
            due = await due_mandates(ts, strat_company, today=TODAY)
        assert due == []

    async def test_the_sweep_emits_review_due_once_per_day(self, strat_company):
        from src.common.database import AsyncSessionLocal

        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            await self._mandate(svc, review_due=TODAY.isoformat())
            await ts.commit()

        first = await sweep_company(strat_company, today=TODAY)
        second = await sweep_company(strat_company, today=TODAY)

        async with AsyncSessionLocal() as cp:
            count = (await cp.execute(text(
                "SELECT COUNT(*) FROM signals WHERE company_id = :c "
                "AND type = 'strategy.review_due'"),
                {"c": str(strat_company)})).scalar()

        assert first["emitted"] == 1
        assert count == 1, f"the second sweep duplicated: {second}"

    async def test_the_sweep_writes_no_review(self, strat_company):
        """It *asks* for a Review. A review the platform filled in by itself is
        a review nobody read."""
        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            await self._mandate(svc, review_due=TODAY.isoformat())
            await ts.commit()

        await sweep_company(strat_company, today=TODAY)

        async with tenant_data_plane.session(strat_company) as ts:
            svc = RecordService(ts, strat_company)
            assert await svc.list_records("Review") == []


class TestRealized:
    async def _snapshot(self, cp, company_id, *, kpi_key, on, value, measurable=True,
                        missing=None):
        await cp.execute(text("""
            INSERT INTO kpi_snapshots
                (id, company_id, kpi_key, captured_on, value, measurable, missing,
                 sample_size, window_days, unit, created_at)
            VALUES (:id, :c, :k, :d, :v, :m, CAST(:miss AS jsonb), 1, 30, 'count', now())
        """), {"id": str(uuid.uuid4()), "c": str(company_id), "k": kpi_key,
               "d": on, "v": value, "m": measurable,
               "miss": __import__("json").dumps(missing or [])})

    async def test_a_met_target_reads_met(self, strat_company):
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as cp:
            await self._snapshot(cp, strat_company, kpi_key="gross_margin",
                                 on=TODAY, value=42)
            await cp.commit()

            result = await compute_realized(
                cp, strat_company,
                {"review_due": TODAY.isoformat()},
                target={"kpi_key": "gross_margin", "direction": "increase",
                        "target_value": 40},
                today=TODAY)

        assert result.verdict == Verdict.MET
        assert result.realized_value == 42.0
        assert result.measurable is True

    async def test_a_decrease_kpi_is_read_in_its_own_direction(self, strat_company):
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as cp:
            await self._snapshot(cp, strat_company,
                                 kpi_key="days_sales_outstanding", on=TODAY, value=30)
            await cp.commit()
            result = await compute_realized(
                cp, strat_company, {"review_due": TODAY.isoformat()},
                target={"kpi_key": "days_sales_outstanding", "direction": "decrease",
                        "target_value": 35},
                today=TODAY)
        assert result.verdict == Verdict.MET

    async def test_a_forecast_beats_the_target_as_the_prediction(self, strat_company):
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as cp:
            await self._snapshot(cp, strat_company, kpi_key="gross_margin",
                                 on=TODAY, value=38)
            await cp.commit()
            result = await compute_realized(
                cp, strat_company, {"review_due": TODAY.isoformat()},
                target={"kpi_key": "gross_margin", "direction": "increase",
                        "target_value": 40},
                forecast={"value": 36},
                today=TODAY)
        # Missed the ask (40) but beat what was actually expected (36).
        assert result.predicted_from == "forecast"
        assert result.predicted_value == 36.0
        assert result.verdict == Verdict.MET

    async def test_no_snapshot_is_not_measurable_never_zero(self, strat_company):
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as cp:
            result = await compute_realized(
                cp, strat_company, {"review_due": TODAY.isoformat()},
                target={"kpi_key": "gross_margin", "direction": "increase",
                        "target_value": 40},
                today=TODAY)

        assert result.verdict == Verdict.NOT_MEASURABLE
        assert result.realized_value is None
        assert result.measurable is False
        assert result.missing, "a missing reading must say why"
        assert "not backfilled" in " ".join(result.missing)

    async def test_a_recorded_absence_reports_its_own_reason(self, strat_company):
        """LEARN stores unmeasurable KPIs as rows rather than skipping them, so
        "we looked and could not measure" and "we never looked" stay different
        facts. This is the first one."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as cp:
            await self._snapshot(cp, strat_company, kpi_key="gross_margin",
                                 on=TODAY, value=None, measurable=False,
                                 missing=["no Invoice.total in the window"])
            await cp.commit()
            result = await compute_realized(
                cp, strat_company, {"review_due": TODAY.isoformat()},
                target={"kpi_key": "gross_margin", "direction": "increase",
                        "target_value": 40},
                today=TODAY)

        assert result.verdict == Verdict.NOT_MEASURABLE
        assert "no Invoice.total in the window" in result.missing

    async def test_a_mandate_with_no_target_says_so(self, strat_company):
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as cp:
            result = await compute_realized(
                cp, strat_company, {"review_due": TODAY.isoformat()}, target=None,
                today=TODAY)
        assert result.verdict == Verdict.NOT_MEASURABLE
        assert "names no Target" in " ".join(result.missing)

    async def test_the_grade_travels_with_the_verdict(self, strat_company):
        """"This bet was graded `forecast` when it was made" is what separates
        an honest track record from a flattering one."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as cp:
            await self._snapshot(cp, strat_company, kpi_key="gross_margin",
                                 on=TODAY, value=10)
            await cp.commit()
            result = await compute_realized(
                cp, strat_company, {"review_due": TODAY.isoformat()},
                target={"kpi_key": "gross_margin", "direction": "increase",
                        "target_value": 40},
                proposition={"honesty_grade": "replay", "twin_run_id": "abc"},
                today=TODAY)

        assert result.verdict == Verdict.MISSED
        assert result.honesty_grade == "replay"
        assert result.twin_run_id == "abc"

    async def test_an_open_window_reports_on_track_not_met(self, strat_company):
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as cp:
            await self._snapshot(cp, strat_company, kpi_key="gross_margin",
                                 on=TODAY, value=50)
            await cp.commit()
            result = await compute_realized(
                cp, strat_company,
                {"review_due": (TODAY + timedelta(days=30)).isoformat()},
                target={"kpi_key": "gross_margin", "direction": "increase",
                        "target_value": 40},
                today=TODAY)
        assert result.verdict == Verdict.ON_TRACK


class TestTwinLink:
    async def test_a_grade_is_read_from_the_run_and_scoped_by_company(
            self, strat_company):
        """Borrowing another tenant's run id would attach their evidence to
        your decision."""
        from src.ai.strategy.twin_link import read_grade, stamp_fields
        from src.common.database import AsyncSessionLocal

        run_id = uuid.uuid4()
        async with AsyncSessionLocal() as cp:
            await cp.execute(text("""
                INSERT INTO twin_runs (id, company_id, grade, method, metrics,
                                       cost_usd, is_baseline, started_at)
                VALUES (:id, :c, 'replay', 'replayed 63 signals',
                        CAST('{}' AS jsonb), 0, false, now())
            """), {"id": str(run_id), "c": str(strat_company)})
            await cp.commit()

            mine = await read_grade(cp, strat_company, run_id)
            theirs = await read_grade(cp, uuid.uuid4(), run_id)
            fields = await stamp_fields(cp, strat_company, run_id)

            await cp.execute(text("DELETE FROM twin_runs WHERE id = :i"),
                             {"i": str(run_id)})
            await cp.commit()

        assert mine.honesty_grade == "replay"
        assert mine.method == "replayed 63 signals"
        assert theirs.honesty_grade == "untested"
        assert fields == {"honesty_grade": "replay", "twin_run_id": str(run_id)}

    async def test_an_unknown_run_yields_untested_and_stamps_nothing(
            self, strat_company):
        """`{}` rather than `{"honesty_grade": "untested"}`, so a failed lookup
        never overwrites a grade the proposition legitimately carries."""
        from src.ai.strategy.twin_link import stamp_fields
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as cp:
            assert await stamp_fields(cp, strat_company, uuid.uuid4()) == {}
            assert await stamp_fields(cp, strat_company, "not-a-uuid") == {}
