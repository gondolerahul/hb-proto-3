#!/usr/bin/env python3
"""
record_golden_runs.py — Run the LEGACY ExecutionEngine against each
regression-suite fixture+input pair and save the resulting RunResult
to disk as a "golden" snapshot.

Track 2's parity tests load these snapshots and assert the new
AgentLoop reaches the same status, similar cost, and similar output
without needing a fresh LLM-credit-burning legacy run on every PR.

Usage:
    cd backend
    source .venv/bin/activate
    python -m backend.scripts.record_golden_runs \\
        --output backend/tests/parity/goldens \\
        --cases simple_skill_topic_easy research_agent_brief

Environment requirements:
    * DATABASE_URL — Postgres reachable from this host.
    * REDIS_URL    — Redis reachable from this host.
    * LLM provider env vars (ANTHROPIC_API_KEY, etc.) — real LLM calls
      will be made.

The recorder seeds a fresh test tenant, inserts the entity fixture,
creates an ExecutionRun, runs ExecutionEngine.execute_run, then writes
the snapshot. It does NOT clean up — the operator is expected to use
a throw-away test database.

This script is INTENTIONALLY one-shot. It is not invoked by CI. The
recorded JSON snapshots are checked into the repo at
``backend/tests/parity/goldens/<case_id>.json``.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("record_golden_runs")


async def _record_one(case_id: str, output_dir: Path) -> bool:
    """Record one case. Returns True on success."""
    # Imports are local so the script can be inspected (--help) even
    # when the DB / Redis env is unset.
    from sqlalchemy import select

    from src.ai.core.execution_engine import ExecutionEngine
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.orm.execution import ExecutionRun
    from src.common.database import AsyncSessionLocal

    from tests.harness import load_entity_fixture
    from tests.parity.extract import extract_run_result
    from tests.regression.loader import load_case

    case_path = REPO_ROOT / "backend" / "tests" / "regression" / "cases" / f"{case_id}.yaml"
    if not case_path.exists():
        logger.error("Case file not found: %s", case_path)
        return False

    case = load_case(case_path)
    entity_dto = load_entity_fixture(case.entity_fixture)

    import redis.asyncio as aioredis
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    redis_client = await aioredis.from_url(redis_url)

    async with AsyncSessionLocal() as db:
        company_id = uuid.UUID(os.environ.get(
            "GOLDEN_COMPANY_ID",
            "00000000-0000-0000-0000-00000000a000",
        ))
        # Insert (or reuse) the entity row.
        existing = (await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.company_id == company_id,
                HierarchicalEntity.name == entity_dto.name,
            )
        )).scalars().first()

        if existing:
            entity_id = existing.id
            logger.info("Reusing entity %s (%s)", entity_dto.name, entity_id)
        else:
            entity_row = HierarchicalEntity(
                id=uuid.uuid4(),
                company_id=company_id,
                name=entity_dto.name,
                display_name=entity_dto.display_name,
                description=entity_dto.description,
                goal=entity_dto.goal,
                type=entity_dto.type.value,
                status=entity_dto.status.value,
                version=entity_dto.version,
                tags=entity_dto.tags,
                identity=entity_dto.identity,
                hierarchy=entity_dto.hierarchy.model_dump() if entity_dto.hierarchy else None,
                logic_gate=entity_dto.logic_gate.model_dump() if entity_dto.logic_gate else None,
                planning=entity_dto.planning.model_dump() if entity_dto.planning else None,
                capabilities=entity_dto.capabilities.model_dump() if entity_dto.capabilities else None,
                governance=entity_dto.governance.model_dump() if entity_dto.governance else None,
                io_contract=entity_dto.io_contract.model_dump() if entity_dto.io_contract else None,
                observability=entity_dto.observability.model_dump() if entity_dto.observability else None,
                metadata_extensions=entity_dto.metadata_extensions,
            )
            db.add(entity_row)
            await db.commit()
            entity_id = entity_row.id
            logger.info("Created entity %s (%s)", entity_dto.name, entity_id)

        # Seed the run.
        run_row = ExecutionRun(
            id=uuid.uuid4(),
            entity_id=entity_id,
            company_id=company_id,
            status="PENDING",
            input_data=case.input,
        )
        db.add(run_row)
        await db.commit()
        run_id = run_row.id
        logger.info("Created run %s for case %s", run_id, case_id)

        # Execute via LEGACY engine — this writes status, cost, logs.
        logger.info("Executing legacy ExecutionEngine ...")
        engine = ExecutionEngine(db, redis_client)
        try:
            await engine.execute_run(run_id)
        except Exception:
            logger.exception("Legacy run raised — recording partial snapshot anyway")

        # Re-fetch + extract.
        await db.refresh(run_row)
        rr = await extract_run_result(db, str(run_id))
        snapshot_path = output_dir / f"{case_id}.json"
        rr.save(snapshot_path)
        logger.info(
            "Saved golden snapshot: %s  (status=%s cost=$%.4f steps=%d)",
            snapshot_path, rr.status, rr.total_cost_usd, rr.step_count,
        )

    await redis_client.aclose()
    return True


async def _main(args: Any) -> int:
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.cases:
        case_ids = list(args.cases)
    else:
        # Default: every case YAML on disk.
        cases_dir = REPO_ROOT / "backend" / "tests" / "regression" / "cases"
        case_ids = [p.stem for p in sorted(cases_dir.glob("*.yaml"))]

    if not case_ids:
        logger.error("No cases to record.")
        return 1

    failures = 0
    for cid in case_ids:
        logger.info("=== Recording golden for %s ===", cid)
        ok = await _record_one(cid, output_dir)
        if not ok:
            failures += 1
    return 0 if failures == 0 else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "backend" / "tests" / "parity" / "goldens"),
        help="Directory to write <case_id>.json snapshots into.",
    )
    parser.add_argument(
        "--cases",
        nargs="*",
        default=None,
        help="Specific case ids to record. Default: every YAML under "
             "backend/tests/regression/cases/.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(asyncio.run(_main(args)))
