"""twin/materialise.py — filling the glass room, and emptying it again (TWIN T2).

Copying a tenant's whole business database per what-if is exactly the expense
charter decision 7 makes visible, so a scenario declares a **scope** and
materialisation copies only that:

* **always** — `tenant_entity_defs` (the schema itself), which is small and
  which everything else references;
* **in scope** — records of the named objects whose ``updated_at`` falls in the
  window, plus the links between the records actually copied;
* **never** — documents, chunks or embeddings. The twin *reads* the
  control-plane memory store; it does not copy or re-embed it. Re-embedding a
  tenant's library for a what-if would be the single most expensive thing the
  Glasshouse could do and it would buy nothing, because retrieval is not what
  the scenario is varying.

**Why this is raw SQL with interpolated schema names.** T1 found that
``schema_translate_map`` rewrites SQLAlchemy constructs and does *not* touch
textual SQL, so the symbolic ``tenant`` token is unavailable here — and an
``INSERT … SELECT`` between two schemas needs to name both at once anyway,
which no single translate map can express. The schema names are not user input:
they come from ``schema_name_for``, which renders a UUID as hex. Everything a
caller supplies (object names, the window) is bound as a parameter.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Sequence

from sqlalchemy import text

from src.ai.tenant_schema.data_plane import Plane, schema_name_for, tenant_data_plane
from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = ["Scope", "MaterialisationResult", "ScopeRefused", "materialise", "reap"]


class ScopeRefused(ValueError):
    """A scope the Glasshouse will not run.

    Raised rather than silently corrected: §6.1 says the window cap is a
    refusal, not a truncation, because quietly shrinking a window makes two
    runs incomparable without telling anyone.
    """


@dataclass(frozen=True)
class Scope:
    """What a scenario copies into the glass room.

    ``objects`` are HBS object names (``tenant_entity_defs.name``). An empty
    tuple is legitimate and means *schema only* — useful for a scenario that
    varies a charter or a roster and needs the shape but no history.
    """

    objects: tuple[str, ...] = ()
    window_days: int = field(default_factory=lambda: settings.TWIN_DEFAULT_WINDOW_DAYS)

    def validate(self) -> None:
        if self.window_days < 1:
            raise ScopeRefused("window_days must be at least 1")
        if self.window_days > settings.TWIN_MAX_WINDOW_DAYS:
            raise ScopeRefused(
                f"window of {self.window_days} days exceeds the "
                f"{settings.TWIN_MAX_WINDOW_DAYS}-day cap. The cap is a refusal "
                f"rather than a truncation: a silently shortened window would "
                f"make this run incomparable with others without saying so."
            )


@dataclass(frozen=True)
class MaterialisationResult:
    entity_defs: int
    records: int
    links: int

    @property
    def rows(self) -> int:
        return self.entity_defs + self.records + self.links


async def materialise(company_id: uuid.UUID, scope: Scope) -> MaterialisationResult:
    """Copy the scoped slice of a tenant's business into its twin plane.

    Idempotent by construction: the twin is emptied first, so re-materialising
    a scenario produces the same plane rather than a doubled one.
    """
    scope.validate()

    live = schema_name_for(company_id, Plane.LIVE)
    twin = schema_name_for(company_id, Plane.TWIN)

    await tenant_data_plane.ensure_ready(company_id, Plane.LIVE)
    await tenant_data_plane.ensure_ready(company_id, Plane.TWIN)

    if tenant_data_plane.backend == "container":
        # Both planes live in the tenant's own database, so the copy is still a
        # single statement — but the live plane is the default schema there and
        # has no name, which the caller's SQL would have to spell differently.
        # Out of scope until the container backend goes live (it is not the
        # tested default); refusing beats a copy that silently reads the wrong
        # schema.
        raise ScopeRefused(
            "twin materialisation is implemented for the schema backend; the "
            "container backend's live plane is unnamed and needs its own "
            "statement shape (see TWIN §4.2)"
        )

    from src.common.database import engine as control_engine

    async with control_engine.begin() as conn:
        # Empty first, child-to-parent, so a re-run replaces rather than doubles.
        for table in ("tenant_record_links", "tenant_records", "tenant_entity_defs"):
            await conn.execute(text(f'DELETE FROM "{twin}"."{table}"'))

        # The schema itself, ids preserved — record FKs must resolve, and a
        # scenario that compares against the live business has to be talking
        # about the same object definitions.
        defs = await conn.execute(text(
            f'INSERT INTO "{twin}".tenant_entity_defs '
            f'SELECT * FROM "{live}".tenant_entity_defs'
        ))
        def_count = defs.rowcount or 0

        record_count = 0
        link_count = 0
        if scope.objects:
            records = await conn.execute(
                text(
                    f'INSERT INTO "{twin}".tenant_records '
                    f'SELECT r.* FROM "{live}".tenant_records r '
                    f'JOIN "{live}".tenant_entity_defs d ON d.id = r.entity_def_id '
                    f'WHERE d.name = ANY(:objects) '
                    f"  AND r.updated_at >= now() - make_interval(days => :days)"
                ),
                {"objects": list(scope.objects), "days": scope.window_days},
            )
            record_count = records.rowcount or 0

            # Only edges whose *both* ends were copied. A dangling link would
            # violate the FK, and an edge to a record outside the window is not
            # a relationship the scenario can reason about anyway.
            links = await conn.execute(text(
                f'INSERT INTO "{twin}".tenant_record_links '
                f'SELECT l.* FROM "{live}".tenant_record_links l '
                f'WHERE l.src_record_id IN (SELECT id FROM "{twin}".tenant_records) '
                f'  AND l.dst_record_id IN (SELECT id FROM "{twin}".tenant_records)'
            ))
            link_count = links.rowcount or 0

    logger.info(
        "Materialised twin for company %s: %d defs, %d records, %d links "
        "(objects=%s, window=%dd)",
        company_id, def_count, record_count, link_count,
        list(scope.objects), scope.window_days,
    )
    return MaterialisationResult(def_count, record_count, link_count)


async def estimate_rows(company_id: uuid.UUID, scope: Scope) -> int:
    """How many record rows a scope would copy, without copying them (T8).

    Counted against the live plane, so a tenant can be told a what-if's size
    before it spends anything. §6.4: a tenant should never learn a what-if's
    price afterwards.
    """
    scope.validate()
    if not scope.objects:
        return 0

    live = schema_name_for(company_id, Plane.LIVE)
    from src.common.database import engine as control_engine

    async with control_engine.connect() as conn:
        result = await conn.execute(
            text(
                f'SELECT count(*) FROM "{live}".tenant_records r '
                f'JOIN "{live}".tenant_entity_defs d ON d.id = r.entity_def_id '
                f'WHERE d.name = ANY(:objects) '
                f"  AND r.updated_at >= now() - make_interval(days => :days)"
            ),
            {"objects": list(scope.objects), "days": scope.window_days},
        )
        return int(result.scalar() or 0)


async def reap(company_id: uuid.UUID) -> None:
    """Drop a tenant's twin plane (§4.3).

    A twin is per scenario run. A permanent shadow of every tenant would double
    the storage bill of a feature most tenants use occasionally.
    """
    await tenant_data_plane.drop_twin(company_id)
