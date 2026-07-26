"""connectors/credential_expiry.py — the bridge, before it breaks (LIB T8, VG-16).

`connector_bindings.status` records that a binding has broken. Nothing recorded
that one is *about to*, so an OAuth token expiring overnight became a total,
silent outage of that connector until somebody noticed the work had stopped.
Spec §15.2's "bridge under repair" tray needs the warning, and a warning that
arrives after the break is not a warning.

**Deliberately narrow.** This module notices and emits; it does not refresh
tokens, does not disable bindings, and does not decide what a tray looks like.
A sweep that quietly re-authenticated on the tenant's behalf would be doing
credential management by side effect.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = ["DEFAULT_WARN_DAYS", "expiring_bindings", "sweep_expiring_credentials"]

#: How far ahead to warn. Two weeks is chosen against the human cost of the
#: fix rather than the technical one: re-authorising a SharePoint connector may
#: need an administrator the tenant does not employ, and a three-day notice
#: assumes a responsiveness a small business does not have.
DEFAULT_WARN_DAYS = 14


async def expiring_bindings(
    db: AsyncSession, *, warn_days: int = DEFAULT_WARN_DAYS,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Bindings whose credentials expire inside the window, already-expired first.

    NULL `credentials_expire_at` is skipped, not warned about: an API key with
    no expiry is the common case and warning about it every day would train
    every tenant to ignore this signal.
    """
    at = now or datetime.utcnow()
    horizon = at + timedelta(days=warn_days)
    rows = (await db.execute(text("""
        SELECT id, company_id, connector_id, status, credentials_expire_at
        FROM connector_bindings
        WHERE credentials_expire_at IS NOT NULL
          AND credentials_expire_at <= :horizon
        ORDER BY credentials_expire_at
    """), {"horizon": horizon})).mappings().all()

    return [{
        "binding_id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "connector_id": row["connector_id"],
        "status": row["status"],
        "expires_at": row["credentials_expire_at"].isoformat(),
        "days_remaining": (row["credentials_expire_at"] - at).days,
        "already_expired": row["credentials_expire_at"] <= at,
    } for row in rows]


async def sweep_expiring_credentials(
    db: AsyncSession, *, warn_days: int = DEFAULT_WARN_DAYS,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Emit one `connector.credentials_expiring` per at-risk binding, per day.

    Deduped on binding **and day** so a fortnight's warning is a fortnight of
    daily notices rather than fourteen notices at once — and so a restarted
    worker does not re-announce everything it already announced this morning.
    """
    from src.ai.signals.models import SignalSource, SignalTrust, SignalTypes
    from src.ai.signals.service import emit_signal

    at = now or datetime.utcnow()
    at_risk = await expiring_bindings(db, warn_days=warn_days, now=at)

    emitted = 0
    for binding in at_risk:
        try:
            signal_id = await emit_signal(
                db, company_id=binding["company_id"],
                source=SignalSource.CONNECTOR,
                type=SignalTypes.CONNECTOR_CREDENTIALS_EXPIRING,
                trust=SignalTrust.PLATFORM,
                payload=binding,
                dedupe_key=f"cred-expiry:{binding['binding_id']}:{at.date().isoformat()}",
            )
            if signal_id is not None:
                emitted += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("credential-expiry emit failed for binding %s: %s",
                           binding["binding_id"], exc)
    return {"at_risk": len(at_risk), "emitted": emitted,
            "warn_days": warn_days}
