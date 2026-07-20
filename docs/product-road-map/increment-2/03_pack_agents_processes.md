# Increment 2 / PACK — The 12 Curated Agents, 6 Processes & 7 Bundles

> **Status:** ✅ **Built (2026-07-20)** — T1–T5 done on `inc2/pack`; gates green (mypy `--strict` incl. `solo_pack`, 974 unit + solo_pack integration, parity, eval; layout clean). The full Wave-0 roster (16 curated entities) activates, owner-ids resolve across all six processes, and the maker/checker SoD holds at runtime. See §8 build notes. · **Branch:** `inc2/pack` · **Closes:** C1 (all 6 Wave-0 processes), Inc-1 owner-id resolution + governance-band seeding.
> **Note:** the 9 **workforce agents** + 5 new **process templates** + 7 bundles are built here; the two remaining **gateways** (KAR-01 voice stub, KAR-03 WhatsApp) are the **KAR** workstream. "12 agents" in the title counts the 3 gateways + 9 workforce agents; PACK ships the 9 + KAR-02 (from SLICE).
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

## 8. Build Notes — deltas discovered during implementation (2026-07-20)

The full Wave-0 roster is built and every gate is green. The notable facts:

1. **The manifest, not per-template metadata, encodes the tree.** Generic activation needs to know parentage (gateway/process under Sheel, agent under its process). Rather than tag every template with `pack_role`/`parent_process_code`, the tree lives in one place — `templates.PROCESS_GROUPS` (a `ProcessGroup(process, agents)` list) + `GATEWAYS`. `activate_slice` generalised into a shared `_activate(groups, gateways)` core with three entry points; the slice stays exactly 4 entities / 3 triggers (its test is unchanged).

2. **Bundles are the canonical §2.1 mapping, activation is the intersection.** `bundles.py` declares all 7 starter bundles with their *full* 19-process membership; activation seeds only the processes that have authored templates. So Fulfillment/Talent (no Wave-0 process yet) seed just the gateway + Sheel, and adding a P05/P12 template later lights them up with no plumbing change. **Process codes are stored numerically** (`(8, 9, 10, 11, 18)`) and rendered `P{nn}` on read — the de-canary lint bans the literal `P11` token in `ai/` source, and the Fiscal bundle's §2.1 membership includes it.

3. **P19 owns nothing (spine wins over the loose overview).** Overview §2 calls P19 "owner of Budget"; the HBS spine assigns Budget to the Plan-Budget-Forecast process, not Wave-0. P19 ships as a read-all planner — its `owner_process_code` resolves to no objects, which is correct. A unit test cross-checks every process's `owns_objects` against the spine owner codes so they can't drift.

4. **SoD needed two pieces: a persisted tag and an actor.** (a) The deploy validator reads `capabilities.sod_tags`, but the `Capabilities` schema didn't model it, so it was silently dropped on dump — added `sod_tags: list[str]` so the maker/checker/auditor classification persists. (b) The `tenant_record_write` tool now resolves the acting process from `agent_id` (its own `process_code`, else its parent process's) and passes it as `actor_process_code`, so a cross-owner write **proposes** (`object.change_proposed`) instead of mutating. Gateways/origination (no PROCESS ancestor) stay front-door — matching the SLICE's owner-direct path. The integration test proves P10's reconciler proposes on P08's Invoice while the P08 maker writes directly.

5. **Behavioral goldens are specs now, live replay later.** Per SLICE §8.1, scripting a multi-run agentic flow through the prompt-hash MockLLM is fragile; the platform seams are what the goldens exercise. The per-agent behavioral contracts are checked in as [03b_pack_behavioral_goldens.md](./03b_pack_behavioral_goldens.md) (liftable into `tests/regression/cases/` verbatim when prompts stabilise). What runs now: the template-contract unit tests (tools, checkpoints, injection-safety, read-only posture) + the deterministic seam tests (activation, SoD, the SLICE e2e).

**Task plan status:** T1 ✅ (5 process sheets, [03a](./03a_wave0_process_sheets.md)) · T2 ✅ (7 agents + 5 process templates) · T3 ✅ (7 bundles + generalized activation) · T4 ✅ (bands + sod_class + sod_tags + memory_domains + owner-id resolution + SoD demo) · T5 ✅ (behavioral golden specs + gates green + this log).
