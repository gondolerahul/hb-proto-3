# Increment 4 — The Connected Business — Charter Stub

> **Status:** Stub for CONN/SOR — deepened just-in-time; a clarifying-questions round with Rahul precedes those docs.
> **Superseded in part (2026-07-22):** the increment gained a third, parallel workstream — **PRAGYA-RT** ([01_pragya_runtime.md](./01_pragya_runtime.md), seam locked). It does not displace the CONN/SOR scope below. See [00_overview.md](./00_overview.md) §1 for why it landed here, and §4 for why it builds first.
> **Parent:** [build_roadmap.md](../build_roadmap.md) §4, Increment 4 (L–XL, parallelizable per connector). **Prerequisite:** Increments 1–2 (SIG + records/links; MCP adapter is already shipped).

## Goal

The tenant's existing systems join the loop without a migration — or HireBuddha *is* all their systems.

## Scope (from the roadmap)

* **CONN** — the functional §6.6 connector catalog built out **MCP-first**: accounting/bank feed first (deepens the Solo Pack's AR/bookkeeping immediately), then calendar, e-sign, enrichment, payouts behind the authority matrix.
* **SOR** — per-object mastering (technical §21, design done): `sor` declaration per object def, mirror rows + `external_ref`, write-back-first semantics, master-wins conflicts via `sync.conflict` signals, HITL-gated ownership migration.
* **HBS module depth** (technical §10.3): field-level completeness for Accounting/HRMS/ERP/Legal so the standalone-system guarantee holds for tenants with no external software.

## Register findings to close here

D2 (per-agent credential scoping — SoD becomes real here or never; KMS/HSM + rotation for the master key), C2 (HUMAN_TASK step type + worker task queue/surface — physical fulfillment appears with real operations).

## Known open questions (CONN/SOR only — PRAGYA-RT's are decided)

1. Connector priority order after accounting (calendar vs e-sign vs enrichment) — driven by early Solo Pack tenant demand.
2. Which accounting systems first (Tally/Zoho Books for the Indian ICP vs QuickBooks/Xero)?
3. C2 worker surface: mobile-web task list vs WhatsApp-driven task flow.
