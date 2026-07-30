# Increment 7 / Redesign — R-3a: The Prototype, First Slice

> **Round R-3a** of [00_redesign_charter.md](./00_redesign_charter.md) §5. Satisfies **decision D4** for three surfaces plus the shell.
> **Run it:** `cd vihara && npm run dev` → <http://localhost:4044> · keys `1`–`4` switch surface, `⌘K` the palette, `⌘↑`/`⌘↓` the depth ladder.
> **Gates:** `tsc --noEmit` clean · `vitest` **13 passed**.

---

## 1. What R-3a is, and why it is real code

Decision D4 moved review from wireframes to a pixel-final interactive prototype, because Phase A proved that wireframe approval (R2) does not predict craft approval. The cheapest way to make a prototype that *is* judgeable as the product is to build it **as** the product: real React, the real material system, real content at real density.

The consequence is a change to charter §5's plan, recorded here rather than left implicit: **R-4 is no longer a rebuild.** The prototype is the app in mock mode. When R-3 passes, R-4 swaps `src/fixtures/` for the salvaged API client and deletes the review scaffold. The surfaces themselves carry across untouched.

`src/app/Prototype.tsx`'s `PrototypeNav` is marked in code as review scaffolding to be deleted at R-4, so nobody mistakes it for chrome that needs designing.

## 2. What is in this slice, and why these four

| Surface | Renderer | Answers |
|---|---|---|
| **Still surface** · depth 0 | S | **RD-4** — "no chrome" had been read as "nothing on screen" |
| **The Tray** · certified | C | **RD-7** — the surface that retires `HITLPanel` (D8 row 24), built last time as an L9 fallback |
| **Registry Hall** · depth 2 | S | **RD-7** — the dense-data case, the clearest example of fallback design budget |
| **The shell** | app-owned | **RD-1/RD-5** — chrome that is legible and made of the brand's material |

Not chosen at random: three of the four are exactly what the diagnosis says was shortchanged.

## 3. The design decisions this round made

### 3.1 An edge is never one border

The governing rule of `design/material.css`, and the direct answer to **RD-5**. Every real surface gets four things: a light rim where it catches the key, a body hairline, a **contact shadow** where it meets what is beneath, and a soft cast shadow further out. One border is a div; four is an object. The contact shadow is the cheapest of the four and the one whose absence makes everything float.

Six materials, no more: **plate** (opaque base), **glass** (floats over the world), **well** (inset, where data lives), **metal** (gold, certified only), **hairline** (precision rules), **lamp** (the point light).

### 3.2 Grain on every plate

A warm near-black gradient across 900px of screen bands visibly on an 8-bit panel. ~2% fBm noise at `mix-blend-mode: overlay` hides the banding and gives the dark a texture to be dark *in*. It is the difference between "dark grey fill" and "a surface".

### 3.3 The gold budget is kept, and paid for differently

Art bible §2.1 stands: gold means *this needs you* or *this is certified*, and nothing else. **RD-3** was not that the rule is wrong — it is that the other 94% was given only alpha to work with. Now it has material, light, edge and texture. The still surface at zero hands raised still has no gold but the brand mark.

### 3.4 Atmosphere is per-surface, and the scene is never re-graded

`Background` takes `intensity` — `full` at depth 0, `quiet` in rooms, `hushed` behind the Hall's table. It is a CSS veil over the running scene, not a second grade of it, which is what keeps "ported verbatim" literally true while letting a table of invoices be readable. A breathing floor under dense data competes with the data.

### 3.5 The depth dial is quiet but not invisible

D6 said "hidden until reached for". That is right about *quiet* and wrong about *hidden*: an undiscoverable primary navigation axis is how the zero-training test (§10.4) fails. At rest it is four ticks on the left rim with the current one gold; on hover or `focus-within` the labels slide in.

### 3.6 State is never colour alone

Every state in the Hall is **a lamp plus a word**. The lamp is the fast read, the word is the correct one. Art bible §8 and WCAG 1.4.1 both require it, and a one-hue palette makes it unavoidable anyway.

### 3.7 The tray is a column, not a grid

A grid of approvals invites scanning; a column invites reading. Every card here is a decision with money or legal consequence behind it. Capped at 74ch so the *because* paragraph — the one prose field — never runs to a line length nobody reads. The §6.1 five-field order is preserved exactly: who and how long · what · why in her own words · the facts · the paths.

## 4. Two invariants now held by tests, not convention

**The background port cannot drift** — `tests/background_verbatim.test.ts`, 10 assertions. It caught real drift on its first run: reformatted whitespace inside the fragment shader. Details in [01_background_port.md](./01_background_port.md).

**A null cost renders as nothing** — `tests/tray_cost.test.tsx`. `paths[].cost` is `null` until DRIVER's estimator exists (D5 §4.1). The rule is that it renders as *nothing at all* — never `₹0`, never `—`, never "unknown". On a payment card an invented zero is the worst available bug, so it is a test and not a convention.

## 5. Honest limits of R-3a

**No World surfaces.** The Terrace, district rooms and the Glasshouse are absent, and this is a capability limit, not a scoping choice: `UnrealBloomPass` needs float render targets, this VM has no GPU, and **craft work cannot be done on something that cannot be seen.** Verified by rendering the legacy app itself under the same headless GL — it produces the same near-black frame ([01](./01_background_port.md) §4). They land in **R-3b**, once the owner confirms the background renders on real hardware.

**The screenshots understate the background.** Every shot in this round shows the surfaces over a near-black floor. On real hardware the lava field is running underneath. The surfaces were composed to hold up either way — text over a live scene carries its own shadow so it does not shimmer as the floor breathes — but the *atmosphere* is not visible in any image produced here.

**Fourteen surfaces still to draw.** R-3a is 4 of 18. The remaining fourteen reuse this round's material system and shell, which is the point of building the substrate first.

**The 404 in the console** is the missing favicon. Cosmetic, fixed when the brand mark is cut to an icon.

## 5a. R-3b progress — 2026-07-30

**Decision D2 closed: the owner picked the brand re-key.** It is the default everywhere. The consequence — gold in the atmosphere — is handled by an explicit amendment to the gold budget, [03_art_bible.md](../03_art_bible.md) §2.1a, not by silence. §2.1a also takes on an obligation: beacon-against-atmosphere contrast is measured on real hardware before R-3b closes.

**Three more surfaces stand** (six plus the shell in total):

| Surface | What it settled |
|---|---|
| **The Terrace** · depth 1 · W | **RD-1 and RD-2, structurally.** `world/iso.ts` + `world/Territory.tsx` draw geometry only — not one glyph in the SVG — and every label is DOM in screen space. Solid lit volumes on plinths under one warm key; gold spent solely on beacon shafts |
| **District room** · depth 2 · W+S | The same `Territory` in single-plot mode. Entering a district changes *distance*, not rendering technology |
| **Dossier** · depth 2 · S | Art bible §7 direction **C** ships — a deterministic dot-lattice seal from the entity id, from the *deep* half of the gold ramp so a portrait cannot compete with a raised hand |
| **Boardroom** · depth 2 · S | The four honesty grades told apart by **form, not hue** — replay struck, forecast dashed, unknown slashed, untested a hollow **circle** with no strip. The circle-vs-square split survives greyscale |

### The RD-1/RD-2 fix, stated once

The territory is no longer a scene that happens to contain text. **Geometry is drawn; text is DOM.** Labels are positioned by projecting each plot's anchor through the same isometric transform, in `viewBox` percentages, so they track the SVG's fit with no resize observer and no per-frame projection. They are upright, selectable, and in the accessibility tree at every zoom. `buildTerritory()` is the single model both the drawing and the label layer read, so a label cannot drift from the plot it names.

That split also means **the Terrace needs no WebGL to be correct** — the SVG territory is the tier-C path and the L9 sheet equivalent simultaneously, at full quality rather than as a fallback.

### What the screenshots caught, and it was worth doing

Four rounds of render-and-look on the Terrace alone. The `viewBox` pad was in world units while sized as if it were pixels, shrinking the estate to a third of the frame. Lamp pools at 0.3 alpha merged into one wash that drowned the geometry. Beacon tips read as cartoon bulbs. The district ring entered the gatehouse row and their labels collided. Roads outshouted the buildings they connect. **Every one of these was invisible in the code and obvious in the image** — which is the whole argument for D4.

### Honest note on provenance

`DossierSurface` and `BoardroomSurface` came from a parallel workflow whose agents died mid-run — first on API 529s, then on a usage limit. They had written the TSX but not the CSS, and a concurrent write destroyed the people fixture. Both stylesheets were then written against the exact class and data-attribute lists the surfaces use, and `people.ts` was reconstructed to the exact contract `DossierSurface` consumes. Recorded because the two surfaces have a different authorship path from the rest, not because it changes their status.

### Still outstanding

**Six Sheet surfaces:** Talent Office, Gallery, Standup, Library, Bridges & Gates, Undercroft, The Study. **One World surface:** the Glasshouse. `src/fixtures/decisions.ts` already carries the Standup's data.

## 5b. Owner review round 1 — 2026-07-30

Four comment groups on the six standing surfaces. All implemented; the notable
thing is that one of them **reversed a decision I had argued for**, and was right.

### A · the Terrace

| # | Comment | What changed |
|---|---|---|
| A1 | Beacon too wide and overlapping the building; should be behind it | Shaft narrowed 1.8 → 0.68 and drawn **before** the built form, so buildings occlude it. A shaft the district stands in front of reads as light rising from the place; in front, it reads as a sticker on top |
| A2 | Labels are screen-parallel and overlap the structures; prefer them **lying flat beside** them | Reversed — see below |
| A3 | Zoom/scroll/drag not working | A viewBox camera: pointer-anchored wheel zoom, drag to pan, double-click to reframe |
| A4 | Roads can be more muted; signals much smaller | Roads 0.13 → 0.075 alpha, 0.2 → 0.14 width; dots r 0.26 → 0.14 |

**A2 is the one worth recording properly.** R-3b's headline claim was that finding
RD-1 was fixed *structurally* by moving all text into screen-space DOM. That was
half right and half wrong. RD-1 was three defects arriving together — labels were
skewed **and** colliding **and** too small — and "flat" got the blame for what
collision and size actually did. The inspiration set ([../inspiration/](../inspiration/))
labels flat on the ground and reads beautifully.

So the labels are flat again, with the two real defects fixed by construction
rather than by taste:

* **They cannot collide with built form.** `buildTerritory` places each label on clear ground *outside* its slab, along the plot's own outward vector.
* **They are set to be read.** Heading at display size, at most one detail line, stroked against the floor (`paint-order: stroke fill`) so glyphs keep their edges under shear.
* **They are still real `<text>`** — selectable and in the accessibility tree. Flatness was never what cost accessibility.

Two things took a second pass. The first mirrored-axis matrix rendered text
**backwards**; there is now deliberately no mirrored transform, and labels that
grow the other way keep the one transform with `text-anchor: end`. And labels are
part of the drawing, so they became part of the frame — `LABEL_RUN`/`LABEL_DROP`
extend the viewBox, sized against the ~26-character line budget the surface keeps,
because over-estimating shrinks the estate to make room for whitespace.

### B · the district room — rebuilt as a room

The room now has the Terrace's structure and reveals detail on the structure you
click. Nothing was dropped. `world/Room.tsx` is the estate's grammar one level
down, sharing `iso.ts` deliberately: descending a level should change the *scale*
of what you are looking at and nothing else.

Colleagues are **personified as architecture** — each has a workplace with its own
built form, stable across sessions because the massing derives from their position
in the roster. Fixtures are instruments whose form says what they are: the KPI an
obelisk (a reading standing up), the treasury a low vault with the protected
reserve as a gold seam struck across its lit face, live runs an almost-flat table.

Nothing is selected on arrival — a surface that pre-opens one panel has decided
for you which structure matters.

### C · portraits — art bible direction A, generated

`components/Portrait.tsx` builds the halftone bust **without the raster pipeline
it was blocked on**: a shoulder-up figure whose form is carried by dot density on
a hex lattice, deterministic from the entity id. Per-identity variation is
deliberately narrow (head size and tilt, neck, shoulder width and slope, and a
crown mass — the strongest cue that two portraits are two people). These are
people in one house style, not a character generator.

The ramp is the **deep half** of the gold scale, so the brightest dot in a portrait
sits below the dimmest beacon: a room full of colleagues cannot out-shout one
raised hand. Direction C survives as `components/Seal.tsx` for entities with no
persona — a gateway, a Meta-Agent role, a newly seeded agent.

### D · the Boardroom — the question exposed a real gap

*"How do I brainstorm here — say I am thinking about developing a new marketing
plan?"* There was no way to. The room only rendered propositions **Pragya** raised
from KPI drift; an owner arriving with a thought had nowhere to put it.

The answer is deliberately **not a chat panel**. It is the front of the same
pipeline: a matter you table becomes Minutes, the exchange becomes a Proposition,
and it adopts into a Resolution by the same certified act as hers. A second way to
make strategy would defeat STRAT's premise that there is one.

Four beats, each earning its place: she **reads the matter back**; she opens with
**what she already knows** (named figures, not enthusiasm — a strategy
conversation that opens with "great idea" has taught you nothing); she names **what
she cannot know** and asks, every question carrying *why it is being asked*; and
the draft assembles in the Proposition idiom, arriving `untested` with **no
expected effect at all**, because nothing projects one for a first-of-its-kind
act.

The draft also states **what would worry me** at equal weight beside the because.
A proposition that argues only for itself is advocacy, and an owner cannot weigh
advocacy. And the brainstorm sits **first** in the column, above her prepared
agenda: a boardroom that leads with the chair's agenda every time teaches the
owner their own thinking goes second.

## 5c. R-3b — surfaces standing

Eight plus the shell: **Still · Terrace · district room · Dossier · Boardroom ·
Standup · The Study · Tray · Registry Hall.**

* **The Standup** (D6 §10) — L2 shapes it: every line is relayed by Pragya, never spoken by the colleague, because a tenant who can be addressed by twelve colleagues has twelve channels to mute and will mute the wrong one. The surface states the rule in words. Two densities that are genuinely different registers — a keyed sequence, or one sheet.
* **The Study** (D6 §15a) — all four R2 rules held. Its real design problem is dunning: everywhere else in Vihara quiet reads as calm, which is the product's own aesthetic working against the tenant at the worst moment. So the ladder is **always** visible, the tone explains rather than warns, and no rung uses terracotta.

**Still outstanding:** Talent Office · Gallery · Library · Bridges & Gates ·
Undercroft (Sheet), and the Glasshouse (World).

## 6. What R-3b needs

1. **The owner's background pick** ([01](./01_background_port.md) §2.1) — it changes the atmosphere every remaining surface is composed against.
2. **The World surfaces**, on hardware that can render them: Terrace, district room, Glasshouse. Art bible §13's construction language is reopened (charter §4) and **RD-1** and **RD-2** are the brief — billboarded screen-space type, and solid lit volumes instead of wireframe cages.
3. **The remaining Sheet surfaces**: dossier, Boardroom, Talent Office, Standup, Library, Gallery, Undercroft, Bridges, The Study.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-30 | v1.0 — R-3a built: the shell plus three surfaces, all Sheet renderer, chosen because three of the four are what the diagnosis says was shortchanged. The round's load-bearing artifact is `design/material.css` — six materials under one rule (an edge is never one border), which is the direct answer to RD-5. Recorded a **plan change**: because the prototype is real code, R-4 stops being a rebuild and becomes a data-source swap plus deleting the review scaffold. Two invariants moved from convention to test (verbatim port, null cost). Named the round's hard limit honestly: **no World surfaces, because they cannot be seen on this VM and craft work cannot be done blind.** |
