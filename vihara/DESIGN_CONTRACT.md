# Vihara — the design contract

Read this before writing any surface. It is what stops N surfaces from becoming
N design systems, which is one of the seven findings that got the first build
rejected (see `docs/product-road-map/increment-7/redesign/00_redesign_charter.md`).

---

## 0. The seven findings you are correcting

| # | What went wrong last time | What you must do instead |
|---|---|---|
| RD-1 | Type baked into a 3D ground plane, unreadable | All text is screen-space DOM. Never inside a canvas |
| RD-2 | Built form was hollow wireframe cages | Solid, lit, material volumes |
| RD-3 | Gold budget starved the frame — "calm" became "blank" | Keep the budget; give the other 94% **material**, not just alpha |
| RD-4 | Depth 0 was three lines over black | Every surface is *composed*, even a quiet one |
| RD-5 | The brand's material vocabulary went unused | Use `m-plate`, `m-glass`, `m-well`, `m-metal`, `m-lamp`, hairlines |
| RD-6 | The background was re-derived, not ported | Not your concern — already ported and locked by test |
| RD-7 | Working surfaces got a *fallback's* design budget | **These are first-class rooms.** Design them like the product's centre |

RD-7 is the one that matters most for you. Nine of these surfaces are where a
business owner spends the day. None of them is a fallback for anything.

## 1. Hard rules

1. **Never import `three` or `@react-three/*`.** These are all Sheet-renderer surfaces. An eslint boundary and a bundle gate exist for this.
2. **No emoji, ever.** Icons come from `src/components/Icon.tsx` (`<Icon name="..." />`). Use only names already in `PATHS`. If you genuinely need one that is absent, use the closest existing name and note the gap in your report — **do not edit `Icon.tsx`**, another agent is editing nothing and you would collide.
3. **No raw hex colours and no raw px for colour/space.** Use the CSS variables from `src/design/tokens.brand.css`. Spacing is `var(--s-1)`…`var(--s-10)`. The only px literals allowed are optical one-offs (a 9px tick, a 1px rule) and they get a comment saying why.
4. **Never `!important`**, never inline `style` except for the stagger index (`style={{ ["--i" as string]: i }}`).
5. **Animate only `transform`/`opacity`** (and `translate`/`scale`/`rotate` as their modern longhands). Never animate width, height, top, left, or box-shadow.
6. **TypeScript is strict with `noUncheckedIndexedAccess`.** Index access needs `!` or a guard. `noUnusedLocals` is on.
7. **Own only your own files.** Listed in your brief. Do not touch `src/design/*`, `src/shell/*`, `src/app/*`, `src/background/*`, `src/components/*`, `src/fixtures/estate.ts`, `src/manifest/*`, `src/api/*`, or any file belonging to another family.

## 2. The material system (`src/design/material.css`)

**The governing rule: an edge is never one border.** Every real surface gets a
light rim, a body hairline, a contact shadow, and a cast shadow. One border is a
div; four is an object. That is already baked into the classes — use them rather
than rolling your own `border: 1px solid`.

| Class | Use for | Modifiers |
|---|---|---|
| `m-plate` | The opaque base surface. Cards, panels, rooms | `data-raised`, `data-sunken` |
| `m-glass` | Things that float over the world. Rails, palettes, sticky bars | `data-strong`, `data-gold` |
| `m-well` | Inset. **Where data lives** — tables, logs, code, fact blocks | `data-deep` |
| `m-metal` | Gold. **Certified acts only** | pair with `m-metal-shine` |
| `m-medallion` | A struck gold seal | — |
| `m-gold-text` | Gradient-clipped gold text. Figures and seals only | — |
| `m-rule` / `m-rule-fade` / `m-rule-v` | Hairlines. `-fade` reads machined | — |
| `m-ticks` | Corner L-brackets. The instrument-panel register, costs no gold | — |
| `m-lamp` | The point light — **how status reads** | `data-lit`, `data-positive`, `data-negative`, `data-breathing` |
| `m-chip` | Small pill. Filters, hops, counts, states | `data-selected` |
| `m-btn` | Button | `data-rank="quiet"` / `"certified"` |
| `m-plinth` | Small isometric-feeling volume on a lit base. Stands for a district/colleague/object in a list | — |

**Glass discipline:** glass on glass is fog. Use `m-glass` for one floating
layer per surface at most; everything inside it is `m-plate` or `m-well`.

## 3. Type roles (art bible §6)

| Class | Face | For |
|---|---|---|
| `t-eyebrow` | JetBrains Mono, 10px, uppercase, tracked | Labels a block. `data-certified` makes it gold — **only** when the block it labels is certified |
| `t-display` | Space Grotesk | Surface titles, names, headings |
| `t-figure` | Space Grotesk, 38px, tabular | A KPI number |
| `t-mono` | JetBrains Mono, 12px | Ids, traces, diffs, timestamps, raw data |
| `t-narrative` | Hanken Grotesk, 18px, 1.7, 64ch | **Everything a person reads as prose.** Pragya's voice, stories, explanations |
| `t-muted` / `t-subtle` / `t-faint` | — | The warm-white ramp. `t-faint` is the *disabled* step — never use it for information |

Prose measure never exceeds ~72ch. Figures are always tabular (`.num` or the
classes above). Headings use `text-wrap: balance`, paragraphs `pretty`.

## 4. Colour rules

**The gold budget (art bible §2.1, amended §2.1a):** gold means exactly one of
two things — **this needs you**, or **this is certified**. Nothing else.

Gold **is**: hands-raised beacons · certified blocks and their seals · the
protected-reserve seam on a treasury gauge · Pragya's beam while narrating · the
brand mark · a focus ring.

Gold is **not**: daylight · active/selected states (use `--surface-2` +
`--border-strong`) · healthy KPIs · ordinary links or headings · chart series ·
portraits at rest · "you clicked this".

Everything else is built from the warm-white ramp at varying alpha over the ink
ramp, **plus material** — that last clause is finding RD-3, and it is why you
reach for `m-well`/`m-plate`/hairlines/grain instead of another alpha step.

**Never colour alone.** Every state is a `m-lamp` *plus a word*. The lamp is the
fast read; the word is the correct one. (WCAG 1.4.1, and a one-hue palette makes
it unavoidable anyway.)

Semantic hues are `--positive` (sage) and `--negative` (terracotta), desaturated
so they never compete with gold. Past three chart series, use **texture** (dash
patterns, dot density), not new hues.

## 5. Motion (`src/design/motion.css`)

`vh-enter` (rise+fade, 320ms) · `vh-enter-fade` · `vh-stagger` (children need
`style={{ ["--i" as string]: i }}`) · `vh-lift` (hover: translate, never scale —
scale resamples text and goes soft) · `vh-skeleton` (a sweep, not a pulse — a
pulsing opacity on dark reads as a fault) · `vh-echo`.

Enter slow, exit fast. One `@media (prefers-reduced-motion: reduce)` block
already stops everything; do not add per-component opt-outs.

## 6. Accessibility floor

- Contrast ≥ 4.5:1 for body text, ≥ 3:1 for large text and UI boundaries.
- Every interactive element is a real `<button>`/`<a>`/`<input>` with an accessible name. Icon-only buttons need `aria-label`.
- Never remove focus rings. The global `:focus-visible` handles it.
- Tables: `<caption class="vh-sr-only">`, `<th scope="col">`, sticky headers **opaque** (a translucent sticky header over moving text is unreadable however pretty the blur).
- Touch targets ≥ 44×44 on the mobile breakpoint; ≥ 32px on desktop.
- Anything that reports a result gets `role="status"`.
- Use `<dl>/<dt>/<dd>` for label–value pairs, not divs.

## 7. Content rules — these are correctness, not style

1. **Never invent a number.** If a binding is absent, render **nothing** — never `₹0`, never `—`, never "unknown". A null cost on a payment card is the worst available bug (`tests/tray_cost.test.tsx` holds the precedent).
2. **Honesty grades are four, not three**: `replay` · `forecast` · `untested` · `unknown`. `untested` ("never tried") must **not** render like `unknown` ("could not be graded"). Distinct idioms.
3. **A surface with little to show says so in prose.** Never an empty chart. The KPI series starts 2026-07-25 with no backfill, and for a quarter some surfaces are honestly thin.
4. **Where the platform has a real gap, render the gap.** Do not draw a working feature over a known absence — say it, quietly, in `t-mono` or prose. Your brief names which gaps apply to you.
5. **Realistic, awkward content.** Long party names, overdue counts, a disputed record, a colleague on probation. A design that only survives tidy content has not been tested.

## 8. Shape of a surface file

```tsx
import { useState } from "react";
import { Icon } from "../components/Icon";
import { THING } from "../fixtures/<yourfile>";
import "./<yourfile>.css";

/**
 * <Name> · depth N · S (D6 §X).
 *
 * Which finding this surface answers, and the two or three design decisions
 * you made that a reader would otherwise have to reverse-engineer. Say WHY,
 * not what the code plainly does.
 */
export function <Name>Surface({ onEcho }: { onEcho: (msg: string) => void }) { … }
```

- Named export, no default. Props are exactly `{ onEcho }` unless your brief says otherwise.
- `onEcho(msg)` fires the L10 echo ribbon on every act. Message is lowercase past tense, the user's own words: `"marked Pricing 2026 superseded"`.
- CSS is one file per surface, class prefix unique to that surface (2-letter, e.g. `.do-` for dossier). Never restyle an `m-*` or `t-*` class — compose with them.
- Fixtures in your own `src/fixtures/<name>.ts`, typed, shaped to the D5 contract named in your brief.

## 9. Density

Surfaces have a novice and an operator variant. **Do not build a toggle** — build
the operator layout, and where the brief names a novice difference, put it behind
a `density` prop defaulted to `"operator"` only if it is cheap. Otherwise note in
your report what the novice variant would change. The Undercroft is pinned to
operator regardless (art bible §6).

## 10. Definition of done

- `npx tsc --noEmit` clean.
- Reads correctly at 1600×1000 and does not scroll horizontally at 900px wide.
- Every rule above holds, or the exception is commented with its reason.
- Your report says: files written, decisions made, gaps found, and anything you needed that did not exist.
