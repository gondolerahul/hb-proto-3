"""tenant_schema/hbs_seed — the predefined HireBuddha Business Schema (spine).

This is the approved 03a appendix
(docs/product-road-map/increment-1/03a_hbs_spine.md) as loadable seed data:
the canonical objects with core fields, ref fields (materialised into
tenant_record_links), owning Process code, HBS module, and memory-domain tag.
**27 through Increment 1; 35 from Increment 6 / STRAT**, whose eight Planning
objects are reviewed in increment-6/04a_planning_object_sheets.md.
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
    # Inc-6 STRAT. New rather than reusing `financial` because the domain
    # viewport is exactly the mechanism that should keep board minutes out of a
    # collections agent's retrieval. **No entity is granted it by default** —
    # every one of the 18 seeded Solo Pack agents declares an explicit
    # `memory_domains` list and none includes this, so Planning records are
    # invisible to all of them until someone grants it deliberately. That is
    # the feature, not an oversight (04a §8.9).
    "strategy",
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

# ── Planning / STRAT (Inc 6) ────────────────────────────────────────────────
# The five-step business loop as records — Notice (Minutes) → Strategize
# (Proposition) → Decide (Resolution) → Act (Mandate) → Close (Review) — plus
# the three "frame" objects the loop aims at (Objective / Target / Forecast).
# Approved 2026-07-26; the reviewed sheets are
# docs/product-road-map/increment-6/04a_planning_object_sheets.md.
#
# Every ref below uses an existing SEED_REL_TYPES value — STRAT extends the
# link vocabulary by nothing, which is a small sign these objects sit naturally
# in the spine rather than beside it.
_OBJECTIVE = {
    "name": "Objective", "module": "Planning", "domain": "strategy", "owner": 11,
    "fields": [
        _f("title", "string", required=True),
        _f("narrative", "text"),
        _f("horizon", "enum", values=["quarter", "year", "multi_year"]),
        # `abandoned` sits beside `achieved` deliberately: an objective quietly
        # dropped is the most common real outcome in a small business, and a
        # vocabulary that cannot say so produces a permanently "active" list
        # nobody trusts.
        _f("status", "enum", values=["draft", "active", "achieved", "abandoned"],
           default="draft"),
        _ref("owner", "Employee", "attached_to", optional=True),
    ],
}
_TARGET = {
    "name": "Target", "module": "Planning", "domain": "strategy", "owner": 11,
    "fields": [
        _f("name", "string", required=True),
        # A plain string, not an enum: the C6 registry (ai/kpi/definitions.py)
        # is the single source of truth, and freezing an enum copy of it here
        # would create the second store decision 3.2 forbids — "two stores for
        # one number is how a review ends up arguing with the dashboard".
        _f("kpi_key", "string"),
        # Not decoration. For a days-outstanding or time-to-respond style
        # metric, improving means going *down*, and a review that does not know
        # that reports a genuine success as a miss. (No KPI key is named here:
        # LEARN's §7 guarantee is that a key never appears in platform source,
        # and a tenant's chosen key is a value, not a literal.)
        _f("direction", "enum", values=["increase", "decrease", "hold"]),
        _f("target_value", "decimal"), _f("by_date", "date"),
        _f("status", "enum", values=["open", "met", "missed", "withdrawn"],
           default="open"),
        _ref("objective", "Objective", "belongs_to", optional=True),
    ],
}
_FORECAST = {
    "name": "Forecast", "module": "Planning", "domain": "strategy", "owner": 11,
    "fields": [
        _f("name", "string", required=True),
        _f("kpi_key", "string"),
        _f("method", "enum", values=["manual", "twin_forecast", "external"]),
        _f("value", "decimal"),
        _f("interval_low", "decimal"), _f("interval_high", "decimal"),
        _f("for_period_start", "date"), _f("for_period_end", "date"),
        # A string, not a ref or an FK: TWIN's `twin_runs` is control-plane and
        # this record is tenant-plane. There is no cross-plane foreign key in
        # this architecture and inventing one here would be the wrong precedent.
        _f("twin_run_id", "string", optional=True),
        # Added in review (04a §8.3). Without it, §7.3's "the Forecast's value
        # if one is attached" has nothing to attach to and is unimplementable.
        _ref("target", "Target", "attached_to", optional=True),
    ],
}
_MINUTES = {
    "name": "Minutes", "module": "Planning", "domain": "strategy", "owner": 11,
    "fields": [
        _f("title", "string", required=True),
        _f("held_on", "datetime", required=True),
        # Text rather than a multi-ref: the most common Solo Pack meeting has
        # one attendee who is not an Employee record, and the second most
        # common includes a customer who is a Contact. A ref list would make
        # the honest answer unrepresentable.
        _f("attendees", "text"),
        _f("body", "text"),
        # Not a duplicate of `Resolution.decision`: this is what a meeting felt
        # like it concluded, that is what was formally adopted. Meetings
        # routinely conclude things nobody ever adopts, and the gap is
        # information.
        _f("decisions_summary", "text"),
        _ref("objective", "Objective", "attached_to", optional=True),
    ],
}
_PROPOSITION = {
    "name": "Proposition", "module": "Planning", "domain": "strategy", "owner": 11,
    "fields": [
        _f("title", "string", required=True),
        _f("rationale", "text"),
        _f("expected_effect", "text"),
        _f("cost_estimate", "money"),
        # Four values where TWIN's Grade has three, and the fourth is
        # load-bearing: `untested` means never taken to the Glasshouse, while
        # `unknown` means a run happened and could not be graded. Rendering
        # "we never checked" and "we checked and could not tell" identically is
        # precisely the softening TWIN's grading exists to prevent.
        _f("honesty_grade", "enum",
           values=["replay", "forecast", "unknown", "untested"], default="untested"),
        _f("twin_run_id", "string", optional=True),
        _f("status", "enum",
           values=["draft", "tabled", "adopted", "rejected", "withdrawn"],
           default="draft"),
        _ref("minutes", "Minutes", "derived_from", optional=True),
    ],
}
_RESOLUTION = {
    "name": "Resolution", "module": "Planning", "domain": "strategy", "owner": 11,
    "fields": [
        _f("title", "string", required=True),
        _f("decision", "text", required=True),
        _f("adopted_on", "date", required=True),
        # The HBS module this concerns. Named `concerns_module` rather than the
        # design's `district`, which is Vihara/Atlas *map* vocabulary: the
        # record carries business words and the surface renders the metaphor.
        _f("concerns_module", "string"),
        _f("engraved_at", "datetime"),
        _f("status", "enum", values=["active", "superseded", "revoked"],
           default="active"),
        _ref("adopted_by", "Employee", "attached_to", optional=True),
        # `← converted_to` — the shipped Quote.opportunity pattern. Optional
        # because an owner may resolve something no agent ever proposed, and
        # requiring a Proposition first would make the honest path the slow one.
        _ref("proposition", "Proposition", "converted_to", direction="in",
             optional=True),
    ],
}
_MANDATE = {
    "name": "Mandate", "module": "Planning", "domain": "strategy", "owner": 11,
    "fields": [
        _f("title", "string", required=True),
        # A process *code*, not a ref: Processes are tenant-plane entities
        # (hierarchical_entities), not HBS records, so there is nothing to ref
        # at. Mirrors how owner_process_code is stored on every entity def.
        _f("owning_process", "string"),
        # The only required date in the eight sheets. A mandate without a
        # review date is a wish, and the whole point of the fifth step is that
        # the loop closes.
        _f("review_due", "date", required=True),
        _f("status", "enum", values=["issued", "in_flight", "reviewed", "closed"],
           default="issued"),
        _ref("resolution", "Resolution", "belongs_to", required=True),
        _ref("target", "Target", "attached_to", optional=True),
    ],
}
_REVIEW = {
    "name": "Review", "module": "Planning", "domain": "strategy", "owner": 11,
    "fields": [
        _f("reviewed_on", "date"),
        _f("predicted_value", "decimal"),
        # Nullable, and **None means not measurable — never zero**. Mirrors
        # KpiResult's shape deliberately rather than inventing a parallel
        # vocabulary: a fabricated KPI prompts a decision while a missing one
        # prompts a question, and a strategy review is where a fabricated
        # number would do the most damage.
        _f("realized_value", "decimal", optional=True),
        _f("measurable", "boolean", default=False),
        # Text, not json: a Review is read by a human, and "no invoices were
        # issued in this window" beats ["no_invoices"]. The structured list
        # stays on KpiResult for anything that needs to branch on it.
        _f("missing", "text"),
        # `not_measurable` is a first-class verdict, not an error state — and
        # it will be the most common one until kpi_snapshots has depth.
        _f("verdict", "enum",
           values=["on_track", "off_track", "met", "missed", "not_measurable"]),
        _f("notes", "text"),
        _ref("mandate", "Mandate", "belongs_to", required=True),
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
    _OBJECTIVE, _TARGET, _FORECAST, _MINUTES,
    _PROPOSITION, _RESOLUTION, _MANDATE, _REVIEW,
]

# 27 through Increment 1; **35** from Increment 6 / STRAT, which added the
# eight Planning objects above. The assert exists to make exactly this kind of
# change deliberate, and it did its job — the design doc said "seven objects,
# 27 → 34" while listing eight, and this line is where the arithmetic had to
# be settled. Two sibling asserts move with it: tests/unit/test_tenant_validation
# and the export-bundle count in tests/integration/test_tenant_records_db.
assert len(HBS_SPINE) == 35, "the HBS spine has exactly 35 canonical objects"


def hbs_object_names() -> list[str]:
    return [obj["name"] for obj in HBS_SPINE]
