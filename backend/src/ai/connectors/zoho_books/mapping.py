"""zoho_books/mapping.py — canonical Invoice ↔ Zoho Books invoice.

A deliberately small, explicit field map between the HBS canonical **Invoice**
(tenant_schema hbs_seed) and the Zoho Books invoice resource. Only the fields
that resolve cleanly are mapped; the exact, complete mapping (line items, tax
breakdown, customer resolution) is refined against the live API with credentials
in hand (the §9 boundary). Refs (``account``) are intentionally not pushed —
customer resolution is its own connector concern, out of this slice.
"""
from __future__ import annotations

from typing import Any

__all__ = ["to_zoho_invoice", "from_zoho_invoice"]

# canonical field → Zoho field
_TO_ZOHO = {
    "invoice_number": "invoice_number",
    "issue_date": "date",
    "due_date": "due_date",
    "total": "total",
    "subtotal": "sub_total",
    "status": "status",
}
_FROM_ZOHO = {zoho: canon for canon, zoho in _TO_ZOHO.items()}


def to_zoho_invoice(data: dict[str, Any]) -> dict[str, Any]:
    """Canonical Invoice fields → a Zoho invoice payload (present fields only)."""
    return {zoho: data[canon] for canon, zoho in _TO_ZOHO.items() if data.get(canon) is not None}


def from_zoho_invoice(zoho: dict[str, Any]) -> dict[str, Any]:
    """A Zoho invoice → canonical Invoice fields (present fields only)."""
    return {canon: zoho[z] for z, canon in _FROM_ZOHO.items() if zoho.get(z) is not None}
