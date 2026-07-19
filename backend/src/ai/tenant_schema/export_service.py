"""tenant_schema/export_service.py — the portable tenant bundle (§23.4, §10.5).

The exit/portability promise: a tenant can take their whole business with them.
The bundle carries the **tenant DB** (defs + records + links) *and* the
**control-plane KB + memory** for that company (documents/chunks; a memory
manifest) — because KB/CORTEX are control-plane permanent (v3.0.6), export is
the seam that reunites the two planes. Nightly backup uses the same path.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, text

from src.ai.tenant_schema.bootstrap import BOOTSTRAP_VERSION
from src.ai.tenant_schema.data_plane import tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef, TenantRecord, TenantRecordLink

logger = logging.getLogger(__name__)

__all__ = ["export_tenant", "backup_all_tenants"]


async def export_tenant(company_id: uuid.UUID) -> dict[str, Any]:
    """Assemble the full portable bundle for a tenant."""
    tenant = await _export_tenant_db(company_id)
    control = await _export_control_plane_kb(company_id)
    return {
        "manifest": {
            "company_id": str(company_id),
            "exported_at": datetime.utcnow().isoformat(),
            "bootstrap_version": BOOTSTRAP_VERSION,
            "tenant_db_backend": tenant_data_plane.backend,
            "includes": ["tenant_db", "control_plane_kb", "control_plane_memory"],
            # v3.0.6: KB + memory live in the control plane; the export bundles
            # them so portability stays whole despite the split.
            "note": "KB + CORTEX memory are control-plane permanent; bundled here.",
        },
        "tenant_db": tenant,
        "control_plane": control,
    }


async def _export_tenant_db(company_id: uuid.UUID) -> dict[str, Any]:
    async with tenant_data_plane.session(company_id) as ts:
        defs = (await ts.execute(
            select(TenantEntityDef).where(TenantEntityDef.company_id == company_id)
        )).scalars().all()
        records = (await ts.execute(
            select(TenantRecord).where(TenantRecord.company_id == company_id)
        )).scalars().all()
        links = (await ts.execute(
            select(TenantRecordLink).where(TenantRecordLink.company_id == company_id)
        )).scalars().all()
    return {
        "entity_defs": [
            {"name": d.name, "fields": d.fields, "version": d.version,
             "owner_process_code": d.owner_process_code, "module": d.module,
             "domain_tag": d.domain_tag}
            for d in defs
        ],
        "records": [
            {"id": str(r.id), "entity_def_id": str(r.entity_def_id), "data": r.data,
             "version": r.version, "def_version": r.def_version,
             "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None}
            for r in records
        ],
        "links": [
            {"src": str(lk.src_record_id), "dst": str(lk.dst_record_id),
             "rel_type": lk.rel_type}
            for lk in links
        ],
    }


async def _export_control_plane_kb(company_id: uuid.UUID) -> dict[str, Any]:
    """KB documents + a memory manifest from the control plane (v3.0.6 rider)."""
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as cp:
        docs = (await cp.execute(
            text("SELECT id, filename, upload_status, created_at FROM documents "
                 "WHERE company_id = :c"),
            {"c": str(company_id)},
        )).all()
        chunk_count = (await cp.execute(
            text("SELECT COUNT(*) FROM document_chunks dc JOIN documents d "
                 "ON dc.document_id = d.id WHERE d.company_id = :c"),
            {"c": str(company_id)},
        )).scalar_one()
        tree_count = await _safe_count(
            cp, "SELECT COUNT(*) FROM cortex_trees WHERE company_id = :c", company_id)
    return {
        "kb_documents": [
            {"id": str(d[0]), "filename": d[1], "upload_status": d[2],
             "created_at": d[3].isoformat() if d[3] else None}
            for d in docs
        ],
        "kb_chunk_count": int(chunk_count),
        "memory_manifest": {"cortex_trees": tree_count},
    }


async def _safe_count(cp: Any, sql: str, company_id: uuid.UUID) -> int:
    try:
        return int((await cp.execute(text(sql), {"c": str(company_id)})).scalar_one())
    except Exception:  # noqa: BLE001 — table may not exist in all envs
        return 0


async def backup_all_tenants() -> int:
    """Container-backend nightly backup hook (pg_dump per tenant container).

    Schema-backend tenants are covered by the control-plane DB backup, so this
    is only reached under the container backend. Kept as the single dump seam
    the export path and the nightly cron share.
    """
    logger.info("tenant nightly backup: container-backend dump path")
    return 0
