"""solo_pack/consent.py — the outbound consent / DNC hook (KAR seam).

Every gateway outbound send passes through ``check_outbound_consent`` before it
leaves the tenant. **Consent is tenant-configured from day one** (decision 8):
the platform imposes no global opt-in default — each tenant owns its per-purpose
posture, enforced by a registry.

KAR ships the **seam + contract**; the jurisdiction-agnostic consent/DNC/
unsubscribe **registry (D6) is a TRUST deliverable** that installs a checker via
``set_consent_checker`` — callers (`check_outbound_consent`) never change when it
lands. Until then the default posture allows transactional sends (what a solo
tenant expects) and denies nothing, so the sellable path is not blocked before
the registry exists.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, NamedTuple, Optional, Sequence

__all__ = [
    "ConsentDecision", "ConsentChecker", "set_consent_checker", "check_outbound_consent",
    "ChannelPostureChecker", "set_channel_posture_checker", "check_channel_posture",
    "AudienceFilter", "filter_audience",
]


@dataclass(frozen=True)
class ConsentDecision:
    allowed: bool
    reason: str = ""


# The checker TRUST installs: (company_id, channel, to_address, purpose) → decision.
ConsentChecker = Callable[[uuid.UUID, str, str, str], Awaitable[ConsentDecision]]

_checker: Optional[ConsentChecker] = None


def set_consent_checker(checker: Optional[ConsentChecker]) -> None:
    """Install (or clear with ``None``) the consent/DNC checker (TRUST/D6)."""
    global _checker
    _checker = checker


async def check_outbound_consent(
    company_id: uuid.UUID, channel: str, to_address: str,
    purpose: str = "transactional",
) -> ConsentDecision:
    """Gate an outbound gateway send on the tenant's consent/DNC posture.

    Returns a :class:`ConsentDecision`; the caller must not send when
    ``allowed`` is False. With no registry installed, allows the send (the
    pre-TRUST default posture) — this is the single seam the D6 registry plugs
    into without touching any caller.
    """
    if _checker is not None:
        return await _checker(uuid.UUID(str(company_id)), channel, to_address, purpose)
    return ConsentDecision(
        allowed=True, reason="no consent registry configured (default posture)")


# ── Channel posture (Inc-6 GATE T3) ──────────────────────────────────
#
# A broadcast is not person-addressed, so ``check_outbound_consent`` does not
# fit it: there is no ``to_address``. The question a broadcast asks is a
# different one — *may this tenant publish to this platform for this purpose?*
# — and it is the tenant's own policy, not a counterparty's. Some businesses
# are regulated out of public statements; some want a human on every post
# whatever the band says.
#
# Deliberately a second seam rather than a sentinel address threaded through
# the first: a function whose ``to_address`` sometimes means "nobody in
# particular" is one refactor away from a DNC lookup against a literal "*".

# (company_id, channel, purpose) → decision.
ChannelPostureChecker = Callable[[uuid.UUID, str, str], Awaitable[ConsentDecision]]

_posture_checker: Optional[ChannelPostureChecker] = None


def set_channel_posture_checker(checker: Optional[ChannelPostureChecker]) -> None:
    """Install (or clear with ``None``) the channel-posture checker (TRUST/D6)."""
    global _posture_checker
    _posture_checker = checker


async def check_channel_posture(
    company_id: uuid.UUID, channel: str, purpose: str = "marketing",
) -> ConsentDecision:
    """Gate a broadcast on the tenant's posture for this channel and purpose.

    Permissive until set — Increment 2's decision 8 (consent is
    tenant-configured from day one; the platform imposes no global default).
    Absent an explicit posture a broadcast is allowed and governed by band
    alone, and the tenant may tighten it. The alternative, defaulting closed,
    would have every tenant's first post silently fail with nothing in the
    product yet explaining why.
    """
    if _posture_checker is not None:
        return await _posture_checker(uuid.UUID(str(company_id)), channel, purpose)
    return ConsentDecision(
        allowed=True, reason="no consent registry configured (default posture)")


class AudienceFilter(NamedTuple):
    """The result of running an ad audience through the DNC registry (T4)."""

    allowed: tuple[str, ...]
    suppressed: tuple[str, ...]

    @property
    def suppressed_count(self) -> int:
        return len(self.suppressed)


async def filter_audience(
    company_id: uuid.UUID, channel: str, identities: Sequence[str],
    purpose: str = "marketing",
) -> AudienceFilter:
    """Remove DNC/unsubscribed identifiers from an ad audience — never refuse it.

    An ad "custom audience" is a list of real people's emails or phone numbers,
    and it is the one place on the broadcast surface where the shipped DNC
    registry applies literally.

    **Filter and count, do not refuse** (GATE decision 5). Rejecting a
    10,000-row upload because one person unsubscribed would push tenants to
    build the list by hand outside the platform — strictly worse for the person
    who unsubscribed, since a hand-built list is filtered by nothing at all.
    The suppressed count travels onto the HITL card so the approver can see the
    list was cleaned, and by how much.

    Runs over the *seam*, not the registry, so it needs no session and honours
    whatever provider is installed — including a jurisdiction pack that
    tightens the posture.
    """
    allowed: list[str] = []
    suppressed: list[str] = []
    for identity in identities:
        decision = await check_outbound_consent(company_id, channel, identity, purpose)
        (allowed if decision.allowed else suppressed).append(identity)
    return AudienceFilter(tuple(allowed), tuple(suppressed))
