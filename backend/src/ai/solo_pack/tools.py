"""solo_pack/tools.py — the agent tools the Solo Pack entities call.

Two thin tools bridge the curated agents to the Increment-1 substrate:

* ``tenant_record_write`` — create/update a tenant business record through the
  SCH record service (the one write path: validation, ref materialisation,
  CAS, ownership). Runs in the tenant data plane.
* ``emit_business_signal`` — emit a control-plane signal so the bus routes the
  next step (e.g. the gateway's ``lead.inbound``).

Both read ``company_id``/``run_id`` from the execution context the AgentLoop
injects. Within one tenant's own Solo Pack the agents cooperate, so record
writes take the front-door (owner-direct) path; cross-process SoD (owner-
writes/others-propose) is exercised in PACK, not the single-process slice.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Optional

from src.ai.tools.base import Tool

logger = logging.getLogger(__name__)

__all__ = ["TenantRecordWriteTool", "EmitBusinessSignalTool", "register_solo_pack_tools"]


def _err(message: str, code: str = "solo_pack_tool_error") -> str:
    return json.dumps({"error": message, "error_code": code})


class TenantRecordWriteTool(Tool):
    """Create or update a tenant business record (Lead, Opportunity, Quote, …)."""

    name = "tenant_record_write"
    description = (
        "Create or update a business record in the tenant's data (e.g. a Lead, "
        "Opportunity, or Quote). Pass def_name + a data object. To update, pass "
        "record_id + expected_version. Refs to other records are set by putting "
        "the target record's id in the ref field."
    )

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": {
                "def_name": {"type": "string", "description": "object type, e.g. 'Lead'"},
                "data": {"type": "object", "description": "the record fields"},
                "record_id": {"type": "string", "description": "to update an existing record"},
                "expected_version": {"type": "integer", "description": "CAS version for updates"},
            }, "required": ["def_name", "data"]},
        }

    async def run(self, input_data: str) -> str:
        return await self.run_with_context(input_data, None)

    async def run_with_context(self, input_data: str, context: Optional[Dict[str, Any]] = None) -> str:
        try:
            params = json.loads(input_data) if input_data else {}
        except json.JSONDecodeError:
            return _err("invalid JSON input")
        company_id = (context or {}).get("company_id")
        if not company_id:
            return _err("no company_id in context")
        def_name = params.get("def_name")
        data = params.get("data")
        if not def_name or not isinstance(data, dict):
            return _err("def_name and a data object are required")

        cid = uuid.UUID(str(company_id))
        run_id = (context or {}).get("run_id")
        run_uuid = uuid.UUID(str(run_id)) if run_id else None
        try:
            from src.ai.tenant_schema.data_plane import tenant_data_plane
            from src.ai.tenant_schema.record_service import RecordService
            from src.ai.tenant_schema.validation import ValidationError

            async with tenant_data_plane.session(cid) as ts:
                svc = RecordService(ts, cid)
                try:
                    if params.get("record_id"):
                        res = await svc.update(
                            uuid.UUID(str(params["record_id"])), data,
                            expected_version=int(params.get("expected_version", 1)),
                            run_id=run_uuid,
                        )
                    else:
                        res = await svc.create(def_name, data, run_id=run_uuid)
                except ValidationError as ve:
                    return _err(f"validation failed: {'; '.join(ve.errors)}", "validation_error")
                await ts.commit()
            return json.dumps({
                "status": res.status,
                "record_id": str(res.record.id) if res.record else None,
                "version": res.record.version if res.record else None,
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("tenant_record_write failed: %s", exc)
            return _err(str(exc))


class EmitBusinessSignalTool(Tool):
    """Emit a business signal so the loop routes the next step."""

    name = "emit_business_signal"
    description = (
        "Emit a business signal (e.g. 'lead.inbound') so the right process picks "
        "up the next step. Pass type + an optional payload + object_refs (ids of "
        "related records)."
    )

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": {
                "type": {"type": "string", "description": "dotted signal type, e.g. 'lead.inbound'"},
                "payload": {"type": "object"},
                "object_refs": {"type": "array", "items": {"type": "string"}},
                "urgency": {"type": "string", "enum": ["low", "normal", "high", "critical"]},
            }, "required": ["type"]},
        }

    async def run(self, input_data: str) -> str:
        return await self.run_with_context(input_data, None)

    async def run_with_context(self, input_data: str, context: Optional[Dict[str, Any]] = None) -> str:
        try:
            params = json.loads(input_data) if input_data else {}
        except json.JSONDecodeError:
            return _err("invalid JSON input")
        company_id = (context or {}).get("company_id")
        signal_type = params.get("type")
        if not company_id or not signal_type:
            return _err("company_id (context) and type are required")

        cid = uuid.UUID(str(company_id))
        try:
            from src.common.database import AsyncSessionLocal
            from src.ai.signals.models import SignalSource, SignalTrust
            from src.ai.signals.service import emit_signal, enqueue_dispatch

            async with AsyncSessionLocal() as db:
                sig_id = await emit_signal(
                    db, company_id=cid, source=SignalSource.AGENT, type=str(signal_type),
                    trust=SignalTrust.INTERNAL, payload=params.get("payload") or {},
                    object_refs=params.get("object_refs"),
                    urgency=str(params.get("urgency", "normal")),
                )
                await db.commit()
            if sig_id is not None:
                import redis.asyncio as aioredis
                from src.common.config import settings
                redis_pool = aioredis.from_url(settings.REDIS_URL or "redis://localhost:6379")  # type: ignore[no-untyped-call]
                try:
                    await enqueue_dispatch(redis_pool, sig_id)
                finally:
                    await redis_pool.aclose()
            return json.dumps({"signal_id": str(sig_id) if sig_id else None})
        except Exception as exc:  # noqa: BLE001
            logger.warning("emit_business_signal failed: %s", exc)
            return _err(str(exc))


def register_solo_pack_tools() -> None:
    """Register the Solo Pack tools globally (idempotent)."""
    from src.ai.tools.base import ToolRegistry

    for tool in (TenantRecordWriteTool(), EmitBusinessSignalTool()):
        ToolRegistry.register(tool)
