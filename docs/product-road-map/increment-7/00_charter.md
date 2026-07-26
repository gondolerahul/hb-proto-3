# Increment 7 — Vihara (the GenUI Flagship) — Charter

> **Status:** Charter — created 2026-07-24 when GENUI was **split out of Increment 6 into its own increment** (owner decision, §Decisions below). Design Gate already **passed**; a *design phase* (wireframes, schemas, art bible) is this increment's first gate.
> **Parent:** [build_roadmap.md](../build_roadmap.md) §4, Increment 7 (XL). **Prerequisite:** Increment 6 complete — Vihara's G5 consumes TWIN, its density dial consumes LEARN, its promotion pipeline consumes SEGA's canary, its Boardroom consumes STRAT.
> **Read next:** the ratified spec [genui_design_gate_spec.md](../genui_design_gate_spec.md) v1.2 (**Vihara**) · the owner selection [genui_design_gate_concepts.md](../genui_design_gate_concepts.md) §6 · the gap inventory [increment-6/00a_genui_backend_gap_analysis.md](../increment-6/00a_genui_backend_gap_analysis.md) (VG-01…VG-23).

---

## Goal

Replace the 59 hand-built React screens with **Vihara** — the tenant's estate: a still surface at rest, one walkable territory beneath it inhabited by named colleagues, a Glasshouse beside the real, and a private line in the pocket, all composed by Pragya from manifests rather than hand-laid out.

## Why this is its own increment (decision, 2026-07-24)

Four reasons, recorded so the split is not re-litigated:

1. **Dependency shape.** GENUI consumes *every other* Increment-6 workstream — LEARN (density, morning set), SEGA (the entity-change canary its promotion pipeline calls), TWIN (the Glasshouse itself), STRAT (the Boardroom's mandates). An increment cannot close until its last workstream finishes, and this workstream depends on all the others. That is two increments stacked, not one with parallel tracks.
2. **Size.** The spec's own **G0–G6** is seven internal gates. Increments 1–5 each carried three to six *workstreams*.
3. **Exit criteria are increment-level.** The zero-training test with five naive users (§10.4), a WCAG 2.2 AA audit, a WebGL device matrix, the §12.1 performance floor, a 30-day parallel run with pilot tenants, and a feature-parity reckoning against all 59 legacy screens. None of those is a workstream gate.
4. **It does not reopen the full-flagship decision.** Concepts §6.8 ("full flagship at once") was about not phasing Vihara's *launch* — not shipping the Sanctum first and bolting on the Atlas later. It said nothing about sharing an increment with LEARN and SEGA. Splitting **protects** that decision: Vihara gets a whole increment to be one coherent launch instead of being the tail of another.

## Scope

### Phase A — the design phase (this increment's first gate)

The ratified spec is a **product-and-architecture** spec, not a build spec. It says so itself: §9.3 defers the component schema to "a build-time artifact", and §13 requires the art bible signed off *before G1 visuals begin*. Phase A produces what is missing:

1. **Wireframes / screen-level layouts** for the ~17 first-class surfaces in §5, at both densities (§6.3) and in the S-renderer equivalent every W surface owes under L9.
2. **The component registry JSON schema** — the four classes of §9.2 (primitive · certified · world · narrative), versioned, with the **certified set** frozen and golden-rendered.
3. **The manifest contract in full** (§9.3 made real), including the schema-level requirement that `honesty_grade ∈ {replay, forecast, unknown}` is **mandatory** on any Glasshouse-derived component (L6).
4. **Backend API contracts** for the three seams Vihara needs and the platform does not have: the **estate read model** (VG-02), the **company-scoped live stream** (VG-03), and **Pragya's event channel** (VG-07 — `deliver_tray` / `focus` / `materialize` / `narrate` / `presence`; `viewport` / `depth_change` / `action_echo` / `step_up_result`).
5. **The art bible** — palettes for day and night, typography, motion, and the §14.5 in-house **portrait style boards** (3–4 candidate directions in the engraved-illustration register) for owner sign-off.
6. **Device matrix and per-surface performance budgets** behind §12.1's <300ms first-scaffold number, plus the reduced-motion and screen-reader paths.

### Phase B — G0 → G6

Per spec §12, unchanged: **G0** substrate · **G1** walkable estate · **G2** daily driver · **G3** the steward present · **G4** the pocket · **G5** the Glasshouse opens · **G6** launch quality.

## Register findings

None of its own. Vihara *consumes* the closures of Increment 6 and carries **D3**'s manifest-path obligation: a generative layer that chooses what UI renders is a new injection surface, and L5 (certified surfaces deterministic) is only the mitigation for the money/legal set. The certified-set boundary must be a **tested invariant**, not a convention.

## Prerequisites

* **Increment 6 complete** (LEARN · SEGA · TWIN · STRAT · GATE · LIB).
* **Voice go-live** — G3 ("the steward is present") cannot pass on a tested seam. 🅿️ **PLANNED AND PARKED 2026-07-26: [00a_voice_go_live_plan.md](./00a_voice_go_live_plan.md)** — six phases, two decisions locked, a **fourth gap** found beyond the three Inc-4 §12.5 named (`route_for_number` computes the face and discards it). Note the scope correction recorded there: **business voice is already live**; VG-08 is *Pragya's inward face* alone. Most of the work needs no credentials (VG-08/VR-11).
* **The step-up refusal rendered in the frontend** — `ai/inward_auth/guard.py` shipped 2026-07-24 and returns a machine-readable 403; the React app does not yet open a ceremony on it. Small task, needed before Vihara inherits the same contract.

## Known open questions (for the Phase-A design round)

1. **Stack ratification** — spec §12 *recommends* TypeScript throughout, React for the S/C renderers, Three.js via react-three-fiber for W, and a shared design-token package; the Line app is "React Native or high-quality PWA — decide at G0 with a spike". Confirm at Phase A, not G0.
2. **Push provider** for L8 notification discipline (VG-19) — nothing exists today, and the law requires a broker with exactly **one** writer (Pragya) by construction.
3. **Partner / platform-admin consoles** stay on legacy React (§14.2, ratified). Confirm the cutover checklist marks those screens *out of scope* rather than *retired*, so the 59-screen parity reckoning is honest (VR-10).

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-24 | v1.0 — created by the Increment-6 split (owner decision): GENUI leaves Inc 6 and becomes Increment 7, pushing Scale & Enterprise to [Increment 8](../increment-8/00_charter.md). Adds **Phase A**, the design phase the ratified spec explicitly defers (wireframes · component schema · manifest + API contracts · art bible · device matrix), ahead of G0–G6. |
