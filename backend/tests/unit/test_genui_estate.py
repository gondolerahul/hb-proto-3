"""SEAM T3 — the estate read model's pure parts.

The composition is integration-tested against live Postgres
(``test_genui_estate_db.py``); what lives here is everything that must hold
without a database: the weather precedence, the phase boundary, the channel
attribution and the SLA arithmetic. Weather gets the mutation treatment —
each state reachable alone, and the precedence pinned — because a wrong
weather state is exactly the "quietly does less" bug this repo keeps finding:
every test still passes, and the map lies.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from src.ai.genui.estate import (
    channel_for_signal_type,
    envelope_days_left,
    phase_for,
    sla_seconds_left,
    weather_for,
)


# ── phase ─────────────────────────────────────────────────────────────────────

def test_phase_boundaries_are_six_and_eighteen():
    assert phase_for(datetime(2026, 7, 29, 5, 59)) == "night"
    assert phase_for(datetime(2026, 7, 29, 6, 0)) == "day"
    assert phase_for(datetime(2026, 7, 29, 17, 59)) == "day"
    assert phase_for(datetime(2026, 7, 29, 18, 0)) == "night"


# ── channel attribution ──────────────────────────────────────────────────────

def test_signal_types_land_on_their_gatehouses():
    assert channel_for_signal_type("email.inbound") == "email"
    assert channel_for_signal_type("message.inbound") == "whatsapp"
    assert channel_for_signal_type("voice.inbound") == "voice"
    assert channel_for_signal_type("broadcast.inbound") == "broadcast"
    assert channel_for_signal_type("broadcast.published") == "broadcast"


def test_internal_traffic_belongs_to_no_gatehouse():
    """object.synced, governance.*, learning.* are platform plumbing — they
    must not inflate a door's inbound count."""
    assert channel_for_signal_type("object.synced") is None
    assert channel_for_signal_type("governance.autonomy_demoted") is None
    assert channel_for_signal_type("learning.outcome") is None


# ── SLA arithmetic ────────────────────────────────────────────────────────────

def test_sla_counts_down_and_floors_at_zero():
    now = datetime(2026, 7, 29, 12, 0, 0)
    asked = now - timedelta(seconds=100)
    assert sla_seconds_left(asked, 400, now) == 300
    assert sla_seconds_left(asked, 50, now) == 0  # overdue reads 0, never negative


def test_no_sla_means_none_not_zero():
    """None is "no SLA governs this checkpoint"; 0 is "the SLA fires now".
    Collapsing them would make every unhurried card look overdue."""
    now = datetime(2026, 7, 29, 12, 0, 0)
    assert sla_seconds_left(now, None, now) is None
    assert sla_seconds_left(None, 400, now) is None


# ── weather ───────────────────────────────────────────────────────────────────

def _clear_kwargs() -> dict:
    return dict(
        district_name="Care",
        storming=False,
        envelope_spent_fraction=None,
        envelope_days_left=None,
        all_triggers_disabled=False,
    )


def test_clear_is_the_resting_state_and_says_nothing():
    weather = weather_for(**_clear_kwargs())
    assert weather == {"state": "clear", "icon": None, "sentence": None}


def test_storm_needs_a_stopped_account():
    weather = weather_for(**{**_clear_kwargs(), "storming": True})
    assert weather["state"] == "storm"
    assert weather["icon"] == "cloud-lightning"
    assert "Care" in weather["sentence"]


def test_heat_shimmer_at_the_envelope_downshift():
    weather = weather_for(**{
        **_clear_kwargs(),
        "envelope_spent_fraction": 0.85,
        "envelope_days_left": 11,
    })
    assert weather["state"] == "heat-shimmer"
    assert weather["icon"] == "flame"
    assert "85%" in weather["sentence"] and "11 days" in weather["sentence"]


def test_below_the_downshift_is_not_heat():
    weather = weather_for(**{**_clear_kwargs(), "envelope_spent_fraction": 0.5})
    assert weather["state"] == "clear"


def test_moonlit_when_every_trigger_sleeps():
    weather = weather_for(**{**_clear_kwargs(), "all_triggers_disabled": True})
    assert weather["state"] == "moonlit"
    assert weather["icon"] == "moon"
    assert "hibernating" in weather["sentence"]


def test_precedence_storm_beats_heat_beats_moonlit():
    everything = {
        **_clear_kwargs(),
        "storming": True,
        "envelope_spent_fraction": 0.99,
        "envelope_days_left": 1,
        "all_triggers_disabled": True,
    }
    assert weather_for(**everything)["state"] == "storm"
    everything["storming"] = False
    assert weather_for(**everything)["state"] == "heat-shimmer"
    everything["envelope_spent_fraction"] = 0.1
    assert weather_for(**everything)["state"] == "moonlit"


def test_every_non_clear_state_carries_icon_and_sentence():
    """Art bible §8: the icon and the sentence are what the sheet equivalent
    and the screen reader receive. A state without them is invisible off the
    map."""
    states = [
        weather_for(**{**_clear_kwargs(), "storming": True}),
        weather_for(**{**_clear_kwargs(), "envelope_spent_fraction": 0.9}),
        weather_for(**{**_clear_kwargs(), "all_triggers_disabled": True}),
    ]
    for weather in states:
        assert weather["icon"], weather["state"]
        assert weather["sentence"], weather["state"]


def test_fog_is_a_named_absence():
    """D5 §2.1 derives fog from a KPI target the KPI registry does not declare.
    Until it does, no input combination may produce fog — a fog computed from
    an invented target would teach the owner to distrust the map (the exact
    failure weather exists to prevent). This test is the tripwire that fires
    when someone adds fog without a real target behind it."""
    import inspect

    from src.ai.genui import estate

    source = inspect.getsource(estate.weather_for)
    assert '"fog"' not in source and "'fog'" not in source


# ── envelope cycle ────────────────────────────────────────────────────────────

def test_envelope_days_left_by_cycle():
    now = datetime(2026, 7, 29)
    assert envelope_days_left(now - timedelta(days=10), "monthly", now) == 20
    assert envelope_days_left(now - timedelta(days=2), "weekly", now) == 5
    assert envelope_days_left(now - timedelta(days=40), "monthly", now) == 0
