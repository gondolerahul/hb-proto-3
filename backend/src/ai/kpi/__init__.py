"""ai/kpi — the C6 KPI registry and its computation.

The Blueprint names KPIs and their source processes but gives no formulas.
Pragya reports these numbers in stage 9, so the definitions have to exist
before her reporting means anything — that gap is register finding C6, and
this package closes it.

The rule that shapes the package: **a KPI whose prerequisites are unmet
reports what is missing, never a number.** See `compute.KpiResult`.
"""
from __future__ import annotations

__all__ = [
    "KPI_DEFINITIONS",
    "KpiDefinition",
    "KpiResult",
    "compute_all",
    "compute_one",
    "definition_for",
]

from src.ai.kpi.compute import KpiResult, compute_all, compute_one
from src.ai.kpi.definitions import KPI_DEFINITIONS, KpiDefinition, definition_for
