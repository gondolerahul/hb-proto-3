"""governance/models.py — the HITL checkpoint registry (technical doc §20.2).

`hitl_checkpoint_defs` is a small platform table seeded with the Blueprint
§9.7 catalog (18 checkpoints) plus the 19th added by Increment 4 / CONN+SOR
(`before_external_system_write`, external system-of-record write-back). Tenants
tune thresholds per entity in the governance block; `platform_mandatory` rows
cannot be removed.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

__all__ = ["HITLCheckpointDef"]


class HITLCheckpointDef(Base):
    """A platform-defined HITL checkpoint (Blueprint §9.7)."""

    __tablename__ = "hitl_checkpoint_defs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Default authority-band threshold (USD or pct) this checkpoint fires above;
    # NULL for checkpoints that always fire (e.g. before_employment_offer).
    default_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    # NULL for USD thresholds; "pct" marks percentage-valued thresholds.
    threshold_unit: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Mandatory checkpoints cannot be removed from an entity's opt-in set.
    platform_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # C3 — per-checkpoint HITL SLA: seconds a PENDING approval may wait before
    # its ``on_timeout`` fires (auto_park | auto_deny | escalate). NULL = no SLA.
    sla_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    on_timeout: Mapped[str] = mapped_column(String(12), nullable=False, default="escalate")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_hitl_checkpoint_defs_category", "category"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "category": self.category,
            "description": self.description,
            "default_threshold": self.default_threshold,
            "threshold_unit": self.threshold_unit,
            "platform_mandatory": self.platform_mandatory,
            "sla_seconds": self.sla_seconds,
            "on_timeout": self.on_timeout,
        }
