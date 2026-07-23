"""connectors.zoho_books — the reference OWN_ADAPTER (Increment 4 / CONN T6).

Zoho Books is the flagship accounting connector (decision 2). It has no
canonical public MCP server, so it is our own :class:`ZohoBooksClient` that
speaks the shipped ``MCPClient`` contract (for the agent tool path) *and* the
:class:`~src.ai.connectors.writeback.SorConnector` contract (write-back + change
feed for mastering). All vendor specifics — field mapping, REST shape — live
here; the SOR machine (write-back provider, sweep) stays connector-agnostic.

HTTP is an injectable transport so the whole adapter is provable against a fake
without a live Zoho call (the §9 live-binding boundary — a real token + the live
API are an activation-time step).
"""
from __future__ import annotations

from src.ai.connectors.zoho_books.client import ZohoBooksClient

__all__ = ["ZohoBooksClient"]
