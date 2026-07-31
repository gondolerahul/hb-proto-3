# Increment 7 / Redesign — R-4 Readiness Assessment

> **Written 2026-07-30**, before R-3c and R-4, at the owner's instruction to assess
> the built state against the documents rather than resume from the build notes.
> **Method:** every gate run, not read. Every doc claim checked against the tree.
> Load-bearing findings were then re-checked by an independent pass whose brief was
> to *refute* them; one was refuted and is recorded as such in §6.
> **Produces:** charter [§3a](./00_redesign_charter.md#3a-owner-decisions--round-2-locked-2026-07-30)'s
> four decisions (D5–D8), plus rounds [R-3c](./05_r3c_private_line.md) and
> [R-4](./06_r4_wiring.md).

---

## 1. The one-paragraph version

The **backend is real and in good order**. The **frontend is a pixel-final
prototype with no network code of any kind** — which is what R-3b set out to
build, and is not a criticism of it. What is a finding is the *distance* between
that prototype and the app: [03_resume.md](./03_resume.md) §5 describes R-4 as a
three-step data-source swap, and the tree needs six prerequisites first. Two gates
are red and were not in the gate list. Three "rendered gaps" now draw a false
absence over backend contracts that shipped a day before the fixture that denies
them. Three of the eighteen ratified surfaces were never rebuilt.

**None of this is drift in the code.** It is drift between the code and the record,
and every item below is closable.

## 2. What is real

| Layer | State | Evidence |
|---|---|---|
| Backend Inc-7 seams | **Real and registered.** 12 REST routes under `/api/v1/ai/genui`, the Pragya WebSocket, 2 talent routes, 7 twin routes | `backend/src/ai/genui/router.py`; all included in `backend/src/main.py` |
| Backend types | **Green.** `Success: no issues found in 345 source files` | `backend/scripts/typecheck_ai.py` |
| Migration head | `genui003` | statically resolved from `versions/` |
| The prototype's look | **Standing, at final quality, on all fifteen built surfaces** | sweep 16/16; this assessment does not reopen R-3b's craft verdict |
| `src/api/` | **Salvaged and sound.** Cookie-mode auth, in-memory access token, CSRF double-submit, 401-refresh-retry | `vihara/src/api/client.ts` |
| `src/manifest/` | Salvaged; the four registry JSONs are **live** — the backend byte-compares against them | `backend/tests/unit/test_genui_registry.py` |

## 3. The six prerequisites R-4 does not list

Each blocks the fixture swap. None is optional.

| # | Prerequisite | Why the swap cannot proceed without it |
|---|---|---|
| 1 | **Auth entry + session gate + logout** | `src/main.tsx` renders `<Prototype/>` unconditionally. There is no login screen, no session state, no 401 route, no logout. The first authenticated call 401s, attempts a cookie refresh, fails — no cookie was ever set — and dead-ends with no UI. `PreSession.tsx` (103 lines) was not carried across |
| 2 | **Fetch lifecycle** | Seven surfaces open their first `useState` with a non-null-asserted index-0 read. On an empty API response every one is a TypeError *before* render. `TraySurface.tsx` is the sharpest case: it already carries the copy "Nothing needs you." at line 39 and crashes at line 28 first |
| 3 | **Step-up ceremony** | Six surfaces draw `data-rank="certified"` controls that mutate local state and nothing else. `StepUpCeremony.tsx` / `useCertifiedAct.ts` were not carried across. Three of the wired paths — tray approval, connector bind, strategy adopt — **will** 403 with `step_up_required` the moment they are real, with no UI able to answer |
| 4 | **Navigation replacement** | `PrototypeNav` is the only click path to **eleven of sixteen** surfaces, and deleting it is a stated R-4 task |
| 5 | **`gen:api` + `openapi-typescript`** | `npm run gen:api` → `Missing script`. The resume doc instructs running it |
| 6 | **SSE client** | Nothing updates after first paint. No `EventSource`, no `WebSocket`, no `fetch` anywhere outside `src/api/` |

**The seven crash sites**, for the record: `TraySurface.tsx:28` · `BoardroomSurface.tsx:90` ·
`DossierSurface.tsx:52` · `GlasshouseSurface.tsx:34` · `LibrarySurface.tsx:105` ·
`GallerySurface.tsx:83` · `TalentSurface.tsx:64`.

`noUncheckedIndexedAccess` is on in `tsconfig.json`; the `!` at each site suppresses
exactly the check that setting was added to perform.

**A note on how the lifecycle must be built.** [08_device_matrix.md](../08_device_matrix.md)
§3.1 defines *first scaffold* as layout on screen and **explicitly not** the moment
data arrives, and names the Glasshouse the only surface permitted a visible loading
state. So this is a scaffold-then-hydrate split. "Add a spinner" is
contract-prohibited on fifteen of sixteen surfaces.

## 4. What the salvage did not carry

D3's salvage list names the API client **and its `gen:api` diff gate**, the certified
set's structural goldens, the PWA shell and service worker, and the CI gates
including the ≤220 KB budget. Measured against the tree, those four were not
carried.

| Absent from `vihara/` | Present in `vihara-review-rejected/` | Consequence |
|---|---|---|
| `app/PreSession.tsx` | 103 lines | Prerequisite 1 |
| `estate/{live,sharedStream,useLiveEstate}.ts` | a pure reducer + an injectable wire | Prerequisite 6 |
| `components/certified/{StepUpCeremony,useCertifiedAct,certifiedSet}.tsx` | the T2/T3 ceremony | Prerequisite 3 |
| `renderers/{RenderManifest,bindings}.tsx` + four component modules | the manifest renderer | All 48 registry entries have zero implementations |
| `line/` (4 surfaces) + `line.html` + `public/line-sw.js` + `line.webmanifest` | the whole Private Line | **D6** — three of eighteen surfaces |
| `scripts/gen_api.mjs` + `openapi-typescript` | the API drift gate | Prerequisite 5 |
| `scripts/check_bundle_budget.mjs` | wired into `build` | The 220 KB budget is a guideline with no mechanism |
| `scripts/sync_tokens.mjs` | the two-copies token gate | The DS mirror can drift silently |
| `axe-core` | the a11y gate | G6's a11y leg has no harness on this tree |
| 28 of 32 test files | 288 vitest → 28 | §5 |

## 5. The gate truth

Measured by execution on a clean tree, 2026-07-30.

| Gate | Measured | Verdict |
|---|---|---|
| `npx tsc --noEmit` | exit 0, zero diagnostics | ✅ as claimed |
| `npx vitest run` | 28 passed / 4 files | ✅ as claimed |
| `npx vite build` | exit 0 · shell **140.98 KB gz** (117.81 JS + 23.17 CSS) of 220 | ✅ as claimed — **but nothing enforces the budget** |
| `node scripts/sweep.mjs` | 16/16 clean | ✅ as claimed |
| `backend/scripts/typecheck_ai.py` | 345 files, no issues | ✅ as claimed |
| **`npm run lint`** | **exit 1 — 10 problems (8 errors, 2 warnings)** | ❌ **red, and absent from the resume doc's gate list** |
| **`pytest tests/unit`** | **exit 1 — 4 failed, 2238 passed, 2 skipped** | ❌ **red since the redesign replaced `vihara/`** |
| `npm run gen:api` | `Missing script` | ❌ does not exist |
| bundle-budget script | absent | ❌ guideline, not a gate |
| CI | `.github/workflows/` holds `cortex-memory.yml` only | ❌ **no CI runs any of the above** |

**The two red gates, precisely.**

**Lint.** `.eslintrc.cjs` allowlists `src/components/world/**` and
`src/renderers/world/**` for three.js imports. **Neither directory exists in the
redesign** — its three.js lives in `src/background/`, so the allowlist matches
nothing and all eight imports fire. The *substance* of D7 §3.3 still holds:
`vite.config.ts` still quarantines three into the `world` chunk, so a tier-C device
still never downloads it. What is broken is the rule's enforcement, not the rule.
Two `react-hooks/exhaustive-deps` warnings fail independently under
`--max-warnings 0`.

**Backend unit.** All four failures are `test_genui_fixture_export.py` — the SUB T7
**cross-language wire gate**, and the only proof that the Python composer and the
TypeScript client agree on the wire. It fails on missing
`vihara/tests/fixtures/*.ndjson`, which lived in the tree that was replaced.

This is the finding with the longest reach: **no CI runs any gate**, which is
precisely why a red backend suite and a red lint survived a full workstream and two
review rounds without being noticed.

## 6. Three rendered gaps now render a false absence

[03_resume.md](./03_resume.md) §6 lists seven surfaces that deliberately draw a
platform gap rather than a working feature, under the rule *if you close the
backend gap, close the rendered gap in the same commit*. **Four still hold.** Three
are stale, and the rule was violated in the direction nobody was watching.

| Drawn as blocked | Actually shipped | The delta |
|---|---|---|
| Talent termination — "has no backend contract (VG-18)" | `POST /ai/talent/colleagues/{id}/terminate` — composes the exit interview, files the memo as an Artifact, 409s while runs are live, stamps `terminated_at` for `GET /colleagues-past` | shipped 2026-07-29; the fixture denying it was authored **2026-07-30** |
| "Take to the Glasshouse" — hard-disabled, runner not wired end to end | `POST /ai/twin/scenarios/{id}/run` → arq `twin_scenario_run` → `runner.run_scenario` | shipped 2026-07-29 (GLASS X2–X4) |
| `paths[].cost` null "until DRIVER's estimator exists" | `genui/cost.py`'s `observed_decision_cost`, imported and called from both tray composers | shipped 2026-07-29 (DRIVER) |

**This fails safe rather than unsafe** — a surface understating the platform is
better than one overstating it. But it actively misdirects: a wiring session
following §6 skips three surfaces that are ready. R-5 closes them, and they move to
**"shipped, not yet wired"** rather than straight to a live control, because no
client has yet exercised those endpoints.

**The four that still hold**, unchanged and still correct: `raise_contradiction`
has no production caller · `credentials_expire_at` is never populated (and absence
of an expiry remains absence of information, not a clean bill of health) · the
Gallery's KPI series is genuinely young with no backfill · the Undercroft draws
four bays and names the rest.

**One claim refuted.** An early pass reported that the district room's `weather` and
`traffic` have no backend endpoint. They do — both are payload fields of
`GET /ai/genui/estate/district/{process_code}` and of the `weather.changed` /
`traffic` SSE events. The scan missed them because that route's OpenAPI response is
untyped, so no field names appear in `openapi.json`. What survives is smaller and
different: District needs a **wrapper plus a shape reconcile** (`in_1h`/`out_1h` vs
the fixture's `inPerHour`/`outPerHour`, and a backend weather vocabulary of
`clear|storm|heat-shimmer|moonlit` against a fixture that also uses `fog`, which the
backend docstring says is deliberately absent).

*Recorded because it is the second time this increment that a true premise carried a
wrong conclusion — see [03_resume.md](./03_resume.md) §9's bloom/WebGL note. An
absence in a generated schema is evidence about the schema, not about the server.*

## 7. Four regions with no backend at all

Distinct from §6: these are not rendered gaps, they are fixture data presented as
though sourced. **D8 builds all four.**

| Region | State |
|---|---|
| **Bridges — gate consent + DNC** | `dnc_entries`, `consent_records` and `trust/consent_registry.py` all ship. `grep APIRouter backend/src/ai/trust/` returns **nothing** — there is no HTTP surface. The manifest registry's `certified.consent` binds `source: "consent.state"` with nothing behind it |
| **Undercroft — consent bay** | Names `GET /ai/consent`, which is absent from all 246 paths, while the `Unbuilt` component asserts in prose that the endpoint "answers today" |
| **Dossier — charter clauses, competencies, SLOs, probation** | No endpoint. `tenant.fetchProposals` is a different entity — record-change signals, not colleague-raised charter changes |
| **Talent — BRIEF, PAST_CASES, interview traces** | The surface's three largest structures, of an 862-line fixture. No endpoint |

Consent is nearly free — only the router is missing. **The colleague charter and the
talent brief are real domain design**, and D8 accepts them into Increment 7
deliberately rather than by omission.

## 8. Scale of the wiring itself

`03_resume.md` §5 says *every fixture was shaped to a D5 contract, so the swap is
per-surface and independent*. The field **names** were shaped. A function to fetch
them frequently does not exist.

* **Nine surfaces are a clean swap** — wrapper and endpoint both exist: Still, Terrace, Tray, Hall, Standup, Study, Boardroom, Library, Glasshouse.
* **Thirteen regions have an endpoint and no wrapper**: District, Gallery ×4, Brainstorm chat, Undercroft ×3, Library upload/search, Tray pending, Glasshouse compare, Registry.
* **Four surfaces have no domain api module at all**: Gallery, Dossier, Undercroft, District.
* `src/api/` wraps roughly **45 of `openapi.json`'s 246 paths**.

## 9. Corrections to the record

Small, but they are the numbers other documents quote.

| Claim | Where | Actual |
|---|---|---|
| "the **45-entry** component registry" | charter §3 D3; `03_resume.md` §5 | **48** — primitive 19, certified 10, world 13, narrative 6 |
| "**28 commits** ahead of `master`" | `03_resume.md` header | **30** |
| "shell 87.3 KB gz · world 215.5 KB gz" | `08_device_matrix.md` §9 | those are the **rejected** tree's numbers; the redesign measures 140.98 / 137.59 |
| "all **fifteen** product surfaces" | `03_resume.md`; `Prototype.tsx` | fifteen **of eighteen** — see D6 |
| "`tests/parity` stayed **16** green" | `14_glass.md` §9 | the suite passes, and collects **2** |
| "40 of 49 findings closed" / "every High-severity finding is closed" | `roadmap_gap_register.md` | **45 of 49**, and four High findings are open in the same paragraph: B14, C2, D2, D4 |

`inc7/redesign` is on **no remote**, and `origin/master` is **79 commits** behind.
Every workstream from SUB onward exists on one machine. That is unchanged from the
last three handoffs and remains the largest single operational risk in the project.

## 10. What this assessment does not do

It does not reopen R-3b's craft verdict. It does not re-litigate D1–D4. It does not
touch `backend/src/ai/genui/` beyond reading it. Every finding above is either a
missing piece of plumbing, a red gate, or a sentence in a document that no longer
matches the tree.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-30 | v1.0 — written at the owner's instruction to assess the built state against the documents before resuming. Ran every gate rather than reading build notes, and found two red (lint, backend unit) that no gate list mentions and no CI would have caught. Found six unlisted prerequisites between R-4 as chartered and R-4 as required, four salvage items D3 named that were not carried, three rendered gaps that now draw a false absence over shipped contracts, and three of eighteen surfaces never rebuilt. Produced charter §3a's D5–D8. Records one refuted finding (district weather/traffic) because the failure mode — a true premise carrying a wrong conclusion — has now occurred twice in this increment. |
