"""memory/retrieval_filters.py — metadata predicates for retrieval (RETR T3).

Technical §24.4 asks that retrieval accept metadata predicates so *"invoices for
Acme since March"* **filters before it ranks** rather than ranking the whole
corpus and hoping the right documents float up. Filtering first is not just
faster — it is more correct: a top-50 candidate depth spent on the wrong date
range cannot be recovered by any amount of fusion or reranking downstream.

These compose with, and never replace, the Inc-1 **domain viewport**
(``memory/domain_viewport.py``). The viewport is a need-to-know boundary and is
enforced after fusion regardless of what predicates a caller passed; these
filters are about relevance, not permission. A caller cannot widen its viewport
by passing filters, and a caller that passes none still gets viewport-scoped
results.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Sequence

__all__ = ["ChunkFilters"]


@dataclass(frozen=True)
class ChunkFilters:
    """Predicates applied inside the retrieval SQL, before ranking.

    Every field is optional; an empty instance renders no SQL at all, so the
    unfiltered path costs nothing. Values are always bound as parameters — the
    rendered fragment contains no caller-supplied text.
    """

    file_types: Optional[Sequence[str]] = None
    document_ids: Optional[Sequence[uuid.UUID]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    filename_contains: Optional[str] = None

    def is_empty(self) -> bool:
        return not any((
            self.file_types, self.document_ids, self.created_after,
            self.created_before, self.filename_contains,
        ))

    def to_sql(self) -> tuple[str, dict[str, Any]]:
        """Render as an ``AND``-prefixed SQL fragment plus its bound parameters.

        The fragment is spliced into the retrieval queries' WHERE clause, so it
        must be self-contained and start with ``AND``. Parameter names are
        prefixed ``f_`` to keep them clear of the queries' own binds.
        """
        clauses: list[str] = []
        params: dict[str, Any] = {}

        if self.file_types:
            clauses.append("d.file_type = ANY(:f_file_types)")
            params["f_file_types"] = list(self.file_types)

        if self.document_ids:
            clauses.append("d.id = ANY(CAST(:f_document_ids AS uuid[]))")
            params["f_document_ids"] = [str(d) for d in self.document_ids]

        if self.created_after is not None:
            clauses.append("d.created_at >= :f_created_after")
            params["f_created_after"] = self.created_after

        if self.created_before is not None:
            clauses.append("d.created_at <= :f_created_before")
            params["f_created_before"] = self.created_before

        if self.filename_contains:
            clauses.append("d.filename ILIKE :f_filename")
            params["f_filename"] = f"%{self.filename_contains}%"

        if not clauses:
            return "", {}
        return "AND " + " AND ".join(clauses), params
