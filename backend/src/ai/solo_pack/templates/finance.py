"""solo_pack/templates/finance — P08 Order-to-Cash + P10 Record-to-Report.

The receivable / reconciliation halves of the ledger, deliberately split across
two owners so segregation of duties is structural: P08's Accounts Receivable is
the **maker** (creates Invoice/Payment), P10's Bookkeeping & Reconciliation is
the **checker** (reconciles Ledger Entries, proposes corrections to the maker's
records — never edits them directly). Sheets: 03a_wave0_process_sheets.md §2–3.

``capabilities.sod_tags`` carries the §9.4 conflict-detection tags the deploy
validator reads; ``governance.sod_class`` carries the persisted role.
"""
from __future__ import annotations

from typing import Any

from src.ai.solo_pack.templates._shared import REACT

__all__ = [
    "P08_ORDER_TO_CASH", "AGT_038", "P10_RECORD_TO_REPORT", "AGT_046", "FINANCE_TEMPLATES",
]


# ── P08 Order-to-Cash (PROCESS) ─────────────────────────────────────────────
P08_ORDER_TO_CASH: dict[str, Any] = {
    "name": "p08-order-to-cash",
    "display_name": "Order-to-Cash",
    "description": "Chase what's owed and apply what's paid. Owner of "
                   "Invoice/Payment.",
    "goal": "Remind on overdue invoices (A1-approved), apply inbound payments, "
            "and hand reconciliation to Record-to-Report.",
    "type": "PROCESS",
    "version": "1.0.0",
    "status": "ACTIVE",
    "tags": ["solo_pack", "process", "process_code:P08"],
    "identity": {
        "role": "Order-to-Cash Process",
        "system_prompt": (
            "You orchestrate order-to-cash. On an overdue invoice, dispatch Accounts "
            "Receivable to draft a reminder (approval-gated). On a received payment, apply it "
            "to the invoice and emit ledger.unreconciled so Record-to-Report can reconcile. "
            "Any write-off needs approval within band."
        ),
    },
    "logic_gate": REACT,
    "planning": {
        "static_plan": {
            "enabled": True,
            "steps": [{
                "step_id": "receivable", "order": 1, "name": "Remind / apply payment",
                "type": "CHILD_ENTITY_INVOCATION",
                "target": {"entity_name_hint": "agt-038-accounts-receivable"}, "required": True,
            }],
        },
        "dynamic_planning": {"enabled": False},
    },
    "capabilities": {"memory": {"enabled": True, "mode": "CORTEX"}},
    "governance": {
        "autonomy_level": "A1",
        "sod_class": "none",
        "checkpoint_keys": ["before_high_value_email_dispatch", "before_refund_above_band"],
        "memory_domains": ["general", "financial"],
        "max_cost_usd": 1.00,
        "max_concurrent_children": 1,
    },
    "io_contract": {"input_schema": {"type": "object", "properties": {"signal": {"type": "object"}}},
                    "output_schema": {"type": "object", "properties": {"invoice_id": {"type": "string"}}}},
    "metadata_extensions": {
        "process_code": "P08",
        "owns_objects": ["Invoice", "Payment"],
        "trigger_patterns": ["invoice.overdue", "payment.received"],
    },
}


# ── AGT-038 Accounts Receivable (AGENT under P08 — MAKER) ────────────────────
AGT_038: dict[str, Any] = {
    "name": "agt-038-accounts-receivable",
    "display_name": "Accounts Receivable",
    "description": "Chases overdue invoices and applies received payments.",
    "goal": "Draft empathetic collection reminders (approval-gated) and record "
            "payments against invoices, keeping the receivable ledger current.",
    "type": "AGENT",
    "version": "1.0.0",
    "status": "ACTIVE",
    "tags": ["solo_pack", "workforce", "finance", "agent_code:AGT-038"],
    "identity": {
        "role": "Accounts Receivable",
        "system_prompt": (
            "You manage receivables. On an overdue invoice, draft a firm-but-kind reminder — "
            "sending is approval-gated. On a received payment, record a Payment against the "
            "Invoice and update its status. Keep any write-off within the authorised band; "
            "above it, a human approves. You do not reconcile your own postings — that is the "
            "bookkeeper's job (segregation of duties)."
        ),
        "personality": {"tone": "professional", "empathy_level": 0.6, "decision_confidence": 0.7},
    },
    "logic_gate": REACT,
    "planning": {"static_plan": {"enabled": True, "steps": [
        {"step_id": "receivable_action", "order": 1, "name": "Remind or apply payment",
         "type": "ACTION",
         "target": {"prompt_template": "Handle this receivable event:\n{{input}}"}, "required": True},
        {"step_id": "remind", "order": 2, "name": "Send reminder (approval-gated)",
         "type": "TOOL_CALL", "target": {"tool_id": "send_email"}, "required": False},
    ]}, "dynamic_planning": {"enabled": False}},
    "capabilities": {"tools": [{"tool_id": "tenant_record_write"}, {"tool_id": "send_email"},
                               {"tool_id": "emit_business_signal"}],
                     "memory": {"enabled": True, "mode": "CORTEX"},
                     "sod_tags": ["financial_maker"]},
    "governance": {
        "autonomy_level": "A1",
        "sod_class": "maker",
        "authority": {"refund_usd": 200, "payout_usd": 500},
        "checkpoint_keys": ["before_high_value_email_dispatch", "before_refund_above_band"],
        "memory_domains": ["general", "financial"],
        "max_cost_usd": 0.50,
    },
    "io_contract": {"input_schema": {"type": "object", "properties": {}},
                    "output_schema": {"type": "object", "properties": {"payment_id": {"type": "string"}}}},
}


# ── P10 Record-to-Report (PROCESS) ──────────────────────────────────────────
P10_RECORD_TO_REPORT: dict[str, Any] = {
    "name": "p10-record-to-report",
    "display_name": "Record-to-Report",
    "description": "Categorize, match, and reconcile the books. Owner of "
                   "Ledger Entry.",
    "goal": "Reconcile ledger entries against invoices, payments, and bills; "
            "flag exceptions and roll a reconciliation summary to Sheel.",
    "type": "PROCESS",
    "version": "1.0.0",
    "status": "ACTIVE",
    "tags": ["solo_pack", "process", "process_code:P10"],
    "identity": {
        "role": "Record-to-Report Process",
        "system_prompt": (
            "You orchestrate record-to-report. On an unreconciled ledger entry, dispatch "
            "Bookkeeping & Reconciliation to categorize, match, and reconcile it. Corrections "
            "that touch another owner's records (e.g. an invoice) are proposed, not written."
        ),
    },
    "logic_gate": REACT,
    "planning": {
        "static_plan": {
            "enabled": True,
            "steps": [{
                "step_id": "reconcile", "order": 1, "name": "Categorize & reconcile",
                "type": "CHILD_ENTITY_INVOCATION",
                "target": {"entity_name_hint": "agt-046-bookkeeping-reconciliation"}, "required": True,
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
                    "output_schema": {"type": "object", "properties": {"reconciled_count": {"type": "integer"}}}},
    "metadata_extensions": {
        "process_code": "P10",
        "owns_objects": ["Ledger Entry"],
        "trigger_patterns": ["ledger.unreconciled", "schedule.close"],
    },
}


# ── AGT-046 Bookkeeping & Reconciliation (AGENT under P10 — CHECKER) ─────────
AGT_046: dict[str, Any] = {
    "name": "agt-046-bookkeeping-reconciliation",
    "display_name": "Bookkeeping & Reconciliation",
    "description": "Categorizes and reconciles ledger entries against source "
                   "documents.",
    "goal": "Match ledger entries to invoices/payments/bills, mark them "
            "reconciled, and flag exceptions — proposing (not making) any "
            "correction to another owner's record.",
    "type": "AGENT",
    "version": "1.0.0",
    "status": "ACTIVE",
    "tags": ["solo_pack", "workforce", "finance", "agent_code:AGT-046"],
    "identity": {
        "role": "Bookkeeping & Reconciliation",
        "system_prompt": (
            "You keep the books straight. Categorize each ledger entry, match it against the "
            "invoice, payment, or bill it belongs to, and mark it reconciled when it ties out. "
            "Flag unmatched, duplicate, or imbalanced entries for review. You reconcile — you "
            "do not create receivables, and you never directly edit an invoice you did not own; "
            "propose the correction and the owner applies it (segregation of duties)."
        ),
        "personality": {"tone": "precise", "decision_confidence": 0.7},
    },
    "logic_gate": REACT,
    "planning": {"static_plan": {"enabled": True, "steps": [{
        "step_id": "reconcile_entry", "order": 1, "name": "Categorize & reconcile", "type": "ACTION",
        "target": {"prompt_template": "Categorize and reconcile this ledger entry:\n{{input}}"},
        "required": True,
    }]}, "dynamic_planning": {"enabled": False}},
    "capabilities": {"tools": [{"tool_id": "tenant_record_write"}, {"tool_id": "emit_business_signal"}],
                     "memory": {"enabled": True, "mode": "CORTEX"},
                     "sod_tags": ["financial_checker"]},
    "governance": {
        "autonomy_level": "A1",
        "sod_class": "checker",
        "memory_domains": ["general", "financial"],
        "max_cost_usd": 0.50,
    },
    "io_contract": {"input_schema": {"type": "object", "properties": {}},
                    "output_schema": {"type": "object", "properties": {"reconciled": {"type": "boolean"}}}},
}


FINANCE_TEMPLATES: list[dict[str, Any]] = [
    P08_ORDER_TO_CASH, AGT_038, P10_RECORD_TO_REPORT, AGT_046,
]
