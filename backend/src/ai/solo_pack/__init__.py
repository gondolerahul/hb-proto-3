"""
ai.solo_pack — the Solo Pack: the smallest sellable Sheel (Increment 2).

Curated, hand-authored entity templates (the product's quality bar, reviewed
like the HBS spine) + the activation service that seeds a tenant's Wave-0
agents/processes/triggers onto the Increment-1 substrate. The Meta-Agent Board
stays for tenant-CUSTOM agents; these are the shipped defaults.

Design: docs/product-road-map/increment-2/ (01_slice, 02_kar, 03_pack).
"""
from src.ai.solo_pack.bundles import BUNDLES, Bundle, bundle_by_key
from src.ai.solo_pack.templates import SLICE_TEMPLATES, SOLO_PACK_TEMPLATES

__all__ = [
    "SLICE_TEMPLATES", "SOLO_PACK_TEMPLATES", "BUNDLES", "Bundle", "bundle_by_key",
]
