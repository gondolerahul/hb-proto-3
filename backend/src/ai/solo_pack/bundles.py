"""solo_pack/bundles.py — the 7 starter bundles (functional doc §2.1).

A bundle is a **named packaging view** over Sheel's canonical processes — an
activation/reporting grouping, *not* a pricing tier (decision: all bundles are
included at every subscription tier). Together the seven cover all 19 processes
exactly once; the tuples below are the full §2.1 membership, so when a later
wave authors a process template, activating its bundle brings it online with
zero plumbing change. Activation seeds only the **intersection** of a bundle's
processes with the authored Wave-0 templates (``templates.PROCESS_GROUPS``).

Process codes are stored numerically (like the HBS spine's ``owner`` code) and
rendered ``P{nn}`` on read — the canonical string form the process templates
carry in ``metadata_extensions.process_code``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = ["Bundle", "BUNDLES", "SOLO_PACK", "bundle_by_key"]


@dataclass(frozen=True)
class Bundle:
    """A starter bundle: a named set of Sheel processes."""

    key: str
    display_name: str
    process_nums: tuple[int, ...]

    @property
    def process_codes(self) -> frozenset[str]:
        """The bundle's processes as canonical ``P{nn}`` codes."""
        return frozenset(f"P{n:02d}" for n in self.process_nums)


# The 7 starter bundles — full §2.1 membership (all 19 processes, once each).
BUNDLES: tuple[Bundle, ...] = (
    Bundle("growth", "Growth & Customer Acquisition", (1, 2, 3, 4)),
    Bundle("customer_success", "Customer Success & Support", (6, 7)),
    Bundle("fulfillment", "Operational Fulfillment", (5, 15)),
    Bundle("fiscal", "Continuous Fiscal & Asset Optimizer", (8, 9, 10, 11, 18)),
    Bundle("compliance", "Regulatory & Compliance Engine", (13, 14, 17)),
    Bundle("talent", "Talent Vitality & Resource Alignment", (12,)),
    Bundle("intelligence", "Self-Optimizing Intelligence Engine", (16, 19)),
)

# The Solo Pack default: the cross-functional slice of every critical function
# (not one bundle) — every authored Wave-0 process. Represented as the sentinel
# key the activation service expands to all PROCESS_GROUPS.
SOLO_PACK: str = "solo_pack"


def bundle_by_key(key: str) -> Optional[Bundle]:
    """Return the bundle with ``key`` (e.g. ``"fiscal"``), or None."""
    for bundle in BUNDLES:
        if bundle.key == key:
            return bundle
    return None
