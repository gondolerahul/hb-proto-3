"""seed_model_catalog.py — reconcile the model_registry catalog from declared data.

Idempotent: re-run on every deploy to pick up ``ai/intelligence/catalog.py``
changes. A new model is inserted; a changed price closes the open window and
opens a new one; an unchanged catalog is a no-op.

    poetry run python scripts/seed_model_catalog.py

REG (Increment 5 / B12). The tables are created by migration ``reg001``; this
seeds their contents (control-plane reference data — the pattern the shipped
HITL-checkpoint seed follows, but reconciling rather than one-shot).
"""
import asyncio

import src.ai.orm  # noqa: F401 — register every ORM mapper (auth/config/...) before any query
from src.common.database import AsyncSessionLocal
from src.ai.intelligence.registry import RegistryService


async def main() -> None:
    async with AsyncSessionLocal() as db:
        svc = RegistryService(db)
        report = await svc.install_model_catalog()
        # Bind existing per-company integrations to their catalog row (attribution
        # linkage; never touches credentials or cost).
        backfill = await svc.backfill_integration_bindings()
    print(
        f"model catalog reconciled: "
        f"inserted={report.inserted} updated={report.updated} "
        f"price_windows_opened={report.price_windows_opened}"
    )
    print(
        f"integration bindings backfilled: bound={backfill.bound} "
        f"unmatched={backfill.unmatched} ambiguous={backfill.ambiguous} "
        f"skipped_no_model={backfill.skipped_no_model}"
    )


if __name__ == "__main__":
    asyncio.run(main())
