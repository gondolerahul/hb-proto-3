# Increment 7 / Redesign — Resume Here

> **Start-of-session document.** HANDOFF.md is the whole programme; this is the
> hundred lines that matter for the redesign. Written 2026-07-30.
> **Branch:** `inc7/redesign`, **28 commits** ahead of `master`, working tree clean.
> **Read after this:** [00_redesign_charter.md](./00_redesign_charter.md) (the four locked decisions) · [02_prototype_r3a.md](./02_prototype_r3a.md) §5a–§5e (what was built and what verification found).

---

## 1. Where this stands in one paragraph

Increment 7 shipped all eight workstreams and the **frontend was then rejected on
design** at owner review (2026-07-30). The backend half is untouched and still
good. `vihara/` was preserved as `vihara-review-rejected/` and a new `vihara/` was
built from the visual layer up. **All fifteen product surfaces plus the shell now
stand**, at pixel-final quality, with the owner's first review round implemented.
What remains is **R-4: wire it to the backend.**

## 2. Run it

```bash
cd /home/rahul/workspace/hb-proto-3/vihara && npm run dev
```

<http://localhost:4044> · keys `1`–`9` pick a surface, past nine click the scaffold
bottom-right · `⌘K` palette · `⌘↑`/`⌘↓` the depth ladder · on the Terrace, drag to
pan, scroll to zoom, double-click to reframe.

**No backend needed.** Every surface reads `src/fixtures/`. That is R-4's whole job.

## 3. Gates, and how to run them

```bash
cd vihara
npx tsc --noEmit                  # strict + noUncheckedIndexedAccess
npx vitest run                    # 28 tests
npx vite build                    # shell must stay under 220 KB gz
node scripts/sweep.mjs            # visits all 16 surfaces, needs npm run dev
```

Last measured, all green: **tsc clean · vitest 28 · sweep 16/16 · build clean,
shell 141 KB gz of the 220 budget.**

Four harnesses beyond the tests, and each one found a real defect — do not treat
them as optional:

| Script | What it is for |
|---|---|
| `sweep.mjs` | Every surface: console errors, page errors, empty bodies. Typecheck is not render |
| `shoot_variants.mjs <out> "<nav label>" <name>` | The same surface under `prefers-reduced-motion` and at 720px. Found 165 lines of dead CSS |
| `shoot_surface.mjs <out> <name> "<nav label>" [selector]` | One surface, optionally after a click |
| `shoot_flow.mjs` / `shoot_click.mjs` | Multi-beat flows (the Boardroom's tabling exchange) |

## 4. The four locked decisions — do not re-litigate

Full text in [00_redesign_charter.md](./00_redesign_charter.md) §3.

1. **D1** — visual redesign **plus** an IA rebalance. The nine working surfaces are first-class rooms, not L9 fallbacks. L9 itself is not repealed; its *design consequence* is.
2. **D2** — ✅ closed: the **brand re-key** background ships. Forced art bible **§2.1a**, and that amendment owes a measurement (§7 below).
3. **D3** — `vihara-review-rejected/` is a **parts bin**, not a base. Salvage list in the charter.
4. **D4** — review is a **pixel-final prototype**, because R2 proved wireframe approval does not predict craft approval. The consequence: **R-4 is a data-source swap, not a rebuild.**

## 5. What R-4 actually is

The prototype is real React in mock mode, so wiring is mechanical rather than a
rewrite:

* **16 surfaces import from `src/fixtures/`.** Every fixture was shaped to a D5 contract, so the swap is per-surface and independent.
* **`src/api/` is salvaged, present, and imported by nothing yet** (verified: zero call sites outside itself). It carries the client, `authn`, and the per-domain modules from the rejected build — including cookie-mode auth (VP-01).
* **`src/manifest/` is salvaged too** — the Zod schema, the refusal ladder, and the 45-entry registry.
* **Delete `PrototypeNav`** in `src/app/Prototype.tsx`. It is marked in code as review scaffolding.
* **Re-run the API drift gate** after any backend router change: `scripts/export_openapi.py` then `npm run gen:api`, or the drift gate fails.

Suggested order: Tray and Registry Hall first (their endpoints are the most
exercised), then the Terrace's estate read model, then the rest.

## 6. What is deliberately *not* built, and must stay that way

Each of these is a **rendered gap** — the surface says the platform cannot do this
yet. Drawing a working feature over one is the failure the whole redesign exists to
avoid. If you close the backend gap, close the rendered gap in the same commit.

| Surface | The gap it renders |
|---|---|
| Tray, Dossier, Glasshouse, Gallery | `paths[].cost` / predictions are `null` until DRIVER's estimator exists (D5 §4.1). **A null renders as nothing** — never `₹0`, never a dash. Held by `tests/tray_cost.test.tsx` |
| Library | Nothing calls `raise_contradiction`, so the flag exists and is **always absent**. Staleness is live; contradiction is not, and the surface says why |
| Bridges & Gates | `credentials_expire_at` ships and is **never populated**. Absence of an expiry is absence of information, **not** a clean bill of health. Getting this wrong is a security design bug |
| Talent Office | Termination has no backend contract (VG-18). The exit-interview flow is drawn **blocked** |
| Gallery | The KPI series starts 2026-07-25 with no backfill. The **young state is the primary state** |
| Boardroom, Glasshouse | TWIN's scenario runner is not wired end to end, so "take to the Glasshouse" is drawn **disabled with its reason** |
| Undercroft | Four bays are drawn; five name the endpoint that already answers and say the *table* is what is missing |

## 7. The one thing still owner-side

**Art bible §2.1a's measurement obligation.** The brand re-key put gold in the
atmosphere, so §2.1's budget was amended one layer deep. That amendment is only
safe if a gold beacon still wins against a gold field, and that is an **empirical**
claim on hardware that can render bloom — this VM has no GPU
([[vihara-bloom-needs-a-gpu]], and [01_background_port.md](./01_background_port.md) §4).

The owner confirmed 2026-07-30 that **the beacon is clearly visible on every
surface**, which discharges the practical risk. What remains unrecorded is a
measured number at all three intensities. **If it ever fails, the fix is specified
in advance: drop the field's luminance, never raise the beacon's** — brightening
the beacon to compete is how an estate stops being still.

## 8. Things a fresh session will otherwise rediscover the hard way

* **This VM has no GPU.** WebGL screenshots are near-black and prove nothing — verified by rendering the *legacy* app under the same headless GL and getting the same frame. Never judge a WebGL surface from a screenshot taken here.
* **`waitUntil: "networkidle0"` never settles** against a Vite dev server (the HMR socket stays open). Use `domcontentloaded` plus a dwell, and wait for `.pn` before pressing keys — a keypress before React attaches is silently lost.
* **The workflow concurrency cap here is 2** (4 cores → `min(16, cores-2)`). Four parallel agents run two at a time, so a four-surface fan-out is two rounds, not one.
* **Portraits: user ADC is expired; the VM's attached service account works.** `gcloud auth application-default` cannot refresh non-interactively, but `hirebuddha-vertex-ai` on the metadata server has cloud-platform scope. That is how the twelve portraits were drawn. Regenerate with:
  ```bash
  cd vihara && ../backend/.venv/bin/python scripts/portraits.py all --force
  ```
  Edit a persona in that script to change a face; **do not edit the STYLE block** — it is owner-reviewed and byte-identical to the pre-redesign pipeline, and editing it to fix one portrait makes the medium drift across twelve.
* **`origin/master` is 79 commits behind** and this VM has no git credentials. A push from a credentialed host is a standing owner action, and it now includes the whole redesign branch.

## 9. The two lessons worth carrying past this increment

**A compound defect can hide its own cause.** Finding RD-1 said territory labels
were unreadable because they were painted flat on the ground. I "fixed" it by
moving every glyph into screen-space DOM and argued the fix was structural. The
owner reversed it, and was right: RD-1 was **three** defects arriving together —
skewed **and** colliding **and** too small — and "flat" took the blame for what
collision and size did. Labels are flat again with the real causes fixed by
construction (§2.1b). *When a finding names one cause for a compound defect, check
whether it named the load-bearing one.*

**A capability limit may block one implementation, not the surface.** "No World
surfaces, because this VM has no GPU" had a true premise and a wrong conclusion —
the blocker was *bloom*, not WebGL. Drawing the territory in SVG dissolved it, and
the result is better than the WebGL version would have been: an SVG territory is
the tier-C path and the L9 sheet equivalent *simultaneously*, at full quality, with
labels that are real selectable text.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-30 | v1.0 — written as the redesign's session-resume document. All fifteen product surfaces plus the shell stand; owner review round 1 implemented; twelve generated portraits shipped. R-4 (wire to backend) is next, and is a data-source swap rather than a rebuild because the prototype is real code. |
