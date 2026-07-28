"""Seed Pragya and set up her shared voice line.

Usage, from ``backend/``::

    poetry run python scripts/setup_pragya_voice.py --check
    poetry run python scripts/setup_pragya_voice.py --seed
    poetry run python scripts/setup_pragya_voice.py --seed --company <tenant uuid>
    poetry run python scripts/setup_pragya_voice.py --assign 918065251144 \
        --owner-company <APP company uuid>

``--check`` reports without writing: which tenants have a Pragya, whether the
speech registry rows resolve, and where the number stands. Run it first and
again afterwards — the point of a setup script is that you can see what it did.

**Idempotent throughout.** ``--seed`` skips tenants that already have her;
``--assign`` re-labels a number that is already the shared line rather than
refusing. Running the whole thing twice is a no-op, which is what makes it safe
to run on a machine where you have lost track of what you already did.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from typing import Any

sys.path.insert(0, ".")


async def _check() -> int:
    from sqlalchemy import text

    from src.ai.pragya.channels.routing import PRAGYA_SHARED_LABEL, route_for_number
    from src.ai.pragya.channels.speech import ASR_SKU, TTS_SKU_IN, TTS_SKU_OUT
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        tenants = (await db.execute(text(
            "SELECT id, name FROM companies WHERE type='TENANT' AND status='active' "
            "AND name NOT LIKE 'parity-%' AND name NOT LIKE 'ledger-%' ORDER BY name"
        ))).all()
        with_pragya = {r[0] for r in (await db.execute(text(
            "SELECT DISTINCT company_id FROM hierarchical_entities "
            "WHERE type='AGENT' AND deleted_at IS NULL AND LOWER(name) LIKE '%pragya%'"
        ))).all()}

        print(f"Tenants: {len(tenants)}   with a Pragya: {len(with_pragya)}")
        for cid, name in tenants:
            print(f"  {'✓' if cid in with_pragya else '·'} {name}")

        print("\nSpeech registry rows:")
        for sku in (ASR_SKU, TTS_SKU_IN, TTS_SKU_OUT):
            rows = (await db.execute(text(
                "SELECT company_id, provider_name, model_name, status, service_metadata "
                "FROM integration_registry WHERE service_sku = :sku"
            ), {"sku": sku})).all()
            if not rows:
                print(f"  ✗ {sku}  — MISSING; voice_ready will refuse")
                continue
            meta = rows[0][4] or {}
            region = meta.get("region", "(none — defaults to us-central1)")
            print(f"  ✓ {sku} → {rows[0][1]}/{rows[0][2]} ({rows[0][3]})  "
                  f"project={meta.get('project_id', '—')} region={region}")
            # Chirp 3 is served from the `us`/`eu` **multi-regions**, not from
            # us-central1. A wrong region here does not fail at config time —
            # it fails on the first call, which is the expensive place to find
            # out, so it is called out where somebody will read it.
            if "asr" in sku and region not in ("us", "eu"):
                print(f"      ⚠ Chirp 3 is served from the `us`/`eu` "
                      f"multi-regions — {region!r} will not resolve")

        print("\nShared line:")
        shared = (await db.execute(text(
            "SELECT phone_number, status, company_id FROM phone_numbers "
            "WHERE label = :label"), {"label": PRAGYA_SHARED_LABEL})).all()
        if not shared:
            print("  · none assigned yet")
        for number, status, owner in shared:
            route = await route_for_number(db, str(number))
            print(f"  ✓ {number} ({status}, held by {owner})")
            print(f"    routes → {route.face.value}: {route.reason}")
    return 0


async def _seed(company_id: str | None = None) -> int:
    from src.ai.pragya.seed import seed_pragya, seed_pragya_everywhere
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        if company_id:
            entity, created = await seed_pragya(db, uuid.UUID(company_id))
            await db.commit()
            print(f"{'Seeded' if created else 'Already present:'} Pragya "
                  f"{entity.id} for company {company_id}")
            return 0
        summary = await seed_pragya_everywhere(db)
        await db.commit()
    print(f"Seeded Pragya: {summary['created']} created, "
          f"{summary['already_present']} already present, "
          f"across {summary['companies']} tenants.")
    return 0


async def _assign(number: str, owner_company_id: str) -> int:
    from src.ai.pragya.channels.routing import (
        assign_shared_pragya_number, route_for_number,
    )
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            row = await assign_shared_pragya_number(
                db, phone_number=number,
                owner_company_id=uuid.UUID(owner_company_id))
        except ValueError as exc:
            print(f"✗ {exc}")
            return 1
        await db.commit()
        route = await route_for_number(db, str(row.phone_number))

    print(f"✓ {row.phone_number} is now the shared account-manager line.")
    print(f"  routes → {route.face.value}: {route.reason}")
    print("\n  The line says *which face*; the caller says *which tenant*. A "
          "caller\n  with no verified voice binding reaches no tenant at all "
          "and is capped\n  at T0 — she can greet them and read nothing.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="report state without writing")
    parser.add_argument("--seed", action="store_true",
                        help="give every active tenant a Pragya entity")
    parser.add_argument("--company", metavar="UUID",
                        help="with --seed, seed only this tenant (a dev DB is "
                             "full of leftover test tenants that do not need one)")
    parser.add_argument("--assign", metavar="NUMBER",
                        help="mark NUMBER as the shared account-manager line")
    parser.add_argument("--owner-company", metavar="UUID",
                        help="which company holds the number (required with --assign)")
    args = parser.parse_args()

    if args.assign and not args.owner_company:
        parser.error("--assign needs --owner-company")
    if not (args.check or args.seed or args.assign):
        parser.error("nothing to do — pass --check, --seed or --assign")

    result = 0
    if args.seed:
        result |= asyncio.run(_seed(args.company))
    if args.assign:
        result |= asyncio.run(_assign(args.assign, args.owner_company))
    if args.check:
        result |= asyncio.run(_check())
    return result


if __name__ == "__main__":
    raise SystemExit(main())
