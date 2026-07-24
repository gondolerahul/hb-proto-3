# Increment 6 — The Self-Improving Platform — Charter Stub

> **Status:** Stub — deepened just-in-time; the hardest-gated increment. A clarifying-questions round with Rahul precedes the full docs. **GenUI's Design Gate is PASSED** (2026-07-24) — [genui_design_gate_concepts.md](../genui_design_gate_concepts.md) §6 (owner selection) + the ratified [genui_design_gate_spec.md](../genui_design_gate_spec.md) v1.2 (**Vihara**).
> **Parent:** [build_roadmap.md](../build_roadmap.md) §4, Increment 6 (XL). **Prerequisite:** Increment 5 (EVX gates operational — nothing self-modifying ships without them).
> **Read next:** [00a_genui_backend_gap_analysis.md](./00a_genui_backend_gap_analysis.md) — the Vihara spec walked against the shipped code (23 backend gaps, 12 road-map gaps, proposed workstream shape, six extra owner questions).

## Goal

The "Week 12 > Week 1" promise, measured by the §22 harness rather than asserted.

## Scope (from the roadmap, in order)

1. **LEARN** — unified learning store on the signal bus; charter tuning under EVX gates + the B10 risk policy (reward-hacking constraints: Karuna bounds are hard constraints, drift monitors, explicit cross-tenant learning policy).
2. **SEGA** — self-evolution GA: independent-suite rule + canary + B11 blast-radius limits (**tenant-scoped only**; global tool changes stay on the platform-admin pipeline). Builds on the shipped tool-synthesis pipeline.
3. **GENUI** — **Vihara**, a completely new frontend built from scratch (Design Gate passed); the shipped React app remains the surface until cutover. Note §14.2 keeps the **partner and platform-admin consoles on legacy React** — the cutover retires the *tenant* surface, not all 59 screens.
4. **Dynamic-schema evolution triggers** (technical §10.2) — agent-proposed fields, learning-driven def promotion, learning-promoted expression indexes (§19.3).

**Proposed additions from the gap analysis** (owner decision pending — question 1 below):

5. **TWIN** — the Glasshouse as its own subsystem: twin data plane, replay engine, forecast engine, honesty grading (L6) at schema level, the Scenario Shelf, and the promotion pipeline over SEGA's entity-change canary. *Introduced by the Design Gate; never scoped in the road map* (VR-02).
6. **STRAT** — the strategy pipeline (Minutes → Propositions → Resolutions → Mandates → Reviews) plus HBS **Planning** module depth. The Planning module ships with one object today (`Budget`); Inc-4's HBS-depth line named Accounting/HRMS/ERP/Legal only (VR-03).

## Register findings to close here

B10 (learning-system risk blindspots), B11 (self-evolution blast radius), D3 (full context-taint tracking — the §18.6 trust field shipped in Inc 1 is the down-payment). **D3 grows in weight under GenUI**: a manifest architecture lets model output choose what UI renders, so taint rules must cover the manifest path and the certified-set boundary must be a tested invariant (VG-23).

## Decisions (locked 2026-07-24 with Rahul — do not re-litigate)

1. ~~Design Gate process~~ — **ANSWERED** by the Design Gate itself: concepts §6 (owner selection) + the ratified Vihara spec; §13 there defines the exit criteria and the G0–G6 internal gate plan.
2. **B10 cross-tenant learning — SPLIT.** *Platform-level* learning (routing decisions, model performance — **no business content**) pools across tenants; *tenant-level* learning (charter tuning, density, behavioural preference) stays strictly per-tenant. The split is drawn where the leakage risk actually lives, and it is a **schema-level** distinction, not a query convention: a learning record must declare its scope and the pooled path must be structurally incapable of carrying tenant content.
3. **Learning-store shape — REUSE.** Extend the shipped **signal bus** (events) + **CORTEX Intelligence trees** (distilled learning). No dedicated `learning_signals` table. Consequence to design around: both systems now carry a third job, so B10's scoping must be explicit in the record shape (see decision 2) rather than implied by which store a row sits in.
4. **Flagship scope — BOTH IN, full flagship.** **TWIN** and **STRAT** are named Increment-6 workstreams. G5 ships. This is consistent with the owner's §6.8 full-flagship decision and makes Increment 6 the largest increment attempted.
5. **Certified-action step-up — PULLED FORWARD** as standalone hardening ahead of the Inc-6 design docs (it is a live gap in the shipped React app, not only a Vihara gap).

## Still open — for the workstream design rounds

* **Twin spend's budget class** (VG-09, for the TWIN doc): spec §12.1 says twin spend sits under the *platform-initiated* class, but a tenant's what-if is tenant-asked-for work — and the B13 convention forbids putting tenant-asked-for work in `PLATFORM_INITIATED_ATTRIBUTIONS`, or ordinary tenant activity exhausts the cap that exists to protect tenants *from* platform work.
* **Broadcast gates** (VR-06, for the GENUI doc): the full-flagship decision implies the **KAR-05** governed social family is in scope — to be confirmed when the gateway roster is designed, since the shipped `social_connection_service` sits outside SIG/Karuna/consent.

## Prerequisites that must land before the GENUI build

* **Certified-action step-up** (VG-05/VR-12) — decision 5: **building now**.
* **Voice go-live** (VG-08/VR-11) — G3 cannot pass on a tested seam. Ops-coupled (real Vertex/Gemini credentials + carrier media); schedule against a credentialed environment.
