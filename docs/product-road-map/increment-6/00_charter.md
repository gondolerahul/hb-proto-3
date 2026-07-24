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

## Known open questions

1. ~~Design Gate process~~ — **ANSWERED 2026-07-24** by the Design Gate: concepts §6 (owner selection) + the ratified Vihara spec; §13 there defines the exit criteria and the G0–G6 internal gate plan.
2. Cross-tenant learning policy (B10): pooled with disclosure vs strictly per-tenant with cold start.
3. Learning-store shape: extend the shipped signal bus + CORTEX Intelligence trees vs a dedicated `learning_signals` store.
4. **Flagship scope** (VR-02/VR-03): does the Vihara launch include TWIN and STRAT as built subsystems, or does it ship without G5 and without the Boardroom's Resolutions/Mandates?
5. **Twin spend's budget class** (VG-09): spec §12.1 says twin spend sits under the *platform-initiated* class, but a tenant's what-if is tenant-asked-for work — and the B13 convention forbids putting tenant-asked-for work in `PLATFORM_INITIATED_ATTRIBUTIONS`.
6. **Broadcast gates** (VR-06): build the KAR-05 governed social family, or cut social from the flagship and leave the legacy ungoverned path?
7. **Certified-action step-up** (VR-12): pull forward now as standalone hardening — `require_tier` has no REST call sites today — or fold into G2?

## Prerequisites that must land before the build

* **Voice go-live** (VG-08/VR-11) — G3 cannot pass on a tested seam.
* **Certified-action step-up** (VG-05/VR-12) — subject to question 7.
