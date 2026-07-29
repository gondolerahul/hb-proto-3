"""genui/models.py — the tables the Vihara seams own.

SEAM's two (migration ``genui001``): the **echo log** (an act that already
happened, kept so Pragya can learn from it and audit can ask "what was on
screen") and the **push subscriptions** (L8 — a device token in our own
table is what makes the single-writer law enforceable in our own code,
VG-19).

STEWARD's two (migration ``genui002``): the **delivery ledger** (a tray
told to a person once and only once, restart-safe — the reason it is a
table and not a cursor) and the **tray recommendations** (Pragya's one
generated sentence per tray, written once at delivery so re-renders never
re-bill).

There is intentionally no ``ui_manifests`` table (D4 §5.1) — what audit
needs is the certified manifest's hash on the approval and on the echo, and
both carry one.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

__all__ = ["UiEcho", "PushSubscription", "TrayDelivery", "TrayRecommendation"]


class UiEcho(Base):
    """One manual act, told in a sentence (L10, VG-06).

    Append-only; 90-day retention with the reaper **in the producer's own
    path** (`echo.py`), because a reaper on its own schedule is a reaper
    that eventually stops being deployed (the LIB T3 lesson). The query
    text of the act is in ``action_ref.params`` as the surface sent it —
    an echo describes, it never causes.
    """

    __tablename__ = "ui_echoes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    sentence: Mapped[str] = mapped_column(String(500), nullable=False)
    #: {"kind": "register.filter", "surface_id": "hall.accounting", "params": {…}}
    action_ref: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict)
    #: What was on screen when the user did this — the audit pair (D5 §6).
    manifest_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    component_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_ui_echoes_company_created", "company_id", "created_at"),
    )


class PushSubscription(Base):
    """One device's Web Push subscription (VG-19, charter decision 7).

    A row, not a vendor token: self-hosted VAPID means revocation is a
    DELETE and the single-writer law is an import-boundary test rather than
    a promise. ``revoked_at`` keeps the row as history — a push endpoint
    that stops working is worth knowing about, not worth forgetting.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    ua: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )


class TrayDelivery(Base):
    """One tray reached one person (STEWARD S1, migration ``genui002``).

    The grain is **(approval, user)**, and both directions of it matter: a
    user reached once is never notified twice for the same card (the row
    survives a restart, which is why this is not an in-memory cursor), and a
    user who appears *later* — a new phone subscribes, a first socket opens
    — still receives a still-pending card on the next sweep, because no row
    exists for that pair yet. A tray undeliverable today is retried, not
    marked "nowhere" and forgotten.
    """

    __tablename__ = "tray_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    approval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("human_approvals.id"),
        nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    #: "socket" | "push" — the door that actually reached the person.
    via: Mapped[str] = mapped_column(String(16), nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "approval_id", "user_id", name="uq_tray_deliveries_approval_user"),
    )


class TrayRecommendation(Base):
    """Pragya's one advisory sentence on a tray (STEWARD S2, ``genui002``).

    Written **once, at first delivery**, and never after — a recommendation
    appearing under a card the owner already read would look like the
    platform changing its mind after the fact. The primary key is the
    approval id: one card, one sentence, no history. It sits outside the
    certified block's hash by construction (D5 §4.2 — the tray is not
    certified *because of* this field), and nothing anywhere reads it back
    into an execution path.
    """

    __tablename__ = "tray_recommendations"

    approval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("human_approvals.id"), primary_key=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    sentence: Mapped[str] = mapped_column(String(500), nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow)
