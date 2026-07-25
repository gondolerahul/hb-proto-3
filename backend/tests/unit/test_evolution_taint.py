"""SEGA T6 — the taint ladder and the tool-call firewall (D3).

Increment 1 shipped one rule: a `counterparty` triggering signal cannot drive a
high-impact category. D3's complaint is that taint is read *once*, at the
signal, so a run started by an internal schedule that then scrapes a hostile
page is still treated as fully trusted at the gate.

Two properties carry the weight:

* **taint only descends** — there is no recovery transition, because the only
  thing that can honestly raise trust is a human reading the content, and that
  is a HITL card rather than a state change;
* **the `counterparty` / high-impact cell is unchanged**, which is how the
  replacement of the shipped special case is proven non-regressive.

Design: docs/product-road-map/increment-6/02_sega.md §7.
"""
from __future__ import annotations

import pytest

from src.ai.evolution.taint_firewall import (
    ALLOW,
    HITL,
    LADDER,
    REFUSE,
    descend,
    descend_all,
    firewall,
    level_for_source,
    rank,
    source_for_tool,
)


# ── the ladder ───────────────────────────────────────────────────────────────

def test_the_ladder_matches_the_signal_trust_vocabulary():
    """One taxonomy, not two — a signal's declared trust and a run's
    accumulated taint have to be directly comparable."""
    from src.ai.signals.models import SignalTrust

    assert set(LADDER) == {SignalTrust.COUNTERPARTY, SignalTrust.EXTERNAL_VERIFIED,
                           SignalTrust.INTERNAL, SignalTrust.PLATFORM}


def test_an_unknown_level_ranks_at_the_bottom():
    """A level this code does not understand must not out-rank one it does."""
    assert rank("something_new") < rank("counterparty")


# ── descent ──────────────────────────────────────────────────────────────────

def test_taint_descends_when_untrusted_content_arrives():
    assert descend("internal", "counterparty") == "counterparty"


def test_taint_never_rises():
    """The load-bearing property. A 'sanitised' transition would be the single
    most attackable line in the system."""
    assert descend("counterparty", "platform") == "counterparty"
    assert descend("counterparty", "internal") == "counterparty"
    assert descend("external_verified", "platform") == "external_verified"


def test_an_unstamped_run_takes_the_arriving_level():
    assert descend(None, "internal") == "internal"


def test_unknown_provenance_is_external_verified_not_internal():
    """"We do not know where this came from" is not "we wrote it".

    Defaulting unknown to internal would make the whole ladder decorative,
    since most shipped content predates provenance tracking.
    """
    assert descend(None, None) == "external_verified"
    assert descend("platform", None) == "external_verified"


def test_descent_is_order_independent():
    """Being a min, it has to be — otherwise the same run could end up at two
    different levels depending on which tool answered first."""
    forward = descend_all("internal", ["web_search", "connector_read"])
    backward = descend_all("internal", ["connector_read", "web_search"])
    assert forward == backward == "counterparty"


def test_a_harmless_tool_contributes_no_taint():
    """A calculator is not a content source. If every tool tainted, the ladder
    would collapse to one level within a turn or two."""
    assert source_for_tool("calculator") is None
    assert source_for_tool("pdf_generator") is None
    assert descend_all("internal", []) == "internal"


@pytest.mark.parametrize("tool,expected", [
    ("web_search", "counterparty"),
    ("scraper_tool", "counterparty"),
    ("batch_search", "counterparty"),
    ("mcp__zoho_books__get_invoice", "external_verified"),
    ("get_customer", "external_verified"),
])
def test_content_bringing_tools_lower_the_level(tool, expected):
    source = source_for_tool(tool)
    assert source is not None
    assert level_for_source(source) == expected


# ── the firewall ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("category", ["payout", "refund", "contract", "vendor_creation"])
def test_counterparty_context_may_not_move_money(category):
    """Unchanged from what shipped — this cell is the non-inferiority claim."""
    assert firewall("counterparty", category) == REFUSE


@pytest.mark.parametrize("category", ["payout", "refund", "contract", "vendor_creation"])
def test_external_verified_context_needs_a_human_to_move_money(category):
    """The new bite: a run that has read an external system may no longer move
    money autonomously, however high its band."""
    assert firewall("external_verified", category) == HITL


def test_counterparty_context_needs_a_human_to_write_into_another_system():
    """Writing into a system of record because a stranger's message said so."""
    assert firewall("counterparty", "external_write") == HITL


def test_outbound_comms_stay_band_based_even_at_counterparty():
    """The design delta, and the reason for it.

    A run's taint is seeded from its triggering signal, so **every Karuna
    gateway run is counterparty-tainted from turn one**. Forcing a card on
    outbound comms there would raise an approval on every gateway reply — the
    whole sellable path — and make A2+ meaningless for gateways. Replying to a
    counterparty is what a gateway is *for*; the Karuna profile is the control
    that covers it.
    """
    assert firewall("counterparty", "email_dispatch") == ALLOW
    assert firewall("counterparty", "broadcast") == ALLOW


@pytest.mark.parametrize("taint", ["internal", "platform"])
@pytest.mark.parametrize("category", ["payout", "external_write", "email_dispatch"])
def test_trusted_context_defers_entirely_to_the_bands(taint, category):
    """ALLOW means "the firewall has no opinion", never "permitted" — the
    PolicyGate's band logic still runs after it."""
    assert firewall(taint, category) == ALLOW


def test_an_uncategorised_act_is_never_touched():
    assert firewall("counterparty", "generic") == ALLOW


def test_an_unknown_taint_is_treated_as_the_most_tainted():
    """Fail toward caution: an unrecognised level must not buy more privilege
    than the lowest one we know about."""
    assert firewall("who_knows", "payout") == REFUSE
    assert firewall(None, "payout") == REFUSE


def test_the_firewall_is_total():
    """It is called inside a gate that fails *open* on exception. A pure
    function over a total mapping has nothing to throw, which is what makes
    that fail-open safe here rather than merely convenient."""
    for taint in [*LADDER, None, "nonsense"]:
        for category in ["payout", "external_write", "email_dispatch", "generic", ""]:
            assert firewall(taint, category) in {ALLOW, HITL, REFUSE}
