"""kpi/definitions.py — the C6 KPI registry (typed, declarative).

The Blueprint gives KPIs *sources* but no formulas: "gross_margin, source: P10"
does not say what to divide by what. Pragya reports these numbers in stage 9,
so the definitions have to exist before her reporting can be trusted — and
that is the whole of register finding C6.

Every KPI declares four things:

* **formula** — in words, precise enough that two people compute the same
  number from the same records.
* **prerequisites** — which HBS objects and fields must be populated. This is
  what makes the honest-absence rule mechanical rather than aspirational.
* **baseline** — what "better" is measured against, because a number with no
  comparison is decoration.
* **captured_today** — whether the shipped Solo Pack actually populates the
  prerequisites, or whether it waits on an Inc-4 connector.

**The honest-absence rule.** A KPI whose prerequisites are unmet reports
"not yet measurable: missing X" and never a number. This is the single most
important property in the file: a fabricated KPI is worse than a missing one,
because a missing KPI prompts a question and a wrong one prompts a decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "Cadence",
    "KpiDefinition",
    "KPI_DEFINITIONS",
    "definition_for",
    "kpi_keys",
]


class Cadence(str, Enum):
    """The window a KPI is naturally read over."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ROLLING_30D = "rolling_30d"


@dataclass(frozen=True)
class KpiDefinition:
    """One KPI, defined well enough to compute and to refuse to compute."""

    key: str
    display_name: str
    #: The formula in words. Must be unambiguous about numerator and denominator.
    formula: str
    #: HBS object names whose records are required.
    required_objects: tuple[str, ...]
    #: "Object.field" pairs that must be populated for the formula to work.
    required_fields: tuple[str, ...]
    #: What the current value is compared against.
    baseline: str
    unit: str                    # "currency" | "percent" | "count" | "days"
    cadence: Cadence
    #: Whether the shipped Solo Pack populates the prerequisites today.
    captured_today: bool
    #: Which process owns the data. Ties the KPI back to the Blueprint source.
    owner_process: str
    #: Why this KPI is worth an owner's attention.
    why_it_matters: str
    #: Set when the number is easy to misread.
    caveat: str | None = None


KPI_DEFINITIONS: tuple[KpiDefinition, ...] = (
    KpiDefinition(
        key="open_pipeline_value",
        display_name="Open pipeline value",
        formula=(
            "Sum of Opportunity.amount over Opportunity records whose stage is "
            "not 'won' and not 'lost'."
        ),
        required_objects=("Opportunity",),
        required_fields=("Opportunity.amount", "Opportunity.stage"),
        baseline="Same measure 30 days earlier.",
        unit="currency",
        cadence=Cadence.ROLLING_30D,
        captured_today=True,
        owner_process="P03",
        why_it_matters=(
            "The clearest early signal of next quarter's revenue, and the "
            "first thing to move when acquisition starts working."
        ),
        caveat=(
            "Counts stated deal sizes, not probability-weighted value — a "
            "single large speculative opportunity can dominate it."
        ),
    ),
    KpiDefinition(
        key="lead_response_time",
        display_name="Median first-response time to a new lead",
        formula=(
            "Median of (first outbound touch timestamp − Lead.created_at) over "
            "Leads created in the window that received a response."
        ),
        required_objects=("Lead",),
        required_fields=("Lead.created_at", "Lead.status"),
        baseline="Median over the previous equivalent window.",
        unit="days",
        cadence=Cadence.WEEKLY,
        captured_today=True,
        owner_process="P03",
        why_it_matters=(
            "The metric automation moves most immediately and most visibly — "
            "it is usually the first honest proof the system is working."
        ),
        caveat="Leads never responded to are excluded, so a collapsing "
               "response rate can make this look better than it is.",
    ),
    KpiDefinition(
        key="quote_acceptance_rate",
        display_name="Quote acceptance rate",
        formula=(
            "Quotes with status 'accepted' ÷ Quotes with status in "
            "('accepted', 'rejected', 'expired'), over quotes issued in the "
            "window. Draft and outstanding-sent quotes are excluded from both "
            "sides — an undecided quote is not a loss."
        ),
        required_objects=("Quote",),
        required_fields=("Quote.status", "Quote.total"),
        baseline="Trailing 90-day rate.",
        unit="percent",
        cadence=Cadence.MONTHLY,
        captured_today=True,
        owner_process="P03",
        why_it_matters="Says whether pricing and qualification are aligned.",
    ),
    KpiDefinition(
        key="receivables_outstanding",
        display_name="Outstanding receivables",
        formula=(
            "Sum of (Invoice.total − Invoice.amount_paid) over Invoices whose "
            "status is not 'paid' and not 'void'."
        ),
        required_objects=("Invoice",),
        required_fields=("Invoice.total", "Invoice.amount_paid", "Invoice.status"),
        baseline="Same measure 30 days earlier.",
        unit="currency",
        cadence=Cadence.ROLLING_30D,
        captured_today=True,
        owner_process="P08",
        why_it_matters=(
            "What the business is owed. The number the invoice chaser exists "
            "to reduce, so it is how that agent is judged."
        ),
    ),
    KpiDefinition(
        key="overdue_receivables",
        display_name="Overdue receivables",
        formula=(
            "Sum of (Invoice.total − Invoice.amount_paid) over Invoices whose "
            "status is 'overdue', or whose due_date has passed and status is "
            "not 'paid'/'void'."
        ),
        required_objects=("Invoice",),
        required_fields=("Invoice.total", "Invoice.amount_paid",
                         "Invoice.status", "Invoice.due_date"),
        baseline="Same measure 30 days earlier.",
        unit="currency",
        cadence=Cadence.ROLLING_30D,
        captured_today=True,
        owner_process="P08",
        why_it_matters="Separates 'not yet due' from 'not being paid'.",
    ),
    KpiDefinition(
        key="days_sales_outstanding",
        display_name="Days sales outstanding",
        formula=(
            "(Outstanding receivables ÷ revenue recognised in the window) × "
            "days in the window."
        ),
        required_objects=("Invoice", "Payment"),
        required_fields=("Invoice.total", "Invoice.amount_paid",
                         "Payment.amount", "Payment.payment_date",
                         "Payment.direction"),
        baseline="Trailing 90-day DSO.",
        unit="days",
        cadence=Cadence.MONTHLY,
        captured_today=True,
        owner_process="P10",
        why_it_matters="How long cash takes to arrive — the cash-flow metric "
                       "an owner feels before they see it.",
        caveat="Unstable at low invoice volume; needs a meaningful "
               "denominator before it means anything.",
    ),
    KpiDefinition(
        key="collections_recovered",
        display_name="Collections recovered",
        formula=(
            "Sum of Payment.amount where direction is 'inbound' and status is "
            "'cleared', over payments received in the window against invoices "
            "that were overdue when the chase began."
        ),
        required_objects=("Payment", "Invoice"),
        required_fields=("Payment.amount", "Payment.direction",
                         "Payment.status", "Payment.payment_date",
                         "Invoice.due_date"),
        baseline="Previous equivalent window.",
        unit="currency",
        cadence=Cadence.MONTHLY,
        captured_today=True,
        owner_process="P08",
        why_it_matters=(
            "The most direct answer to 'what did this actually get me' — "
            "money that arrived after being chased."
        ),
    ),
    KpiDefinition(
        key="ticket_resolution_time",
        display_name="Median ticket resolution time",
        formula=(
            "Median of (resolved timestamp − Ticket.created_at) over Tickets "
            "resolved in the window."
        ),
        required_objects=("Ticket",),
        required_fields=("Ticket.status", "Ticket.created_at"),
        baseline="Previous equivalent window.",
        unit="days",
        cadence=Cadence.WEEKLY,
        captured_today=True,
        owner_process="P06",
        why_it_matters="The customer-facing half of whether support is coping.",
    ),
    KpiDefinition(
        key="gross_margin",
        display_name="Gross margin",
        formula=(
            "(Revenue recognised − direct cost of delivery) ÷ revenue "
            "recognised, over the window. Revenue from cleared inbound "
            "Payments; direct cost from Bills tagged to delivery."
        ),
        required_objects=("Payment", "Bill", "Ledger Entry"),
        required_fields=("Payment.amount", "Payment.direction",
                         "Bill.amount", "Ledger Entry.account"),
        baseline="Trailing 3 months.",
        unit="percent",
        cadence=Cadence.MONTHLY,
        # The Blueprint names this KPI but the Solo Pack does not capture cost
        # attribution — it has no cost-of-delivery tagging. Honest absence is
        # exactly what C6 exists to make explicit.
        captured_today=False,
        owner_process="P10",
        why_it_matters="Whether the business keeps what it earns.",
        caveat=(
            "Needs cost-of-delivery tagging on Bills, which the Solo Pack "
            "does not capture. Waits on the Inc-4 accounting connector."
        ),
    ),
    KpiDefinition(
        key="agent_hitl_load",
        display_name="Approvals waiting on you",
        formula=(
            "Count of human_approvals rows in a pending state for the company, "
            "at read time."
        ),
        required_objects=(),
        required_fields=(),
        baseline="Rolling 7-day average.",
        unit="count",
        cadence=Cadence.WEEKLY,
        captured_today=True,
        owner_process="P14",
        why_it_matters=(
            "At A1 every external effect needs a human. A rising queue means "
            "the workforce is outrunning the owner's attention, which is the "
            "signal to consider promoting a well-behaved agent."
        ),
    ),
)


def definition_for(key: str) -> KpiDefinition | None:
    for definition in KPI_DEFINITIONS:
        if definition.key == key:
            return definition
    return None


def kpi_keys() -> tuple[str, ...]:
    return tuple(d.key for d in KPI_DEFINITIONS)
