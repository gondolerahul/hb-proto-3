# Increment 7 / Redesign — Resume Here

> **Start-of-session document.** HANDOFF.md is the whole programme; this is the
> hundred lines that matter for the redesign. Written 2026-07-30.
> **Branch:** `inc7/redesign`, **40 commits** ahead of `master`, working tree clean, **on no remote**.
> **Read after this:** [00_redesign_charter.md](./00_redesign_charter.md) (**eight** locked decisions — D1–D4 and §3a's D5–D8) · [04_r4_readiness.md](./04_r4_readiness.md) (what measuring the tree found) · [02_prototype_r3a.md](./02_prototype_r3a.md) §5a–§5e (what was built and what verification found).

> ## ⚠️ 2026-07-30 — THIS DOCUMENT WAS WRONG IN THREE PLACES, AND THEY ARE FIXED BELOW
>
> A readiness assessment ran before R-4 and measured the tree rather than reading
> the build notes ([04_r4_readiness.md](./04_r4_readiness.md)). It found:
>
> * **§3's gate list omitted `npm run lint`, which is red** (8 errors), and the backend unit suite is red too (4 failures — the cross-language wire gate). **No CI runs any gate**, which is how both survived.
> * **§5's "R-4 is a data-source swap" understated it by six prerequisites.** Charter **D5** restates R-4 as one round of nine parts — see [06_r4_wiring.md](./06_r4_wiring.md).
> * **§6's rendered-gap table is stale on three of seven rows** — they now draw a *false* absence over backend contracts that shipped. Marked inline below.
>
> Also: **fifteen of eighteen** surfaces stood, not fifteen of fifteen. The Private
> Line was never rebuilt; charter **D6** rebuilt it as
> [R-3c](./05_r3c_private_line.md).
>
> ### ✅ Since then: R-3c and **the whole of R-4** have landed
>
> * **R-3c — the eighteen are complete.** Thread, Morning Story, Pocket Desk, plus the PWA shell and a second Vite entry.
> * **R-4 — all nine parts.** Gates honest + CI (G) · auth entry (A) · ⌘K navigator and `pushState` URLs (N) · fetch lifecycle (L) · step-up ceremony (C) · every surface wired (W) · the missing client wrappers (P) · the live SSE estate (S) · four new backend endpoints (E, incl. E3's colleague dossier and E4's talent brief).
> * **Nothing under `src/surfaces/`, `src/line/` or `src/shell/` reads `src/fixtures/`.** The fixtures stay on disk for tests.
>
> **✅ Proven live 2026-07-31: `all 18 surfaces clean`**, three consecutive sweeps
> against a real backend and a real session — the first end-to-end browser proof
> of this increment. It found three defects 384 green unit tests could not: an
> unbounded SSE stream that froze the API under `--reload`, a sweep that was
> measuring the scaffold, and **the Line having no session gate at all**. All
> three fixed; see [06](./06_r4_wiring.md) §10d.
>
> **Next is R-5**, the honesty pass: re-walk the parity register against the
> rebuilt app (v1.4), burn down `tests/motion.test.ts`'s frozen debt list
> (`width` in `standup.css` first — it is the only layout-triggering one), and
> decide onboarding staging + `world.ghost`, whose retirement claim in parity
> row 4 is currently **false in fact**.

---

## 1. Where this stands in one paragraph

Increment 7 shipped all eight workstreams and the **frontend was rejected on
design** at owner review (2026-07-30). The backend was untouched. `vihara/` was
preserved as `vihara-review-rejected/` and a new `vihara/` was built from the
visual layer up. **All eighteen surfaces plus the shell now stand and are wired
to the API** — R-3c added the Private Line, R-4 wired everything — and the whole
thing is **proven live: `all 18 surfaces clean`**. What remains is **R-5**, the
honesty pass, plus the owner-side legs.

## 2. Run it

```bash
cd /home/rahul/workspace/hb-proto-3/backend && .venv/bin/python -m uvicorn src.main:app --port 8000
```

```bash
cd /home/rahul/workspace/hb-proto-3/vihara && npm run dev
```

<http://localhost:4044> — the estate, behind a login · <http://localhost:4044/line.html> — the Line.
`⌘K` is the navigator, `⌘↑`/`⌘↓` the depth ladder, and every surface has a URL.

**A backend is now required.** Nothing reads `src/fixtures/` except tests. Need an
account?

```bash
cd backend && .venv/bin/python scripts/ensure_sweep_user.py
```

It prints the credentials and refuses to run against a non-local database.

> ⚠️ **Do not run the API with `--reload` while a browser has the app open** unless
> you are on a build with the bounded stream ([06](./06_r4_wiring.md) §10d). Before
> that fix an open SSE connection made graceful shutdown hang forever, and the
> backend stopped answering while still holding its port.

## 3. Gates, and how to run them

```bash
cd vihara
npx tsc --noEmit                  # strict + noUncheckedIndexedAccess
npm run lint                      # covers src AND tests
npx vitest run                    # 384
npm run build                     # both entries, each under its own 220 KB gz
npm run gen:api && git diff --exit-code -- src/api/schema.d.ts   # contract drift
npm run check:tokens              # the design-token mirror
```

```bash
cd backend
.venv/bin/python scripts/typecheck_ai.py      # mypy --strict, 352 files
.venv/bin/python -m pytest tests/unit tests/parity -q
```

**And the one that has caught what every other gate missed** — needs both servers up:

```bash
VIHARA_SWEEP_EMAIL=… VIHARA_SWEEP_PASSWORD=… node scripts/sweep.mjs
```

Last measured 2026-07-31, all green: **tsc · lint · vitest 384 · build clean
(index 183.7, line 117.7 KB gz of 220 each) · no API drift · tokens match ·
backend 2329 unit + 2 parity · typecheck 352 · sweep `all 18 surfaces clean`.**

**CI runs all of it** (`.github/workflows/gates.yml`) except the sweep, which needs
a browser and a live backend, and the integration suite, which needs Postgres and
Redis. Both absences are recorded in the file.

The harnesses beyond the tests — each one has found a real defect, so do not treat
them as optional:

| Script | What it is for |
|---|---|
| `sweep.mjs` | All 18 surfaces: console errors, page errors, empty bodies, horizontal spill. **Typecheck is not render, and jsdom is not a browser** |
| `shoot_variants.mjs` | The same surface under `prefers-reduced-motion`, at 720px and at 390px. Found 165 lines of dead CSS |
| `shoot_surface.mjs` / `shoot_flow.mjs` / `shoot_click.mjs` | One surface, optionally after a click; multi-beat flows |

## 4. The four locked decisions — do not re-litigate

Full text in [00_redesign_charter.md](./00_redesign_charter.md) §3.

1. **D1** — visual redesign **plus** an IA rebalance. The nine working surfaces are first-class rooms, not L9 fallbacks. L9 itself is not repealed; its *design consequence* is.
2. **D2** — ✅ closed: the **brand re-key** background ships. Forced art bible **§2.1a**, and that amendment owes a measurement (§7 below).
3. **D3** — `vihara-review-rejected/` is a **parts bin**, not a base. Salvage list in the charter.
4. **D4** — review is a **pixel-final prototype**, because R2 proved wireframe approval does not predict craft approval. The consequence: **R-4 is a data-source swap, not a rebuild.**

## 5. What R-4 actually is — ⚠️ CORRECTED

**R-3c comes first** ([05_r3c_private_line.md](./05_r3c_private_line.md)): the
Private Line's three surfaces plus the PWA shell, so R-4 wires eighteen surfaces
rather than fifteen.

**R-4 is one round of nine parts** ([06_r4_wiring.md](./06_r4_wiring.md)), not the
three mechanical steps this section used to claim. Still true:

* **16 surfaces import from `src/fixtures/`.** The field *names* were shaped to D5 contracts — but a function to fetch them frequently does not exist, so "the swap is per-surface and independent" holds for only **nine** of them.
* **`src/api/` is salvaged and imported by nothing** (verified again 2026-07-30: zero call sites outside itself). It wraps ~45 of `openapi.json`'s 246 paths; **four surfaces have no domain module at all** — Gallery, Dossier, Undercroft, District.
* **`src/manifest/` is salvaged too** — the Zod schema, the refusal ladder, and the **48**-entry registry (not 45: primitive 19, certified 10, world 13, narrative 6). The four registry JSONs are live — the backend byte-compares against them — but **no renderer was carried across**, so the layer stays dormant in R-4 by decision.
* **Delete `PrototypeNav`** — but only after part **N** replaces it. It is the only click path to **eleven of sixteen** surfaces.

**The six prerequisites the old text omitted**, none optional: an auth entry point
(there is none — `main.tsx` mounts the prototype unconditionally) · the fetch
lifecycle (seven surfaces TypeError on an empty response) · the step-up ceremony
(six surfaces draw certified controls that only mutate local state) · the
navigation replacement · `gen:api` (the command does not exist) · an SSE client.

Order is in [06](./06_r4_wiring.md) §1. **Part G first** — nothing measured is
trustworthy until the red gates are green and CI exists.

## 6. What is deliberately *not* built, and must stay that way

Each of these is a **rendered gap** — the surface says the platform cannot do this
yet. Drawing a working feature over one is the failure the whole redesign exists to
avoid. If you close the backend gap, close the rendered gap in the same commit.

| Surface | The gap it renders | Status |
|---|---|---|
| Library | Nothing calls `raise_contradiction`, so the flag exists and is **always absent**. Staleness is live; contradiction is not, and the surface says why | ✅ still true |
| Bridges & Gates | `credentials_expire_at` ships and is **never populated**. Absence of an expiry is absence of information, **not** a clean bill of health. Getting this wrong is a security design bug | ✅ still true |
| Gallery | The KPI series starts 2026-07-25 with no backfill. The **young state is the primary state** | ✅ still true |
| Undercroft | Four bays are drawn; five name the endpoint that already answers and say the *table* is what is missing | ✅ still true — but **three of the named endpoint strings are wrong** and one never existed. R-4 part P |
| ~~Tray, Dossier, Glasshouse, Gallery~~ | ~~`paths[].cost` is `null` until DRIVER's estimator exists~~ | ❌ **STALE.** `genui/cost.py`'s `observed_decision_cost` shipped 2026-07-29 and is called from both tray composers. Cost is `None` today only because the dev DB has **zero** `human_approvals` rows and the estimator floors at five observations — a *seeding* gap, not a build gap. The **null-renders-as-nothing** rule stands and is still held by `tests/tray_cost.test.tsx` |
| ~~Talent Office~~ | ~~Termination has no backend contract (VG-18)~~ | ❌ **STALE.** `POST /ai/talent/colleagues/{id}/terminate` shipped 2026-07-29 — composes the exit interview, files the memo as an Artifact, 409s while runs are live. The fixture denying it was authored **the next day** |
| ~~Boardroom, Glasshouse~~ | ~~TWIN's scenario runner is not wired end to end~~ | ❌ **STALE.** `POST /ai/twin/scenarios/{id}/run` → arq `twin_scenario_run` → `runner.run_scenario`, shipped 2026-07-29 (GLASS X2–X4) |

**The three stale rows fail safe** — understating the platform is better than
overstating it — **but they misdirect R-4**: a wiring session following this table
skips three surfaces that are ready. R-5 closes them, and they move to **"shipped,
not yet wired"** rather than straight to a live control, because no client has yet
exercised those endpoints.

**Four regions are worse than a rendered gap** — they draw fixture data as though
sourced, with no endpoint at all: the Bridges board's consent/DNC, the Undercroft's
consent bay, the Dossier's charter/competencies/SLOs, and the Talent Office's brief
and past cases. Charter **D8** builds all four (R-4 part **E**).

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
| 2026-07-30 | v1.1 — **corrected against a measured tree** ([04_r4_readiness.md](./04_r4_readiness.md)). Three things this document asserted were wrong: the gate list omitted `npm run lint` (red, 8 errors) and the backend unit suite (red, 4 failures) and **no CI runs any gate**; "R-4 is a data-source swap" understated it by six prerequisites, so charter **D5** restates it as nine parts; and **three of §6's seven rendered-gap rows are stale**, drawing a false absence over contracts that shipped 2026-07-29 — the rule "close the backend gap and the rendered gap in the same commit" was violated in the direction nobody watches. Also: fifteen surfaces of **eighteen**, not of fifteen (**D6** adds R-3c); the registry is **48** entries, not 45; the branch is **30** commits ahead, not 28. |
| 2026-07-30 | v1.0 — written as the redesign's session-resume document. All fifteen product surfaces plus the shell stand; owner review round 1 implemented; twelve generated portraits shipped. R-4 (wire to backend) is next, and is a data-source swap rather than a rebuild because the prototype is real code. |
