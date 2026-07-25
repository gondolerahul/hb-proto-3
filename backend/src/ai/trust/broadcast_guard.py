"""trust/broadcast_guard.py — the pre-execute consent check for broadcast (GATE T3+T4).

TRUST's shape, followed exactly: **policy here, enforcement at the existing
call site.** The call site is ``SocialMediaTool.run_with_context`` — every one
of the 64 social tools funnels through it, it has already resolved the
company, and a tool added later inherits the check by construction rather than
by remembering to add it. That last property is why it is there and not in the
sixteen platform modules.

Two checks, because §5 found two different questions:

* a **broadcast** asks the tenant's own policy — *may we publish to LinkedIn
  for marketing?* — which is channel posture, not counterparty consent;
* an **ad audience** is a list of real people, which is the one place on this
  surface where the person-addressed DNC registry applies literally.

This runs *after* the PolicyGate, not instead of it. The gate decides whether
the agent may act at its autonomy band; this decides whether the tenant
broadcasts on this channel at all. A refusal here is not an approval request —
there is nothing for a human to approve, because the tenant already answered.
"""
from __future__ import annotations

import uuid
from typing import Any, Mapping, NamedTuple

from src.ai.governance.authority import category_for_tool
from src.ai.solo_pack.consent import check_channel_posture, filter_audience

__all__ = [
    "AUDIENCE_KEYS",
    "BroadcastGuardResult",
    "guard_social_call",
    "purpose_for_tool",
]

#: Parameter names that would carry a custom-audience list of person
#: identifiers (emails / phone numbers).
#:
#: **Honest limit, recorded rather than hidden:** *no shipped social tool
#: currently declares any of these.* The audience tools that ship
#: (`meta_ads_manage_audiences`, `x_ads_manage_audiences`, …) build audiences
#: from rules and lookalike sources, so the platform never receives a raw list
#: through this surface — the design assumed an upload the tool schemas do not
#: expose. The filter is built, tested and wired anyway, so the first tool to
#: grow such a parameter is filtered on the day it lands rather than on the day
#: someone remembers. A test pins both halves of this: that the filter works,
#: and that nothing shipped feeds it yet.
AUDIENCE_KEYS: tuple[str, ...] = (
    "emails", "phones", "phone_numbers", "identifiers", "contacts",
    "audience_members", "user_list", "members", "recipients",
)

#: Publishing is marketing; replying to someone in public is support. Split so
#: a tenant can refuse marketing on a channel while keeping its agents able to
#: answer a customer's public comment — refusing both together would make the
#: posture switch unusable for anyone who does support on social.
_TRANSACTIONAL_MARKERS: tuple[str, ...] = ("_manage_comments",)


def purpose_for_tool(tool_name: str) -> str:
    """The consent purpose a social tool's act falls under."""
    if any(marker in tool_name for marker in _TRANSACTIONAL_MARKERS):
        return "transactional"
    return "marketing"


class BroadcastGuardResult(NamedTuple):
    allowed: bool
    reason: str
    params: Mapping[str, Any]
    suppressed_count: int


async def guard_social_call(
    tool_name: str,
    platform: str,
    company_id: uuid.UUID | str,
    params: Mapping[str, Any],
) -> BroadcastGuardResult:
    """Check a social tool call against the tenant's consent posture.

    Returns the (possibly audience-filtered) params to execute with. Read verbs
    are uncategorised and pass through untouched — checking consent before an
    analytics read would be both meaningless and slow.

    ``company_id`` is accepted as a string too: the tool base resolves it from
    an execution context that carries it either way.
    """
    company_uuid = uuid.UUID(str(company_id))
    category = category_for_tool(tool_name)

    if category == "broadcast":
        decision = await check_channel_posture(
            company_uuid, platform, purpose_for_tool(tool_name))
        if not decision.allowed:
            return BroadcastGuardResult(False, decision.reason, params, 0)
        return BroadcastGuardResult(True, decision.reason, params, 0)

    if category == "ad_spend":
        suppressed_total = 0
        cleaned = dict(params)
        for key in AUDIENCE_KEYS:
            value = cleaned.get(key)
            if not isinstance(value, list) or not value:
                continue
            identities = [str(item) for item in value]
            result = await filter_audience(
                company_uuid, platform, identities, purpose_for_tool(tool_name))
            cleaned[key] = list(result.allowed)
            suppressed_total += result.suppressed_count
        reason = (
            f"{suppressed_total} audience identifier(s) suppressed by the "
            f"do-not-contact registry"
            if suppressed_total
            else "no audience identifiers suppressed"
        )
        return BroadcastGuardResult(True, reason, cleaned, suppressed_total)

    return BroadcastGuardResult(True, "uncategorised act", params, 0)
