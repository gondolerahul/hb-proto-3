"""ai/inward_auth — the inward-channel authentication floor (Inc-3 AUTH, D1).

Karuna verifies the *counterparty* on the way out (SKL-X04); this package is the
inward mirror: it decides whether the voice on the other end of Pragya's channel
is allowed to make the company do the thing it just asked for.

The shape is TRUST's — policy here, enforcement at the existing call site:

* ``tiers``    — the pure T0–T3 classifier over the §20 authority categories.
* ``sessions`` — session elevation + ``require_tier``, the predicate every
  Pragya command calls before it acts.
* ``step_up``  — the WebAuthn and TOTP ceremonies that produce an elevation.
* ``bindings`` — channel enrollment; which addresses resolve to which user.
* ``oob``      — the T3 second-channel confirmation leg.

Standing rule from the design: *channel identity routes, verification
authorizes*. A caller ID or a WhatsApp sender is a hint about who is calling,
never proof, so nothing in here treats an address as an authentication factor.
"""
from __future__ import annotations

__all__ = ["ChannelKind", "AuthLevel", "Tier"]

from src.ai.inward_auth.models import AuthLevel, ChannelKind
from src.ai.inward_auth.tiers import Tier
