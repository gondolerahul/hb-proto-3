"""trust/fee_guard.py — the fee-formula guard (E4).

The global billing formula (``billing/billing_service.py``) is::

    TB = (c·mf) + (c·mf·pf) + (c·mf·spf) − (c·mf·d)

**Ordering intent — deliberate, asserted here.** The discount is taken on the
*multiplied cost* and subtracted **last**; it does not reduce the platform fee
or the sales-partner fee. A partner earns their fee on the marked-up cost
regardless of what discount the tenant negotiated — a discount is the
platform's concession, not the partner's. Reordering the terms would silently
move who pays for a discount, so the intent is stated here and pinned by a test
rather than left implicit in the arithmetic.

**A negative TB is never a legitimate price.** It can only come from a
misconfigured ``BillingConfig`` — a discount that exceeds ``1 + pf + spf``, or a
negative multiplier. Clamping it silently to zero is finding **E4**: the tenant
is billed nothing, the ledger looks fine, and the misconfiguration survives.
This module keeps the clamp — a config bug must never *credit* a customer — but
makes it **loud**: a structured ERROR log plus a ``billing.fee_misconfigured``
signal carrying the offending factors, so it surfaces in the signals inspector
instead of vanishing into a rounding difference.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "FeeMisconfiguration",
    "SIGNAL_FEE_MISCONFIGURED",
    "inspect_fee_result",
    "clamp_total_billing",
    "report_fee_misconfiguration",
]

SIGNAL_FEE_MISCONFIGURED = "billing.fee_misconfigured"


@dataclass(frozen=True)
class FeeMisconfiguration:
    """A negative Total Billing and the factors that produced it."""

    total_billing: Decimal
    multiplier_factor: Decimal
    platform_fee_pct: Decimal
    sales_partner_fee_pct: Decimal
    discount_pct: Decimal
    reason: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "total_billing": str(self.total_billing),
            "multiplier_factor": str(self.multiplier_factor),
            "platform_fee_pct": str(self.platform_fee_pct),
            "sales_partner_fee_pct": str(self.sales_partner_fee_pct),
            "discount_pct": str(self.discount_pct),
            "reason": self.reason,
        }


def inspect_fee_result(
    tb: Mapping[str, Decimal],
    *,
    mf: Decimal,
    pf: Decimal,
    spf: Decimal,
    d: Decimal,
) -> Optional[FeeMisconfiguration]:
    """Return a finding when the computed TB is negative, else ``None``.

    Pure — the caller decides whether to log, alert, or clamp. ``reason`` names
    the most likely culprit so the operator does not have to re-derive it: a
    discount above the ``1 + pf + spf`` break-even is the common misconfig; a
    negative multiplier is the other way to get here.
    """
    total = Decimal(str(tb.get("total_billing", Decimal("0"))))
    if total >= 0:
        return None

    breakeven = Decimal("1") + pf + spf
    if d > breakeven:
        reason = (
            f"discount_pct {d} exceeds the break-even {breakeven} "
            f"(1 + platform_fee_pct + sales_partner_fee_pct)"
        )
    elif mf < 0:
        reason = f"multiplier_factor {mf} is negative"
    else:
        reason = "fee factors combine to a negative price"

    return FeeMisconfiguration(
        total_billing=total,
        multiplier_factor=mf,
        platform_fee_pct=pf,
        sales_partner_fee_pct=spf,
        discount_pct=d,
        reason=reason,
    )


def clamp_total_billing(total: Decimal) -> Decimal:
    """Never bill (or credit) a negative amount. Loud at the call site, not here."""
    return total if total >= 0 else Decimal("0")


async def report_fee_misconfiguration(
    db: AsyncSession,
    company_id: uuid.UUID,
    finding: FeeMisconfiguration,
    *,
    period: str = "",
) -> None:
    """Log the finding and raise a ``billing.fee_misconfigured`` signal.

    Deduped per company and period so a misconfigured config that fires on
    every billed call raises one card, not thousands. Signal emission is
    best-effort — a billing write must never fail because the outbox did.
    """
    logger.error(
        "E4 fee misconfiguration: company=%s total_billing=%s clamped to 0 — %s",
        company_id, finding.total_billing, finding.reason,
    )

    from src.ai.signals.models import SignalSource, SignalTrust
    from src.ai.signals.service import emit_signal

    try:
        await emit_signal(
            db, company_id=company_id, source=SignalSource.TELEMETRY,
            type=SIGNAL_FEE_MISCONFIGURED, trust=SignalTrust.PLATFORM,
            urgency="high", payload=finding.as_payload(),
            dedupe_key=f"{SIGNAL_FEE_MISCONFIGURED}:{company_id}:{period}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("fee-misconfiguration signal skipped: %s", exc)
