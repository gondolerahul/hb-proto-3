"""ai/pragya — the account-manager engagement (Inc-3 PRAGYA).

Only the reviewed stage scripts exist so far (T4's drafting half). The
orchestration around them — stage machine, chat transport, intent extraction
behind ``inward_auth.require_tier`` — lands with T1–T3.
"""
from __future__ import annotations

__all__ = ["DISCOVERY_SCRIPTS", "script_for_stage"]

from src.ai.pragya.scripts import DISCOVERY_SCRIPTS, script_for_stage
