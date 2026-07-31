# Increment 7 / Phase A — The Design Phase: Overview & Plan

> ⚠️ **2026-07-30 — R2's central assumption failed.** This phase's blocking review passed the wireframes (§4, R2), the app was built to them, and the built app was **rejected on design**. The lesson is recorded as the redesign's decision D4: **low-fidelity approval does not predict craft approval**, so the redesign reviews a pixel-final interactive prototype instead. D6's drawings are superseded; its surface inventory and bindings survive. See **[redesign/00_redesign_charter.md](./redesign/00_redesign_charter.md)** §2 for what the boards actually produced (findings RD-1…RD-7).
>
> **Status:** ✅ **PHASE A EXITED 2026-07-29.** All eight deliverables written; **R1 and R2 both PASSED** (art bible all eight rulings; wireframes all seventeen surfaces). Portraits: **A with C fallback** (VP-02 resolved). **VP-03 resolved: The Study.** §8 records what the phase found. Next: the workstream decomposition — [10_workstream_decomposition.md](./10_workstream_decomposition.md).
> **Goal:** produce what the ratified spec deliberately defers, so that G0 starts against contracts rather than against prose.
> **Gate:** no G0 code until every deliverable below is complete (charter sequencing decision).
> **Read next:** [00_charter.md](./00_charter.md) §Decisions · the ratified [genui_design_gate_spec.md](../genui_design_gate_spec.md) · the gap inventory [increment-6/00a](../increment-6/00a_genui_backend_gap_analysis.md).

---

## 1. Why this phase exists

The ratified spec says of itself, twice, that it is not a build spec: §9.3 defers the component schema to "a build-time artifact", and §13 requires the art bible signed off before G1 visuals begin. Everything in it is true at the level of *product and architecture* and under-determined at the level of *what a renderer receives*.

Phase A closes exactly that distance. It is a documentation increment with no code, and it ends when a G0 engineer can build the manifest service without asking a design question.

**One thing changed since the charter was written.** The **Buddha Cognitive Lab design system** landed in this folder on 2026-07-28 — a real brand with real tokens, a voice, a type stack and a material. Charter decision 2 made it canonical across all three renderers, which means Phase A's art bible is not an invention exercise: it is a **translation** of a settled brand onto a world the brand has never had to describe. That is a smaller job than the charter assumed and a more constrained one.

## 2. The deliverables

Eight, not six: the charter's six §Scope items, plus the **stack ratification** its open question 1 demands, plus the **parity register** VR-10 requires.

| # | Doc | Deliverable | Closes |
|---|---|---|---|
| D1 | [02_stack_and_repo.md](./02_stack_and_repo.md) | Stack and repo ratification: the `vihara/` app, TS/React/react-three-fiber, the token package, the PWA Line, the test runner and CI gates | Charter Q1 · decisions 4/5/6 |
| D2 | [03_art_bible.md](./03_art_bible.md) | The art bible: palette, day–night as luminance, type, motion, material, portrait direction + specimens, the a11y colour rules | Spec §13(b) · §14.5 · decisions 2/3/8 |
| D3 | [04_component_registry.md](./04_component_registry.md) | The component registry JSON schema — §9.2's four classes, versioned, the **certified set frozen** and golden-rendered | VG-01 (half) · L5 |
| D4 | [05_manifest_contract.md](./05_manifest_contract.md) | The manifest contract in full — §9.3 made real, `honesty_grade` mandatory at schema level, the intent-shape cache, schema-derived re-derivation | VG-01 (half) · L6 |
| D5 | [06_backend_api_contracts.md](./06_backend_api_contracts.md) | Backend API contracts: estate read model, company-scoped live stream, Pragya event channel, echo bus, density store, push subscriptions | VG-02 · VG-03 · VG-06 · VG-07 · VG-19 · VG-21 |
| D6 | [07_surface_wireframes.md](./07_surface_wireframes.md) | Screen-level layouts for the §5 surfaces, at **both densities**, each with its **L9 sheet equivalent** | Spec §5 · §6.3 · L9 |
| D7 | [08_device_matrix.md](./08_device_matrix.md) | Device matrix, per-surface performance budgets behind the <300ms first-scaffold floor, WebGL fallback rules, reduced-motion and screen-reader paths | VG-22 · §12.1 |
| D8 | [09_screen_parity_register.md](./09_screen_parity_register.md) | All 59 legacy screens, each marked **replaced-by / out-of-scope / retired** | VR-10 |

## 3. Order, and the one cycle in it

```
D1 stack ─┐
D2 art ───┼──▶ D6 wireframes ──▶ D7 device matrix
D3 registry ──▶ D4 manifest ──▶ D5 backend contracts
     ▲                                    │
     └──────── delta pass ◀───────────────┘
D8 parity register — independent, any time
```

D1 and D2 have no dependencies beyond the brand bundle and the charter. D3 can be written from spec §5's surface inventory and §9.2's four classes without the wireframes, because the **certified set is fixed by L5** and is knowable today; D4 needs D3; D5 needs D4's manifest shape and §4's ontology.

**The cycle is real and planned for.** D6 will discover components D3 did not list — that is what drawing seventeen surfaces is *for*. Rather than pretend D3 got it right first, D3 carries a **§Delta** section that D6 writes back into, and D3 is not considered final until D6 is done. A registry declared complete before anything was drawn against it would be a registry that is wrong and says it isn't.

## 4. Owner review checkpoints

This repo has a settled rule about which artifacts get a blocking owner review: **the ones a business owner reads or looks at**. The HBS spine, the Pragya stage scripts and the STRAT object sheets all got one, and each round found something drafting alone had not — an arithmetic error, a third assert site, three field names in engineer-speak.

Two Phase-A deliverables meet that bar:

| Checkpoint | Artifact | Why it blocks |
|---|---|---|
| **R1** | **D2 — the art bible** | Spec §13(b) makes owner-approved samples a gate condition, and §14.5 makes the portrait round explicitly an owner sign-off. Nothing aesthetic ships before it passes. |
| **R2** | **D6 — the wireframes** | These are the product a naive user will be tested against (§10.4). Seventeen surfaces at two densities is where "calm" either survives contact with real content or does not. |

D1, D3, D4, D5, D7 and D8 are engineering artifacts and do not block on review — they are reported, not ratified.

## 5. What Phase A is *not*

* **Not a build.** No `vihara/` directory is created, no dependency installed, no endpoint written. D1 specifies the app; it does not scaffold it.
* **Not a re-litigation of the spec.** The ten Binding Laws, the depth ladder, the §4 ontology and the surface inventory are ratified input. Where Phase A contradicts the spec it is because a **decision** overrode it (decisions 2 and 3 override §11), and every such override is named in the deliverable and in the spec's own change log — never silently applied.
* **Not the Increment-7 workstream decomposition.** G0–G6 are the spec's gates; how they split into named workstreams with branches and build notes is the first thing written **after** Phase A exits, when the contracts exist to size them against.

## 6. Exit criteria

Phase A is complete when all eight deliverables exist, **R1 and R2 have passed**, and three specific properties hold — each chosen because its absence is the failure mode that would only surface at G2:

1. **Every surface in spec §5 appears in D6 with both a density variant and a sheet equivalent.** L9 is a guarantee, and a guarantee with an unlisted exception is a convention.
2. **Every component D6 composes exists in D3**, and every certified component in D3 has a golden-render fixture named. (The delta pass of §3 is what makes this true; it is checked at the end, not assumed at the start.)
3. **Every binding D6 draws exists in D5** or is named there as absent with the finding that owns it. A wireframe that reads a number nothing projects is a wireframe that will be redrawn at G1.

## 7. Standing risks carried into the phase

| Risk | Why it is real here |
|---|---|
| **The brand has never had to describe a world** | The bundle specifies chrome, cards, type and a material. It says nothing about a district, a beacon, weather or a portrait, and its one imagery rule ("dark, warm, high-contrast, slightly golden") is a mood, not a cartography. D2 is extrapolation, and extrapolation is where a brand breaks. Mitigated by R1 being a blocking review with samples rather than prose. |
| **Design-before-code buys against rework and pays in latency** | The owner chose the stricter sequencing knowingly. The exposure is that a contract nobody has implemented can be confidently wrong; D5 mitigates it by specifying against **shipped** endpoints and named findings, never against imagined ones. |
| **Auth and the API client are rebuilt** (decision 4) | Real cost, accepted. The exposure is drift between two clients against one backend. D1 names how the contract is kept honest. |
| **`origin/master` is 49 commits behind** | Not Phase A's work, but Phase A adds to the pile. Flagged in the charter §Verified so it is not discovered later. |

---

## 8. What the phase found

Eight deliverables, written 2026-07-28. Each carries its own reasoning; these are the findings that outlive it.

### 8.1 New findings raised

| # | Finding | Raised in | State |
|---|---|---|---|
| **VP-01** | `localStorage` tokens are a materially worse trade in an app that renders generated UI and drives T2/T3 step-up than in the app that shipped them | D1 §5 | **Resolved** in D5 §9 — access token in memory, refresh token in an `HttpOnly` cookie, legacy path untouched (~half a day of backend work) |
| **VP-02** | The procedural seal portrait direction has no production cost, needs no ADC and cannot drift from a colleague's versions — it may be the floor rather than the fallback | D2 §7.1 | **Resolved at R1 (2026-07-29):** A is the house style, C stays the fallback — the recommendation as written. A-direction rasters remain a pre-G1 obligation |
| **VP-03** | Three tenant functions have **no Vihara surface at all** — pre-session, account & security, billing & wallet. Passkey enrolment sits inside that gap and is the prerequisite for every T2 act | D8 §4 | **Resolved at R2 (2026-07-29): The Study** — one depth-2 surface reachable from the shell, as proposed; pre-session stays conventional. D8 §4 records the ruling |

### 8.2 Corrections to shipped documents

| What | Where it was wrong |
|---|---|
| **The certified endpoint count is six, not five** | STRAT added resolution adoption on 2026-07-26 with `IntentKind.STRATEGY_RESOLUTION`; the HANDOFF, the gap analysis and the VG-05 build note all still say five. D3 §3.3 — and rule R5 now keeps the count honest by CI rather than by memory |
| **VG-21 is already closed** | LEARN's preference store shipped 2026-07-25 with the `density` namespace, an observation threshold and both endpoints. The gap analysis still lists it open at severity **M**. D5 §8 |
| **"59 screens" is a file count** | Five of the 59 `.tsx` files are not screens. The honest denominator is 54, and cutover parity is **28 of 30 in-scope tenant screens**. D8 §1, §3 |
| **Spec §11 is superseded** | Marked in place, with what is retired *and* what is carried forward both named. D2 §1 |

### 8.3 Decisions the phase made that the spec did not

* **The gold budget** (D2 §2.1) — gold means *this needs you* or *this is certified*, and nothing else. Under a single-accent brand this is what makes a still estate visibly still.
* **The certified set is derived from the tier gate, not chosen** (D3 §3.1). It survived the wireframe pass unchanged at ten, which is its correctness proof.
* **There is no `ui_manifests` table** (D4 §5.1), despite technical §8 and VG-01 both sketching one.
* **Weather is projected on read, never stored** (D5 §2.1).
* **The shell is app-owned, not manifest-composed** (D6 §1) — a hostile manifest cannot remove the user's way out.
* **A tier-C device never downloads three.js** (D7 §3.3), enforced as a hard build gate.

### 8.4 Exit criteria — status

| # | Criterion | State |
|---|---|---|
| 1 | Every §5 surface drawn with a density variant and a sheet equivalent | ✅ D6, all seventeen |
| 2 | Every component D6 composes exists in D3; every certified component has a named golden | ✅ D3 §8's delta pass, 35 → 45 |
| 3 | Every binding D6 draws exists in D5 or is named there as absent with the finding that owns it | ✅ — the named absences are `paths[].cost` (D5 §4.1), VG-18, VG-20 |
| — | **R1** — the art bible | ✅ **PASSED 2026-07-29** — all eight §12 rulings approved; portraits A with C fallback |
| — | **R2** — the wireframes | ✅ **PASSED 2026-07-29** — all four §21 judgments accepted; VP-03 resolved to The Study in the same session |

**Phase A has exited.** The workstream decomposition — sized against these contracts, as §5 required — is [10_workstream_decomposition.md](./10_workstream_decomposition.md).

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-29 | v1.3 — **PHASE A EXITED.** R1 passed (all eight art-bible rulings, portraits A+C — VP-02 resolved) and R2 passed (all seventeen surfaces; VP-03 resolved to The Study). Every exit criterion is met. The decomposition ([10](./10_workstream_decomposition.md)) is written as the phase's closing artifact. |
| 2026-07-28 | v1.2 — **the visual boards are built** (art bible §13, wireframes header): five interactive end-state boards forming the walkable depth ladder, in the brand palette with the legacy app's energy-floor background carried forward. The owner approved the territory construction language on the terrace and district boards, which materially advances **R1** (the language is approved; §12's eight rulings remain) and gives **R2** its primary review material. |
| 2026-07-28 | v1.1 — all eight deliverables written; §8 added. Three new findings (**VP-01** resolved, **VP-02** for R1, **VP-03** open and the most consequential), four corrections to shipped documents, and six decisions the spec did not make. Exit criteria 1–3 met; the phase now waits on R1 and R2. |
| 2026-07-28 | v1.0 — Phase A opened. Seven deliverables (the charter's six plus VR-10's parity register), the dependency order with its one deliberate cycle, two blocking owner review checkpoints chosen by the repo's own precedent, and exit criteria written as the three properties whose absence would only surface at G2. |
