# Increment 6 — The Self-Improving Platform — Charter

> **Status:** Charter — decisions locked with Rahul 2026-07-24. **GENUI has been split out** into its own increment ([increment-7/](../increment-7/00_charter.md), *Vihara*), which pushed Scale & Enterprise to [increment-8/](../increment-8/00_charter.md). This increment is now **entirely backend**, which is what its title always promised.
> **Parent:** [build_roadmap.md](../build_roadmap.md) §4, Increment 6 (XL). **Prerequisite:** Increment 5 (EVX gates operational — nothing self-modifying ships without them).
> **Read next:** [00_overview.md](./00_overview.md) (the increment plan) · [00a_genui_backend_gap_analysis.md](./00a_genui_backend_gap_analysis.md) (the gap inventory that produced the scope).

## Goal

The "Week 12 > Week 1" promise, **measured** by the §22 harness rather than asserted — and the platform state Vihara will need in order to render any of it.

## Scope — six workstreams

| # | Workstream | What it is |
|---|---|---|
| 1 | **LEARN** | Unified learning store on the signal bus + CORTEX Intelligence trees; charter tuning under EVX gates; the B10 risk policy; **KPI history**; the per-user density/preference store |
| 2 | **SEGA** | Self-evolution GA — independent-suite rule, the **entity-change canary**, B11 blast-radius limits (tenant-scoped only), the **entity version ledger**, D3 context taint |
| 3 | **TWIN** | The Glasshouse subsystem — twin data plane, replay engine, forecast engine, honesty grading, the Scenario Shelf, the promotion pipeline over SEGA's canary |
| 4 | **STRAT** | The strategy pipeline — Minutes → Propositions → Resolutions → Mandates → Reviews — plus **HBS Planning module depth** |
| 5 | **GATE** | **KAR-05** governed broadcast gates: social/ad channels enter SIG under the Karuna profile and the consent/DNC registry |
| 6 | **LIB** | The Library data layer — document provenance & source kinds, the **retrieval-usage log** (influence), staleness, connected drives, artifact→record linkage |

Plus **dynamic-schema evolution triggers** (technical §10.2) — agent-proposed fields, learning-driven def promotion, learning-promoted expression indexes (§19.3) — which land inside LEARN and SEGA rather than as a seventh workstream.

**Not in this increment:** everything Vihara. The manifest substrate, the estate read model, the live event stream, the echo-bus *endpoint*, trays, the Private Line and push all belong to [Increment 7](../increment-7/00_charter.md).

## Register findings to close here

**B10** (learning-system risk blindspots) · **B11** (self-evolution blast radius) · **D3** (full context-taint tracking — the §18.6 trust field shipped in Inc 1 is the down-payment).

## Decisions (locked 2026-07-24 with Rahul — do not re-litigate)

1. ~~Design Gate process~~ — **ANSWERED** by the Design Gate itself: concepts §6 (owner selection) + the ratified Vihara spec; §13 there defines the exit criteria and the G0–G6 gate plan.
2. **B10 cross-tenant learning — SPLIT.** *Platform-level* learning (routing decisions, model performance — **no business content**) pools across tenants; *tenant-level* learning (charter tuning, density, behavioural preference) stays strictly per-tenant. The split is **schema-level**, not a query convention: a learning record declares its scope, and the pooled path must be *structurally incapable* of carrying tenant content.
3. **Learning-store shape — REUSE.** Extend the shipped **signal bus** (events) + **CORTEX Intelligence trees** (distilled learning). No dedicated `learning_signals` table. Consequence to design around: both systems now carry a third job, so decision 2's scoping must live in the record shape rather than be implied by which store a row sits in.
4. **Flagship scope — BOTH IN.** **TWIN** and **STRAT** are named workstreams; the Glasshouse ships.
5. **Certified-action step-up — PULLED FORWARD.** ✅ Built 2026-07-24 (`ai/inward_auth/guard.py`) — see [00a](./00a_genui_backend_gap_analysis.md) §7.
6. **GENUI splits into its own increment.** Rationale in [increment-7/00_charter.md](../increment-7/00_charter.md) §Why. Strictly sequential: Increment 6 completes before Vihara's Phase A begins. Scale & Enterprise renumbers to 8.
7. **Twin spend is TENANT-initiated.** A what-if is tenant-asked-for work, so the attribution stays **out** of `PLATFORM_INITIATED_ATTRIBUTIONS` — the same rule RETR's `rerank` follows. This **overrides spec §12.1**, which put twin spend under the platform-initiated class; that would have let tenant experimentation exhaust the cap whose entire purpose is protecting tenants *from* platform work (B13).
8. **Pooled platform learning gets no opt-out, but is disclosed.** If decision 2's schema guarantee holds, the pooled path carries platform telemetry, not tenant data — an opt-out would cripple router learning for no privacy gain. The published [data-flow disclosure](../increment-5/03a_data_flow_disclosure.md) is **extended to name exactly what pools**. *(Note the asymmetry with D5's opt-in posture for foreign providers: that governs where tenant data physically goes; this governs aggregate telemetry that by construction contains none.)*
9. **KAR-05 broadcast gates are IN** (workstream GATE). Social and ad channels become real Karuna gateways — outbound through SIG, governed by the Karuna profile and consent/DNC exactly as KAR-02/03 are. This closes an ungoverned outbound path that exists in shipped code today (`social_connection_service.py` sits outside SIG, Karuna and consent).

## Build order

**LEARN → SEGA → TWIN → STRAT**, with **GATE** and **LIB** parallelisable at any point (neither depends on the other four).

The order is forced, not preferred: SEGA's entity-change canary is what TWIN's promotion pipeline calls, and TWIN's honesty grades are what STRAT's predicted-vs-realized reviews read. LEARN goes first because its **KPI history** is a time series — it is worth nothing until it has been accumulating, and three later surfaces (the Seasons timeline, plinth trends, mandate reviews) read it. The same "start collecting early" logic puts LIB's **retrieval-usage log** as early as its workstream allows.

## Known open questions

*(None blocking. Both former blockers were answered by decisions 7 and 9.)*

Carried into the workstream design rounds as design detail rather than owner decisions:

* **Dynamic-schema evolution** (§10.2) splits across LEARN (learning-driven def promotion) and SEGA (agent-proposed fields, under blast-radius limits) — confirm the seam when both docs are written.
* **Connected drives** (SharePoint / Google Drive) need §6.6 catalog rows; only a generic `notion_knowledge` row exists (VG-14). Sized inside LIB.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-24 | v1.0 — charter deepened from the stub. Nine decisions locked; **GENUI split out to Increment 7** and Scale & Enterprise renumbered to 8; six workstreams named (LEARN · SEGA · TWIN · STRAT · GATE · LIB) with a forced build order; twin spend ruled tenant-initiated *against* spec §12.1; pooled learning disclosed-but-not-opt-out; KAR-05 in scope. |
