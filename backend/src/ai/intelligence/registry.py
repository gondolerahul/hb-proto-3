"""intelligence/registry.py — the model-registry service (REG T2/T3).

* ``install_model_catalog`` — the idempotent reconciler. Upserts ``catalog.FLEET``
  by the uniqueness key; opens a price window per component; on a *changed*
  price it closes the open window and inserts a new one (never mutates). Safe to
  re-run on every deploy — an unchanged catalog is a no-op.
* ``eligible`` — the router's candidate query. The **only** place candidate
  filtering happens (allow-list + modality + context), so a disallowed provider
  is never even a candidate (D5, §3.4 of the tech doc).
* ``resolve_price`` — the effective-dated point-in-time price lookup (the B12
  reproducibility fix).
* ``capability_profile`` — what ``scoring.utility`` reads.

Design: docs/product-road-map/increment-5/01_model_registry.md §5, §6.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.intelligence.admission import AdmissionResult, ModelEval, SuiteSet
from src.ai.intelligence.catalog import FLEET, PRICE_EPOCH, ModelSpec
from src.ai.intelligence.models import ModelPrice, ModelRegistry, ModelStatus

__all__ = ["RegistryService", "InstallReport"]


@dataclass
class InstallReport:
    inserted: int = 0
    updated: int = 0
    price_windows_opened: int = 0


@dataclass
class BackfillReport:
    bound: int = 0          # matched a single active catalog row, model_registry_id set
    unmatched: int = 0      # no catalog row for (provider, model_name) — stays NULL (ops reconciles)
    ambiguous: int = 0      # several catalog rows matched (regions/versions) — left for ops to pick
    skipped_no_model: int = 0


class RegistryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- seeding -----------------------------------------------------------

    async def install_model_catalog(
        self, specs: Sequence[ModelSpec] = FLEET, *, now: datetime | None = None
    ) -> InstallReport:
        """Reconcile the DB catalog from declared data. Idempotent."""
        now = now or datetime.utcnow()
        report = InstallReport()

        for spec in specs:
            row = (await self.db.execute(
                select(ModelRegistry).where(
                    ModelRegistry.provider == spec.provider,
                    ModelRegistry.model_name == spec.model_name,
                    ModelRegistry.version == spec.version,
                    ModelRegistry.region == spec.region,
                )
            )).scalar_one_or_none()

            if row is None:
                row = ModelRegistry(
                    model_key=spec.model_key,
                    provider=spec.provider,
                    model_name=spec.model_name,
                    version=spec.version,
                    region=spec.region,
                    capability_profile=spec.capability_profile,
                    data_flow=spec.data_flow,
                    status=spec.status,
                )
                self.db.add(row)
                await self.db.flush()  # assign row.id
                report.inserted += 1
            else:
                # Catalog facts are the seeder's to own; the *status* is not —
                # a preview->active flip is EVX's/admin's, so re-seeding leaves it.
                row.model_key = spec.model_key
                row.capability_profile = spec.capability_profile
                row.data_flow = spec.data_flow
                report.updated += 1

            for px in spec.prices:
                if await self._reconcile_price(
                    row.id, px.component_type, px.unit_price, px.cost_unit, px.currency, now
                ):
                    report.price_windows_opened += 1

        await self.db.commit()
        return report

    async def _reconcile_price(
        self, model_id: uuid.UUID, component_type: str,
        unit_price: Any, cost_unit: str, currency: str, now: datetime,
    ) -> bool:
        """Ensure an open price window matches the declared price. Returns True
        if a window was opened (new model, or a price change closed+reopened)."""
        windows = (await self.db.execute(
            select(ModelPrice).where(
                ModelPrice.model_registry_id == model_id,
                ModelPrice.component_type == component_type,
            ).order_by(ModelPrice.effective_from.desc())
        )).scalars().all()

        open_window = next((w for w in windows if w.effective_to is None), None)

        if open_window is None:
            # No live window: open at the epoch if this component is brand new,
            # else at `now` (a gap being healed).
            effective_from = PRICE_EPOCH if not windows else now
            self.db.add(ModelPrice(
                model_registry_id=model_id, component_type=component_type,
                unit_price=unit_price, cost_unit=cost_unit, currency=currency,
                effective_from=effective_from, effective_to=None,
            ))
            return True

        if (open_window.unit_price != unit_price
                or open_window.cost_unit != cost_unit
                or open_window.currency != currency):
            # Price changed: close the current window, open a new one. History
            # is preserved so a past invoice still resolves the old window.
            open_window.effective_to = now
            self.db.add(ModelPrice(
                model_registry_id=model_id, component_type=component_type,
                unit_price=unit_price, cost_unit=cost_unit, currency=currency,
                effective_from=now, effective_to=None,
            ))
            return True

        return False  # unchanged — idempotent no-op

    # -- backfill ----------------------------------------------------------

    async def backfill_integration_bindings(self) -> BackfillReport:
        """Bind existing per-company IntegrationRegistry rows to their catalog
        row by (provider, model_name). Only an *unambiguous* single active match
        binds; unmatched (old model not in the catalog) and ambiguous (several
        regions/versions) rows stay NULL for ops to reconcile — never a guess.
        Never changes credentials or cost; only sets the attribution link."""
        from src.config.models import IntegrationRegistry  # local: keeps this module import-light

        report = BackfillReport()
        rows = (await self.db.execute(
            select(IntegrationRegistry).where(IntegrationRegistry.model_registry_id.is_(None))
        )).scalars().all()

        for ir in rows:
            if not ir.model_name:
                report.skipped_no_model += 1
                continue
            matches = (await self.db.execute(
                select(ModelRegistry).where(
                    ModelRegistry.provider == ir.provider_name,
                    ModelRegistry.model_name == ir.model_name,
                    ModelRegistry.status == ModelStatus.ACTIVE,
                )
            )).scalars().all()
            if len(matches) == 1:
                # config.IntegrationRegistry is legacy Column-style (not Mapped),
                # so a direct attribute write trips mypy --strict; setattr is the
                # clean cross-boundary write.
                setattr(ir, "model_registry_id", matches[0].id)
                report.bound += 1
            elif not matches:
                report.unmatched += 1
            else:
                report.ambiguous += 1

        await self.db.commit()
        return report

    # -- router-facing reads ----------------------------------------------

    async def eligible(
        self, *, modality: str = "text", min_context: int = 0,
        allow_list: Sequence[str] | None = None,
    ) -> list[ModelRegistry]:
        """Active catalog rows a router step may select. Allow-list + modality +
        context filter here — the single candidate gate."""
        stmt = select(ModelRegistry).where(ModelRegistry.status == ModelStatus.ACTIVE)
        if allow_list is not None:
            stmt = stmt.where(ModelRegistry.provider.in_(list(allow_list)))
        rows = (await self.db.execute(stmt)).scalars().all()

        out: list[ModelRegistry] = []
        for r in rows:
            cap: dict[str, Any] = r.capability_profile or {}
            if modality not in (cap.get("modalities") or []):
                continue
            if int(cap.get("max_context", 0)) < min_context:
                continue
            out.append(r)
        return out

    async def resolve_price(
        self, model_registry_id: uuid.UUID, component_type: str, at: datetime,
    ) -> ModelPrice | None:
        """The effective-dated window whose [effective_from, effective_to)
        contains ``at`` — the point-in-time price for reproducible billing."""
        return (await self.db.execute(
            select(ModelPrice).where(
                ModelPrice.model_registry_id == model_registry_id,
                ModelPrice.component_type == component_type,
                ModelPrice.effective_from <= at,
                (ModelPrice.effective_to.is_(None)) | (ModelPrice.effective_to > at),
            ).order_by(ModelPrice.effective_from.desc()).limit(1)
        )).scalar_one_or_none()

    async def capability_profile(self, model_registry_id: uuid.UUID) -> dict[str, Any]:
        row = (await self.db.execute(
            select(ModelRegistry).where(ModelRegistry.id == model_registry_id)
        )).scalar_one_or_none()
        return dict(row.capability_profile) if row and row.capability_profile else {}

    # -- gated activation (EVX) -------------------------------------------

    async def activate(
        self, model_registry_id: uuid.UUID, *,
        candidate: "ModelEval", incumbent: "ModelEval", suites: "SuiteSet",
        task_classes: Sequence[str] = (),
    ) -> "AdmissionResult":
        """Flip a catalog model to ACTIVE **only** through the §22.4 admission
        gate. On a failed admission the model is left as-is — router preference
        can never override a refusal (the gate is in the mutation path, EVX §8).
        The audit signal is persisted whether or not the flip happens."""
        from src.ai.intelligence.admission import admit_model_change

        result = await admit_model_change(
            self.db, model_id=model_registry_id, candidate=candidate,
            incumbent=incumbent, suites=suites, task_classes=task_classes)
        if result.admitted:
            model = (await self.db.execute(
                select(ModelRegistry).where(ModelRegistry.id == model_registry_id)
            )).scalar_one_or_none()
            if model is not None:
                model.status = ModelStatus.ACTIVE
        await self.db.commit()   # persist the audit signal (+ the flip if admitted)
        return result
