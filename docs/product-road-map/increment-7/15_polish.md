# Increment 7 / Phase B — POLISH: Launch Quality (G6)

> **Status:** ✅ **BUILT 2026-07-29** (P0–P12 on `inc7/polish`) — G6's buildable half met at the test level; **every owner-side leg is consolidated into one run-sheet document, [15a_launch_protocols.md](./15a_launch_protocols.md)**, and G6's *exit* (the zero-training pass, the parallel run) is owner-side by nature. Build notes: §9.
> **Read first:** [10_workstream_decomposition.md](./10_workstream_decomposition.md) §9 (the scope) · [03_art_bible.md](./03_art_bible.md) (the rules this workstream applies and is checked against) · [07_surface_wireframes.md](./07_surface_wireframes.md) + `wireframes/*-visual.html` (the look the owner approved at R2) · [08_device_matrix.md](./08_device_matrix.md) (D7 — the tiers and the p75 floor VG-22 must prove).

---

## 1. What POLISH is, and what the reckoning found

The decomposition gives POLISH six obligations: onboarding staged in the world over the unchanged step APIs · the §10.4 zero-training test with five naive users · the WCAG 2.2 AA audit on S and C · the p75-on-tier-B performance floor (**VG-22**, the last open gap-analysis finding) · **the art bible applied everywhere and checked against its own rules** · the parity reckoning against D8, and the 30-day parallel run started.

The owner's review of the built app (2026-07-29) landed on the fifth obligation before this doc was written: *none of the screens are close to the wireframes, and the real screens are supposed to be **better** than the wireframes.* Walking the app against the R2-approved visuals confirms it, and finds the cause is structural, not scattered:

**Finding 1 — the background system was never built.** Every one of the five approved visual wireframes (Still, Terrace, District, Glasshouse, Undercroft) carries an atmosphere the app does not have: the radial vignette, the **energy floor** — matte hex tiles over slow-drifting warm light, explicitly annotated in `still-visual.html` as *"carried over from the legacy app's background system… re-keyed to the brand's single hue; the legacy blue is retired"* — and the dotted-B watermark. The legacy app's original is `frontend/src/components/layout/AnimatedBackground.tsx` (three.js: instanced hex tiles, a simplex-noise "lava" shader, bloom, a mouse-ripple lift). The shipped Vihara renders flat `--bg` on every surface at every depth.

**Finding 2 — the brand's material layer was never adopted.** SUB's token mirror covers `colors_and_type.css` only. The design system's `styles.css` — the **liquid glass** utilities (`--glass-tint`/`--glass-edge`/sheen), the semantic type scale, the gold text treatments, buttons, chips, eyebrows — is consumed **nowhere** in `vihara/src`. The tray, the steward dock and the depth dial, which art bible §10 names as glass ("glass is used where something floats *over* the world"), are flat bordered boxes. The certified frame renders its seal as a 10px disc where the specimens give it the metallic treatment.

**Finding 3 — the motion language (art bible §9) is unimplemented.** No tray slide (240ms from Pragya's edge), no depth crossfade + 12px rise (320ms), no beacon breath outside the three.js world, no weather transitions. The one animation in the app is the echo ribbon's 120ms entry.

**Finding 4 — late workstreams drifted off-token.** STEWARD, LINE and GLASS CSS reference `--vh-line`, `--vh-surface`, `--vh-gold` — variables no file defines — so their hardcoded fallbacks are what actually renders, and one of them (`#c9a227`) is not even the brand gold.

**What is already right, and must not be broken:** the three.js terrace faithfully implements the §13 construction language; the gold budget is pinned in comments and audited per-file; the portraits shipped; and the 247 vitest goldens pin *structure* (data-parts, roles, wire shapes), not pixels — which is what makes a material pass safe.

## 2. § Decisions (locked with Rahul 2026-07-29 — do not re-litigate)

1. **The background palette is the brand re-key, not the literal legacy colors.** Warm light (`246,241,233` alphas) through matte tiles; the legacy electric blue stays retired; the floor spends **no gold** — exactly what R1/R2 approved. The one-hue law holds.
2. **The background engine is the full three.js port on tier A/B** — the legacy scene's character (instanced hex tiles, noise-driven light, bloom, the pointer ripple) re-keyed to the brand — **with the Canvas-2D floor as tier C's version, the reduced-motion version, and the instant paint under the GL chunk's load**. The GL atmosphere rides the same lazy-chunk discipline as the world: the tier-C-never-fetches-three.js gate keeps holding.
3. **The gold budget stands.** "Very luxurious" is delivered through material, light, motion and typography — glass, metallic seals, atmosphere, the type scale — never by widening where gold may appear. R1's ruling is unchanged: gold means *this needs you* or *this is certified*, and a still estate shows none.
4. **Fonts are self-hosted.** The Google Fonts `@import` leaves the canonical DS file (`buddha-cognitive-lab-design-system/project/colors_and_type.css`) in favour of local `@font-face`; both mirrors re-sync. No FOUT, no third-party request, and the Line's offline shell keeps its faces.

And one standing directive from the same session: **the wireframes are the floor, not the ceiling** — the built screens are expected to read *better* than the R2 HTML, not merely equal to it.

## 3. The task plan

| P | Task | Where |
|---|---|---|
| P0 | This doc · branch `inc7/polish` | docs |
| P1 | **Foundation**: fix the `--vh-*` drift · mirror `styles.css` beside the tokens (sync gate extended) · self-host the fonts (canonical DS edit + re-sync) | `vihara/src/tokens/`, DS project |
| P2 | **The atmosphere layer, 2D**: `vihara/src/atmosphere/` — Canvas-2D energy floor + vignette + dotted-B watermark + day–night luminance, mounted in the shell at every depth, in pre-session, and in the Line | `vihara/src/atmosphere/` |
| P3 | **The atmosphere layer, GL**: the legacy scene ported and re-keyed, lazy behind the tier gate; one-GL-context rule; context-loss and FPS demotion to 2D; budget gates extended | `vihara/src/atmosphere/gl/` |
| P4 | **Glass where things float** (art bible §10): tray, steward dock, terrace controls + depth dial, echo ribbon, standup cards, Line vitals, pre-session card. Sheets stay flat | `app.css` + surfaces |
| P5 | **The motion language** (art bible §9): tray arrival, sheet open, depth change, beacon breath, ribbon dwell — reduced-motion first-class | shell + surfaces |
| P6 | **Surface-by-surface art-bible pass** — all 18 surfaces + the Line against their wireframes and §6/§10/§11, then past them: type hierarchy, eyebrows, spacing, empty states, the certified frame's metallic seal, tables, focus states | `vihara/src/app/`, `line/` |
| P7 | **Onboarding staged in the world** (spec §15.1, wireframes §19): the ghost estate over the unchanged step APIs; depth 0 unlocks at stage 9 | `vihara/src/app/`, `estate/` |
| P8 | **WCAG 2.2 AA audit** on S and C, with fixes | app-wide |
| P9 | **VG-22**: the p75-on-tier-B floor measured against D7 §3.1, harness + recorded numbers | `vihara/tests/`, docs |
| P10 | **Parity reckoning** against D8 — the register walked with evidence | [09](./09_screen_parity_register.md) |
| P11 | Owner-side protocols written: the five-user zero-training script (§10.4), the parallel-run checklist, the real-device matrix run sheet | docs |
| P12 | Gates · §Build notes · HANDOFF · merge | docs |

## 4. Design — the atmosphere layer (P2/P3)

One package, `vihara/src/atmosphere/`, two renderers of the same scene description, chosen by the tier probe:

```
atmosphere/
  scene.ts        — the shared description: tile grid params, light-blob field
                    (seeded, deterministic), day–night interpolation, depth dimming
  Atmosphere.tsx  — the mount: picks 2D or GL, owns the fallback ladder
  floor2d.ts      — Canvas-2D: matte hex tiles over drifting radial glows (the
                    wireframes' implementation, productionised)
  gl/Floor3D.tsx  — the legacy port: instanced extruded hexes, the simplex light
                    shader re-keyed to warm white, bloom, pointer ripple
```

Rules, each carrying a reason:

* **The palette is light, never signal.** Every glow is `rgba(246,241,233,…)`. The floor spends no gold (§2.1's budget is what makes a raised hand visible) and reintroduces no blue (the one-hue law). The legacy shader's two-color mix collapses to one warm-white family at two intensities.
* **The GL atmosphere shares the world's chunk discipline.** `gl/` is reached only by dynamic import behind the same tier gate as `WorldTerrace`; the existing "tier C provably never fetches three.js" build gate extends to it. The 2D floor lives in the shell and must cost single-digit KB.
* **One GL context at a time.** When the world canvas is live (depth ≥ 1 on tier A/B), the atmosphere **pauses and hides** — the terrace draws its own energy floor, and a second WebGL context with bloom under a full scene is how the p75 floor (VG-22) dies. The atmosphere runs at depth 0, in pre-session, and dimmed behind depth-2/3 sheets; the wireframes show it at every one of those depths.
* **The fallback ladder never shows a black rectangle** (D7 §4's rule, inherited): GL context lost twice, or the frame watchdog breaching sustained → swap to the 2D floor in place, silently. Reduced motion → the 2D floor renders **one static frame** (the wireframes' own pattern). `prefers-reduced-transparency` is irrelevant here (the floor is background, not glass) but the vignette respects the same restraint.
* **Day–night is luminance, on the tenant's clock** (art bible §4): a single multiplier pair (face alpha, glow strength) interpolated over 20 real minutes either side of local sunrise/sunset — the estate-visual's `--daymul`/`--glowmul` mechanism, computed in `scene.ts` so both renderers agree. Beacons and certified gold are exempt by rule.
* **The watermark is the brand's own mark** (the dotted-B at ~5% opacity, fixed, bottom-right) — sanctioned by the art bible the same way the wordmark is, and rendered once as static SVG.

## 5. Design — material adoption (P1/P4)

**The mirror grows a second file.** `styles.css` joins `colors_and_type.css` under the same discipline: copied by `scripts/sync_tokens.mjs`, byte-equality asserted by the tokens vitest, never edited in `vihara/`. What Vihara *adds* stays in its own files, importing on top. This is SUB's two-copies gate, unchanged in shape.

**The fonts edit is a canonical DS change, made deliberately.** Decision 4 authorises editing `project/colors_and_type.css` itself: the `@import url(googleapis…)` line is replaced by local `@font-face` blocks for Space Grotesk, Hanken Grotesk and JetBrains Mono (woff2, the weights the DS declares), beside the Roblox faces already local. The font files land in the DS `fonts/` folder and the mirror's; both mirrors re-sync to byte equality. If the files cannot be fetched on this VM, the task parks with the `@import` intact and a named remainder — a network dependency is not silently traded for broken faces.

**The glass placement map** (art bible §10 — glass floats over the world, never inside a sheet):

| Glass (`.glass` / `.glass-strong` / `.glass-bar`) | Flat (`--surface`) |
|---|---|
| Tray panel · steward dock · terrace controls + depth dial · echo ribbon · standup cards · the Line's pinned vitals · pre-session card · demotion offer | Registry halls · record sheets · dossiers · Boardroom · Library · Study · Undercroft (mono, dense) · Gallery lists · Glasshouse panes (the desaturation *is* the material) |

`prefers-reduced-transparency` falls back to solid `--surface` — the brand ships that rule in `styles.css` already.

**The `--vh-*` drift is fixed by deletion.** The four fallback-only variables are replaced with the brand tokens they were reaching for (`--border` / `--surface-2` / `--gold-500`); a one-line vitest greps `src/` for `--vh-(line|surface|gold)` so the drift cannot return.

## 6. Design — the surface pass (P6)

The pass is per-surface against three references in order: its wireframe (structure and composition), the art bible (§2.1 gold audit, §6 type, §10 material, §11 contrast), and the DS specimens (component finish). Its unit of work is one surface, its gate is the existing structural goldens staying green — the pass changes classes and CSS, not data-parts, roles or wire shapes.

What "past the wireframe" means concretely, so it does not decay into taste: real hover/press/focus states on everything interactive (the wireframes have almost none) · empty states written as sentences, not dashes (LIB's lesson: the "nothing happened" path is where quality dies) · `tabular-nums` on every figure · the certified frame's seal upgraded to the metallic conic treatment with prose staying `--fg` (§11) · tables in the register idiom (uppercase mono headers, hairline rules) · the still line set left, on the clamp measure, in the light weight — the composition `still-visual.html` draws.

## 7. Design — onboarding staged in the world (P7)

No new surfaces and no new backend: the nine-stage engagement (Pragya's Inc-3 stage contract, the unchanged Inc-2 step APIs) drives what the estate *shows* — empty plot → ghost estate (`world.ghost` does the work) → Halls and Library filling as documents land → the first Boardroom → candidates in the Talent Office → Bridges → rehearsal → **the Still Surface appearing for the first time at stage 9**. The sequencing rule the wireframes call un-get-wrongable is enforced in the shell's routing: **depth 0 is unreachable until the engagement reaches stage 9** — before that, the app opens onto the Terrace with the ghost estate, and the steward carries the stage.

## 8. Design — the proofs (P8–P10)

* **WCAG 2.2 AA (P8):** the §11 contrast table re-checked against built CSS (`--fg-subtle` never below 18px, gold text ≥18px only, focus never removed — including keyboard teleport landing visibly in the world); an axe-core pass over every S and C surface in the vitest harness; findings fixed, not filed.
* **VG-22 (P9):** D7 §3.1's budgets measured, p75, on a tier-B profile (4× CPU throttle in the harness): first-paint of depth 0, depth-change latency, tray arrival, world entry. Numbers recorded here in §Build notes; the floor either holds or the miss is named with its cause.
* **Parity (P10):** the D8 register walked row by row — 28 in-scope screens + the Study + pre-session — each row stamped with the surface that answers it and any residual gap named. The two known-out rows stay out with their reasons.

## 9. § Build notes — the delta log

All of P0–P12 built 2026-07-29 on `inc7/polish`, one commit per task. **Vitest 288** (SUB's 247 + 41) · tsc · eslint · budgets **shell 120.4 · line 3.5 · world 218.9 KB gz** (the bloom passes joined the world chunk) · backend untouched and re-measured green at merge.

### 9.1 Deltas — where the build corrected the design

1. **The GL floor lives in `renderers/world/AtmosphereFloor.tsx`, not `atmosphere/gl/`** (§4 sketched the latter). The eslint boundary allows three.js in exactly two trees, and widening a security-shaped rule for a background was the wrong trade — the atmosphere reaches it by dynamic import, so the chunk discipline is identical and the boundary stays narrow.
2. **GL is shell-only, and that is now a *rule*, not a placement** (§4 said "tier A/B"). A login must not spend the 219 KB world chunk before auth, and the pocket must stay phone-light — `chooseEngine` refuses GL for `presession` and `line` contexts outright, pinned by test, whatever the tier.
3. **The DS's reduced-motion collapse would have silently killed the beacon's glow.** The mirrored `styles.css` zeroes every animation duration; the breath at duration ~0 rests at its *zero-glow* keyframe. Vihara pins the beacon to **full glow** under reduced motion — the art bible's "loses atmosphere, never information", which the brand's blanket rule gets wrong for exactly this one element. The motion test counts `infinite` in the CSS and requires exactly one.
4. **The stage-9 gate fails OPEN, stated and tested** (§7 implied but never said it). It is a sequencing rule, not a security control: an unreadable engagement must never lock a working estate out of its own front door. The reverse failure costs one click.
5. **jsdom's canvas returns null, and the floor treats that as a feature** — the 2D painter degrades to silence (the vignette stands, nothing throws), which is also the honest behaviour on a canvas-starved browser.
6. **P9's numbers are a canary, not the proof, and the file says so in its docstring.** Measured p75 over 25 runs in the harness: still scaffold **10.5ms** / 120 budget · terrace sheet **16.5ms** / 200 · tray whole **10.2ms** / 250. The real p75-on-tier-B row lives in [15a](./15a_launch_protocols.md) §3 with the eight numbers to be recorded back here.

### 9.2 What each task shipped (one line each)

P0 doc · **P1** `--vh-*` drift dead + `styles.css` mirrored under the two-copies gate + fonts self-hosted (canonical DS edit, latin+latin-ext carries ₹) · **P2** the atmosphere layer (vignette · Canvas-2D energy floor · dotted-B watermark · day–night luminance · depth dimming · one-GL-context pause) · **P3** the legacy three.js background ported whole and re-keyed (no blue, no gold, warm-light family; context-loss ×2 / FPS-breach / no-WebGL → 2D in place) · **P4** glass per the §10 placement map with the reduced-transparency correspondence test · **P5** the §9 motion table + the ribbon's 400ms leave as a tested hook · **P6** the shared idiom pass (interaction grammar, still-visual composition at depth 0, mono eyebrows, display figures, metallic seal, card idiom, chips) · **P7** onboarding staged in the world (depth 0 = stage 9's reward) · **P8** the computed §11 contrast table + axe over the wire-free surfaces · **P9** the p75 canary · **P10** register v1.3 with two named residuals (password reset · login OAuth) · **P11** [15a](./15a_launch_protocols.md) · **P12** this close-out.

### 9.3 Honest limits — each named, none silent

* **No pixel has been seen by human eyes this session.** The entire pass is spec-and-test-driven; the walkable-look judgement is G1's owner review and §3 of the run sheet. The per-surface *fine* pass (P6's tail) rides that review — the shared idiom is applied everywhere, but taste calls need a screen.
* **The GL floor has never executed** — written from the legacy component and three.js contracts, like every injected-transport seam this repo ships; its first run is the device-matrix sitting.
* **axe ran on two surfaces** (the wire-free harnesses); the other sixteen ride their fixture harnesses and the browser leg (15a §3).
* **The §10.4 zero-training test and the 30-day parallel run are G6's actual exit** and cannot be run from this VM — scripts ready in 15a §1–§2.
* **Two parity residuals** (register §5): password reset and login OAuth are backend-first absences, named, non-blocking for the parallel run.
* The Line's atmosphere is the 2D floor by rule (battery); if the pocket ever earns GL it is a new decision, not a default.
