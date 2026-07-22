"""The C6 KPI registry and its honest-absence rule (Inc-3 PRAGYA T5).

The property these defend is one sentence: **a KPI whose prerequisites are
unmet must report what is missing, never a number.** Zero is a measurement;
absence is the lack of one, and an owner who cannot tell them apart will
eventually act on a figure that was never real.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.ai.kpi.compute import KpiResult, compute_one
from src.ai.kpi.definitions import (
    KPI_DEFINITIONS,
    Cadence,
    definition_for,
    kpi_keys,
)

NOW = datetime(2026, 7, 22, 12, 0, 0)
ALL_OBJECTS = {"Opportunity", "Invoice", "Payment", "Quote", "Lead", "Ticket",
               "Bill", "Ledger Entry"}


async def _compute(key: str, records, defined=None, pending=0):
    definition = definition_for(key)
    assert definition is not None
    return await compute_one(
        definition, records=records, pending_approvals=pending,
        defined=defined if defined is not None else ALL_OBJECTS, now=NOW,
    )


# --- the registry is well-formed ---------------------------------------------

def test_every_definition_is_complete() -> None:
    for d in KPI_DEFINITIONS:
        assert d.key and d.display_name and d.formula.strip()
        assert d.baseline.strip(), f"{d.key} has no baseline to compare against"
        assert d.why_it_matters.strip(), f"{d.key} does not justify itself"
        assert d.unit in ("currency", "percent", "count", "days")
        assert isinstance(d.cadence, Cadence)


def test_keys_are_unique() -> None:
    keys = kpi_keys()
    assert len(keys) == len(set(keys))


def test_every_kpi_declares_its_prerequisites_or_needs_none() -> None:
    """Prerequisites are what make honest absence mechanical."""
    for d in KPI_DEFINITIONS:
        if d.required_objects:
            assert d.required_fields, f"{d.key} names objects but no fields"
        for qualified in d.required_fields:
            obj, _, fld = qualified.partition(".")
            assert fld, f"{d.key}: '{qualified}' is not Object.field"
            assert obj in d.required_objects, (
                f"{d.key}: {qualified} references an undeclared object")


def test_gross_margin_is_declared_but_not_yet_capturable() -> None:
    """The Blueprint names it; the Solo Pack cannot source it. C6 exists to
    make exactly this explicit rather than letting it be quietly invented."""
    gm = definition_for("gross_margin")
    assert gm is not None
    assert gm.captured_today is False
    assert gm.caveat and "connector" in gm.caveat.lower()


# --- honest absence ----------------------------------------------------------

@pytest.mark.asyncio
async def test_a_tenant_with_no_data_gets_no_numbers_at_all() -> None:
    """Day one must be a full list of 'not yet measurable', never zeroes."""
    for d in KPI_DEFINITIONS:
        if d.key == "agent_hitl_load":
            continue  # control-plane; legitimately zero on day one
        result = await _compute(d.key, records={}, defined=set())
        assert not result.measurable, f"{d.key} invented a value from nothing"
        assert result.value is None
        assert result.missing, f"{d.key} is unmeasurable but says nothing missing"


@pytest.mark.asyncio
async def test_uncapturable_kpi_never_computes() -> None:
    result = await _compute("gross_margin", records={
        "Payment": [{"amount": 100, "direction": "inbound"}],
        "Bill": [{"amount": 40}],
        "Ledger Entry": [{"account": "cogs"}],
    })
    assert not result.measurable
    assert result.missing


@pytest.mark.asyncio
async def test_a_field_defined_but_never_populated_counts_as_missing() -> None:
    """The case that would otherwise produce a confident zero."""
    result = await _compute("open_pipeline_value", records={
        "Opportunity": [{"stage": "discovery", "amount": None}],
    })
    assert not result.measurable
    assert "Opportunity.amount" in result.missing


@pytest.mark.asyncio
async def test_no_decided_quotes_is_not_a_zero_percent_acceptance_rate() -> None:
    """Every quote still open means no data, not total failure."""
    result = await _compute("quote_acceptance_rate", records={
        "Quote": [{"status": "sent", "total": 100},
                  {"status": "draft", "total": 50}],
    })
    assert not result.measurable
    assert any("decided" in m for m in result.missing)


@pytest.mark.asyncio
async def test_dso_refuses_to_divide_by_no_revenue() -> None:
    result = await _compute("days_sales_outstanding", records={
        "Invoice": [{"total": 1000, "amount_paid": 0, "status": "sent",
                     "due_date": "2026-07-01T00:00:00"}],
        "Payment": [{"amount": 0, "direction": "outbound", "status": "cleared",
                     "payment_date": "2026-07-10T00:00:00"}],
    })
    assert not result.measurable
    assert any("revenue" in m for m in result.missing)


# --- real computations -------------------------------------------------------

@pytest.mark.asyncio
async def test_open_pipeline_excludes_closed_opportunities() -> None:
    result = await _compute("open_pipeline_value", records={
        "Opportunity": [
            {"stage": "discovery", "amount": 1000},
            {"stage": "proposal", "amount": 500},
            {"stage": "won", "amount": 9999},
            {"stage": "lost", "amount": 8888},
        ],
    })
    assert result.value == 1500.0
    assert result.sample_size == 2


@pytest.mark.asyncio
async def test_receivables_net_off_partial_payments() -> None:
    result = await _compute("receivables_outstanding", records={
        "Invoice": [
            {"total": 1000, "amount_paid": 250, "status": "partially_paid",
             "due_date": "2026-08-01T00:00:00"},
            {"total": 500, "amount_paid": 500, "status": "paid",
             "due_date": "2026-07-01T00:00:00"},
            {"total": 300, "amount_paid": 0, "status": "void",
             "due_date": "2026-07-01T00:00:00"},
        ],
    })
    assert result.value == 750.0


@pytest.mark.asyncio
async def test_overdue_uses_the_due_date_not_just_the_status() -> None:
    """An invoice past its due date is overdue whether or not anything
    remembered to restamp its status."""
    result = await _compute("overdue_receivables", records={
        "Invoice": [
            {"total": 400, "amount_paid": 0, "status": "sent",
             "due_date": "2026-07-01T00:00:00"},   # past due, status stale
            {"total": 600, "amount_paid": 0, "status": "sent",
             "due_date": "2026-09-01T00:00:00"},   # not yet due
        ],
    })
    assert result.value == 400.0


@pytest.mark.asyncio
async def test_quote_acceptance_excludes_undecided_quotes_from_both_sides() -> None:
    result = await _compute("quote_acceptance_rate", records={
        "Quote": [
            {"status": "accepted", "total": 1},
            {"status": "rejected", "total": 1},
            {"status": "sent", "total": 1},      # undecided — excluded entirely
        ],
    })
    assert result.value == 50.0
    assert result.sample_size == 2


@pytest.mark.asyncio
async def test_collections_counts_only_cleared_inbound_in_window() -> None:
    recent = (NOW - timedelta(days=5)).isoformat()
    stale = (NOW - timedelta(days=90)).isoformat()
    result = await _compute("collections_recovered", records={
        "Payment": [
            {"amount": 100, "direction": "inbound", "status": "cleared",
             "payment_date": recent},
            {"amount": 200, "direction": "inbound", "status": "pending",
             "payment_date": recent},
            {"amount": 400, "direction": "outbound", "status": "cleared",
             "payment_date": recent},
            {"amount": 800, "direction": "inbound", "status": "cleared",
             "payment_date": stale},
        ],
        "Invoice": [{"due_date": "2026-07-01T00:00:00", "total": 100,
                     "amount_paid": 100, "status": "paid"}],
    })
    assert result.value == 100.0


@pytest.mark.asyncio
async def test_approvals_backlog_is_a_legitimate_zero() -> None:
    """Distinguishes a real measurement of nothing from an absence of data."""
    result = await _compute("agent_hitl_load", records={}, defined=set(), pending=0)
    assert result.measurable
    assert result.value == 0.0


# --- how Pragya says it ------------------------------------------------------

def test_unmeasurable_kpis_say_what_is_missing() -> None:
    result = KpiResult(
        key="gross_margin", display_name="Gross margin", unit="percent",
        formula="…", missing=["cost-of-delivery tagging on Bills"])
    sentence = result.as_sentence()
    assert "not yet measurable" in sentence
    assert "cost-of-delivery tagging on Bills" in sentence
    # The critical negative: no number appears anywhere in the refusal.
    assert "0" not in sentence
