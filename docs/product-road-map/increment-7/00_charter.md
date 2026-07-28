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

## Decisions — ALL EIGHT LOCKED with Rahul, 2026-07-28 (do not re-litigate)

The clarifying round ran against the measured state of `master` (gates in §Verified below), the ratified spec, and one input the spec has never seen: the **Buddha Cognitive Lab design system** bundle, committed into this folder on 2026-07-28. Three of the eight answer the charter's own open questions; the other five were forced by that bundle and by the measured state.

**1. Next work is Increment 7 Phase A.** The voice go-live remainder ([00a](./00a_voice_go_live_plan.md) §8) is owner-side — two config items and a phone call — and runs in parallel rather than blocking the design phase.

**2. The brand design system governs everywhere — spec §11 is superseded.** The bundle's warm near-black canvas (`#0a0908`), the single gold (`#edab48`), Space Grotesk / Hanken Grotesk / JetBrains Mono, the liquid-glass material and the no-emoji rule are canonical across **all three renderers**, the World renderer included.

What this retires, named so it is not rediscovered as a bug: §11's **parchment daylight cartography**, its **deep-indigo night ground**, its **walnut/brass/paper/linen interiors**, and its **narrative serif**. The territory is now lit rather than tinted — see decision 3.

**3. Living day–night survives as luminance, not as palette.** Concepts §6.7 (an owner decision) is preserved in substance: the territory still follows the tenant's local time. Under decision 2 the shift is **key-light and lamplight** inside one near-black frame — high-key warm gold-white daylight with long soft shadows by day, low-key lamplit pools and a dark ground at night — rather than parchment ↔ indigo. Weather and beacons read identically in both, as §4 requires.

**4. Vihara is a new top-level app in this repo** — `vihara/`, beside `backend/` and `frontend/`: its own `package.json`, build, CI job and deploy target, sharing one git history with the roadmap docs and the backend contracts it consumes. The owner asked for a **separate app entirely**, and this is that with the increment workflow (branch per workstream, build notes, atomic contract+consumer commits) intact. Consequence accepted and stated: auth, session handling and the API client are **rebuilt, not reused** — `frontend/`'s services are not imported.

**5. Stack ratified as spec §12 recommends** — TypeScript throughout, React for the Sheet and Card renderers, Three.js via react-three-fiber for the World renderer, one shared design-token package consumed by all three. *(Charter open question 1, closed.)*

**6. The Private Line is an installable PWA**, not React Native. The decisive reason is not effort: **T2 step-up already works** — the platform ships platform-built WebAuthn (`iauth001`), and platform authenticators are available to installed PWAs, so the biometric certified card needs no native shell. One Card renderer serves the desktop tray and the pocket.

**7. Push is self-hosted Web Push / VAPID** (VG-19). No vendor, no SDK, no per-message cost; a device token is a subscription row in our own table, which is what makes L8's **single-writer** constraint enforceable in our own code rather than promised. Stated ceiling: on iOS the user must install the PWA before push exists at all. *(Charter open question 2, closed.)*

**8. Portrait direction is written now; rasters land before G1.** The art bible carries the portrait direction and HTML/SVG style specimens in the brand tokens; raster generation waits on working ADC (the same blocker voice sits behind) or the owner's own image tool, and must complete before G1 visuals per spec §13.

**Phase A sequencing (locked with the eight):** **all six Phase-A deliverables complete before any G0 code.** This is deliberately stricter than spec §13's v1.1 amendment, which permits G0 to start immediately — the owner chose to pay design-phase latency to buy against rework.

**Still open, and confirmed as such:** the partner / platform-admin console scope (§14.2, ratified tenant-first) needs the cutover checklist to mark those screens **out of scope** rather than *retired*, so the 59-screen parity reckoning stays honest (VR-10). That is a Phase-A deliverable line item, not a decision.

## Verified state at the start of Phase A (2026-07-28, `master` @ `5321e72`)

Measured, not read off the HANDOFF: `typecheck_ai.py` **319 files** strict · layout lint exit 0 · `tests/unit` **2016 passed**, 2 skipped · `tests/parity tests/eval` **16 passed** · `tests/integration` **504 passed** · `alembic heads` **`iauth002`**, single head. `frontend/src/pages` is **59 `.tsx` files** — still exactly the number spec §5 says Vihara replaces.

Two corrections to the HANDOFF, which stops at the Increment-6 close:

1. **Voice go-live is built**, not parked — five commits after the HANDOFF's last line closed all six gaps and added migration `iauth002`. What remains is a live call ([00a](./00a_voice_go_live_plan.md) §8).
2. **`origin/master` is behind again** — 49 commits unpushed. §1's "the push is DONE" is history for the third time.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-28 | v1.1 — **the clarifying round ran; eight decisions locked**, closing the charter's own questions 1 and 2 and adding five the **Buddha Cognitive Lab design system** forced when it landed in this folder the same day. The load-bearing one is decision 2: the brand governs **all three renderers**, so ratified spec §11's parchment-and-indigo art direction is superseded and day–night survives as a *luminance* shift (decision 3). Also: Vihara is a new top-level `vihara/` app in this repo with auth and API client rebuilt (4), the Line is an installable **PWA** because platform WebAuthn already serves it (6), push is self-hosted **Web Push/VAPID** (7), and **all six Phase-A deliverables complete before any G0 code** — stricter than spec §13 permits, by owner choice. State at Phase-A start measured and recorded (§Verified), including two HANDOFF corrections: voice go-live is **built**, and the remote is behind by 49 commits. |
| 2026-07-24 | v1.0 — created by the Increment-6 split (owner decision): GENUI leaves Inc 6 and becomes Increment 7, pushing Scale & Enterprise to [Increment 8](../increment-8/00_charter.md). Adds **Phase A**, the design phase the ratified spec explicitly defers (wireframes · component schema · manifest + API contracts · art bible · device matrix), ahead of G0–G6. |
