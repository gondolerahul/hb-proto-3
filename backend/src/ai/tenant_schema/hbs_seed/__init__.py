"""tenant_schema/hbs_seed — the predefined HireBuddha Business Schema (spine).

This is the approved 03a appendix
(docs/product-road-map/increment-1/03a_hbs_spine.md) as loadable seed data:
the 27 canonical objects with core fields, ref fields (materialised into
tenant_record_links), owning Process code, HBS module, and memory-domain tag.
Loaded verbatim by the HBS initializer at tenant provision. Per-tenant
evolution (§10.2) extends this baseline; it never starts blank.

Field types (closed set, 03a §1): string · text · integer · decimal · boolean
· date · datetime · enum · money · email · phone · url · json · artifact · ref.
"""
from __future__ import annotations

from typing import Any

__all__ = ["HBS_SPINE", "hbs_object_names", "DOMAIN_TAGS"]

DOMAIN_TAGS: frozenset[str] = frozenset({
    "general", "crm", "marketing", "operations",
    "financial", "hr", "payroll", "legal", "trust",
})


def _f(name: str, ftype: str, **kw: Any) -> dict[str, Any]:
    return {"name": name, "type": ftype, **kw}


def _ref(name: str, target: str, rel: str, direction: str = "out", **kw: Any) -> dict[str, Any]:
    return {"name": name, "type": "ref", "target": target, "rel": rel,
            "direction": direction, **kw}


# ── Marketing & PR ──────────────────────────────────────────────────────────
_SIGNAL = {
    "name": "Signal", "module": "Marketing & PR", "domain": "marketing", "owner": 1,
    "fields": [
        _f("title", "string", required=True),
        _f("source_type", "enum", values=["market_research", "news", "social",
                                          "referral", "web", "event", "conversation", "other"]),
        _f("summary", "text"),
        _f("strength", "enum", values=["weak", "moderate", "strong"], default="moderate"),
        _f("status", "enum", values=["new", "reviewed", "actioned", "dismissed"], default="new"),
        _f("captured_at", "datetime"),
        _ref("related_to", "*", "attached_to", optional=True),
    ],
}
_CAMPAIGN = {
    "name": "Campaign", "module": "Marketing & PR", "domain": "marketing", "owner": 2,
    "fields": [
        _f("name", "string", required=True),
        _f("channel", "enum", values=["email", "whatsapp", "voice", "social", "web", "event", "multi"]),
        _f("objective", "text"),
        _f("status", "enum", values=["draft", "active", "paused", "completed", "archived"], default="draft"),
        _f("start_date", "date"), _f("end_date", "date"),
        _f("budget", "money"), _f("spend", "money"),
        _f("target_audience", "text"),
        _ref("product", "Product/SKU", "attached_to", optional=True),
    ],
}

# ── CRM ─────────────────────────────────────────────────────────────────────
_LEAD = {
    "name": "Lead", "module": "CRM", "domain": "crm", "owner": 3,
    "fields": [
        _f("display_name", "string", required=True),
        _f("email", "email"), _f("phone", "phone"),
        _f("source", "enum", values=["campaign", "referral", "inbound_call",
                                     "inbound_email", "whatsapp", "web", "signal", "manual"]),
        _f("status", "enum", values=["new", "contacted", "qualified", "disqualified", "converted"], default="new"),
        _f("qualification_notes", "text"),
        _f("score", "integer", optional=True, min=0, max=100),
        _ref("campaign", "Campaign", "derived_from", optional=True),
        _ref("source_signal", "Signal", "converted_to", direction="in", optional=True),
    ],
}
_ACCOUNT = {
    "name": "Account", "module": "CRM", "domain": "crm", "owner": 6,
    "fields": [
        _f("name", "string", required=True, unique=True),
        _f("type", "enum", values=["prospect", "customer", "partner", "former"], default="prospect"),
        _f("industry", "string"), _f("website", "url"),
        _f("billing_address", "text"), _f("tax_id", "string"),
        _f("email", "email"), _f("phone", "phone"),
        _f("status", "enum", values=["active", "dormant", "churned"], default="active"),
    ],
}
_CONTACT = {
    "name": "Contact", "module": "CRM", "domain": "crm", "owner": 6,
    "fields": [
        _f("first_name", "string", required=True), _f("last_name", "string"),
        _f("email", "email"), _f("phone", "phone"), _f("whatsapp", "phone", optional=True),
        _f("role_title", "string"), _f("is_primary", "boolean", default=False),
        _ref("account", "Account", "belongs_to", required=True),
    ],
}
_OPPORTUNITY = {
    "name": "Opportunity", "module": "CRM", "domain": "crm", "owner": 3,
    "fields": [
        _f("name", "string", required=True),
        _f("stage", "enum", values=["discovery", "proposal", "negotiation", "verbal", "won", "lost"], default="discovery"),
        _f("amount", "money"), _f("probability", "integer", min=0, max=100),
        _f("expected_close", "date"),
        _f("loss_reason", "string", required_when={"stage": "lost"}),
        _ref("account", "Account", "belongs_to", required=True),
        _ref("lead", "Lead", "converted_to", direction="in", optional=True),
        _ref("primary_contact", "Contact", "attached_to", optional=True),
    ],
}
_QUOTE = {
    "name": "Quote", "module": "CRM", "domain": "crm", "owner": 3,
    "fields": [
        _f("quote_number", "string", sequence=True),
        _f("status", "enum", values=["draft", "sent", "accepted", "rejected", "expired"], default="draft"),
        _f("valid_until", "date"),
        _f("line_items", "json"),
        _f("subtotal", "money"), _f("tax", "money"), _f("total", "money"),
        _ref("opportunity", "Opportunity", "converted_to", direction="in", required=True),
        _ref("account", "Account", "belongs_to", required=True),
    ],
}
_TICKET = {
    "name": "Ticket", "module": "CRM", "domain": "crm", "owner": 6,
    "fields": [
        _f("subject", "string", required=True),
        _f("channel", "enum", values=["voice", "email", "whatsapp", "web", "internal"]),
        _f("priority", "enum", values=["low", "normal", "high", "urgent"], default="normal"),
        _f("status", "enum", values=["open", "in_progress", "waiting_customer", "resolved", "closed"], default="open"),
        _f("resolution", "text"),
        _f("opened_at", "datetime"), _f("resolved_at", "datetime"),
        _f("csat", "integer", optional=True, min=1, max=5),
        _ref("account", "Account", "belongs_to", required=True),
        _ref("contact", "Contact", "attached_to", optional=True),
        _ref("related_to", "*", "attached_to", optional=True),
    ],
}

# ── Legal ───────────────────────────────────────────────────────────────────
_CONTRACT = {
    "name": "Contract", "module": "Legal", "domain": "legal", "owner": 13,
    "fields": [
        _f("title", "string", required=True),
        _f("contract_type", "enum", values=["sales", "purchase", "service", "employment", "nda", "other"]),
        _f("status", "enum", values=["draft", "in_review", "signed", "active", "expired", "terminated"], default="draft"),
        _f("effective_date", "date"), _f("end_date", "date"),
        _f("tcv", "money"), _f("signed_at", "datetime"),
        _f("document", "artifact"),
        _ref("counterparty_account", "Account", "belongs_to", optional=True),
        _ref("counterparty_vendor", "Vendor", "belongs_to", optional=True),
        _ref("quote", "Quote", "converted_to", direction="in", optional=True),
    ],
}
_RISK = {
    "name": "Risk", "module": "Legal", "domain": "trust", "owner": 14,
    "fields": [
        _f("title", "string", required=True),
        _f("category", "enum", values=["financial", "legal", "operational", "security", "reputational", "compliance"]),
        _f("severity", "enum", values=["low", "medium", "high", "critical"]),
        _f("likelihood", "enum", values=["rare", "possible", "likely"]),
        _f("status", "enum", values=["identified", "assessed", "mitigating", "accepted", "closed"], default="identified"),
        _f("mitigation", "text"),
        _ref("related_to", "*", "attached_to", optional=True),
    ],
}
_INCIDENT = {
    "name": "Incident", "module": "Legal", "domain": "trust", "owner": 17,
    "fields": [
        _f("title", "string", required=True),
        _f("incident_type", "enum", values=["security", "outage", "data", "fraud", "pr", "safety", "other"]),
        _f("severity", "enum", values=["sev1", "sev2", "sev3", "sev4"]),
        _f("status", "enum", values=["declared", "contained", "resolved", "postmortem", "closed"], default="declared"),
        _f("declared_at", "datetime", required=True), _f("resolved_at", "datetime"),
        _f("summary", "text"),
        _ref("related_to", "*", "attached_to", optional=True),
        _ref("risk", "Risk", "attached_to", optional=True),
    ],
}
_POLICY = {
    "name": "Policy/Obligation", "module": "Legal", "domain": "legal", "owner": 14,
    "fields": [
        _f("title", "string", required=True),
        _f("policy_type", "enum", values=["internal_policy", "regulatory_obligation", "contractual_obligation"]),
        _f("status", "enum", values=["draft", "active", "retired"], default="draft"),
        _f("effective_date", "date"), _f("review_date", "date"),
        _f("body", "text"), _f("document", "artifact", optional=True),
        _ref("source_contract", "Contract", "derived_from", optional=True),
    ],
}
_EVIDENCE = {
    "name": "Evidence", "module": "Legal", "domain": "trust", "owner": 14,
    "fields": [
        _f("title", "string", required=True),
        _f("evidence_type", "enum", values=["document", "screenshot", "log", "recording", "attestation"]),
        _f("captured_at", "datetime", required=True),
        _f("artifact", "artifact", required=True),
        _f("content_hash", "string"), _f("retention_until", "date"),
        _ref("supports", "*", "attached_to", required=True),
    ],
}

# ── Accounting ──────────────────────────────────────────────────────────────
_INVOICE = {
    "name": "Invoice", "module": "Accounting", "domain": "financial", "owner": 8,
    "fields": [
        _f("invoice_number", "string", sequence=True),
        _f("status", "enum", values=["draft", "sent", "partially_paid", "paid", "overdue", "disputed", "void"], default="draft"),
        _f("issue_date", "date"), _f("due_date", "date"),
        _f("line_items", "json"),
        _f("subtotal", "money"), _f("tax", "money"), _f("total", "money"), _f("amount_paid", "money"),
        _ref("account", "Account", "belongs_to", required=True),
        _ref("order", "Order", "billed_by", direction="in", optional=True),
    ],
}
_PAYMENT = {
    "name": "Payment", "module": "Accounting", "domain": "financial", "owner": 8,
    "fields": [
        _f("direction", "enum", values=["inbound", "outbound"]),
        _f("method", "enum", values=["bank_transfer", "upi", "card", "cheque", "cash", "gateway", "other"]),
        _f("amount", "money", required=True), _f("payment_date", "date", required=True),
        _f("reference", "string"),
        _f("status", "enum", values=["pending", "cleared", "failed", "refunded"], default="pending"),
        _ref("invoice", "Invoice", "paid_by", direction="in", optional=True),
        _ref("bill", "Bill", "paid_by", direction="in", optional=True),
    ],
}
_BILL = {
    "name": "Bill", "module": "Accounting", "domain": "financial", "owner": 9,
    "fields": [
        _f("bill_number", "string"),
        _f("status", "enum", values=["received", "approved", "scheduled", "paid", "disputed", "void"], default="received"),
        _f("bill_date", "date"), _f("due_date", "date"),
        _f("total", "money"), _f("amount_paid", "money"),
        _ref("vendor", "Vendor", "belongs_to", required=True),
        _ref("purchase_order", "Purchase Order", "billed_by", direction="in", optional=True),
    ],
}
_LEDGER = {
    "name": "Ledger Entry", "module": "Accounting", "domain": "financial", "owner": 10,
    "fields": [
        _f("entry_date", "date", required=True),
        _f("account_code", "string"), _f("description", "string"),
        _f("debit", "money"), _f("credit", "money"),
        _f("journal", "enum", values=["sales", "purchases", "bank", "general"]),
        _f("reconciled", "boolean", default=False),
        _ref("source", "*", "derived_from", optional=True),
    ],
}

# ── ERP / Operations ────────────────────────────────────────────────────────
_ORDER = {
    "name": "Order", "module": "ERP / Operations", "domain": "operations", "owner": 5,
    "fields": [
        _f("order_number", "string", sequence=True),
        _f("status", "enum", values=["confirmed", "in_progress", "fulfilled", "cancelled"], default="confirmed"),
        _f("order_date", "date"), _f("line_items", "json"), _f("total", "money"),
        _ref("account", "Account", "belongs_to", required=True),
        _ref("contract", "Contract", "converted_to", direction="in", optional=True),
    ],
}
_PROJECT = {
    "name": "Project/Engagement", "module": "ERP / Operations", "domain": "operations", "owner": 5,
    "fields": [
        _f("name", "string", required=True),
        _f("status", "enum", values=["planned", "active", "on_hold", "completed", "cancelled"], default="planned"),
        _f("start_date", "date"), _f("due_date", "date"),
        _f("completion_pct", "integer", min=0, max=100),
        _ref("order", "Order", "fulfilled_by", direction="in", optional=True),
        _ref("account", "Account", "belongs_to", required=True),
    ],
}
_DELIVERABLE = {
    "name": "Deliverable", "module": "ERP / Operations", "domain": "operations", "owner": 5,
    "fields": [
        _f("title", "string", required=True),
        _f("status", "enum", values=["pending", "in_progress", "review", "delivered", "accepted"], default="pending"),
        _f("due_date", "date"), _f("delivered_at", "datetime"), _f("acceptance_notes", "text"),
        _ref("project", "Project/Engagement", "belongs_to", required=True),
    ],
}
_VENDOR = {
    "name": "Vendor", "module": "ERP / Operations", "domain": "operations", "owner": 9,
    "fields": [
        _f("name", "string", required=True, unique=True),
        _f("category", "string"), _f("email", "email"), _f("phone", "phone"),
        _f("tax_id", "string"),
        _f("bank_details", "json", sensitive=True),   # R5: JSONB in the isolated tenant DB
        _f("status", "enum", values=["prospective", "active", "on_hold", "terminated"], default="prospective"),
    ],
}
_PO = {
    "name": "Purchase Order", "module": "ERP / Operations", "domain": "operations", "owner": 9,
    "fields": [
        _f("po_number", "string", sequence=True),
        _f("status", "enum", values=["draft", "sent", "acknowledged", "fulfilled", "cancelled"], default="draft"),
        _f("order_date", "date"), _f("expected_date", "date"),
        _f("line_items", "json"), _f("total", "money"),
        _ref("vendor", "Vendor", "belongs_to", required=True),
    ],
}
_ASSET = {
    "name": "Asset/Inventory Item", "module": "ERP / Operations", "domain": "operations", "owner": 15,
    "fields": [
        _f("name", "string", required=True),
        _f("asset_type", "enum", values=["inventory", "equipment", "license", "facility", "digital"]),
        _f("sku", "string", optional=True), _f("quantity", "decimal"), _f("unit", "string"),
        _f("location", "string"), _f("unit_cost", "money"),
        _f("status", "enum", values=["in_stock", "allocated", "in_service", "maintenance", "retired", "disposed"]),
        _ref("product", "Product/SKU", "derived_from", optional=True),
        _ref("vendor", "Vendor", "attached_to", optional=True),
    ],
}
_PRODUCT = {
    "name": "Product/SKU", "module": "ERP / Operations", "domain": "operations", "owner": 16,
    "fields": [
        _f("name", "string", required=True), _f("sku", "string", unique=True),
        _f("description", "text"), _f("unit_price", "money"), _f("cost", "money"), _f("unit", "string"),
        _f("status", "enum", values=["draft", "active", "discontinued"], default="draft"),
    ],
}

# ── HRMS ────────────────────────────────────────────────────────────────────
_CANDIDATE = {
    "name": "Candidate", "module": "HRMS", "domain": "hr", "owner": 12,
    "fields": [
        _f("name", "string", required=True), _f("email", "email"), _f("phone", "phone"),
        _f("role_applied", "string"),
        _f("stage", "enum", values=["applied", "screening", "interview", "offer", "hired", "rejected", "withdrawn"], default="applied"),
        _f("resume", "artifact"), _f("source", "string"),
    ],
}
_EMPLOYEE = {
    "name": "Employee", "module": "HRMS", "domain": "payroll", "owner": 12,
    "fields": [
        _f("name", "string", required=True), _f("email", "email"), _f("phone", "phone"),
        _f("role_title", "string"),
        _f("employment_type", "enum", values=["full_time", "part_time", "contractor"]),
        _f("start_date", "date"), _f("end_date", "date"),
        _f("compensation", "money"),
        _f("status", "enum", values=["active", "on_leave", "exited"], default="active"),
        _ref("reports_to", "Employee", "belongs_to", optional=True),
    ],
}

# ── Planning ────────────────────────────────────────────────────────────────
_BUDGET = {
    "name": "Budget", "module": "Planning", "domain": "financial", "owner": 11,
    "fields": [
        _f("name", "string", required=True),
        _f("period_start", "date", required=True), _f("period_end", "date", required=True),
        _f("category", "string"), _f("planned", "money"), _f("actual", "money"),
        _f("status", "enum", values=["draft", "active", "closed"], default="draft"),
    ],
}

HBS_SPINE: list[dict[str, Any]] = [
    _SIGNAL, _CAMPAIGN,
    _LEAD, _ACCOUNT, _CONTACT, _OPPORTUNITY, _QUOTE, _TICKET,
    _CONTRACT, _RISK, _INCIDENT, _POLICY, _EVIDENCE,
    _INVOICE, _PAYMENT, _BILL, _LEDGER,
    _ORDER, _PROJECT, _DELIVERABLE, _VENDOR, _PO, _ASSET, _PRODUCT,
    _CANDIDATE, _EMPLOYEE,
    _BUDGET,
]

assert len(HBS_SPINE) == 27, "the HBS spine has exactly 27 canonical objects"


def hbs_object_names() -> list[str]:
    return [obj["name"] for obj in HBS_SPINE]
