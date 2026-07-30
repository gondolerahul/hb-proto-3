# Increment 7 / Redesign — R-3c: The Private Line

> **Round R-3c**, opened 2026-07-30 by charter [§3a decision D6](./00_redesign_charter.md#3a-owner-decisions--round-2-locked-2026-07-30).
> **Why it exists:** three of the eighteen ratified surfaces were never rebuilt, and
> nothing recorded a decision to drop them.
> **Read first:** [04_r4_readiness.md](./04_r4_readiness.md) §4 (what the salvage did
> not carry) · [07_surface_wireframes.md](../07_surface_wireframes.md) §16–18 (the
> surfaces as drawn) · [13_line.md](../13_line.md) (the LINE workstream — the backend
> half, which ships).
> **Produces:** the eighteen complete, so that R-4 wires a whole product.

---

## 1. What was missing, and why it read as done

The Private Line is three surfaces — **Thread**, **Morning Story**, **Pocket
Desk** — plus an installable PWA shell. All three were built in the first
Increment-7 pass (LINE, `inc7/line`, merged 2026-07-29) and none was carried into
the redesign.

The omission survived because of a counting habit. R-3b's build notes said *"all
fifteen product surfaces plus the shell stand"*, and every document since has
repeated fifteen as though it were the total. It is not: [D6's
inventory](../07_surface_wireframes.md) specifies **eighteen** — §2–§15 are
fourteen, §15a The Study is the fifteenth, and §16–18 are the Line. The shell is
chrome, not a surface; onboarding is retired as a surface by ratification.

**Fifteen was always a subtotal reported as a total.** That is the whole
mechanism, and it is worth naming because it is not a coding error — no test
could have caught it, and the sweep passes at 16/16 because the sweep enumerates
what exists.

## 2. The decision, restated

**D6: rebuilt, not ported.** D3 makes `vihara-review-rejected/` a parts bin, and
that applies to the Line exactly as it applied to the estate. The split:

| Carried across as plumbing | Written new |
|---|---|
| `public/line-sw.js` — the service worker and, more importantly, **its three refusals** | Every visual implementation of all three surfaces |
| `public/line.webmanifest` · `line-icon.svg` | The Thread's card rhythm, the Story's swipe, the Desk's vitals |
| `line.html` as a second Vite entry, with its own hard 220 KB budget | Type, material, glass, motion — against `design/material.css` |
| `src/line/push.ts` — VAPID subscribe / unsubscribe | — |

The rejection at owner review was of the estate's *look*. The Line's plumbing was
never the subject of it, and its refusals are load-bearing safety properties that
should not be re-derived (§4).

## 3. The three surfaces

Composition per [D6 §16–18](../07_surface_wireframes.md). Bindings are
`pragya/channel` (WS) · `trays` · `estate` (vitals only).

### 3.1 Thread · C

Pragya's thread and nothing else — **no per-agent threads** (L3: one voice). Voice
notes, story cards, and certified trays with biometric step-up.

* Registry types: `narrative.story-card` · `certified.*` · `certified.step-up`.
* **The certified section IS `TraySurface`.** Not a phone-shaped imitation of it —
  the same component, so the biometric bar is the platform passkey unchanged. This
  is the invariant that makes "a push is a tray or it does not exist" true rather
  than aspirational, and it is why the Line cannot be a separate app that merely
  looks similar.
* Density is `C`, so the estate's operator density never reaches here.

### 3.2 Morning Story · C

The Standup, swipeable, Pragya's voice over each card.

* Registry type: `narrative.standup-line`, in sequence.
* The backend ships this whole surface's data: `genui/morning.py` composes it,
  `morning_job.py` runs at 02:25 UTC with pre-generated audio, and
  `GET /ai/genui/line/morning` serves it. **Every failure degrades to text with
  its reason named** — the surface must render that degradation, not hide it.
* Swipe emits echoes carrying `renderer: "C"`.

### 3.3 Pocket Desk · C

Pinned live cards, vitals always on top.

* Registry types: `primitive.figure` · `primitive.kpi-dial` · `narrative.still-line`.
* Pins bind to `surface.line_pins`.
* Vitals-only slice of the estate — the Desk is not a small Terrace.

### 3.4 Not on the Line

**Depth 3.** The Undercroft is desktop-only by design, and R-3c does not soften
that. A phone-sized Undercroft is a worse Undercroft, not a more available one.

## 4. The refusals that carry across verbatim

These are the reason the plumbing is salvaged rather than rewritten. Each is a
safety property that reads as a missing feature until you know why it is absent.

1. **No background sync, no offline queue.** An offline approval would be a
   certified act with no server. It must not exist. The service worker refuses
   both explicitly.
2. **The push payload is `{tray_id, one_sentence}` and nothing else.** L8 made
   richer pushes unimplementable server-side; the worker matches that shape and
   invents nothing.
3. **API responses are never cached.** Only the shell is, network-first — the Line
   degrades to the last shell, never to a dinosaur, and never to stale estate data.

**The iOS install-first ceiling is stated, not worked around.** iOS delivers Web
Push only to an installed PWA. The Line says so rather than silently never
notifying.

## 5. Tasks

| # | Task | Done when |
|---|---|---|
| **C1** | Second Vite entry: `line.html`, `input: {main, line}`, `src/line/main.tsx`. Its own hard 220 KB gz budget, separate from the shell's | `vite build` emits two entries; the budget script (R-4 G3) measures both |
| **C2** | PWA assets: `line.webmanifest`, `line-icon.svg`, `public/line-sw.js` carried verbatim, registration in `main.tsx` | The app installs on Android; the manifest validates |
| **C3** | `push.ts` — VAPID subscribe/unsubscribe over `POST /ai/genui/push/subscriptions` and `GET /push/vapid-public-key` | Subscribing returns 201; unsubscribing 204 |
| **C4** | **Thread**, rebuilt. Story cards, voice notes, and the certified section **rendering `TraySurface` itself** | A test asserts the Thread's certified block and the estate's Tray resolve to the same component |
| **C5** | **Morning Story**, rebuilt. Swipeable sequence, audio per card, the text-degrade path visible | Renders a story with audio and one with `audio: null` + its stated reason |
| **C6** | **Pocket Desk**, rebuilt. Vitals band pinned above pinned cards | Pins read `surface.line_pins` |
| **C7** | `LineApp` shell — the three surfaces, C density, no depth ladder, no ⌘K | Sweep covers all three |
| **C8** | Extend `scripts/sweep.mjs` to the Line entry; add the three to the variant shoots (`prefers-reduced-motion`, 720px) | sweep 19/19 |

**C4 is the load-bearing one.** If the Thread's certified section is a
reimplementation rather than the component, the invariant is untestable and the
Line becomes a place where a certified act is *drawn* differently from where it is
*approved* — which is exactly the class of defect that makes step-up theatre.

## 6. Gates

R-3c is complete when, in addition to the existing gates staying green:

* `vite build` emits both entries, each under its own 220 KB gz budget.
* `sweep.mjs` visits **19** surfaces (16 + 3) with no console or page errors.
* The C4 invariant is held by a test, not by convention.
* The three surfaces render at 390×844 (the D7 phone reference) without horizontal
  scroll, and under `prefers-reduced-motion`.

**What R-3c does not do:** wire anything. The Line is fixture-backed exactly as the
estate is, and R-4 wires all eighteen together. Building the Line against live data
while the estate is on fixtures would produce two half-wired apps and one shared
component with two data sources.

## 7. Standing risks

| Risk | Held by |
|---|---|
| The Line is rebuilt to a phone-shaped *version* of the estate's look rather than its own | D6 §16–18's compositions are fixed input; C density is not "the same, smaller" |
| The certified section drifts into a copy | C4's test |
| The service worker's refusals get "fixed" by a future session that reads them as gaps | §4, and the comments in `line-sw.js` itself, which are kept verbatim |
| A second entry blows the shared-chunk assumption | The first build measured the Line at 3.5 KB gz because shared chunks ride the cached shell; C1's budget check must measure the entry, not the transitive graph |

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-30 | v1.0 — round opened by charter D6. Records the counting habit that hid the omission (fifteen was a subtotal reported as a total, and no test could have caught it), fixes the split between salvaged plumbing and rebuilt visuals, and names **C4** — the Thread's certified section must *be* `TraySurface`, not resemble it — as the round's load-bearing task. |
