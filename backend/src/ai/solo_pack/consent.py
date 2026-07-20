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
from typing import Awaitable, Callable, Optional

__all__ = [
    "ConsentDecision", "ConsentChecker", "set_consent_checker", "check_outbound_consent",
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
