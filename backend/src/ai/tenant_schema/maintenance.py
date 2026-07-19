"""tenant_schema/maintenance.py — tenant-DB hibernation + backup crons (§23.4).

These crons are only meaningful under the container backend; under the schema
backend (dev/CI default) they are no-ops. Nightly backup + the tenant-triggered
export both use the same dump path — and the export bundle additionally carries
the control-plane KB+memory dump, since KB/CORTEX are control-plane permanent
(v3.0.6), so tenant portability stays whole.
"""
from __future__ import annotations

import logging
from typing import Any

from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = ["tenant_db_hibernation", "tenant_db_nightly_backup"]


async def tenant_db_hibernation(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: hibernate idle tenant-DB containers past their tier idle window."""
    if settings.TENANT_DB_BACKEND != "container":
        return {"skipped": "schema backend"}
    try:
        from src.ai.tools.sandbox.tenant_db_manager import TenantDatabaseManager

        manager = TenantDatabaseManager()
        paused = await manager.hibernate_idle(settings.TENANT_DB_SOLO_IDLE_SECONDS)
        return {"hibernated": paused}
    except Exception as exc:  # noqa: BLE001
        logger.error("tenant_db_hibernation failed: %s", exc)
        return {"error": str(exc)}


async def tenant_db_nightly_backup(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: nightly encrypted dump per tenant DB to object storage (§23.4).

    Under the schema backend there is no per-tenant container to dump; the
    per-tenant schema is captured by the control-plane DB's own backup, so this
    is a no-op there. Container-backend dump wiring uses ``pg_dump`` against each
    tenant container and is exercised by the export path (see export_service).
    """
    if settings.TENANT_DB_BACKEND != "container":
        return {"skipped": "schema backend (covered by control-plane backup)"}
    from src.ai.tenant_schema.export_service import backup_all_tenants

    count = await backup_all_tenants()
    return {"tenants_backed_up": count}
