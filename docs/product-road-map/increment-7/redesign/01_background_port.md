# Increment 7 / Redesign — R-1: The Background Port

> **Round R-1** of [00_redesign_charter.md](./00_redesign_charter.md) §5. Closes the build half of **decision D2**; the *pick* is owner-side and open.
> **Code:** `vihara/src/background/` · **Test:** `vihara/tests/background_verbatim.test.ts` (10 assertions, green).

---

## 1. What was ported

`frontend/src/components/layout/AnimatedBackground.tsx` — instanced hexagonal tiles over a simplex-noise "energy floor" shader, with `UnrealBloomPass` and a mouse-driven tile lift.

Finding **RD-6** was that the first build never actually ported this. It re-derived the effect as Canvas-2D (`atmosphere/floor2d.ts`) plus a partial GL scene behind a tier gate, and the result was not the thing that had been approved. So the port is structured to make that failure impossible to repeat:

| File | Role |
|---|---|
| `background/LegacyBackground.tsx` | **Byte-identical** to the legacy file. Not edited, not reformatted, not linted, and excluded from `tsconfig` — see §4 |
| `background/hexField.ts` | The same scene with the four colours lifted into one parameter. Both shaders are **character-identical** to the legacy source; grid, camera, fog and bloom constants are identical values |
| `background/Background.tsx` | The React wrapper — variant, atmosphere intensity, reduced-motion path |
| `tests/background_verbatim.test.ts` | Fails if any of the above stops being true |

The test reads both files as **text**. Nothing imports across the `frontend/` boundary.

## 2. The two candidates

Identical geometry, shaders, bloom, camera, fog and interaction. Four colour values differ, and nothing else does.

| | `colorA` (crack of light) | `colorB` (pulse) | Tile | Clear colour |
|---|---|---|---|---|
| **Legacy (verbatim)** | `vec3(0.4, 0.2, 0.1)` copper | `vec3(0.1, 0.2, 0.4)` electric blue | `#080808` | `#382b02ff` *(invalid — §3)* |
| **Brand re-key** | `vec3(0.39, 0.28, 0.12)` `--gold-500` at legacy luminance | `vec3(0.16, 0.18, 0.22)` desaturated cool neutral | `#100e0c` `--ink-900` | `#241a06` warm haze |

The re-key's `colorA` is brand gold scaled to the luminance the legacy copper carried, so the cracks read at the intensity that was approved rather than brighter. `colorB` drops the hue entirely: art bible §2.1's gold budget survives a cool *sheen* where it would not survive a cool *hue*.

### 2.1 The conflict, stated rather than resolved

Charter D2 names this and does not paper over it. The legacy copper glow is warm light across the whole lower frame, and §2.1 exists so that a gold beacon is *the only gold on screen* and therefore unmissable. Those two approved things are in genuine tension.

The R-1 board is built to make that judgeable instead of arguable: it puts a breathing gold beacon and a gold certified block on top of each background, so the question becomes **"can you still find the beacon"** rather than "which floor is prettier". If the verbatim version wins, §2.1 is amended in the same commit.

## 3. A latent bug found in the legacy file

`new THREE.Color('#382b02ff')` is **invalid** — THREE.Color does not accept 8-digit hex. It logs `THREE.Color: Invalid hex color #382b02ff` and leaves the colour at its default **white**.

So the legacy app's intended warm-olive haze has never rendered, in three years of that file existing. The only reason it was never noticed is that this camera (position `y=9`, looking at `y=-8`) never sees above the horizon, so the clear colour is covered by floor in every frame.

**It is deliberately left invalid in `LEGACY_PALETTE`,** with a comment saying so, because D2's contract is *reproduce the approved app* — and correcting it would introduce a warm haze at the top of the frame that the owner has never seen. That is a visible change wearing a bug fix's clothes. The valid-hex version of the same intent is `BRAND_PALETTE.background`, where it is a choice.

## 4. Two honest limits

**The verbatim file does not typecheck, and must not be made to.** It predates `noUncheckedIndexedAccess` and trips it in five places. Editing it would break the byte-identity the test enforces, so it is excluded in `tsconfig.json` with the reasoning inline. `hexField.ts` — the file that actually runs — is fully checked. The verbatim copy exists to *prove the port is faithful*, not to execute.

**The background cannot be judged on this VM, and neither could the original.** Under headless software GL (SwiftShader, no GPU) the scene renders as near-black with faint hex texture and no lava glow, because `UnrealBloomPass` needs float render targets. Verified by rendering the **legacy app itself** under identical conditions: it produces the same near-black frame. That is the evidence the port is faithful — and it means **the R-1 pick has to be made in a browser with a real GPU.** Any screenshot taken here understates both variants equally.

## 5. One addition the redesign makes

The scene is never re-graded, but a surface can ask for less of it. `Background` takes an `intensity`:

| Intensity | Where | What it does |
|---|---|---|
| `full` | Depth 0, the Terrace | The atmosphere is the surface |
| `quiet` | District rooms, the Boardroom | Warm ember at the rim, calm in the middle |
| `hushed` | Trays, Halls, the Undercroft | Near-flat — a breathing floor under a table of invoices competes with the invoices |

This is a CSS veil over the running scene, not a second grade of it. The approved look is never modified, only veiled — which is what keeps "ported verbatim" true while still letting a dense working surface be readable.

Under `prefers-reduced-motion` no scene is mounted at all, so the veil layer carries a static gradient in the same key for each variant.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-30 | v1.0 — R-1 built. Verbatim port byte-identical and enforced by test; re-key differs in exactly four colour values with both shaders character-identical. Found and documented a **three-year-old latent bug** in the legacy file (`#382b02ff` is invalid hex, silently falls back to white, invisible only because the camera never sees the horizon) and deliberately preserved it in the legacy palette. Recorded two honest limits: the verbatim file is excluded from typecheck by design, and **neither variant can be judged on this VM** — verified by rendering the legacy app itself under the same headless GL and getting the same near-black frame. The pick is owner-side, on real hardware. |
