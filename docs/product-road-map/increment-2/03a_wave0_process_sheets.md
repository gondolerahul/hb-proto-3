# Increment 2 / PACK — Wave-0 Process Design Sheets (closes C1)

> **Status:** Draft — for brainstorm review · **Branch:** `inc2/pack` · **Parent:** [03_pack_agents_processes.md](./03_pack_agents_processes.md) §2 · **Closes:** C1 (the 5 remaining Wave-0 processes; P03 authored in [SLICE §3](./01_slice_email_to_quote.md)).
> **Design authority:** Blueprint §5 (process catalogue), §14 (Wave-0 roster); [HBS spine](../increment-1/03a_hbs_spine.md) (object → owning-process assignment, the numeric `owner` code). The C1 register finding wants step-level process design, not an org-chart row — each sheet below has the SLICE §3 shape: **triggers → stages → decisions → exceptions → SLAs → definition-of-done → objects**.

---

## 0. Why these five, and how ownership resolves

The Wave-0 Solo Pack activates thin slices of **six** processes — **P03** (authored in the SLICE) plus the five below. Each PROCESS entity, when seeded, becomes the write-**owner** of the HBS objects whose spine `owner` code matches its `process_code` (the Inc-1 owner-id resolution, [SCH §23.1](../increment-1/03_sch_tenant_schema.md)). Everything else a process touches it **reads**; a cross-owner write goes through *others-propose* (`object.change_proposed`) or a `before_cross_owner_write` HITL — never a silent mutation. That propose path is what makes the finance segregation (P08 maker ≠ P10 checker) real at runtime, not just a label.

| Process | Owns (HBS spine) | Reads | Bundle (§2.1) |
|---|---|---|---|
| P03 Cold-to-Closed Acquisition | Lead, Opportunity, Quote | Account, Contact, Product/SKU, Signal | Growth |
| **P06** Resolve-to-Retain | Account, Contact, Ticket | Opportunity, Order, Contract | Customer Success |
| **P08** Order-to-Cash | Invoice, Payment | Account, Order, Quote | Fiscal & Asset Optimizer |
| **P10** Record-to-Report | Ledger Entry | Invoice, Payment, Bill | Fiscal & Asset Optimizer |
| **P14** Continuous Guardrails | Risk, Policy/Obligation, Evidence | Contract, Incident, Ledger Entry | Regulatory & Compliance |
| **P19** Sense-Decide-Optimize | *(none — read-all planner)* | Budget, Invoice, Payment, Ledger Entry, envelope stats | Intelligence |

> **Ownership note (resolves the doc/spine divergence).** The PACK overview §2 loosely says P19 is "owner of Budget"; the HBS spine assigns **Budget to a different owning process** (the Plan-Budget-Forecast process, not yet in Wave-0). P19 is a **read-all planner** — it owns no HBS object and mutates nothing directly; it reads across the graph and proposes. The spine is corrected-first on divergence, so P19 ships owning nothing (its `owner_process_code` resolves to no objects, which is correct).

Every process is **A1**: each external effect raises a HITL card (checkpoint 17), draft-first. Bands, `sod_class`, and `memory_domains` per sheet are seeded complete (PACK §3, closing the Inc-1 "unset bands pass through" window for the sellable path).

---

## 1. P06 — Resolve-to-Retain (Customer Success)

Turn an inbound support contact into a resolved, satisfied customer; book appointments when the resolution needs one.

* **Agents:** AGT-030 Omnichannel Care Orchestrator (drafts replies), AGT-035 Appointment Concierge (books/confirms/reschedules), AGT-092 Scheduling Agent (thin calendar helper under AGT-035 until connectors land, Inc 4).
* **Triggers:** `ticket.opened` (an inbound care contact became a Ticket), `ticket.followup` (heartbeat sweep of waiting tickets), `appointment.requested`.
* **Stages:** (1) **Triage** — read the Ticket, classify priority/intent, set `in_progress`; (2) **Draft reply** — AGT-030 drafts a support response → A1 `email_dispatch` HITL before send; (3) **Appointment?** — if the resolution needs a booking, AGT-035 proposes a slot and AGT-092 coordinates the calendar; (4) **Resolve** — set `resolved`, capture `resolution`; (5) **CSAT** — request a satisfaction score, then `closed`.
* **Decisions:** `priority=urgent` → escalate + notify owner; needs-appointment → appointment sub-flow; unresolved past SLA → escalate to human.
* **Exceptions:** spam/unparseable → PARK + owner notify; churn-risk/angry sentiment → escalate to human (do not auto-reply); double-booking → AGT-092 re-proposes a slot.
* **SLAs:** first-response draft within 1 heartbeat; appointment confirmation same run; CSAT requested after resolve (per-checkpoint SLA lands in TRUST, C3).
* **Definition of done:** Ticket in `resolved`/`closed` with a `resolution`; any appointment confirmed; CSAT captured when returned.
* **Objects:** **owns** Account, Contact, Ticket; **reads** Opportunity, Order, Contract.

## 2. P08 — Order-to-Cash (Fiscal & Asset Optimizer)

Chase what's owed and apply what's paid — the receivable half of the ledger.

* **Agents:** AGT-038 Accounts Receivable — `sod_class: maker`, `sod_tags: [financial_maker]`.
* **Triggers:** `invoice.overdue` (heartbeat sweep of past-due invoices), `payment.received` (an inbound payment event to apply).
* **Stages:** (1) **Remind** — on overdue, AGT-038 drafts an empathetic reminder → A1 `email_dispatch` HITL; (2) **Escalate** — graduated reminders (aligned to the TRUST dunning ladder, C5); (3) **Apply payment** — on `payment.received`, record a Payment against the Invoice, bump `amount_paid`/`status`; (4) **Reconcile hand-off** — set `paid`/`partially_paid` and emit `ledger.unreconciled` so P10 reconciles.
* **Decisions:** write-off proposed → `refund`/`payout` authority band → HITL; disputed → park + notify; overpayment → flag for review.
* **Exceptions:** payment with no matching invoice → **propose** to P10 (others-propose) or park; repeated non-payment → escalate to human collection.
* **SLAs:** reminder within 1 heartbeat of overdue; payment applied same run.
* **Definition of done:** Invoice `paid`/`partially_paid` with a linked Payment; a `ledger.unreconciled` signal emitted for P10.
* **Objects:** **owns** Invoice, Payment; **reads** Account, Order, Quote.
* **SoD:** the **maker** — it creates receivable records; the checker (P10) reconciles them independently. A maker never reconciles its own postings.

## 3. P10 — Record-to-Report (Fiscal & Asset Optimizer)

Keep the books straight: categorize, match, reconcile, and flag what doesn't tie out.

* **Agents:** AGT-046 Bookkeeping & Reconciliation — `sod_class: checker`, `sod_tags: [financial_checker]`.
* **Triggers:** `ledger.unreconciled` (from P08 or an import), `schedule.close` (period-close heartbeat).
* **Stages:** (1) **Categorize** — classify a Ledger Entry to an `account_code`/`journal`; (2) **Match** — match entries against Invoices/Payments/Bills; (3) **Reconcile** — set `reconciled=true` when matched; (4) **Flag exceptions** — unmatched/duplicate/imbalanced → raise for review.
* **Decisions:** unmatched above threshold → HITL; suspected duplicate → flag; a correction that touches a P08 Invoice → **propose** (SoD: the checker cannot silently edit the maker's receivable).
* **Exceptions:** ambiguous categorization → park with a suggestion; ledger imbalance → raise a Risk (propose to P14).
* **SLAs:** categorize within 1 heartbeat; period close on the scheduled cadence.
* **Definition of done:** ledger entries `reconciled=true` or explicitly flagged; a reconciliation summary rolled to Sheel.
* **Objects:** **owns** Ledger Entry; **reads** Invoice, Payment, Bill (cross-owner changes go via propose).
* **SoD:** the **checker** — it reconciles what the maker (P08/AGT-038) posted; separation is enforced by ownership, not honor system.

## 4. P14 — Continuous Guardrails (Regulatory & Compliance)

Watch obligations and regulatory change; raise risk before it bites. A **protected process**: reserved envelope, never paused (§20.4), and it keeps that reserve through the dunning grace window (TRUST, C5).

* **Agents:** AGT-068 Regulatory Watchdog — `sod_class: auditor`, `sod_tags: [audit]`, **read-only** (no `operate` tag → auditor independence).
* **Triggers:** `reg.change` (a regulatory-update feed event), `schedule.guardrail` (periodic obligation review).
* **Stages:** (1) **Watch** — monitor active Policy/Obligation and change feeds; (2) **Assess** — evaluate impact; (3) **Raise Risk** — create a Risk with `severity`/`likelihood`; (4) **Notify** — alert the owner and attach Evidence.
* **Decisions:** `severity=critical` → immediate notify + escalate; obligation breach → raise Risk and **propose** an Incident to P17.
* **Exceptions:** ambiguous applicability → park for human; missing evidence → request it (do not fabricate).
* **SLAs:** assess a `reg.change` within 1 heartbeat; periodic review on schedule.
* **Definition of done:** a Risk raised + assessed, Evidence attached, owner notified.
* **Objects:** **owns** Risk, Policy/Obligation, Evidence; **reads** Contract, Incident, Ledger Entry (read-only — the watchdog observes, it does not operate).

## 5. P19 — Sense-Decide-Optimize (Intelligence)

The read-all planner: gather the numbers, forecast, and propose — feeding Sheel's decision loop. Owns nothing; mutates nothing directly.

* **Agents:** AGT-051 Cashflow Forecaster.
* **Triggers:** `schedule.optimize` (a Loop-heartbeat cadence).
* **Stages:** (1) **Gather KPIs** — read across Invoices, Payments, Ledger, Budget, and envelope stats; (2) **Forecast** — roll a cash-position forecast; (3) **Propose** — surface recommendations into Sheel's CORTEX and the envelope stats.
* **Decisions:** forecast shortfall → raise a Risk (propose to P14) + notify; budget variance beyond band → flag.
* **Exceptions:** insufficient data → emit a low-confidence note; anomaly → flag for review.
* **SLAs:** forecast on the heartbeat cadence.
* **Definition of done:** a cash forecast + KPI snapshot rolled into Sheel; recommendations recorded.
* **Objects:** **owns** none; **reads** Budget, Invoice, Payment, Ledger Entry, envelope stats (read-all). All outward proposals go through the propose path or a HITL — a planner never writes another owner's records.

---

## 6. Cross-process interactions (Wave-0)

The sheets interlock through **signals + the propose path**, never direct cross-owner writes:

* P03 → P08: an accepted Quote / fulfilled Order becomes an Invoice (P08 owns Invoice; P03 proposes or the owner creates on `order.fulfilled`).
* P08 → P10: `ledger.unreconciled` hands receivable postings to the reconciler.
* P10 → P14: a ledger imbalance proposes a Risk to the guardrails owner.
* P19 → P14: a forecast shortfall proposes a Risk; P19 also reads P08/P10 outputs to build KPIs.
* P06 ↔ P03: care reads the Opportunity/Order graph acquisition owns; acquisition reads the Account/Contact care owns — each side reads, neither writes the other's records.

This is the **SoD demonstration surface** for PACK T4: AGT-046 (P10, checker) attempting to edit an Invoice (P08, maker) resolves to `proposed`, not `written`.
