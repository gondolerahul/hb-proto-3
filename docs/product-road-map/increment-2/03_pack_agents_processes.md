# Increment 2 / PACK — The 12 Curated Agents, 6 Processes & 7 Bundles

> **Status:** Draft — for brainstorm review · **Branch:** `inc2/pack` · **Closes:** C1 (all 6 Wave-0 processes), Inc-1 owner-id resolution + governance-band seeding.
> **Design authority:** Blueprint §14 (Wave-0 roster), §5 (processes), §7.3 (agents), §9.3 (authority bands); Functional §2.1 (bundles). Curated hand-authored templates (decision 3).
> **Depends on:** SLICE (the template pattern), GOV (governance schema + validators), SCH (record ownership).

---

## 1. The Wave-0 roster (Blueprint §14) — Sheel + 12 agents, all A1

| Agent | Tier | Process | Does |
|---|---|---|---|
| KAR-01 Voice *(stub)* / KAR-02 Email / KAR-03 Messaging | AGENT (axle) | feed all | outward gateways (KAR workstream) |
| AGT-013 Inbound Deal Closer | AGENT | **P03** | qualify inbound leads → opportunities |
| AGT-015 Proposal & Quote | AGENT | **P03** | draft & send quotes |
| AGT-030 Omnichannel Care Orchestrator | AGENT | **P06** | draft support replies across channels |
| AGT-035 Appointment Concierge | AGENT | **P06** | book/confirm/reschedule appointments |
| AGT-092 Scheduling Agent | AGENT | **P06** | calendar coordination behind the concierge |
| AGT-038 Accounts Receivable | AGENT | **P08** | chase invoices, apply payments |
| AGT-046 Bookkeeping & Reconciliation | AGENT | **P10** | categorize & reconcile ledger entries |
| AGT-051 Cashflow Forecaster | AGENT | **P19** | roll KPIs + a cash forecast into Sheel |
| AGT-068 Regulatory Watchdog | AGENT | **P14** | watch obligations; raise risks |

## 2. The 6 Wave-0 process design sheets (closes C1)

> **Full sheets:** the five new Wave-0 processes are authored step-level in **[03a_wave0_process_sheets.md](./03a_wave0_process_sheets.md)** (P03 in [SLICE §3](./01_slice_email_to_quote.md)). That doc is the C1 deliverable; the summaries below are the index.

Each is a checked-in sheet (trigger list → stages → decisions → exceptions → SLAs → DoD → objects), same shape as SLICE §3 for P03. Summaries:

* **P03 Cold-to-Closed Acquisition** — authored in [SLICE](./01_slice_email_to_quote.md) §3. Owner of Lead/Opportunity/Quote.
* **P06 Resolve-to-Retain** — trigger `ticket.opened`; stages triage→draft-reply→(appointment?)→resolve→CSAT; A1 draft-first; owner of Ticket. Appointment sub-flow via AGT-035/092.
* **P08 Order-to-Cash** — trigger `invoice.overdue`/`payment.received`; stages remind→escalate→apply-payment→reconcile; authority band on any write-off; owner of Invoice/Payment.
* **P10 Record-to-Report** — trigger `ledger.unreconciled`/schedule; stages categorize→match→reconcile→flag-exceptions; owner of Ledger Entry.
* **P14 Continuous Guardrails** — trigger `reg.change`/schedule; **protected process** (reserved envelope, never paused, §20.4); stages watch→assess→raise-Risk→notify; owner of Risk/Policy/Evidence.
* **P19 Sense-Decide-Optimize** — trigger schedule (Loop heartbeat); stages gather-KPIs→forecast→propose; owner of Budget (read-all); feeds Sheel's CORTEX + envelope stats.

## 3. Governance seeding (closes the Inc-1 carryovers)

Every entity ships with a **complete** governance block (Inc-1 GOV left unset bands pass-through; PACK closes that window):

* **Authority bands** per the §9.3 matrix (payout/refund/discount/contract/price/vendor) on every money-adjacent agent.
* **`sod_class`** — AGT-038 (AR, `maker`) ≠ AGT-046 (reconciliation, `checker`); AGT-068 (`auditor`, read-only). SoD tag pairs so the deploy validator enforces separation.
* **`karuna_profile: true`** on the gateways (KAR-*).
* **`memory_domains`** need-to-know: care agents get `[general, crm]`, finance agents `[general, financial]`, the watchdog `[general, legal, trust]` — a support agent's viewport can't contain financial nodes (§24.3).
* **`owner_process_id` resolution** — seeding the 6 PROCESS entities resolves the 27 HBS defs' `owner_process_code` → the new entity ids (Inc-1 SCH decision).

## 4. The 7 bundles (Functional §2.1) — activation sets, not pricing

The 7 starter bundles (Growth, Customer Success, Fulfillment, Finance, Compliance, Talent, Intelligence) are **named agent-activation groupings** — a bundle activates/deactivates a set of the Solo Pack (and, later, expansion) agents + their processes + trigger registrations. The **Solo Pack** is the cross-cutting default (the 12 agents / 6 processes). Bundles map to process groups; pricing is a **separate** concern from activation.

> **Decision (Rahul, 2026-07-20): all bundles are included at all subscription tiers.** No per-tier bundle gating in Inc 2 — every tenant can activate any bundle regardless of subscription tier. (Tiers still differ on the shipped dimensions — wallet/credit limits, rerank-flag Growth+ features, hibernation windows — just not on *which bundles are available*.)

## 5. Code Mapping

| Piece | Where | Notes |
|---|---|---|
| Agent/process templates | `backend/src/ai/solo_pack/templates/` | 12 agents + 6 processes as reviewed defs (extends SLICE's 4) |
| Bundle definitions | `solo_pack/bundles.py` | bundle → {agents, processes, trigger patterns} |
| Activation service | `solo_pack/activation.py` (from SLICE) | generalized to seed any bundle; idempotent per tenant |
| SoD seed data | extends GOV's `sod_rules` | the maker/checker/auditor tag assignments |
| Behavioral goldens | `tests/eval/` | one golden per agent (technical §22 GA gate) |

## 6. Task Plan (outline — firms up per-agent as built)

| # | Task | Acceptance |
|---|---|---|
| T1 | Author + review the 6 process sheets (P06/P08/P10/P14/P19; P03 from SLICE) | Rahul reviews; each becomes a checked-in sheet |
| T2 | Author + review the 9 workforce agent templates (AGT-013/015 from SLICE) | complete governance blocks; deploy validators pass |
| T3 | Bundle definitions + generalized activation service | activating a bundle seeds its agents/processes/triggers; Solo Pack default activates all 12/6 |
| T4 | Governance seeding: bands + sod_class + memory_domains + owner-id resolution | SoD demo (AR ≠ reconciliation) holds; no channel-facing entity has unset bands |
| T5 | Per-agent behavioral goldens + gates | each agent has an eval golden; mypy/parity/eval green |

## 7. Brainstorm Decisions (Rahul, 2026-07-20)

1. **Author all 6 process sheets up front** (they're the product spec), then build agents incrementally.
2. **AGT-092 stays distinct but thin** — a helper under AGT-035 Appointment Concierge until calendar connectors land (Inc 4).
3. **All bundles included at all subscription tiers** (§4) — no per-tier bundle gating.
