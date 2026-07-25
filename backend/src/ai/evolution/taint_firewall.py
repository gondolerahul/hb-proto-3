"""evolution/taint_firewall.py — context taint and the tool-call firewall (D3).

**D3:** *prompt-injection defence is pattern-matching. Missing: privilege
separation (contaminated context cannot invoke high-impact tools),
provenance/taint on signal payloads, tool-call firewalls per trust zone.*

Increment 1 shipped the down-payment: `evaluate_policy` refuses
``HIGH_IMPACT_CATEGORIES`` when the *triggering signal* carried
``trust: counterparty``. Its limits are the whole of D3:

* taint is read **once**, at the triggering signal, and never updated — so a
  run started by an internal schedule that then fetches a hostile page is
  treated as fully trusted at the gate;
* there are two levels in practice where the envelope declares four.

This module is the ladder, the descent, and the firewall table. Three
properties are load-bearing:

1. **Taint only ever descends.** ``min`` at every entry point, no recovery
   transition. There is no honest way for code to *raise* trust — the only
   thing that can is a human reading the content, and that is a HITL card, not
   a state change. A "sanitised" transition would be the single most
   attackable line in the system.
2. **Unknown provenance reads ``external_verified``, not ``internal``.**
   *"We do not know where this came from"* is not *"we wrote it"*. Defaulting
   unknown to internal would make the whole ladder decorative, since most
   shipped content predates provenance tracking (LIB).
3. **The firewall is pure and total.** ``gate_and_maybe_stop`` fails *open* on
   an exception so a gate bug cannot wedge every run; a pure function over a
   total mapping has nothing to throw, which is what makes that fail-open safe
   here rather than merely convenient.

Design: docs/product-road-map/increment-6/02_sega.md §7.
"""
from __future__ import annotations

from typing import Iterable

__all__ = [
    "ALLOW",
    "HITL",
    "REFUSE",
    "LADDER",
    "SOURCE_LEVELS",
    "TOOL_SOURCES",
    "descend",
    "descend_all",
    "firewall",
    "level_for_source",
    "rank",
    "source_for_tool",
]

ALLOW = "ALLOW"
HITL = "HITL"
REFUSE = "REFUSE"

#: The trust ladder, weakest first. Deliberately the **same vocabulary** as
#: ``signals.SignalTrust`` — one taxonomy, not two, so a signal's declared
#: trust and a run's accumulated taint are directly comparable.
LADDER: tuple[str, ...] = (
    "counterparty", "external_verified", "internal", "platform",
)

_RANK = {level: index for index, level in enumerate(LADDER)}

#: What entering content does to a run's trust. The six entry points §7.3 names.
#: Kept as data so the whole descent map is readable in one place — and so that
#: *adding* a content source without deciding its trust is a visible omission
#: rather than an accidental "internal".
SOURCE_LEVELS: dict[str, str] = {
    # Free-web fetches: the classic injection vector.
    "web_search": "counterparty",
    "scraper": "counterparty",
    "batch_search": "counterparty",
    # A connector/MCP read is a system a tenant chose to trust, but its
    # contents came from outside this platform.
    "connector_read": "external_verified",
    "mcp_read": "external_verified",
    # A retrieved chunk carries its LIB provenance; absent, see rule 2 above.
    "retrieved_chunk": "external_verified",
    # A record field whose origin is an inbound proposal is counterparty text
    # that has been stored — storage does not launder it.
    "inbound_record_field": "counterparty",
}


#: Which shipped tools bring content in, and under which source. Matched
#: exactly then by substring, the same shape as
#: ``governance.authority.category_for_tool`` — and for the same reason: a
#: connector tool is qualified ``mcp__<server>__<verb>``, so an exact table
#: would need a row per server.
#:
#: A tool that is **not** here contributes no taint. That is the right default
#: for a calculator or a file writer, and it is why the map lists content
#: *sources* rather than trying to enumerate everything harmless.
TOOL_SOURCES: dict[str, str] = {
    "web_search": "web_search",
    "batch_search": "batch_search",
    "scraper": "scraper",
    "browser": "scraper",
    "mcp__": "mcp_read",
    "get_": "connector_read",
    "list_": "connector_read",
    "fetch_": "connector_read",
}


def source_for_tool(tool_name: str | None) -> str | None:
    """The content source a tool represents, or ``None`` if it brings none in."""
    if not tool_name:
        return None
    if tool_name in TOOL_SOURCES:
        return TOOL_SOURCES[tool_name]
    low = tool_name.lower()
    for needle, source in TOOL_SOURCES.items():
        if needle in low:
            return source
    return None


def rank(level: str | None) -> int:
    """Where a level sits on the ladder. Unknown levels rank at the bottom.

    Failing an unrecognised level to the *most* tainted end is the safe
    direction: a level this code does not understand must not out-rank one it
    does.
    """
    if level is None:
        return -1
    return _RANK.get(level, -1)


def descend(current: str | None, incoming: str | None) -> str:
    """The new taint after content arrives. Pure, and monotone downward.

    ``None`` for ``current`` means the run has not been stamped yet, so the
    incoming level *is* the level. ``None`` for ``incoming`` means content of
    unknown provenance — rule 2: that is ``external_verified``, never
    ``internal``.
    """
    arriving = incoming if incoming in _RANK else "external_verified"
    if current not in _RANK:
        return arriving
    return arriving if rank(arriving) < rank(current) else current


def level_for_source(source: str | None) -> str:
    """The taint a named content source imposes. Unknown sources are cautious."""
    if source is None:
        return "external_verified"
    return SOURCE_LEVELS.get(source, "external_verified")


def descend_all(current: str | None, sources: Iterable[str]) -> str:
    """Apply several arrivals in one go. Order-independent, being a ``min``."""
    level = current
    for source in sources:
        level = descend(level, level_for_source(source))
    return level if level is not None else "external_verified"


#: Categories a counterparty-tainted run may not drive at all — the shipped
#: ``HIGH_IMPACT_CATEGORIES``, imported lazily in :func:`firewall` so this
#: module stays free of governance imports and can be reasoned about alone.
_HIGH_IMPACT = frozenset({"payout", "refund", "contract", "vendor_creation"})

#: Writing into another business system on the strength of tainted content.
#:
#: **Design delta.** §7.4's table also put ``email_dispatch`` and ``broadcast``
#: here at ``counterparty`` taint. That is wrong, and the reason is structural:
#: a run's taint is seeded from its *triggering signal*, so **every Karuna
#: gateway run is counterparty-tainted from turn one** — an inbound email, a
#: WhatsApp message, a call. Forcing a card on outbound comms at that level
#: would raise an approval on every single gateway reply, which is the entire
#: sellable path (SLICE's email→quote), and would make A2+ meaningless for the
#: gateways. "A gate that fires constantly is a gate people learn to click
#: through" — the same reasoning that kept VG-05 from gating autonomy
#: *lowering*. Replying to a counterparty is what a gateway is *for*; the
#: control that covers it is the Karuna profile (no monetary authority,
#: counterparty text carried as data), not an approval on every reply.
#:
#: ``external_write`` stays: writing into a *system of record* because a
#: stranger's message said so is a genuine escalation, and it is rare enough
#: that a card is not noise.
_OUTWARD = frozenset({"external_write"})


def firewall(taint: str | None, category: str) -> str:
    """What a run at this taint may do in this category. Pure and total.

    | taint | high-impact | `external_write` | everything else |
    |---|---|---|---|
    | `counterparty` | **REFUSE** | **HITL** regardless of band | ALLOW |
    | `external_verified` | **HITL** regardless of band | band-based | ALLOW |
    | `internal` / `platform` | band-based | band-based | ALLOW |

    ``ALLOW`` here means *"the firewall has no opinion"* — the PolicyGate's
    band logic still runs. It never means "permitted".

    The ``counterparty``/high-impact cell reproduces the shipped §18.6
    behaviour exactly, which is how this change is proven non-regressive: the
    existing PolicyGate tests pass unchanged. The `external_verified` row is
    the new bite — a run that has read an external system may no longer move
    money autonomously, however high its band.
    """
    level = rank(taint)

    if level < 0 or taint == "counterparty":
        # Unknown levels are treated as the most tainted (see `rank`).
        if category in _HIGH_IMPACT:
            return REFUSE
        if category in _OUTWARD:
            return HITL
        return ALLOW

    if taint == "external_verified":
        if category in _HIGH_IMPACT:
            return HITL
        return ALLOW

    return ALLOW
