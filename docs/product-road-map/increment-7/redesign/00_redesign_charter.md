# Increment 7 / Redesign — Charter

> **Status:** ✍️ opened **2026-07-30** by owner decision: the built Vihara frontend was **reviewed and rejected on design**. Backend seams stand; the tenant-facing app is redesigned and rebuilt from the visual layer up.
> **Resuming in a fresh session? Read [03_resume.md](./03_resume.md) first** — this charter is the *why*; that is the *how*.
> **Parent:** [00_charter.md](../00_charter.md) · [10_workstream_decomposition.md](../10_workstream_decomposition.md).
> **What this does not touch:** `backend/src/ai/genui/` (the SEAM workstream), the D5 API contracts, the manifest contract, the entity ontology, the depth ladder, or the parity register's denominators.

---

## 1. What happened

Increment 7 built to completion. All eight workstreams merged to `master` — SEAM, SUB, WORLD, DRIVER, STEWARD, LINE, GLASS, POLISH — followed by three unplanned polish rounds (`polish-look`, `polish-rooms`, `polish-light`) driven by owner screenshots. The extra rounds are the first signal in the record: three consecutive corrective passes on *look* meant the look was not converging.

At the owner review on 2026-07-30 the app was **rejected on design and feel**. The verdict, in the owner's words, is that the UI does not read as though every element was designed with care and given the time to be perfected. That is a craft judgment, and it is correct.

`vihara/` is preserved as **`vihara-review-rejected/`** — 23.9k LOC, gates green, retained as a parts bin (§4) and as evidence. It is not deleted, and it is not the base of the redesign.

## 2. The diagnosis

Written from the R2-approved visual boards ([../wireframes/](../wireframes/)) rendered at 1440×900, not from recollection. Seven findings, ordered by how much each cost.

| # | Finding | Why it happened |
|---|---|---|
| **RD-1** | **Typography is baked into the ground plane.** District names, colleague names, KPI figures and hop-lists are all skewed and rotated with the perspective. At 1440×900 they are not readable. | The territory was treated as a scene to be labelled rather than an interface to be read. Text in a 3D scene belongs in screen space, billboarded — never painted on the floor. |
| **RD-2** | **The built form is hollow wireframe cages.** Districts, halls and gatehouses are line-boxes with no material, no bevel, no thickness, no surface. They read as an unfinished CAD export. | Art bible §13's "holographic volumes" was implemented literally as wireframe. The inspiration set ([../inspiration/](../inspiration/)) is the opposite: solid, precisely-lit volumes dense with fine detail. |
| **RD-3** | **The gold budget starved the frame.** With gold restricted to *needs-you* and *certified*, everything else sits at 6–22% warm-white on near-black. Calm collapsed into blank. | The budget rule (art bible §2.1) is sound and is **kept**. What was missing is that the non-gold 94% needed its own richness — material, light, edge, texture — and it was given only alpha. |
| **RD-4** | **Depth 0 is a near-empty void.** Three lines of text mid-page over black. | "No chrome because it *is* the chrome" was read as "nothing on screen." A still surface still has to be composed. |
| **RD-5** | **The brand's own material vocabulary went unused.** `--gradient-gold-metallic`, `--gradient-gold-conic`, `--glass-edge-gold`, `--glow-gold`, `--glass-sheen` — the tokens that make the brand feel precious — barely appear in the rejected app. | The brand bundle was mined for colour and type and not for **material**. That is most of the perceived cheapness. |
| **RD-6** | **The legacy background system was never actually ported.** The owner's stated favourite — `frontend/src/components/layout/AnimatedBackground.tsx`, instanced hex tiles over a simplex-noise energy floor with `UnrealBloomPass` and a mouse-driven tile lift — was replaced by a thin Canvas-2D approximation (`vihara-review-rejected/src/atmosphere/floor2d.ts`) plus a partial GL port behind a tier gate. | It was treated as an effect to re-derive rather than an asset to carry across. |
| **RD-7** | **The working surfaces were structurally second-class.** Trays, Registry Halls, dossiers and the Boardroom were built as the "L9 sheet equivalent" — the guaranteed fallback for when the World renderer is off. The surfaces a business owner spends the day in inherited a fallback's design budget. | L9 is written as a *guarantee* ("every W surface owes a sheet"), and a guarantee framing produces adequacy, not excellence. |

**The through-line:** the 3D world absorbed the design effort, and the 3D world is not where the work happens. RD-1 through RD-6 are craft defects and are fixable by redrawing. RD-7 is structural, and it is what decision D1 below changes.

## 3. Owner decisions — locked 2026-07-30

Four, taken in one round against the diagnosis above.

**D1 · Scope: visual redesign plus an information-architecture rebalance.**
The ratified product architecture is kept — the eighteen surfaces, the depth ladder, the §4 entity ontology, the manifest system, the component registry, and every D5 backend contract. What changes is **where 3D is spent**. The World renderer keeps the overview surfaces that are genuinely spatial (the Still surface, the Terrace, district rooms, the Glasshouse's two panes) and gives up its claim on the rest. The nine working surfaces are promoted from *sheet equivalent* to **first-class designed rooms**, with their own layout grammar, their own density work and their own polish budget.

This does not repeal L9. Every W surface still owes a non-W path, and the parity register is unchanged. What is repealed is the *design consequence* of L9 — that the sheet is a fallback. Under D1 the sheet is the primary artifact for nine of eighteen surfaces, and the world is what those rooms sit inside.

**D2 · The background is ported verbatim, then a re-key is offered.**
`AnimatedBackground.tsx` is copied exactly — same shader, same hex geometry, same `UnrealBloomPass` parameters, same mouse-ripple interaction, same `NEON_ORANGE` / `ELECTRIC_BLUE` / `#382b02` values. That is the artifact the owner approved and it is carried across unchanged, not re-derived. In parallel a **brand-keyed variant** is built — identical geometry, shader and motion, with the two accent vectors moved to brand gold plus a desaturated cool counterpoint over `--ink-950` — and the two are shown side by side on a real surface for the owner to choose between. Neither is assumed.

The tension is named rather than resolved by fiat: the legacy palette's copper glow competes with gold beacons, which is exactly what art bible §2.1's budget exists to prevent. If the verbatim version wins, §2.1 is amended in the same commit rather than quietly broken.

**D3 · The rejected app is a parts bin, not a base.**
A new `vihara/` app is scaffolded. Carried across from `vihara-review-rejected/` are the layers that are correct, tested, and not what was rejected: the API client and its `gen:api` diff gate, cookie-mode auth (VP-01), the Zod manifest schema and its refusal ladder, the 45-entry component registry and the authored-vs-served correspondence test, the certified set's structural goldens, the PWA shell and service worker, the CI gates including the ≤220 KB budget, and the Vitest harness. Rewritten from nothing: the renderers, every component's visual implementation, and all eighteen surfaces.

**D4 · Review is a pixel-final interactive prototype, before app code.**
The Phase-A failure mode is now documented: **R2 passed on wireframes, and wireframe approval did not predict implementation approval.** Low-fidelity boards cannot carry a craft judgment, and craft was the whole verdict. So the redesign's review artifact is a clickable prototype that already looks finished — real background, real self-hosted type, real glass and metal, real motion, real content at real density — browsable surface by surface. What the owner approves is what gets built, because it will already be built to that standard.

This replaces R1/R2's format for the redesign. It does not replace their *rulings*: the gold budget, day–night as luminance, the desaturated twin, the type mapping, and portraits A-with-C-fallback all stand unless a redesign round explicitly reopens one and records it here.

## 3a. Owner decisions — round 2, locked 2026-07-30

Four more, taken against the **R-4 readiness assessment** ([04_r4_readiness.md](./04_r4_readiness.md)). That assessment
is the reason this round exists: R-4 was chartered as three mechanical steps, and
measuring the tree found six unlisted prerequisites, two red gates, and three
surfaces that were never rebuilt. The decisions below are the response.

**D5 · R-4 is one large round, not a mechanical swap.**
The charter's "swap `src/fixtures/`, delete `PrototypeNav`, re-run `gen:api`"
stands as *part* of R-4 and no longer as the whole of it. Folded in, because none
of them is optional and each blocks the swap: the auth entry point and session
gate, the fetch lifecycle (scaffold-then-hydrate, not spinners — D7 §3.1 permits a
visible loading state on the Glasshouse alone), the step-up ceremony, the
navigation replacement, the `gen:api` drift gate, and the SSE client.

The plan table in §5 is amended rather than annotated. **A plan that claims three
steps when the tree needs nine is not a plan, it is an estimate that has already
failed** — and the first build's drift began the same way, with a round whose
stated size stopped matching its actual one.

**D6 · The Private Line is rebuilt before R-4, to the new design standard.**
Three of the eighteen ratified surfaces — Thread, Morning Story, Pocket Desk —
plus the installable PWA shell, the service worker and the webmanifest were not
carried into the redesign. Nothing recorded a decision to drop them; every
document since R-3b has said "all fifteen product surfaces" as though fifteen were
the total. It was an omission, and it is closed by building, not by amending the
count.

They are **rebuilt, not ported.** D3 makes `vihara-review-rejected/` a parts bin,
and that applies to the Line exactly as it applies to the estate — the plumbing
(push subscription, the service worker's refusals, the second Vite entry and its
own 220 KB budget) carries across; every visual implementation is written new
against `design/material.css`. This is **R-3c**, and it completes the eighteen.

**D7 · Navigation is the ⌘K palette plus `pushState`.**
`PrototypeNav` is the only click path to eleven of sixteen surfaces, so deleting it
— a stated R-4 task — strands them. The palette already exists in `Shell.tsx` as a
designed and empty shell, and D6 §1 requires navigation to be app-owned rather
than manifest-composed, so the palette becomes the real navigator. No router
dependency.

**Surface identity reaches the URL** via hand-rolled `pushState`. This is not
optional polish: L8 makes a push *a tray or nothing*, and a push that cannot
deep-link to the tray it announces is a notification that drops you at the front
door. Bookmarks and reload-in-place fall out of the same mechanism.

**D8 · Every unsourced region gets a real endpoint.**
Four regions render fixture data with no backend behind it: the Bridges board's
gate consent and DNC state, the Undercroft's consent bay, the Dossier's charter
clauses / competencies / SLOs / probation, and the Talent Office's brief and past
cases. All four are built rather than converted to rendered gaps.

The cost is honest and is accepted: **two of the four are real backend design, not
a missing HTTP surface.** Consent is nearly free — `consent_records`, `dnc_entries`
and `trust/consent_registry.py` all ship behind no router. The colleague charter
and the talent brief are new domain work, and they enter Increment 7 as a
consequence of this decision. The alternative — shipping invented data that looks
live — is the failure the whole redesign exists to avoid, and a rendered gap on
four regions of two flagship surfaces would have been a large one.

## 4. What is carried forward, and what is not

| Layer | Status |
|---|---|
| `backend/src/ai/genui/` — all D5 endpoints, manifest service, `genui001` | **Untouched.** Rejection was frontend-only |
| D3 component registry · D4 manifest contract · D5 API contracts | **Kept as contracts.** Visual implementations rewritten |
| D2 art bible §2.1 gold budget · §4 luminance day–night · §5 desaturated twin · §6 type · §7 portraits | **Kept as rulings.** §13's territory construction language is **reopened** — it is what produced RD-2 |
| D6 wireframes | **Superseded as layouts.** The surface inventory and every binding survive; the drawings do not |
| D7 device matrix · D8 parity register | **Kept.** Tier gates, budgets and the 28-of-30 reckoning are unaffected by a visual redesign |
| `vihara-review-rejected/` | **Parts bin** per D3. Retained in history, not built on |

## 5. Plan

| # | Round | Produces |
|---|---|---|
| **R-0** | This charter · the rename committed · roadmap docs updated | The record |
| **R-1** | The background ported verbatim + the brand re-key, both live | **Owner pick** — D2's open half |
| **R-2** | The design foundation: tokens, self-hosted faces, the glass and metal material system, elevation, motion language, icon set | The shared substrate every board consumes |
| **R-3a** ✅ | Shell · Still surface · the Tray · Registry Hall — [02_prototype_r3a.md](./02_prototype_r3a.md) | The design language, judgeable |
| **R-3b** ✅ | **Fifteen of the eighteen product surfaces + the shell stand.** Owner review round 1 implemented (A1–A4, B, C, D), then the Glasshouse, Undercroft, Library, Bridges & Gates, Talent Office and Gallery. Gates: tsc · vitest 28 · sweep 16/16 · build. See [02](./02_prototype_r3a.md) §5a–§5e | **Owner review** — D4's gate, now open |
| **R-3c** ◀ **NEXT** | **The Private Line — the missing three.** Thread · Morning Story · Pocket Desk, rebuilt to the new material system; the second Vite entry, service worker, webmanifest and VAPID subscribe carried across as plumbing. **D6.** See [05_r3c_private_line.md](./05_r3c_private_line.md) | The eighteen complete |
| **R-4** | **One round, nine parts (D5).** Gates honest again · auth entry + session gate · navigation (⌘K + `pushState`, **D7**) · fetch lifecycle · step-up ceremony · the fixture swap · the missing client wrappers · the SSE live estate · the four new endpoints (**D8**). See [06_r4_wiring.md](./06_r4_wiring.md) | Live |
| **R-5** | The honesty pass: the three stale rendered gaps closed, the parity register re-walked against the rebuilt app, and the G0–G6 proofs that must be re-measured on the new tree | A citable record |

R-1 and R-2 ran together. R-3 does not begin on a surface until R-2's material system can render it at final quality.

**Plan change recorded at R-4 readiness (2026-07-30):** R-4's stated size stopped
matching its actual one, and the gap was six prerequisites wide. §3a's D5 folds
them in, D6 adds R-3c for the three surfaces that were never rebuilt, and R-5 is
split out so that correcting the record is a round with a name rather than a
rounding error inside a build.

**Plan change recorded at R-3a:** because D4's prototype is built as *real code* rather than as a mockup, **R-4 is no longer a rebuild.** The prototype is the app in mock mode; R-4 swaps `src/fixtures/` for the salvaged API client and deletes the review scaffold. This is strictly better than the original plan — it removes a translation step, and a translation step between an approved design and shipped code is exactly where the first build lost its look.

~~**R-3b is gated on the owner's background pick**~~ — **closed 2026-07-30: the brand re-key.** It is the default everywhere; art bible §2.1a amends the gold budget for the atmosphere layer and takes on the beacon-contrast measurement obligation.

## 6. Standing risks

| Risk | Why it is real here | Held by |
|---|---|---|
| A second rejection | The first review consumed a full increment. A second one on the same grounds would mean the diagnosis in §2 was wrong. | R-3's fidelity bar — the prototype must be judgeable *as the product*, not as a representation of it. Any surface that cannot be shown at final quality is not shown. |
| The verbatim background fights the gold budget | Named in D2. Two approved things are in genuine conflict. | Resolved by owner pick at R-1, with §2.1 amended in the same commit if verbatim wins |
| Reopening art bible §13 reopens R1 | §13's construction language was owner-approved on 2026-07-28, and it produced RD-2 | Only §13 reopens. The other seven §12 rulings stand, and the redesign is measured against them |
| IA rebalance drifts into concept change | D1 is deliberately bounded; "promote the sheets" is one step from "delete the world" | The eighteen-surface inventory and the depth ladder are fixed input. Any proposal to remove a surface or a depth comes back here as a decision |
| Salvage carries the old look across | D3 lists plumbing only, but a component registry encodes structure | The 45 entries are kept as *names and contracts*; every visual implementation is written new |

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-30 | v1.1 — **round 2 decisions (§3a), taken against the R-4 readiness assessment** ([04_r4_readiness.md](./04_r4_readiness.md)). **D5:** R-4 is one large round, because measuring the tree found six unlisted prerequisites — a plan claiming three steps for nine is an estimate that has already failed. **D6:** the Private Line's three surfaces plus the PWA shell were never rebuilt and nothing recorded dropping them; they are **rebuilt to the new standard** as **R-3c**, closing the eighteen. **D7:** navigation is the ⌘K palette plus hand-rolled `pushState` — surface identity must reach the URL because L8 makes a push *a tray or nothing*, and a push that cannot deep-link is a notification that drops you at the front door. **D8:** all four unsourced regions get real endpoints, accepting that two of them (the colleague charter, the talent brief) are new domain work rather than a missing HTTP surface. §5 amended: R-3c added, R-4 restated at its real size, **R-5** split out as the honesty pass. |
| 2026-07-30 | v1.0 — redesign opened after the built app was rejected on design. Seven findings (**RD-1**…**RD-7**) diagnosed from the rendered boards, with RD-7 identified as structural rather than cosmetic. Four owner decisions locked: visual redesign **plus** an IA rebalance that promotes the nine working surfaces out of fallback status (D1); the legacy background ported **verbatim** with a brand re-key offered beside it and the gold-budget conflict named rather than papered over (D2); the rejected app kept as a **parts bin** with a named salvage list (D3); and review moved to a **pixel-final interactive prototype**, because Phase A proved wireframe approval does not predict implementation approval (D4). Art bible §13 is the only R1 ruling reopened. |
