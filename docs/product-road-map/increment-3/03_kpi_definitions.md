# Increment 3 / PRAGYA — KPI Definitions (register finding C6)

> **Status:** ✅ BUILT (2026-07-22) · **Code:** `backend/src/ai/kpi/{definitions,compute}.py` · **API:** `GET /api/v1/ai/kpi/{definitions,business}`
> **Closes:** register **C6** — the Blueprint names KPIs and their source processes but gives no formulas.
> **Parent:** [02_pragya_v1.md](./02_pragya_v1.md) §3

---

## 1. Why this document exists

The Blueprint says things like *"gross_margin, source: P10"*. That names a number and an owner; it does not say what to divide by what, which records must exist first, or what "better" is measured against. Pragya **reports** these numbers in stage 9 of the engagement, so until the definitions exist her reporting is either vague or invented.

The registry is code (`kpi/definitions.py`), not prose — this document is the reviewable rendering of the judgment inside it.

## 2. The honest-absence rule (the load-bearing part)

> **A KPI whose prerequisites are unmet reports what is missing. It never reports a number, and in particular it never reports zero.**

Zero is a measurement: *"you are owed nothing."* Absence is the lack of one: *"I cannot tell what you are owed."* An owner who cannot distinguish them will eventually make a decision on a figure that was never real, and that is a worse outcome than showing them nothing.

`compute.py` enforces this structurally — every KPI checks prerequisites *before* it computes, and returns `value=None` with a populated `missing` list when they fail. Three distinct cases all resolve to honest absence:

| Case | Example | Why it is not zero |
|---|---|---|
| Object never defined | tenant has no `Invoice` records at all | Nothing has been measured |
| Field defined but never populated | `Opportunity.amount` null on every row | The formula has no input |
| Denominator empty | every quote still open; no cleared revenue | A ratio over nothing is undefined, not 0% |

The one legitimate zero in the registry is `agent_hitl_load` — "approvals waiting on you: 0" is a real measurement of a real queue.

## 3. Each KPI declares four things

| Field | Purpose |
|---|---|
| **formula** | Precise enough that two people compute the same number from the same records |
| **prerequisites** | The HBS objects and `Object.field` pairs that must be populated — this is what makes honest absence mechanical rather than aspirational |
| **baseline** | What "better" is measured against; a number with no comparison is decoration |
| **captured_today** | Whether the shipped Solo Pack actually populates the prerequisites, or whether it waits on an Inc-4 connector |

## 4. The registry

| Key | Unit | Owner | Formula (summary) | Captured today |
|---|---|---|---|---|
| `open_pipeline_value` | currency | P03 | Σ `Opportunity.amount` where stage ∉ {won, lost} | ✅ |
| `lead_response_time` | days | P03 | median(first outbound touch − `Lead.created_at`) | ⚠️ needs a first-response timestamp |
| `quote_acceptance_rate` | percent | P03 | accepted ÷ (accepted + rejected + expired); undecided quotes excluded from **both** sides | ✅ |
| `receivables_outstanding` | currency | P08 | Σ (`Invoice.total` − `amount_paid`) where status ∉ {paid, void} | ✅ |
| `overdue_receivables` | currency | P08 | as above, restricted to status `overdue` **or** `due_date` past | ✅ |
| `days_sales_outstanding` | days | P10 | (outstanding ÷ revenue in window) × window days | ✅ |
| `collections_recovered` | currency | P08 | Σ cleared inbound `Payment.amount` in window against previously-overdue invoices | ✅ |
| `ticket_resolution_time` | days | P06 | median(resolved − `Ticket.created_at`) | ⚠️ needs a resolved timestamp |
| `gross_margin` | percent | P10 | (revenue − direct delivery cost) ÷ revenue | ❌ needs cost-of-delivery tagging |
| `agent_hitl_load` | count | P14 | pending `human_approvals` for the company | ✅ |

## 5. Definitional decisions worth reviewing

1. **An undecided quote is not a loss.** `quote_acceptance_rate` excludes `draft` and outstanding `sent` quotes from numerator *and* denominator. Counting sent-but-undecided as rejections would make the metric fall every time the sales motion sped up, which is exactly backwards.
2. **Overdue reads the due date, not just the status.** An invoice past `due_date` counts as overdue whether or not anything remembered to restamp its status. Trusting the status field would make the number depend on a background job having run.
3. **Open pipeline is not probability-weighted.** It sums stated deal sizes, so one large speculative opportunity can dominate it. Weighting would need a `probability` field the Solo Pack does not reliably populate — declared as a caveat rather than silently approximated.
4. **`gross_margin` is declared but not computable, on purpose.** The Blueprint names it; the Solo Pack has no cost-of-delivery tagging on `Bill` records. Rather than drop it from the registry (which would hide the gap) or approximate it (which would fabricate), it is registered with `captured_today=False` and reports what it needs. **This is the worked example of C6's whole point.**
5. **Two timing KPIs are honest about an event timeline we do not yet write.** `lead_response_time` and `ticket_resolution_time` need a first-touch/resolved timestamp per record. Approximating from `created_at` would silently measure a different thing, so they report the missing field instead.
6. **DSO refuses to divide by no revenue.** A tenant with invoices but no cleared payments gets "not yet measurable: recognised revenue in the window", not an infinity or a zero.

## 6. Where the numbers come from

Records live in the **tenant data plane** (`get_tenant_session`); approvals live in the **control plane**. The two are queried through separate sessions — never assume one transaction spans both (HANDOFF §5).

`GET /ai/kpi/business` is the single read path, used by **both** Pragya's stage-9 reporting and the dashboards. If they computed separately they would eventually disagree, and an owner shown two different revenue figures stops believing either.

## 7. What still needs to happen

* **Inc 4** — the accounting connector supplies cost-of-delivery tagging, which makes `gross_margin` computable. No definition change required; `captured_today` flips.
* **A per-record event timeline** (first outbound touch, resolved-at) unlocks the two timing KPIs. Worth doing: `lead_response_time` is the metric automation moves most visibly, and is usually the first honest proof to an owner that the system works.
* **Baselines are declared but not yet stored.** Every definition names its baseline method; `compute.py` returns `baseline_value=None` until a rollup writes trailing windows. Until then Pragya reports the current value without a comparison, which is honest but less useful.
