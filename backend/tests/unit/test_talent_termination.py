"""DRIVER D7 — the handover memo's pure half (VG-18, 11_driver.md §5).

Deterministic composition from shipped data, no generative prose: the
same summary always writes the same memo, pending approvals are named as
the human's (never the colleague's), and the memo states what survives.
"""
from __future__ import annotations

from datetime import datetime

from src.ai.talent.termination import TenureSummary, compose_memo_text

NOW = datetime(2026, 7, 29, 12, 0, 0)


def _summary(**overrides: object) -> TenureSummary:
    base = dict(
        name="Meera",
        entity_id="e-1",
        process_name="Collections",
        first_run_at="2026-06-01",
        last_run_at="2026-07-28",
        runs_total=40,
        runs_completed=36,
        runs_failed=2,
        pending_approvals=1,
    )
    base.update(overrides)
    return TenureSummary(**base)  # type: ignore[arg-type]


def test_the_memo_is_deterministic() -> None:
    assert compose_memo_text(_summary(), NOW) == compose_memo_text(_summary(), NOW)


def test_pending_approvals_belong_to_the_human() -> None:
    memo = compose_memo_text(_summary(pending_approvals=2), NOW)
    assert "2 approval(s) still waiting" in memo
    assert "belong to you" in memo


def test_a_clean_exit_says_so_rather_than_omitting_the_section() -> None:
    memo = compose_memo_text(_summary(pending_approvals=0), NOW)
    assert "Nothing was waiting on an approval." in memo


def test_the_memo_names_where_new_work_goes_and_what_survives() -> None:
    memo = compose_memo_text(_summary(), NOW)
    assert "the Collections front door" in memo
    assert "survives this termination" in memo
    assert "Gallery" in memo


def test_a_colleague_who_never_ran_is_told_honestly() -> None:
    memo = compose_memo_text(
        _summary(first_run_at=None, last_run_at=None, runs_total=0,
                 runs_completed=0, runs_failed=0),
        NOW)
    assert "never started" in memo
    assert "0 runs" in memo
