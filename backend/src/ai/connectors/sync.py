"""connectors/sync.py — SoR sync-in: external changes → mirror + object.synced.

The inbound half of mastering (§21.2 / §5.4). An external change — from a
connector webhook or the scheduled sweep — reflects into the mirror and enters
the loop as an ``object.synced`` signal, deduped on the external event id so a
webhook retry or an overlapping sweep cannot double-apply. The sweep is
**platform-initiated** (``CONNECTOR_SYNC``, B13): a scheduled poll the tenant did
not ask for draws on the platform envelope, never the tenant wallet.

The connector-specific "what changed" fetch is a :class:`ConnectorSyncSource`
supplied by the adapter (Zoho, T6); this module owns the generic ingest + sweep
loop, so it is provable against a fake source without a live connector (the §9
live-binding boundary).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

from src.ai.connectors.catalog import ConnectorDef

logger = logging.getLogger(__name__)

__all__ = [
    "SyncEvent",
    "ConnectorSyncSource",
    "ingest_external_change",
    "sweep_connector",
]


@dataclass(frozen=True)
class SyncEvent:
    """One external change to reflect into the mirror."""

    object_name: str               # canonical HBS object (e.g. "Invoice")
    external_id: str
    data: dict[str, Any]
    etag: Optional[str] = None
    event_id: Optional[str] = None  # dedupe; defaults to connector:external:etag

    def dedupe_key(self, connector_id: str) -> str:
        return self.event_id or f"{connector_id}:{self.external_id}:{self.etag or ''}"


@runtime_checkable
class ConnectorSyncSource(Protocol):
    """The connector-specific change feed (implemented by an adapter, T6)."""

    async def fetch_changes(self, object_name: str, since: Optional[str]) -> list["SyncEvent"]:
        ...


async def ingest_external_change(
    company_id: uuid.UUID, connector_id: str, event: SyncEvent, *, redis: Any = None,
) -> Optional[uuid.UUID]:
    """Reflect one external change into the mirror + emit object.synced (deduped).

    Returns the emitted signal id, or None when the change was a duplicate (the
    dedupe key already fired) or the emit failed. The mirror upsert and the
    signal live in different planes (tenant DB vs control plane), so they run in
    separate transactions — the mirror is written first, then announced.
    """
    from src.ai.tenant_schema.data_plane import tenant_data_plane
    from src.ai.tenant_schema.record_service import RecordService

    async with tenant_data_plane.session(company_id) as ts:
        svc = RecordService(ts, company_id, redis=redis)
        res = await svc.sync_mirror(
            event.object_name, event.external_id, event.data,
            connector_id=connector_id, etag=event.etag,
        )
        await ts.commit()
        record_id = res.record.id if res.record else None

    return await _emit_synced(company_id, connector_id, event, record_id, redis)


async def _emit_synced(
    company_id: uuid.UUID, connector_id: str, event: SyncEvent,
    record_id: Optional[uuid.UUID], redis: Any,
) -> Optional[uuid.UUID]:
    from src.ai.signals.models import SignalSource, SignalTrust, SignalTypes
    from src.ai.signals.service import emit_signal, enqueue_dispatch
    from src.common.database import AsyncSessionLocal

    payload = {
        "connector": connector_id, "object": event.object_name,
        "external_id": event.external_id, "etag": event.etag,
        "record_id": str(record_id) if record_id else None,
    }
    try:
        async with AsyncSessionLocal() as cp:
            sig_id = await emit_signal(
                cp, company_id=company_id, source=SignalSource.CONNECTOR,
                type=SignalTypes.OBJECT_SYNCED, trust=SignalTrust.INTERNAL,
                payload=payload, dedupe_key=event.dedupe_key(connector_id),
                object_refs=[str(record_id)] if record_id else None,
            )
            await cp.commit()
        if sig_id is not None:
            await enqueue_dispatch(redis, sig_id)
        return sig_id
    except Exception as exc:  # noqa: BLE001 — a sync announce must never crash the sweep
        logger.warning("object.synced emit failed (%s/%s): %s",
                       connector_id, event.external_id, exc)
        return None


async def sweep_connector(
    company_id: uuid.UUID, connector: ConnectorDef, source: ConnectorSyncSource, *,
    since: Optional[str] = None, redis: Any = None,
) -> int:
    """Poll a connector for changes across its mastered objects; ingest each.

    Platform-initiated (``CONNECTOR_SYNC``, B13). Returns the number of changes
    that produced a fresh ``object.synced`` (duplicates are not counted). One
    object's failure never sinks the others.
    """
    ingested = 0
    for object_name in connector.masters:
        try:
            changes = await source.fetch_changes(object_name, since)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sweep fetch failed (%s/%s): %s",
                           connector.connector_id, object_name, exc)
            continue
        for event in changes:
            sig = await ingest_external_change(
                company_id, connector.connector_id, event, redis=redis)
            if sig is not None:
                ingested += 1
    return ingested
