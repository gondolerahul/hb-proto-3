"""pragya/models.py — engagement persistence (migration ``prag001``).

One row per company: where the engagement has reached and everything it has
learned. ``artifacts`` is a JSON document keyed by the artifact names the
stage scripts declare (``assumptions.list``, `analysis.verdicts`, …) — a
schema-per-artifact would freeze the scripts, which are reviewed assets meant
to evolve.

The authentication state deliberately does **not** live here. Sessions belong
to AUTH's ``account_manager_sessions``; Pragya reads them through AUTH's API
and never writes an auth level herself, so there is exactly one place that can
decide how well-authenticated a conversation is.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

# FK targets registered before mapper configuration.
from src.auth.models import Company, User  # noqa: F401

__all__ = ["PragyaEngagement", "PragyaTurn"]


class PragyaEngagement(Base):
    """The engagement state for one company."""

    __tablename__ = "pragya_engagements"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_pragya_engagement_company"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    stage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Artifact bag keyed by the names the stage scripts declare.
    artifacts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict)
    #: Every stage entry, so the engagement can explain how it got here.
    stage_history: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PragyaTurn(Base):
    """One turn of conversation, kept for continuity and for eval goldens.

    Stored rather than held in memory because the engagement spans months and
    channels: a conversation started in the console continues on WhatsApp, and
    stage 4's re-entry needs to know what was already said.
    """

    __tablename__ = "pragya_turns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    stage: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)  # user|pragya
    content: Mapped[str] = mapped_column(Text, nullable=False)
    #: Set when the turn carried a command: the classified tier and outcome.
    intent_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(4), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
