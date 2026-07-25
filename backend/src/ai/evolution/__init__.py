"""ai.evolution — the SEGA workstream (Increment 6; closes B11 and D3).

Self-evolution, bounded: what an automated change may touch (`blast_radius`),
what every entity change leaves behind (`ledger`), how a change earns its way to
GA (`entity_canary`), and what a run may still do once untrusted content has
entered it (`taint_firewall`).

The init deliberately re-exports almost nothing — an ``ai/`` package init must
not import back toward its own consumers (the VOICE lesson). Import submodules
directly.

Design: docs/product-road-map/increment-6/02_sega.md
"""
from src.ai.evolution.blast_radius import BlastRadiusError, ChangeKind

__all__ = ["BlastRadiusError", "ChangeKind"]
