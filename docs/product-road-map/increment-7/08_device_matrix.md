# Increment 7 / Phase A — D7: Device Matrix & Performance Budgets

> **Deliverable D7** of [01_phase_a_overview.md](./01_phase_a_overview.md). Closes **VG-22**; puts numbers behind spec §12.1's <300ms first-scaffold floor.
> **Status:** ✅ complete 2026-07-28. Engineering artifact.
> **Depends on:** [07_surface_wireframes.md](./07_surface_wireframes.md).

---

## 1. Who is actually holding the device

The tenant product is India-first (spec §14.3's WhatsApp read-mirror, the ₹ figures throughout), sold to small businesses, and its second surface is a phone in a pocket. That makes the device distribution roughly the opposite of the one a WebGL flagship is usually designed for: **the median user is on a mid-range Android, and the owner is on a laptop.**

Spec §12.1 already flags "WebGL performance floor on cheap devices" as a risk and answers it with *"L9 sheet fallback is a first-class product, not an apology"*. This document is that answer made specific enough to fail a build.

## 2. The tiers

| Tier | Who | Primary renderer | World renderer |
|---|---|---|---|
| **A** | Desktop / laptop, WebGL2, ≥8 GB, discrete or modern integrated GPU | **W** | Full: day–night lighting, shadows, weather texture, camera flight |
| **B** | Recent mid-range phone or tablet, WebGL2, ≥4 GB | **W**, reduced | No shadows, simplified weather, shorter flights, half-resolution render target |
| **C** | Low-end Android, no reliable WebGL2, <4 GB, or a saved-data/battery-saver signal | **S** | **Never loaded** (§4) |
| **D** | Screen reader, keyboard-only, `prefers-reduced-motion`, `prefers-reduced-transparency` | **S** | Never loaded |

**Tier C and tier D are not degraded tier A.** They get the surface D6 drew as the sheet equivalent, which is a designed product with its own layout — the same `estate` payload, sorted so beacons come first. The one guarantee that matters: **no information is reachable only through the World renderer** (L9), and the exit criterion in §8 is what keeps that true.

### 2.1 Tiering is probed, never sniffed

At first run: `WebGL2RenderingContext` availability, `navigator.deviceMemory`, `navigator.hardwareConcurrency`, `navigator.connection.saveData`, and the two media queries. User-agent strings are not consulted — they are wrong about capability on both ends, and a wrong guess here means either a broken map or a needlessly plain product.

The result is stored in LEARN's preference store under the existing **`surface.*`** namespace (D5 §8) — no new table, no new endpoint, and the user can override it. A tenant on tier C who wants the map gets the map with a warning; a tenant on tier A who prefers sheets keeps sheets forever, because §6.3's density rule ("never gates capability") applies here too.

## 3. Budgets

### 3.1 The floor, per surface

"First scaffold" is the moment the layout and component skeletons are on screen (D4 §6's scaffold part), not the moment data arrives.

| Surface | First scaffold | Fully hydrated | Notes |
|---|---|---|---|
| Still Surface (depth 0) | **120ms** | 400ms | The default of every session; it must feel instant or the whole product feels slow |
| Terrace — W | **300ms** | 1200ms | Spec §12.1's number. The scaffold is the ground plane and district shells; districts hydrate after |
| Terrace — S | **200ms** | 700ms | |
| District room | 300ms | 1000ms | |
| Registry Hall (register) | 300ms | 900ms | First page of rows only; the grid virtualises |
| Tray | **250ms**, whole | — | Certified components do not stream (D4 §6): whole or not at all |
| Dossier / Library / Boardroom | 300ms | 1200ms | |
| Glasshouse | 400ms | 2000ms | The only surface permitted a visible loading state, because a scenario is understood to take time |
| Undercroft | 300ms | 1500ms | Dense, but all of it is shipped endpoints |

Measured at the **75th percentile on tier B**, not the median on tier A. A budget met only on the developer's laptop is not a budget.

### 3.2 Frame budgets for the World renderer

| Tier | Target | Floor | On sustained breach |
|---|---|---|---|
| A | 60fps | 45fps | Drop weather texture, then shadows |
| B | 30fps | 24fps | Drop to half-resolution, then offer the sheet |
| C | — | — | Never entered |

"Sustained" is **90 frames below the floor within a 5-second window** — long enough that a single scroll hitch does not demote a working device, short enough that a genuinely struggling one does not stay struggling.

**Demotion is offered, never imposed** (except on context loss, §4). A map that silently becomes a list has broken the user's mental model of where things are; a map that says *"this is running slowly — would you rather have the list?"* has not.

### 3.3 Bundle budgets — the load-bearing one

| Bundle | Budget | Gate |
|---|---|---|
| Shell + Sheet + Card renderers (the tier-C/D path) | **≤ 220 KB** gzipped | CI build gate, fails the build |
| World renderer chunk (three.js + r3f + drei + world components) | ≤ 600 KB gzipped | CI budget, warns |
| Certified components | counted inside the shell budget | never lazy — a tray must not wait on a chunk |

> **A tier-C device must never download three.js.** The World renderer is a dynamic import behind the tier probe, so the phone that cannot render the map also never pays for it.

This is the single highest-leverage performance rule in the document, and it is the one most likely to be broken by accident — one static import of a world component from a shared module pulls the entire 3D stack into the main bundle, and nothing about the app *looks* wrong afterwards. It is therefore a **build gate with a hard number**, not a guideline, and D1 §3's class directories are what make the boundary lintable.

## 4. When the world goes away mid-session

| Event | Behaviour |
|---|---|
| WebGL context lost | Restore once. On a second loss, **switch to S immediately** and echo it: *"the map stopped responding — here's the list."* Never a blank canvas |
| Sustained frame breach (§3.2) | Offer the sheet |
| `saveData` toggled on mid-session | Offer the sheet at the next depth change, not immediately — a surface that changes under the user's hand is worse than one that waits |
| Tab backgrounded | Halt rendering entirely; keep the SSE stream. Beacons are still delivered, the estate is simply not being drawn |

The context-loss row is the one that matters, and it is written the way it is because of this repo's own recurring lesson: **the failure mode to fear is the one that quietly does less.** A lost WebGL context with a generic `try` around it produces a black rectangle where the estate was, and every test still passes.

## 5. Reduced motion

`prefers-reduced-motion: reduce` is a **first-class path**, not a suppression of animation (art bible §9):

* Camera flights become 160ms crossfades. The steward-walk still *goes somewhere* — the destination is what carried the meaning, not the travel.
* The beacon stops breathing and stays at full glow. It must not become less visible for having stopped moving.
* Weather texture freezes to a static state; heat-shimmer is removed entirely rather than frozen (a frozen shimmer reads as a rendering artefact).
* Tray and sheet transitions become instant.

**No information is lost**, because every state motion expresses also has an icon and a sentence (art bible §8). That is what makes this a path rather than a degradation, and it is worth re-stating here because §8's rule was written for colour-blindness and does double duty for motion.

## 6. Screen readers and keyboard

* **The screen-reader path is the Sheet renderer** (tier D). Not an ARIA layer over a canvas — L9's whole point is that the alternative is a real product.
* Every surface is fully keyboard-traversable at depth ≥ 1. ⌘K teleports; the depth dial is ⌘↑/⌘↓; the tray traps focus and returns it on close.
* **The focus ring is never removed**, including inside the World renderer, where keyboard teleport must show where it landed (art bible §11).
* Live regions: a beacon raise announces once, politely. Traffic, pulse and envelope burn are `aria-hidden` — they are ambient, and announcing them would make the product unusable with a reader on.
* WCAG 2.2 AA is audited on S and C at G6. The W renderer is out of scope for the audit **by design**, and L9 is the reason that is legitimate rather than an exemption.

## 7. What is measured, and where

| Signal | Where | Gate |
|---|---|---|
| Bundle sizes (§3.3) | CI, every build | **Hard fail** on the shell budget |
| Certified golden renders | CI, every build | Hard fail (D1 §4.1) |
| First-scaffold p75 by tier and surface | Runtime, sampled | G6 exit criterion |
| Sustained frame breaches, context losses, demotions | Runtime, sampled | Reviewed at G1 and G6 |

Runtime numbers are **aggregate and tenant-anonymous** — they are platform telemetry about the *renderer*, not about a tenant's business, so they belong in LEARN's pooled `platform_observations` store, which by construction has no `company_id`, no free-text and no JSON column. The B10 guarantee already covers this shape of data, and routing it anywhere else would be inventing a second telemetry path with weaker properties.

## 8. Exit criteria this document owns

1. **A device matrix run** at G1 on at least one real device per tier — not emulated throttling alone, because thermal behaviour on a real mid-range phone is what actually decides tier B.
2. **The bundle gate green**, meaning a tier-C device provably never fetches three.js.
3. **Every surface in D6 reachable on tier C**, verified by walking the seventeen with the World renderer disabled. This is L9's audit and it is the reason L9 is a required manifest field (D4 §4) rather than an intention.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-28 | v1.0 — four device tiers probed rather than sniffed, per-surface scaffold budgets measured at **p75 on tier B** (a budget met only on the developer's laptop is not a budget), and frame budgets with a demotion rule that is **offered, not imposed** — a map that silently becomes a list has broken the user's model of where things are. The load-bearing rule is the bundle gate: **a tier-C device must never download three.js**, which one careless static import would undo invisibly, so it is a hard build failure with a number rather than a guideline. Runtime telemetry routes into LEARN's pooled store, whose B10 schema guarantee already fits this shape of data exactly. |
