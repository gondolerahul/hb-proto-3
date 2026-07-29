"""STEWARD S3 — navigation derived from the turn, pure.

The properties: at most one event per turn (focus OR materialize, never
both); a read opens, an act focuses; an unmapped target stays still (her
text answer is the whole reply — staying still is not a failure); and an
anchor points only at something the turn made real.
"""
from __future__ import annotations

from types import SimpleNamespace

from src.ai.genui.navigation import anchors_from_outcome, navigation_for
from src.ai.inward_auth.tiers import IntentKind


def _command(kind=IntentKind.TENANT_READ, target=None, summary=""):
    return SimpleNamespace(kind=kind, target=target, summary=summary)


# ── navigation_for ───────────────────────────────────────────────────────────

def test_no_command_means_no_navigation():
    assert navigation_for(None) is None


def test_no_target_means_no_navigation():
    assert navigation_for(_command(target=None)) is None
    assert navigation_for(_command(target="   ")) is None


def test_a_read_of_the_estate_materializes_the_terrace():
    nav = navigation_for(_command(target="estate", summary="the overview"))
    assert nav == {
        "type": "materialize", "surface_id": "terrace",
        "reason": "the overview"}


def test_a_read_of_a_district_materializes_its_sheet():
    nav = navigation_for(_command(target="p06"))
    assert nav["type"] == "materialize"
    assert nav["surface_id"] == "district.P06"


def test_an_act_on_a_district_focuses_it_instead_of_opening_it():
    nav = navigation_for(_command(
        kind=IntentKind.PROCESS_PAUSE, target="P06", summary="pause care"))
    assert nav == {
        "type": "focus",
        "target_ref": {"kind": "district", "id": "P06"},
        "narration": "pause care",
    }


def test_an_unmapped_target_stays_still():
    assert navigation_for(_command(target="the blue invoice")) is None
    assert navigation_for(
        _command(kind=IntentKind.PROCESS_PAUSE, target="everything")) is None


def test_at_most_one_event_by_construction():
    """The function returns one dict or None — pinned so a future editor who
    wants 'focus then materialize' has to break a named test to do it."""
    nav = navigation_for(_command(target="P06"))
    assert isinstance(nav, dict)
    assert nav["type"] in ("focus", "materialize")


# ── anchors_from_outcome ─────────────────────────────────────────────────────

def test_a_raised_approval_anchors_the_tray():
    outcome = SimpleNamespace(raised_approval=True, command=None)
    assert anchors_from_outcome(outcome) == [
        {"kind": "tray", "label": "the waiting decision", "ref": "tray"}]


def test_the_touched_district_is_an_anchor():
    outcome = SimpleNamespace(
        raised_approval=False, command=_command(target="p03"))
    assert anchors_from_outcome(outcome) == [
        {"kind": "district", "label": "P03", "ref": "P03"}]


def test_a_quiet_turn_has_no_anchors():
    outcome = SimpleNamespace(raised_approval=False, command=None)
    assert anchors_from_outcome(outcome) == []
