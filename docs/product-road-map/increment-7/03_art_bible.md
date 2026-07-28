# Increment 7 / Phase A — D2: The Art Bible

> **Deliverable D2** of [01_phase_a_overview.md](./01_phase_a_overview.md). Satisfies spec §13(b) and §14.5.
> **Status:** 🔍 **AWAITING OWNER REVIEW (checkpoint R1)** — nothing aesthetic ships before this passes. **The territory construction language (§13) is owner-approved as of 2026-07-28** on the terrace and district boards; R1 still owes rulings on §12's eight items.
> **Supersedes** ratified spec §11 by charter decision 2. Specimens: [art-bible/specimens.html](./art-bible/specimens.html) · five interactive boards: [§13](#13-the-territory-construction-language--built-2026-07-28).
> **Source of truth for tokens:** [buddha-cognitive-lab-design-system/project/colors_and_type.css](./buddha-cognitive-lab-design-system/project/colors_and_type.css). This document adds only what a *world* needs and the brand has never had to describe.

---

## 1. What this replaces, said plainly

Ratified spec §11 described a different-looking product: parchment daylight cartography, a deep-indigo night ground, walnut-brass-paper-linen interiors, and "one serif of real character" for narrative surfaces. Charter decision 2 makes the Buddha Cognitive Lab system canonical across all three renderers, so **all four of those are retired.**

They are named here so that nobody rediscovers them in the spec and files a bug. What survives from §11, unchanged and load-bearing:

* **Living day–night** (concepts §6.7, an owner decision) — preserved as *luminance*, §4 below.
* **The Glasshouse looks materially different from the real** (L6) — preserved, and §5 solves it without introducing a second hue.
* **Portraits are stylized, disclosed, never photoreal** (L7) — preserved, and §7 makes the medium itself carry the disclosure.
* **Motion is inertial, weighty, silent, and fully removable** — preserved, §6.
* **Colour never carries meaning alone** — preserved and *strengthened*, because a one-hue palette gives colour less to say (§8).

## 2. The problem this document actually has to solve

The brand is a **single accent on a warm near-black canvas**. That is a superb product-chrome palette and it is an unusually hard *world* palette, because a world has more things that need to be distinguishable than a console does.

In Vihara, gold is simultaneously asked to mean: the brand, a raised hand, a certified seal, daylight, the protected treasury reserve, an active state, and a hero figure. Seven meanings in one hue is not a palette — it is noise that happens to be beautiful.

**So the load-bearing decision of this art bible is not a colour. It is a budget.**

### 2.1 The gold budget

> **Gold means one of exactly two things: _this needs you_, or _this is certified_. Nothing else in Vihara is gold.**

| Gold is | Gold is not |
|---|---|
| Hands-raised beacons | Daylight |
| Certified action blocks and their seal | Active/selected states (use `--surface-2` + `--border-strong`) |
| The protected reserve seam on a treasury gauge | Healthy KPIs |
| Pragya's beam while she is narrating | Ordinary links or headings |
| The brand mark and wordmark | Colleague portraits at rest |
| A single hero figure at depth 0 | Chart series |

Everything else in the world is built from the **warm-white ramp at varying alpha** (`--white` → `--fg` → `--fg-muted` → `--fg-subtle` → `--fg-faint`) over the ink ramp. That ramp has five usable steps and no meaning of its own, which is exactly what a world needs for its ambient mass.

The consequence is the product's most important visual property: **on a still estate with nothing to do, there is almost no gold on screen.** The silence L1 promises becomes literally visible, and the first gold beacon to appear is unmissable because it is the only gold in the frame. A design that spends gold on decoration cannot make that promise.

### 2.2 The one exception, and why it is not one

Charts need more than one distinguishable series. Rather than break the palette, chart series use the **warm-white ramp plus the two semantic hues** (`--positive` sage, `--negative` terracotta) and, past three series, **texture** (dash patterns, dot density) rather than new hues. The brand's rule that semantic colours stay desaturated so they never compete with gold is what makes this work: a five-series chart still has no gold in it, so a beacon appearing beside it still wins the eye.

## 3. Palette

The brand tokens are used **unchanged**. Vihara adds one small layer that the brand does not have, because a world has surfaces the console does not.

| Vihara token | Value | Purpose |
|---|---|---|
| `--world-ground` | `--ink-950` | The territory's ground plane at night; the frame at all hours |
| `--world-mass` | `rgba(246,241,233,.06)` | Un-lit built form — districts, halls, gatehouses at rest |
| `--world-mass-lit` | `rgba(246,241,233,.14)` | The same form under daylight key (§4) |
| `--world-line` | `rgba(246,241,233,.22)` | Roads, edges, contour |
| `--world-traffic` | `rgba(246,241,233,.34)` | Signal traffic in motion on the roads |
| `--world-key-day` | `#fff6e6` at 0.9 | The daylight key light — **warm white, not gold** (§2.1) |
| `--world-key-night` | `--gold-700` at 0.5 | Lamplight pools only; low, local, few |
| `--twin-desat` | filter: `saturate(.15) brightness(.92)` | The Glasshouse's material shift (§5) |
| `--twin-line` | `rgba(228,232,236,.28)` | Cool-neutral edge inside the twin only |

That is the complete addition. No new hue is introduced anywhere in the product.

## 4. Day–night, as luminance (charter decision 3)

The territory follows the tenant's local time. Under the brand palette the shift is a **lighting model**, not a palette swap — the frame, the chrome, the sheets and the cards are near-black at every hour.

| | Day | Night |
|---|---|---|
| Key light | One high, soft, warm-white key (`--world-key-day`), long shadows | No key |
| Ground | `--world-ground`, lifted ~8% by bounce | `--world-ground`, unlifted |
| Built form | `--world-mass-lit` | `--world-mass` |
| Local light | none | Lamplight pools (`--world-key-night`) at gatehouses, occupied workplaces, and the Terrace |
| Traffic | Fully visible | Visible; the roads themselves fall to `--world-line` at half alpha |
| Beacons & certified gold | **Identical in both** | **Identical in both** |
| Transition | 20 minutes of real time either side of local sunrise/sunset, interpolated | — |

The beacon rule is the one that matters and it is inherited from §4 of the spec: *"weather and beacons read identically in both"*. A raised hand must not be easier to see at 3pm than at 9pm.

**Night is the default look of the brand, so night is the cheaper render** — which conveniently means the low-power path (D7's device tiers) is also the more on-brand one.

## 5. The Glasshouse: silvered without a second hue (L6)

L6 requires that real and twin panes keep **distinct material treatment**, and the ratified spec reached for "warm vs silvered glass" — easy when you have parchment and indigo, awkward under one gold.

**The twin is the real, desaturated.** Not recoloured: `--twin-desat` drains the world toward neutral, gold falls to a cool white-silver, and edges pick up `--twin-line`. The glass material loses its gold tint (`--glass-tint` instead of `--glass-tint-gold`) and its sheen flattens.

Three reasons this is the right answer rather than a compromise:

1. **It introduces no hue**, so the brand's central rule holds.
2. **It is the correct metaphor.** A simulation is the world with the life taken out of it, and desaturation is what that looks like. A blue twin would say "different place"; a drained twin says "not yet real".
3. **It cannot be forged.** Desaturation is applied by the renderer at the plane boundary, not chosen per component — so a twin-derived component cannot be styled to look real. L6 asks the manifest layer to enforce honesty; this makes the *material* enforce it too.

**Gold inside the Glasshouse** is reserved for exactly two things: the **divergence ribbon** (where twin and real disagree) and **certified seals on the promotion pipeline**. Everything else is silver. So the one thing your eye finds in a simulation is the thing that differs from reality — which is the only reason to be in there.

## 6. Type

The brand's four faces, mapped to Vihara's surfaces. No serif — spec §11's narrative serif is retired with the rest of it (§1).

| Face | Used for |
|---|---|
| **Roblox** (`--font-logo`) | The wordmark and the depth-0 hero figure only. Nothing else. It is a logotype, and the brand flags it as a substitute pending the real files |
| **Space Grotesk** (`--font-display`) | Surface titles, district names, colleague names, KPI figures, Boardroom headings |
| **Hanken Grotesk** (`--font-body`) | Everything a person reads — the still line, tray prose, Pragya's narration, dossiers, standup lines, forms, sheets |
| **JetBrains Mono** (`--font-mono`) | Eyebrows (UPPERCASE, `--track-eyebrow`, gold **only** when the eyebrow labels a certified block), agent ids, signal ids, the Undercroft in full, traces, diffs |

**The narrative register is carried by Hanken Grotesk at `--lh-relaxed` and a 60–72ch measure**, not by a display face. This is a real change from §11's intent and worth an owner eye at R1: the brand's voice is "calm, confident, quietly profound", and it achieves that with a neutral humanist sans plus air. A serif would have been a fifth face and a second personality.

**The Undercroft is mono throughout** — depth 3 is the engine room, its audience is operators, and the density scalar at that depth is pinned to operator regardless of the learned value.

## 7. Portraits (L7, spec §14.5)

The single highest-leverage art decision, and the brand hands us an unusually good answer: **the dotted-B mark is a halftone of gold dots.** Making the *portrait medium* a dot screen means the brand's only ornament becomes the way people are drawn.

That matters beyond style. L7 requires portraits that are "unmistakably non-human" and "disclosed as AI". A halftone-dot bust discloses itself **by its medium, at a glance, in every context, with no label to localise, no badge to crop off, and no way to be mistaken for a photograph.** A disclosure carried by the artwork cannot be lost in a card layout.

### 7.1 Four candidate directions (for R1 sign-off)

| # | Direction | Character | Cost |
|---|---|---|---|
| **A** | **Halftone bust** — shoulder-up figure rendered as a field of gold dots, density carrying the form; features implied by dot spacing, never drawn | Warm, human enough to name and greet; unmistakably synthetic | Raster generation (blocked on ADC) or a per-colleague dot-field render |
| **B** | **Engraved hairline** — spec §11's original engraved-illustration register, re-keyed to gold hairlines on near-black | Closest to the ratified spec; dignified, cool, a little formal | Raster generation; hardest to keep consistent across dozens of colleagues |
| **C** | **Seal** — no figure at all: a concentric dot arrangement, deterministic from the entity id, reading as a personal seal | Most honest, most consistent, coldest. **Procedural: no raster step, ever** | None — SVG, generated in the client |
| **D** | **Silhouette on a halftone field** — solid near-black bust against a gold dot field, features entirely absent | Striking; strong at card size; anonymous at scale | Raster or procedural |

**Recommendation: A as the house style, C as the automatic fallback.** A colleague with a defined persona gets a halftone bust; every other entity — a newly seeded agent, a gateway, a Meta-Agent role, a colleague in the Gallery — gets a seal generated from its id. Nothing is ever portrait-less, and nothing waits on an art pipeline to exist.

### VP-02 · The fallback should probably be the floor

Direction **C is procedurally generatable in SVG from the entity id**, which means: no ADC, no illustrator, no raster assets, no drift between a colleague's portrait and its versions, and a Gallery that can render a colleague terminated two years ago without an asset store. It is the only direction with no production cost at all.

The honest counter is that seals are cold, and spec §5's dossier and one-on-one surfaces are built on the premise that you *meet* a colleague. A room of seals is a filing cabinet.

**Raised, not decided** — it is an owner call at R1, and it is genuinely a taste question rather than an engineering one.

### 7.2 Rules that hold whichever direction wins

* One style for **every** colleague. A mixed roster reads as a bug.
* Portraits are **never** gold-glowing at rest (§2.1) — a colleague with a raised hand gets a beacon *above* it, not a gilded face.
* A portrait in the **Gallery** (terminated) is desaturated by the same rule as the twin (§5) — the past and the not-yet-real share a material, which is correct: neither is currently true.
* **No photoreal, no expressions, no implied feeling**, in the real estate and the Glasshouse alike (L7). Simulated people are permitted in the Twin (owner override §6.4) and use the identical portrait system, so a simulated colleague never looks *more* real than a real one.

## 8. Weather, and the colour-alone rule

§4's weather states (fog / heat-shimmer / storm cell / moonlit stillness) carry health information, and under a one-hue palette they cannot lean on colour at all. Each is therefore **texture + motion + a Lucide icon + a sentence**, and the icon and sentence are what the sheet equivalent (L9) and the screen reader receive.

| State | Means | Texture & motion | Icon | Sentence |
|---|---|---|---|---|
| Clear | Nothing wrong | — | — | — *(silence is the resting state, L1)* |
| Fog | KPI trouble in this district | Ground haze, edges lose definition, traffic dims | `cloud-fog` | "Sales has been below target for 9 days." |
| Heat-shimmer | Budget burning fast | Vertical shimmer over the district, faster than any other motion in the product | `flame` | "Support has used 80% of its envelope with 11 days left." |
| Storm cell | Circuit breaker tripped | A dark cell overhead; **traffic on the district's roads stops** | `cloud-lightning` | "Collections is stopped — the breaker tripped at 14:02." |
| Moonlit stillness | Hibernating | Everything static, lamplight only, no traffic | `moon` | "Marketing is hibernating; nothing is scheduled." |

**The stopped traffic is the real signal in a storm, not the cloud.** Under WCAG 2.2 AA and a palette this narrow, the motion channel does more work than colour — and the reduced-motion path (§9) is precisely where that breaks, which is why every row above also has an icon and a sentence.

## 9. Motion

Brand easing throughout: `--ease-out` `cubic-bezier(.16,1,.3,1)`, durations 120–640ms, no bounce, no overshoot, no spin.

| Movement | Duration | Note |
|---|---|---|
| Camera flight (steward walk, teleport) | 480–640ms | Eases like an aircraft; never linear, never elastic |
| Depth change (rise / go deeper) | 320ms | Crossfade + a 12px rise; the depth ladder must feel like one axis |
| Tray arrival | 240ms | Slides like paper from the edge Pragya occupies |
| Sheet open | 200ms | |
| Beacon raise | 640ms | The slowest thing in the product, and the only element permitted a repeating animation — a slow breathing glow, ~4s cycle |
| Weather transition | 2–4s | Weather should never appear to *snap* |
| Echo ribbon (L10) | 120ms in, 4s dwell, 400ms out | |

**Motion always communicates causality** — where a thing came from and where it went. A card that appears without travelling from somewhere is a card the user has to hunt for.

**Reduced motion is a first-class path, not a degradation.** `prefers-reduced-motion` turns every camera flight into a 160ms crossfade, stops the beacon breath (the beacon stays at full glow), freezes weather texture to a static state, and removes the shimmer entirely. The product remains fully usable and loses nothing but atmosphere. Under §8's rules it also loses no *information*, because every state that motion expresses has an icon and a sentence.

## 10. Material

The brand's **liquid glass** is used for exactly what the brand says it is for — floating chrome, overlays, and controls — and Vihara adds one rule the brand could not have known it needed:

> **Glass is used where something floats *over* the world. Never inside a sheet.**

Depth 2 and 3 are dense, readable surfaces; glass over a flat surface is milky and costs GPU for nothing. Glass over the territory refracts the gold beneath it and earns its cost. Concretely: the tray, the ⌘K palette, the depth dial, the Time Scrubber and the Line's pinned vitals are glass; registers, forms, dossiers and the whole Undercroft are flat `--surface`.

`prefers-reduced-transparency` falls back to solid `--surface`, per the brand.

## 11. Accessibility

* **WCAG 2.2 AA** on the S and C renderers. The W renderer's guarantee is L9 — the sheet equivalent is a first-class product, not an apology.
* **Colour never carries meaning alone** — enforced by §8's icon+sentence doubles and by §2.2's chart textures.
* **Contrast, checked against the brand ramp:** `--fg` (#f6f1e9) on `--bg` (#0a0908) is far above AA. `--fg-subtle` (#7c746b) on `--bg` clears AA for large text only — **so `--fg-subtle` is never used for body copy**, only for captions ≥18px or metadata. `--fg-faint` is decorative and disabled-state only, never informational.
* **Gold on near-black** clears AA at `--gold-500` for text ≥18px; certified blocks therefore render their prose in `--fg` and use gold for the seal, the rule and the eyebrow — which is also what §2.1 wants.
* **Focus is never removed** — the brand's `--focus-ring` on every interactive element, including inside the W renderer, where keyboard teleport must show where it landed.

## 12. What R1 needs from the owner

1. **The gold budget (§2.1)** — the single most consequential rule here. Everything else follows from it.
2. **Portrait direction** — A / B / C / D, and the VP-02 question of whether the procedural seal should be the floor rather than the fallback.
3. **No serif (§6)** — confirmation that the narrative register is Hanken Grotesk with air rather than a fifth face.
4. **Day–night as luminance (§4)** — that this preserves concepts §6.7 in substance, since it demonstrably does not preserve it in appearance.

Four more, surfaced by building the boards (§13) and their adversarial reviews:

5. **The real pane's reserve seam inside the Glasshouse.** §5 says gold in that room is the ribbon and certified seals only; but the real pane renders *the real*, and draining its reserve seam would break L6 in the opposite direction. Proposed ruling (implemented in the board pending sign-off): the seam stays, **subdued to flat gold-700**, ranked below ribbon and seal.
6. **§9's repeating-animation scope.** As written, the beacon is "the only element permitted a repeating animation" — which the built product contradicts four ways (road traffic, dotted flows, Sheel's heartbeat, the energy floor). Proposed amendment: the beacon is the only repeating **attention** animation; the ambient families — traffic flow/drift at constant velocity, the heartbeat, the energy floor's slow light — are sanctioned as *world liveness*, not attention.
7. **The focus ring inside the drained plane.** The brand ring is gold; a focused scenario card inside the Glasshouse wears it. Proposed: the ring is **chrome, not content** — it stays gold everywhere.
8. **Depth-3 translucency.** The Undercroft's panels sit at .82 alpha over the machine floor, against §10's "flat surfaces" default. Proposed: sanctioned at depth 3 only — the engine room sits visibly *on* the machinery.

Specimens are in [art-bible/specimens.html](./art-bible/specimens.html); the five interactive boards of §13 are the review material for everything above.

## 13. The territory construction language — built (2026-07-28)

The abstract rules above now have a walkable proof: **five interactive boards** in [wireframes/](./wireframes/), linked into the depth ladder — click through them in order:

| Depth | Board | What it proves |
|---|---|---|
| 0 | [still-visual.html](./wireframes/still-visual.html) | The still line, the pulse, and §2.1's claim: at zero hands raised, no gold but the brand mark |
| 1 | [estate-visual.html](./wireframes/estate-visual.html) | The territory: quarters, gatehouses, traffic, weather, the one beacon; day–night as luminance |
| 2 | [district-visual.html](./wireframes/district-visual.html) | Inside a Process: colleagues as workstations, KPI plinth, treasury, live runs |
| 2 | [glasshouse-visual.html](./wireframes/glasshouse-visual.html) | Real vs twin panes, the gold divergence ribbon, four honesty grades, the promotion pipeline |
| 3 | [undercroft-visual.html](./wireframes/undercroft-visual.html) | The engine room: mono, dense, the manifest inspector, sitting on the machine floor |

The **owner approved the territory language on the first two boards (2026-07-28)**; the rest are built to it. The construction vocabulary they establish, derived from the owner's five inspiration references re-keyed to this palette:

* **Floating plinths** — every site rests 7px off the ground, rising to 18px on hover; light beneath sells the float.
* **Holographic volumes** — translucent warm-white glass with floor-lines, a **ghost wireframe scaffold** above the solid mass; the Glasshouse's silver variant drains at the *site* boundary, never per component.
* **Flat surface-printed UI** — nameplates, detail plates, halos, flows, scrubbers all lie on the ground at the world's own perspective. Paint order is deterministic by a sub-pixel lift: text at `translateZ(.5px)`, roads at `.25px`, ambient marks at 0.
* **Concentric halos** under the focused object; the beacon's gold ripple never varies with lighting, hover, or reduced motion.
* **The energy floor** — the legacy app's hex-tile-over-glow background, carried forward as the void beneath every surface and **re-keyed to warm-white**. Three independent reviews converged on the same ruling: the glow is *light, never gold* — a gold floor would spend the budget on decoration and dilute every real beacon above it.
* **The dotted-B watermark** — the brand's actual SVG (never redrawn), at ≤.05 opacity, on the Still Surface and in the Undercroft.

Rules the build round earned, now binding:

* **Needs-you dots are flat `--gold-500`; `--gradient-gold` is reserved for the brand mark and certified seals** (a §2.1 refinement — the gradient is the most precious form of the most precious color).
* **Reduced motion is 160ms crossfades, never hard snaps** — `animation: none` plus `transition-duration: .16s`, and the static beacon holds its breathe *peak*.
* **`--fg-faint` never carries information** — enforced down to table headers.
* An engineering lesson for the G1 renderers, recorded so it is not relearned: a bare `.flows path { fill:none }` also matches paths inside SVG `<marker>` defs and silently deletes every arrowhead — CSS beats presentation attributes.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-28 | v1.1 — **§13 added: the territory construction language, built.** Five interactive boards (still → terrace → district → glasshouse → undercroft) linked into the walkable depth ladder; the owner approved the language on the first two. The construction vocabulary (floating plinths, holographic volumes + ghost scaffolds, flat surface-printed UI with deterministic paint order, concentric halos, the **energy floor** carried from the legacy app and re-keyed to warm-white) is now specified from working artifacts rather than prose. Three adversarial review rounds produced four new binding rules (needs-you dots are flat gold-500; reduced motion is 160ms crossfades; `--fg-faint` never informational; the marker-defs CSS lesson) and **four new R1 rulings** (§12 items 5–8: the real pane's reserve seam, §9's animation scope, the focus ring in the drained plane, depth-3 translucency). |
| 2026-07-28 | v1.0 — the art bible, superseding spec §11 per charter decision 2. Its load-bearing content is not a palette but the **gold budget**: gold means *this needs you* or *this is certified*, and nothing else, which is what lets a still estate be visibly still. The Glasshouse is solved by **desaturation rather than a second hue** — no new colour, the right metaphor, and un-forgeable because the renderer applies it at the plane boundary. Portraits are proposed as **halftone dot fields**, making the brand's one ornament the medium and letting the artwork itself carry L7's disclosure. Raised **VP-02**: the procedural seal direction has no production cost and cannot drift, which may make it the floor rather than the fallback. |
