"""solo_pack/templates/intelligence — P19 Sense-Decide-Optimize.

The read-all planner: gather KPIs across the record graph, roll a cash
forecast, and propose recommendations into Sheel's decision loop. Owns no HBS
object and mutates nothing directly — every outward change is a proposal or a
HITL. Sheet: 03a §5.

(Overview §2 loosely calls P19 "owner of Budget"; the HBS spine assigns Budget
to the Plan-Budget-Forecast process, not Wave-0. P19 ships read-all — its
owner-code resolves to no objects, which is correct.)
"""
from __future__ import annotations

from typing import Any

from src.ai.solo_pack.templates._shared import REACT

__all__ = ["P19_OPTIMIZE", "AGT_051", "INTELLIGENCE_TEMPLATES"]


# ── P19 Sense-Decide-Optimize (PROCESS — read-all planner) ──────────────────
P19_OPTIMIZE: dict[str, Any] = {
    "name": "p19-sense-decide-optimize",
    "display_name": "Sense-Decide-Optimize",
    "description": "The read-all planner: gather KPIs, forecast, and propose. "
                   "Owns no records; reads across the graph.",
    "goal": "On the heartbeat cadence, gather KPIs and roll a cash forecast, "
            "then propose recommendations into Sheel's decision loop.",
    "type": "PROCESS",
    "version": "1.0.0",
    "status": "ACTIVE",
    "tags": ["solo_pack", "process", "process_code:P19"],
    "identity": {
        "role": "Sense-Decide-Optimize Process",
        "system_prompt": (
            "You run the tenant's decision loop. On the heartbeat, dispatch the Cashflow "
            "Forecaster to gather KPIs and forecast the cash position, then surface "
            "recommendations to Sheel. You own no records — you read across the business and "
            "propose; you never write another owner's data directly."
        ),
    },
    "logic_gate": REACT,
    "planning": {
        "static_plan": {
            "enabled": True,
            "steps": [{
                "step_id": "optimize", "order": 1, "name": "Gather, forecast, propose",
                "type": "CHILD_ENTITY_INVOCATION",
                "target": {"entity_name_hint": "agt-051-cashflow-forecaster"}, "required": True,
            }],
        },
        "dynamic_planning": {"enabled": False},
    },
    "capabilities": {"memory": {"enabled": True, "mode": "CORTEX"}},
    "governance": {
        "autonomy_level": "A1",
        "sod_class": "none",
        "memory_domains": ["general", "financial"],
        "max_cost_usd": 1.00,
        "max_concurrent_children": 1,
    },
    "io_contract": {"input_schema": {"type": "object", "properties": {"signal": {"type": "object"}}},
                    "output_schema": {"type": "object", "properties": {"forecast": {"type": "object"}}}},
    "metadata_extensions": {
        "process_code": "P19",
        "owns_objects": [],  # read-all planner — owns nothing
        "trigger_patterns": ["schedule.optimize"],
    },
}


# ── AGT-051 Cashflow Forecaster (AGENT under P19) ───────────────────────────
AGT_051: dict[str, Any] = {
    "name": "agt-051-cashflow-forecaster",
    "display_name": "Cashflow Forecaster",
    "description": "Rolls KPIs and a cash-position forecast for the decision loop.",
    "goal": "Read invoices, payments, ledger, and budget; forecast the cash "
            "position; and propose recommendations — flagging shortfalls.",
    "type": "AGENT",
    "version": "1.0.0",
    "status": "ACTIVE",
    "tags": ["solo_pack", "workforce", "intelligence", "agent_code:AGT-051"],
    "identity": {
        "role": "Cashflow Forecaster",
        "system_prompt": (
            "You forecast cash. Read the receivables, payments, ledger, and budget, project "
            "the cash position over the coming periods, and summarise KPIs for Sheel. If you "
            "foresee a shortfall, propose raising a Risk and notify — you read and recommend, "
            "you do not move money or edit another owner's records. Be honest about confidence "
            "when data is thin."
        ),
        "personality": {"tone": "analytical", "decision_confidence": 0.65},
    },
    "logic_gate": REACT,
    "planning": {"static_plan": {"enabled": True, "steps": [{
        "step_id": "forecast", "order": 1, "name": "Gather KPIs & forecast", "type": "ACTION",
        "target": {"prompt_template": "Gather KPIs and forecast the cash position:\n{{input}}"},
        "required": True,
    }]}, "dynamic_planning": {"enabled": False}},
    "capabilities": {"tools": [{"tool_id": "tenant_record_write"}, {"tool_id": "emit_business_signal"}],
                     "memory": {"enabled": True, "mode": "CORTEX"}},
    "governance": {
        "autonomy_level": "A1",
        "sod_class": "none",
        "memory_domains": ["general", "financial"],
        "max_cost_usd": 0.50,
    },
    "io_contract": {"input_schema": {"type": "object", "properties": {}},
                    "output_schema": {"type": "object", "properties": {"forecast": {"type": "object"}}}},
}


INTELLIGENCE_TEMPLATES: list[dict[str, Any]] = [P19_OPTIMIZE, AGT_051]
