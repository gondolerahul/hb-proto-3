# Increment 7 / Redesign — R-4: Wire It To The Backend

> **Round R-4**, restated 2026-07-30 by charter [§3a decisions D5, D7, D8](./00_redesign_charter.md#3a-owner-decisions--round-2-locked-2026-07-30).
> **What changed:** R-4 was chartered as three mechanical steps. Measuring the tree
> found six prerequisites first ([04_r4_readiness.md](./04_r4_readiness.md) §3).
> **D5 folds them in: one round, nine parts.**
> **Prerequisite:** [R-3c](./05_r3c_private_line.md) — the Line, so R-4 wires
> eighteen surfaces rather than fifteen.
> **Produces:** Vihara on live data, behind a login, with working certified acts.

---

## 1. The shape of the round

Nine parts. They are ordered by dependency, not by size — G comes first because
nothing measured after it is trustworthy until it lands, and W comes late because
wiring a surface that cannot handle an empty response is wiring a crash.

| Part | Name | Closes |
|---|---|---|
| **G** | **Ground** — the gates honest again | Two red gates, three missing gate scripts, no CI |
| **A** | **Access** — auth entry, session gate, logout | Prerequisite 1 |
| **N** | **Navigation** — ⌘K as the real navigator, `pushState` identity | Prerequisite 4 (**D7**) |
| **L** | **Lifecycle** — scaffold-then-hydrate, empty and failure states | Prerequisite 2 |
| **C** | **Ceremony** — step-up restored | Prerequisite 3 |
| **W** | **Wire** — the nine clean surfaces | The fixture swap proper |
| **P** | **Wrappers** — the thirteen endpoint-exists regions | §8 of the readiness assessment |
| **S** | **Stream** — the live estate | Prerequisite 6 |
| **E** | **Endpoints** — the four unsourced regions | **D8** |

**E runs in parallel with A–S**, because it is backend work with its own test
surface and two of its four items are real domain design.

## 2. Part G · Ground

*Nothing below G is measurable until G lands.*

| # | Task | Done when |
|---|---|---|
| G1 | Regenerate `vihara/tests/fixtures/*.ndjson` from `backend/scripts/export_genui_fixtures.py`, **and add a vihara-side test that parses them.** Regenerating alone leaves the gate comparing the composer to a snapshot of itself | `pytest tests/unit` green; a vitest test reads the same NDJSON |
| G2 | Fix lint. Move `src/background/hexField.ts` and `LegacyBackground.tsx` under a path the three.js allowlist names, rather than widening the allowlist to wherever the code drifted. Resolve the two `exhaustive-deps` warnings | `npm run lint` exit 0 |
| G3 | Port `scripts/gen_api.mjs` + the `openapi-typescript` devDependency; port `scripts/check_bundle_budget.mjs` and wire it into `build`, measuring **both** entries | `npm run gen:api` regenerates `schema.d.ts`; `npm run build` fails on a budget breach |
| G4 | Port `scripts/sync_tokens.mjs` (the two-copies token gate) and `axe-core` | The DS mirror cannot drift silently |
| G5 | **CI.** A workflow running, on every push: vihara `tsc` · `lint` · `vitest` · `build`+budget · `sweep`; backend `typecheck_ai` · `pytest tests/unit` · `pytest tests/parity` | A red gate cannot survive a merge again |

**G2's direction matters.** The allowlist names `renderers/world/` and
`components/world/`; the code lives in `background/`. Widening the rule to match
where the code drifted would make the rule describe the code instead of
constraining it — and this rule is the only thing standing between a tier-C phone
and a three.js download.

**G5 is the finding with the longest reach.** A red backend suite and a red lint
survived a full workstream and two review rounds. Nothing in the project runs a
gate unless a human types it.

## 3. Part A · Access

| # | Task | Done when |
|---|---|---|
| A1 | Rebuild pre-session: login, register, and the **honest password-reset absence** (the backend ships no reset endpoint; the screen says so) | Parity rows 32 and 35 close against the shipping app |
| A2 | Session gate in `main.tsx` — bootstrap refresh, then Prototype or PreSession | An unauthenticated visit lands on login, not on a crash |
| A3 | Logout in the shell | — |
| A4 | 401 handling above the client's own retry: a refresh that fails is a normal logged-out state, not an error cascade | Session expiry returns you to login with your place remembered |

**Pre-session stays conventional and unthemed beyond the brand**, per the R2
ruling. A login screen that tries to be an estate is a login screen that is slow.

**A note on inheriting a legacy session — it cannot be done.** Vihara's refresh
sends `X-Token-Delivery: cookie` and the CSRF double-submit; `auth/router.py` 403s
unless the `csrf_token` cookie exists, and only a cookie-mode login sets it. The
legacy React app never opts in. During the 30-day parallel run a user therefore
logs into each app separately. That is a consequence of VP-01, not a defect, and it
should be in the parallel-run brief rather than discovered by a pilot.

## 4. Part N · Navigation (D7)

| # | Task | Done when |
|---|---|---|
| N1 | Promote the ⌘K palette from designed-and-empty to the real navigator — all eighteen surfaces, keyboard-first, the depth ladder intact | Every surface reachable without `PrototypeNav` |
| N2 | `pushState` surface identity. A URL names a surface and, where one exists, its subject (`/tray/{id}`, `/district/{code}`) | Reload returns you where you were; a link is shareable |
| N3 | `popstate` → the depth ladder, so Back rises rather than exiting | — |
| N4 | **Delete `PrototypeNav`** and `boards/BackgroundPick.tsx` (D2 review scaffolding, its decision closed) | Sweep enumerates surfaces from the palette |

**Why URLs are not deferrable.** L8 makes a push *a tray or it does not exist*. The
service worker's `notificationclick` opens the Line at the tray — which requires a
URL that names one. Without N2 the Line's central interaction lands on the front
door, and the surface that announced something urgent makes you go find it.

## 5. Part L · Lifecycle

| # | Task | Done when |
|---|---|---|
| L1 | Fix the seven crashing index-0 initialisers (readiness §3) — derive from the collection, never assert into it | An empty response renders empty state, not a TypeError |
| L2 | Collection-level empty states, following the idiom already at `BridgesSurface.tsx:79` | Each surface has designed copy for "nothing here" |
| L3 | Failure states — a surface that cannot load says so and offers a retry | No silent blank |
| L4 | `ErrorBoundary` at the surface boundary, so one surface cannot take the shell down | — |
| L5 | **Scaffold-then-hydrate**, per D7 §3.1: layout paints immediately, data fills it. **The Glasshouse is the only surface permitted a visible loading state** | No spinner appears on the other seventeen |

**L5 is a contract, not a preference.** D7 §3.1 defines *first scaffold* as layout
on screen and explicitly not the moment data arrives. "Add a spinner" is prohibited
on seventeen of eighteen surfaces, and the Glasshouse's exception exists because a
twin run is genuinely slow and pretending otherwise would be the lie.

**On empty states and calm.** An estate with nothing in the tray and an estate that
failed to load look identical if only one of them is designed. The Study's dunning
panel was built around exactly this reading — a quiet estate must be legibly quiet
rather than ambiguously broken.

## 6. Part C · Ceremony

| # | Task | Done when |
|---|---|---|
| C1 | Rebuild `StepUpCeremony` — WebAuthn platform passkey with TOTP fallback, over `/ai/authn/*` | A T2 act prompts and completes |
| C2 | `useCertifiedAct` — the hook every certified control routes through | No surface calls a gated endpoint directly |
| C3 | Handle `step_up_required` 403 as the ceremony's *entry point*, not as an error | Tray approval, connector bind and strategy adopt all complete |
| C4 | Restore the certified set's structural goldens | The ten certified components are pinned again |
| C5 | Every certified path echoes | The echo bus sees Line and estate taps distinctly (`renderer` C vs S) |

**What is currently drawn is not a ceremony.** Six surfaces print "it will ask for
your passkey" and then mutate local state. Three of those paths will 403 the moment
they are wired; two will not, because `hireFromTemplate` forces A1 and
`certified.consent` maps to no gate. **The two that silently succeed are the
dangerous ones** — a certified control that works without a ceremony teaches the
user the ceremony is decorative.

## 7. Part W · Wire — the nine clean surfaces

Wrapper and endpoint both exist. Mechanical, and the first real proof the salvaged
client works.

| Surface | Endpoint |
|---|---|
| Still + Shell | `GET /ai/genui/estate` · `/auth/me` |
| Terrace | `GET /ai/genui/estate` |
| Tray | `GET /ai/genui/trays` · `POST /ai/approvals/{id}/respond` |
| Registry Hall | `/ai/tenant/*` |
| Standup | `GET /ai/genui/line/morning` |
| Study | `/auth/me` · `/ai/learning/preferences*` · `/credits/*` · `/ai/authn/webauthn/*` |
| Boardroom | `/ai/kpi/business` · `/ai/tenant/records` · `POST /ai/strategy/adopt` |
| Library | `/ai/documents/*` |
| Glasshouse | `/ai/twin/*` |

Also: delete `genui.fetchTrays()`, which duplicates `trays.fetchTrayList()` on the
same endpoint with a weaker type, before anything imports it.

**Three surfaces here are drawn blocked for reasons that are now false** — the
Boardroom's "take to the Glasshouse", the Talent Office's termination, and the
Tray's cost line. Those are R-5's to close (readiness §6); W must not quietly
enable them, because no client has yet exercised those endpoints and "it compiles"
is not "it works".

## 8. Part P · Wrappers

Endpoint exists, wrapper does not. Thirteen regions:

District (`fetchDistrict`, **plus a shape reconcile** — `in_1h`/`out_1h` vs the
fixture's `inPerHour`/`outPerHour`, and the backend's `clear|storm|heat-shimmer|moonlit`
weather vocabulary against a fixture that also uses `fog`, which the backend
deliberately does not emit) · Gallery ×4 (alumni, mandates, seasons, KPI history) ·
Brainstorm chat · Undercroft signals / routing / flags · Library upload + search ·
Tray pending · Glasshouse compare · Registry.

**Fix the three wrong `source` strings in `fixtures/undercroft.ts` in the same
commit** — `/ai/tenant-schema/defs`, `/ai/intelligence/routing` and `/ai/flags` are
all wrong, and one (`/ai/consent`) never existed. The Undercroft asserts in prose
that each named endpoint "answers today", which makes a wrong string a false
statement on the surface whose whole job is to be checkable.

## 9. Part S · Stream

| # | Task | Done when |
|---|---|---|
| S1 | A **fetch-based SSE reader** — the `Authorization` header rides the request | The stream authenticates with no backend change |
| S2 | Port `estate/live.ts` — a pure reducer with an injectable wire — plus `sharedStream.ts` and `useLiveEstate.ts`. One connection per app | Terrace beacons light; the tray SLA counts down |
| S3 | Reconnect with backoff; a dropped stream is *stale*, marked, never silently calm | — |

**Why fetch-based and not the native `EventSource`.** `GET /ai/genui/stream` is
guarded by header-based `get_current_user`, which a native `EventSource` cannot
satisfy — it sends no custom headers — and the refresh cookie is scoped to
`path=/api/v1/auth` so it is not sent either. There is a precedent for a
query-param token elsewhere in the codebase, and it should **not** be followed
here: it would put a bearer credential into URLs, proxy logs and `Referer` headers,
on the surface that drives T2/T3 step-up. That precedent predates VP-01 and undoes
most of what VP-01 bought. Reading SSE from `fetch` costs a few dozen lines and no
security.

Nothing is lost by not using the native protocol: replay is snapshot-on-connect,
not `Last-Event-ID`. (D5 §3 says otherwise and is stale — R-5.)

**The steward dock is deliberately out of scope.** `live.ts` carries across with no
design decisions attached; the dock is a WebSocket plus voice plus presence UI that
the new shell only gestures at. It gets its own round.

## 10. Part E · Endpoints (D8) — backend, parallel

| # | Task | Notes |
|---|---|---|
| E1 | `GET /ai/consent` over `consent_records` / `dnc_entries` / `unsubscribe_log` | Nearly free — the tables, the registry and migration `trust001` all ship behind no router. Unblocks the Bridges gate panel **and** the Undercroft consent bay |
| E2 | Surface consent state on the estate's `gatehouses` block | So a gate's consent posture is visible where the gate is |
| E3 | **Colleague charter, competencies, SLOs, probation** — the Dossier's spine | Real domain design. The charter is the colleague's terms of engagement; it is not `tenant.fetchProposals`, which is record-change signals |
| E4 | **Talent brief + past cases** | Real domain design. The Talent Office's two largest structures |
| E5 | Make `recommendation` one shape everywhere; have `tray_list`/`tray_detail` read back the persisted `TrayRecommendation` | Today REST hard-codes `null` and WS overwrites with a bare string, so a reload **permanently** loses Pragya's sentence |
| E6 | Populate `what_happened.object` | Currently hard-coded `None`, and not on the module's declared honest-nulls list — so the tray names no object to click through to |
| E7 | Seed `human_approvals`: pending approvals across checkpoints **and ≥5 approved-with-usage per checkpoint** | Without the second, `paths[].cost` — the field D5 §4.1 argued hardest about — is `None` in every demo. The dev DB has zero rows |
| E8 | Add the deployment origin to CORS, or commit to a same-origin Apache path-mount | Dev works only because the Vite proxy collapses origins. `SameSite=Strict` on the refresh cookie already assumes same-site, so cross-origin means **weakening VP-01**, not adjusting config |

**E3 and E4 are the honest cost of D8.** They are not missing HTTP surfaces over
shipped tables; they are domain modelling that Increment 7 acquires because the
alternative was shipping invented data that looks live.

## 10a. Build notes — parts G · A · N · C · P · S and E-small ✅ BUILT 2026-07-30

**Remaining: parts L (lifecycle) and W (wire), and E3/E4** — the colleague charter
and the talent brief, which D8 accepted as real domain design.

**Gates:** tsc · lint · **vitest 216** (from 65) · build clean, index 159.4 KB gz ·
line 87.9 KB gz, both of 220 · `gen:api` idempotent · tokens match · backend
**2265** unit + 2 parity · typecheck **347** files.

**Six deltas worth reading.**

**1. A real auth defect, found by the sweep and not by any test.** Cookie mode set
*both* cookies with `path=/api/v1/auth`. The refresh token belongs there — it is a
credential and pinning it is most of what cookie mode buys. **The CSRF cookie does
not.** It is a same-origin *proof* that the client must be able to **read**
(`csrfFromCookie`), which is why it is deliberately not HttpOnly — and a cookie
scoped to `/api/v1/auth` is invisible to `document.cookie` on a page served from
`/`. So every refresh went out with no `X-CSRF-Token`, earned a 403, and surfaced
as "your session ended" **on every reload**. No deep link into the estate worked.

The frontend suite could not catch it: its tests mock the API client, so the
cookie → header → refresh path had no coverage on either side of the wire. It is
now pinned in `test_token_delivery.py`, where the cookie is actually set, and
mutation-tested. Verified against a real RFC 6265 cookie jar: `csrf_token` is
visible at `/`, and `refresh_token` still is not.

*The lesson is the one this increment keeps teaching: **a mock at the seam is a
hole in the gate.** The two ends were each individually correct and disagreed
about the middle.*

**2. Widening the CSRF cookie costs nothing.** Worth stating because it looks like
a loosening. What protects a double-submit is the **same-origin policy**, never
the path — an attacker on another origin cannot read the cookie to echo it, and
`SameSite=Strict` means it is not sent cross-site at all.

**3. The §1.5 motion gate existed and reached one directory.** It walked
`src/components/certified/` only, and its regex read just the *first* property of
a comma-separated list — so `transition: background …, box-shadow …` passed on the
strength of its first clause. Rewritten as `tests/motion.test.ts` over **every**
stylesheet, every clause, and every `@keyframes` body.

Running it for the first time found the rule broken in **22 files, including the
shared design system the other twenty-one inherit from**. Two new violations this
round were fixed properly (both now fade an overlay's opacity). The rest is frozen
in a per-property debt list that **cannot grow**, with a fourth test that fails if
a forgiven entry is fixed and left listed. **`width` in `standup.css` is the one
to fix first** — every other entry is paint-only; `width` triggers layout on every
frame and §1.5 names it explicitly. Burning the list down is R-5's.

**4. The certified boundary is real where it can be, and currently vacuous.**
`useCertifiedAct` exists, `RunnableCertifiedType` makes "schedule a ceremony as
the act it guards" a compile error, and three source-scan tests forbid a gated
route string outside the certified layer. But **all three pass vacuously today**:
no surface imports the hook yet, because wiring is part W. Recorded rather than
claimed — the guards have never been exercised against a real consumer, and they
need a non-emptiness assertion when W lands.

**5. `GET /ai/consent` is company-scoped by construction.** There is no
`company_id` parameter on the signature at all; it is taken from the session, and
every query filters on it. Passing one is silently ignored. That is the shape to
copy — an unscoped read here would be a cross-tenant disclosure on a surface whose
whole subject is who may be contacted.

**6. E8 resolved to same-origin, not to wider CORS.** The refresh cookie is
`SameSite=Strict`, so a genuinely cross-origin deployment means **weakening
VP-01**, not adjusting config. Dev keeps the Vite proxy; production is an Apache
path-mount.

**Honest limits.** The browser round-trip has not been re-run since the cookie fix
— it needs seeded credentials the sweep documents nowhere, which is itself a gap
worth closing. The wire-level proof above is the cookie jar and the unit test, not
a live login. And the surfaces still read `src/fixtures/`: parts L and W are what
change that.

## 10b. Build notes — parts L and E3/E4 ✅ BUILT 2026-07-30

**Remaining in R-4: part W only** — the surfaces still read `src/fixtures/`.

**Gates:** tsc · lint · **vitest 267** · build clean, index 162.1 · line 89.6 KB gz
of 220 each · `gen:api` idempotent and carrying all three new endpoints · backend
**2327** unit + 2 parity · typecheck **352** files.

**What E3 and E4 refused to invent, which is the point of them.**

D8 said build these rather than render a gap. It did not license inventing data,
and the read models are unusually disciplined about the difference. Each ships an
`absent` list travelling *with* the payload — so the surface is **told** where to
render an absence rather than discovering an empty field.

* **There is no SLO target anywhere on the platform**, so no dial can be drawn. The *readings* exist and are what the demotion sweep acts on, so they ship as `reliability` — a name that promises no target — with `demotion_bar` named as itself. `failure_rate` is `null` when there are no runs, never `0.0`, because zero reads as "never fails".
* **A competency's note is omitted when the registry cannot resolve the tool.** The templates grant `send_email`; the registered tool is `email_send`. A lesser read model would have printed a description for a tool that cannot be called.
* **Authority asks `evaluate_policy` verbatim** rather than re-deriving the §9.3 matrix. A panel that computes its own answer eventually disagrees with the control that actually refuses the act, and the tenant believes the panel. Where the gate's real answer depends on an amount the dossier does not have, that is surfaced as `conditional_on_amount` rather than flattened to "autonomous".
* Two constants were made public instead of duplicated (`FAILED_STATUSES`, `ACTIVE_RUN_STATUSES`). A dossier that counted failures differently from the sweep that removes a level would make every demotion look arbitrary.

**Three defects the verification pass caught, all fixed.**

**1. The backend suite was red and `gen:api` was a false green.** Three endpoints
existed in the live app and were never exported, so `openapi.json` described an
app that no longer existed — and `gen:api` regenerated `schema.d.ts` from that
stale file, staying perfectly self-consistent while the frontend had no types for
any of them. **A generator is only as honest as its input**, and this is why the
contract gate lives on the backend where the live app can be compared.

**2. `Dossier.decisions` acquired neither a value nor a declared absence** — the
single field unaccounted for in either direction, in a module whose whole rule is
that an unanswerable field must be named. Now declared, with the real reason:
`GET /ai/executions` takes **no parameters at all** and returns every root
execution the company ever ran, so a dossier cannot ask for its own colleague's.
Naming the decisions needs a filterable execution read first.

**3. `SurfaceBoundary` was built, correct, tested — and mounted nowhere.** A
TypeError in any of the eighteen rooms still took the whole tree down, which is
exactly the failure its own docstring described. **A component that protects
nothing passes every test written about the component.** It is now mounted inside
`Shell` (so a room that throws loses the room, never the rail and the way out),
separately at depth 0 (which renders no Shell to survive), and inside the Line's
tab body (which has no palette, no depth ladder, and on an installed PWA no
address bar — a white screen there has no way out at all). Verified by mutation
in both directions: with the boundary the siblings survive; without it they do not.

**And a fourth, found while fixing the third.** The test written to pin the mount
matched only `surface={…}`, so mutating a mount to `surface="a room"` matched
*nothing* and the loop passed over an empty set — a vacuous test reporting the
property it was not checking. It now matches both forms and asserts it examined
at least three mounts. *This is the second vacuous test this increment (the
certified guards were the first). A source-scan test needs a non-emptiness
assertion or it grades its own homework.*

**Honest limits.** `useResource` and `Scaffold` are unwired — nothing fetches
until part W, so the Glasshouse's permitted loading state has never been
exercised. Roughly a dozen collections still need bespoke empty copy; the most
consequential is **Registry Hall, which prints `₹0` for an empty register** —
the exact bug `tray_cost.test.tsx` exists to prevent, one surface over. And
`vh-skeleton`'s ground is a 6/255 delta on the raw canvas, so part W's scaffolds
must draw their plates first and put bars inside them.

## 10c. Build notes — part W ✅ BUILT 2026-07-31. **R-4 is complete.**

All eighteen surfaces plus the shell read the API. **No file under `src/surfaces/`,
`src/line/` or `src/shell/` imports `src/fixtures/`** — the fixtures stay on disk
and are read only by tests.

**Gates:** tsc · lint · **vitest 383** (five runs, including one under 2× CPU
oversubscription) · build clean, index 183.7 · line 115.9 KB gz of 220 each ·
`gen:api` no drift · tokens match · backend **2327** unit + 2 parity ·
typecheck 352.

**The defect class this round kept producing: a check satisfied by the thing it
meant to exclude.**

* `tray_cost` and the Line's C4 identity test both settled on `.tr-list`
  appearing — and **the Tray's scaffold draws its ghost cards inside a `.tr-list`
  of its own**. The condition meant to wait past the loading state was satisfied
  *by* the loading state. It passed under light load and failed under heavy,
  which is why it read as a flake rather than as a wrong assertion. Both now
  settle on `[data-lifecycle="scaffold"]` being gone.
* `w5_surfaces` asserted `.uc-bay-count` was absent — **a class no code path
  renders**, surviving only as a dead rule in `undercroft.css`. It could not
  fail. The rule is deleted and the assertion now reads the rail that exists: no
  entry may contain a digit. Mutation-tested.
* The Talent Office's lifecycle case mocked `[]` where E4's reads answer an
  object carrying its own `absent` list, so `Office` crashed on
  `briefs.briefs.length`. **A mock of the wrong shape tests the surface against a
  response the server cannot send.**

That is four in one increment, counting the certified guards' vacuity. The
common shape: *the assertion names the property and measures something the
property shares with its opposite.* A settle condition, an absent class, a mock's
shape, an empty corpus — all four looked like coverage.

**Five residuals the verification pass found, all fixed.**

1. **The shell still rendered fixture data as chrome on every desk surface** — a
   hardcoded company name and a hardcoded "2 waiting". It was outside every
   agent's ownership, so eighteen wired surfaces sat under a rail that was not.
   Now on `/auth/me` and the live estate, and it renders **nothing** until each
   answers: a placeholder company name on the rail of every room is a lie the
   owner reads all day. `stillLine` is imported from the surface that owns it, so
   the rail and depth 0 cannot drift.
2. **`PocketDesk` printed `Signals an hour = 0` for an estate with no districts.**
   `reduce` over an empty list answers 0 for a quiet hour *and* for an estate
   nobody has built — and the second is every tenant's first fortnight.
   `StillSurface` reads the same snapshot and says so in words.
3. **`HallSurface.tsx` contained two raw NUL bytes** as sentinels. Not a runtime
   bug — but git called the file binary, so **the largest file in the round could
   not be diffed or reviewed**, and `grep` exited silently without matching
   anything in it. Every text audit of that file passed by not reading it. Now
   ` ` escapes: same value, reviewable file.
4. The dead `.uc-bay-count` rule (above).
5. A raw hex `#2a1d08` in two seals — which is exactly `--on-accent`. Now
   `currentColor` plus the token, since a presentation attribute cannot hold a
   `var()`.

**What the wiring refused to draw.** Four instruments were deleted rather than
rescaled — the district's KPI meter, the treasury's reserve seam, the Dossier's
three SLO arcs, the Pocket Desk's target meter. Each was drawn against something
the platform does not have. **No `KpiDefinition` declares a target or a
direction**, which is one gap with five separate visible consequences: no dial on
reliability, no proportion on a district gauge, no "six days better", and `fog`
off the estate's weather vocabulary entirely. Each deletion carries its reason
where the rule used to be, so it is not re-added by someone who reads the gap as
an omission.

**Bridges got sharper, not softer.** `credentials_expire_at` is not merely
unpopulated — `_binding_view` does not project it at all, so the block now says
both: nobody has written one, *and* the endpoint a reader would check does not
carry it. No positive lamp can appear in an unknown-expiry block, held by test.

**The certified boundary's guards are no longer vacuous.** `TraySurface`,
`BoardroomSurface` and `BridgesSurface` are real consumers, and the verification
pass broke the tree four ways — a direct gated call, a route literal outside
`src/api`, a deep import past the barrel, and renaming every call site — and all
four failed as intended, including the non-emptiness backstop.

**Honest limits.** **Nothing has been run against a live backend.** Every claim
is the type checker, 383 unit tests and readings of the backend source — not a
login. The sweep needs seeded credentials documented nowhere, which is now the
single largest blocker to proving any of this works. One `w6_line` failure was
seen once during a concurrent run and has not reproduced in five subsequent runs
including under load; it is recorded rather than called fixed. `useResource`'s
Glasshouse loading exemption is still unexercised.

## 10d. The first live proof — ✅ 2026-07-31. **`all 18 surfaces clean`.**

Every round before this one ended with the same honest limit: *nothing has been
run against a live backend*. That is now closed, and closing it found three
defects that 384 green unit tests could not.

**The blocker was a missing account, so the account is now a script.**
`sweep.mjs` needs credentials and aborts loudly without them — correctly. But
*which* account was documented nowhere, so the sweep has been unrunnable since
the app went behind a session gate, and with it every browser-level proof this
increment could have had. `backend/scripts/ensure_sweep_user.py` mints one
on demand and refuses to run against a non-local database, because a password in
a document is a password somebody eventually creates in production. Its first
version used `sweep@vihara.local` and could never log in: `.local` is a reserved
TLD and `EmailStr` refuses it — a 422 from the validator, not a 401.

**Defect 1 — the SSE stream had no lifetime, and it froze the API.**
`stream_events` ran `while True` with a `max_ticks` bound that only tests passed.
uvicorn's graceful shutdown waits for open connections, so **once any browser had
the app open, `--reload` — the command `start_services.sh` actually runs — hung
on "Waiting for connections to close" forever**, and the backend stopped
answering while still holding its port. I hit this by editing a file. It is
bounded at ten minutes now; the client already owns a reconnect ladder with
jitter, so a close is a path it exercises rather than an error it reports, and
replay is snapshot-on-connect so nothing is lost across the seam.

**Defect 2 — the sweep was measuring the scaffold.** It reported **EMPTY on
fourteen surfaces that render perfectly in a browser**. Before part W the
surfaces read module constants, so their content was in the first paint and a
fixed dwell sufficed; now every one paints a scaffold and fills it a round-trip
later. The harness now settles on `[data-lifecycle="scaffold"]` being gone —
*the same lesson as the unit tests' settle conditions, one level up, and the
fifth instance of this shape in the increment.*

**Defect 3 — the Line had no session gate at all.** `line/main.tsx` mounted
`LineApp` unconditionally, so its default tab fired reads with **no access
token**: a 401 storm on The Line · Morning. Part A gave the estate a gate and the
second entry never got one, because nothing in a mocked unit test can see it.
`Session` now takes its destination as `children` — `main.tsx` hands it the
estate, `line/main.tsx` hands it the Line — which also keeps the estate's fifteen
surfaces out of the Line's budget, the entire reason the Line is a second HTML
entry. Cost: **1.8 KB gz**, 115.9 → 117.7 of 220.

**Measured, live:**

* `all 18 surfaces clean` — three consecutive runs, against a real backend and a real session.
* The cookie fix confirmed **on the wire**: `csrf_token … Path=/` beside `refresh_token … Path=/api/v1/auth`. The asymmetry is real, not just unit-tested.
* The Shell's rail reads the tenant's actual name.
* tsc · lint · **vitest 384** · build clean, index 183.7 · line 117.7 KB gz · `gen:api` no drift · tokens match · backend **2329** unit + 2 parity · typecheck 352.

**What this still does not prove.** A real device, a real phone call, a push
arriving as a tray, a fingerprint approving a payment — all owner-side, all in
[15a_launch_protocols.md](../15a_launch_protocols.md). And the sweep walks a
tenant with almost no data: it proves every surface *loads, hydrates and renders
without error*, not that a busy estate looks right.

## 11. Gates

R-4 is complete when:

* `npm run lint` · `tsc` · `vitest` · `build`+budget (both entries) · `sweep` **all green, in CI**.
* `pytest tests/unit` green — including the cross-language wire gate.
* `npm run gen:api` runs, and `schema.d.ts` is regenerated from a live export.
* A real user can log in, reach all eighteen surfaces by ⌘K and by URL, approve a tray through a passkey ceremony, and watch a beacon light without reloading.
* No surface reads `src/fixtures/` except in tests.
* `PrototypeNav` is gone.

## 12. What R-4 does not do

* **The manifest renderer stays dormant.** 48 registry entries, no implementations. Rebuilding `RenderManifest` plus four component modules would *replace* the hand-authored surfaces D4 said carry across untouched. The Undercroft's manifest **inspector** is wired (a read of the log), which makes the layer observable without committing to it.
* **The steward dock** — WebSocket, voice, presence, narration. Its own round.
* **Onboarding staging + `world.ghost`.** Parity row 4 claims onboarding is "retired in fact" because depth 0 was unreachable before stage 9; that gate was not rebuilt, so depth 0 is currently everyone's start screen and the claim is false. R-5 decides it.
* **The three stale rendered gaps.** R-5.
* **Owner-side legs** — the device matrix, the live call, the parallel run. [15a_launch_protocols.md](../15a_launch_protocols.md).

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-30 | v1.0 — R-4 restated at its real size under charter D5: nine parts, not three steps. **G** first because two gates were red and no CI runs any of them — the finding with the longest reach. **N** implements D7 and records why URLs are not deferrable (L8 makes a push a tray or nothing, and a push that cannot deep-link drops you at the front door). **S** rules out the query-param token precedent for the SSE stream: it would put a bearer credential in URLs on the surface that drives step-up, undoing most of what VP-01 bought. **E** implements D8 and names its honest cost — two of the four unsourced regions are new domain design, not missing routers. Records that the two certified paths which *silently succeed* today are more dangerous than the three that will 403. |
