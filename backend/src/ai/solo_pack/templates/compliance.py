"""solo_pack/templates/compliance — P14 Continuous Guardrails.

The watchdog slice: monitor obligations and regulatory change, assess impact,
raise Risks with Evidence, and notify. A **protected process** — reserved
envelope, never paused (§20.4), keeps its reserve through the dunning grace
window. Owner of Risk/Policy-Obligation/Evidence. Sheet: 03a §4.

The Regulatory Watchdog is an **auditor**: it observes and records findings but
carries no ``operate`` capability, so the deploy validator keeps it independent
of the processes it audits (§9.4 auditor independence).
"""
from __future__ import annotations

from typing import Any

from src.ai.solo_pack.templates._shared import REACT

__all__ = ["P14_GUARDRAILS", "AGT_068", "COMPLIANCE_TEMPLATES"]


# ── P14 Continuous Guardrails (PROCESS — protected) ─────────────────────────
P14_GUARDRAILS: dict[str, Any] = {
    "name": "p14-continuous-guardrails",
    "display_name": "Continuous Guardrails",
    "description": "Watch obligations and regulatory change; raise risk before "
                   "it bites. Owner of Risk/Policy-Obligation/Evidence.",
    "goal": "Assess regulatory and obligation changes, raise and evidence "
            "Risks, and notify the owner — always on, never paused.",
    "type": "PROCESS",
    "version": "1.0.0",
    "status": "ACTIVE",
    "tags": ["solo_pack", "process", "protected", "process_code:P14"],
    "identity": {
        "role": "Continuous Guardrails Process",
        "system_prompt": (
            "You run continuous compliance guardrails. On a regulatory change or a scheduled "
            "review, dispatch the Regulatory Watchdog to assess impact, raise a Risk with "
            "evidence, and notify the owner. You are a protected process — you keep watching "
            "even when the tenant is in a degraded state."
        ),
    },
    "logic_gate": REACT,
    "planning": {
        "static_plan": {
            "enabled": True,
            "steps": [{
                "step_id": "guardrail", "order": 1, "name": "Assess & raise risk",
                "type": "CHILD_ENTITY_INVOCATION",
                "target": {"entity_name_hint": "agt-068-regulatory-watchdog"}, "required": True,
            }],
        },
        "dynamic_planning": {"enabled": False},
    },
    "capabilities": {"memory": {"enabled": True, "mode": "CORTEX"}},
    "governance": {
        "autonomy_level": "A1",
        "sod_class": "none",
        "memory_domains": ["general", "legal", "trust"],
        "max_cost_usd": 1.00,
        "max_concurrent_children": 1,
    },
    "io_contract": {"input_schema": {"type": "object", "properties": {"signal": {"type": "object"}}},
                    "output_schema": {"type": "object", "properties": {"risk_id": {"type": "string"}}}},
    "metadata_extensions": {
        "process_code": "P14",
        "owns_objects": ["Risk", "Policy/Obligation", "Evidence"],
        "trigger_patterns": ["reg.change", "schedule.guardrail"],
        "protected": True,
    },
}


# ── AGT-068 Regulatory Watchdog (AGENT under P14 — AUDITOR, read-only) ───────
AGT_068: dict[str, Any] = {
    "name": "agt-068-regulatory-watchdog",
    "display_name": "Regulatory Watchdog",
    "description": "Watches obligations and regulatory change; raises risks "
                   "with evidence.",
    "goal": "Assess whether a regulatory or obligation change affects the "
            "tenant, raise a Risk with severity and evidence, and notify.",
    "type": "AGENT",
    "version": "1.0.0",
    "status": "ACTIVE",
    "tags": ["solo_pack", "workforce", "compliance", "agent_code:AGT-068"],
    "identity": {
        "role": "Regulatory Watchdog",
        "system_prompt": (
            "You are a compliance auditor. Watch active obligations and regulatory changes; "
            "when one is relevant, assess its impact, create a Risk with a severity and "
            "likelihood, attach evidence, and notify the owner. You observe and record — you "
            "do not operate business processes or approve anything yourself. If applicability "
            "is unclear, park it for a human rather than guessing."
        ),
        "personality": {"tone": "precise", "decision_confidence": 0.65},
    },
    "logic_gate": REACT,
    "planning": {"static_plan": {"enabled": True, "steps": [{
        "step_id": "assess", "order": 1, "name": "Assess & raise risk", "type": "ACTION",
        "target": {"prompt_template": "Assess this obligation/regulatory change and raise a risk if relevant:\n{{input}}"},
        "required": True,
    }]}, "dynamic_planning": {"enabled": False}},
    "capabilities": {"tools": [{"tool_id": "tenant_record_write"}, {"tool_id": "emit_business_signal"}],
                     "memory": {"enabled": True, "mode": "CORTEX"},
                     "sod_tags": ["audit"]},
    "governance": {
        "autonomy_level": "A1",
        "sod_class": "auditor",
        "memory_domains": ["general", "legal", "trust"],
        "max_cost_usd": 0.50,
    },
    "io_contract": {"input_schema": {"type": "object", "properties": {}},
                    "output_schema": {"type": "object", "properties": {"risk_id": {"type": "string"}}}},
}


COMPLIANCE_TEMPLATES: list[dict[str, Any]] = [P14_GUARDRAILS, AGT_068]
