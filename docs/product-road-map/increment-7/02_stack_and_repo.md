# Increment 7 / Phase A — D1: Stack & Repo Ratification

> **Deliverable D1** of [01_phase_a_overview.md](./01_phase_a_overview.md). Closes charter open question 1; records decisions 4, 5 and 6 as an engineering specification.
> **Status:** ✅ **BUILT 2026-07-29 — SUB (`inc7/sub`, T1–T8) scaffolded and shipped the substrate.** Build notes + deltas: **§8**. G0's exit is met at the test level; the live browser walk is the owner's.

---

## 1. Where Vihara lives

```
hb-proto-3/
├── backend/          # unchanged
├── frontend/         # the 59 legacy screens — unchanged, runs until cutover
├── vihara/           # ← new, this increment
└── docs/
```

`vihara/` is a **separate application** — its own `package.json`, `tsconfig.json`, `vite.config.ts`, `node_modules`, build output, CI job and deploy target. It shares one git history with the roadmap docs and with the backend whose contracts it consumes, so a backend API change and its Vihara consumer land in **one commit**. That atomicity is the whole reason this is a directory rather than a second repository (charter decision 4).

**What it does not share with `frontend/`:** nothing. No import crosses the boundary in either direction — not a service, not a component, not a type. Auth, session handling and the API client are rebuilt (decision 4, cost accepted). A lint rule enforces it, because a single convenience import would silently make the two apps one app and the boundary would be gone before anyone noticed:

```
no-restricted-imports: paths matching ../frontend/** or @/legacy/** → error
```

**Why enforce a boundary nobody intends to cross?** The same reason the LEARN⇸SEGA import boundary is a build failure rather than a convention: the first violation is always reasonable and always cheap, and by the third one the property is gone.

## 2. The stack (charter decision 5 — spec §12's recommendation, ratified)

| Layer | Choice | Note |
|---|---|---|
| Language | **TypeScript**, `strict` | Same strictness as `frontend/tsconfig.json` **plus `noUncheckedIndexedAccess`** — manifests are dynamic data arriving over the wire, and indexing them is exactly where an unchecked `undefined` gets rendered as text |
| Build | **Vite 5** + `@vitejs/plugin-react` | Same toolchain as `frontend/`, so the VM needs nothing new (Node v20.20.0, npm 10.8.2 confirmed present) |
| S + C renderers | **React 18** | Sheet (DOM) and Card (compact DOM) |
| W renderer | **Three.js** via `@react-three/fiber` + `@react-three/drei` | Already proven present in this repo's dependency set |
| Manifest validation | **Zod** | The manifest contract (D4) is validated **at the client boundary**, not trusted. A manifest is generated content that chooses UI — D3's certified-set boundary is only a real invariant if the client refuses a manifest that violates it |
| Motion | **Framer Motion** | Calm easing only; see the art bible's motion section |
| Icons | **Lucide** (`lucide-react`) | Mandated by the brand system §4 |
| Charts | **Recharts** | The `chart-set` primitive; same library the legacy KPI dashboard uses, so the visual translation is a re-theme rather than a re-derivation |
| HTTP | **Axios** | Contract identical to the shipped one (bearer access token, `/auth/refresh` on 401) — see §5 |
| Tests | **Vitest** + `@testing-library/react` + `jsdom` | New to this repo (§4) |

**No state-management library.** React context plus the live-stream reducer is enough: Vihara's client state is a manifest, a viewport, a density scalar and a stream. Reaching for Redux/Zustand here would add a layer whose job the manifest already does.

### 2.1 The Line is not a second codebase

Charter decision 6 makes the Private Line an **installable PWA**, which collapses spec §12's "one shared design-token + component package consumed by all three renderers **and the Line app**" into something simpler than the spec anticipated: the Line *is* the Card renderer, served from the same build at a different entry, with a manifest and a service worker. The token package is therefore a **module inside `vihara/`** (`src/tokens/`), not a published package.

The decisive property is that **T2 step-up already works there**: `iauth001` ships platform-built WebAuthn, and platform authenticators are available to installed PWAs — so the biometric certified card of spec §8 needs no native shell.

Stated ceilings, both real: on iOS, push exists only after the user installs the PWA (charter decision 7), and an uninstalled iOS visitor gets the thread without notifications rather than an error.

## 3. Directory shape

```
vihara/
├── package.json  tsconfig.json  vite.config.ts  index.html  line.html
├── public/                      # manifest.webmanifest, service worker, brand assets
└── src/
    ├── tokens/                  # the brand system as TS + CSS custom properties (D2)
    ├── manifest/                # Zod schemas (D4), the client-side registry (D3), the resolver
    ├── renderers/
    │   ├── world/               # W — react-three-fiber
    │   ├── sheet/               # S — DOM
    │   └── card/                # C — compact DOM; also the Line
    ├── components/
    │   ├── primitive/  certified/  world/  narrative/   # §9.2's four classes, one dir each
    ├── estate/                  # the read-model client + live stream (D5)
    ├── pragya/                  # the event channel client (D5)
    ├── echo/                    # the L10 echo bus client (D5)
    ├── api/                     # client, auth, generated types (§5)
    └── app/                     # routing, depth ladder, density
```

**The four component classes are four directories.** §9.2's classes carry different rules — certified components may not take generative props (L5), world components are the only ones allowed to import Three.js — and a directory boundary is the cheapest place to make a lint rule bite.

## 4. Gates

`frontend/` has **no test runner at all** — no vitest dependency, no `test` script — which is why VG-05's frontend half rests on the build gate alone (an honest limit recorded 2026-07-25). Vihara fixes that **for itself**; retrofitting the legacy app is explicitly not in scope, since those screens are on a retirement path.

```bash
cd vihara
npm run typecheck     # tsc --noEmit
npm run lint          # eslint, incl. the boundary + class rules of §1 and §3
npm run test          # vitest run — unit + golden renders
npm run build         # vite build
```

### 4.1 The golden renders (L5)

Spec §9.2 requires the certified set "golden-rendered in CI". What that means concretely here:

* **A DOM-structure snapshot per certified component**, per density, checked in.
* **A cross-context assertion** — the same certified manifest rendered through the Sheet renderer, the Card renderer and the Line entry produces the **same certified subtree**. That is what L5's "pixel-identical in trays, Line cards, and sheets" reduces to in a test that does not need a browser.
* **A refusal test per certified component**: a manifest carrying a generative prop must be *rejected*, not rendered. Written the way this repo writes security tests — mutation-tested, one control at a time, each breaking only its own test. A checker never observed to fail is a function that returns `True`.

**Not pixel goldens.** Screenshot diffing needs a browser in CI and produces failures that are usually font rendering. The structural snapshot plus the cross-context assertion catches the failure L5 actually fears — a certified surface *differing between contexts* — and catches it without a browser. If a real pixel regression escapes this, that is the moment to add Playwright, not before.

## 5. Keeping two API clients honest

Two clients against one backend drift. The mechanism, not a promise:

1. `npm run gen:api` runs `openapi-typescript` against the backend's `/openapi.json` into `src/api/schema.d.ts`, **checked in**.
2. A CI step regenerates and fails on a diff — so a backend contract change that Vihara has not absorbed is a red build in the same commit range, not a runtime 422 three weeks later.

Vihara's auth **contract** is identical to the shipped one — bearer access token, refresh on 401 — because it talks to the same endpoints. Only the code is new.

### VP-01 · Tokens in `localStorage`, in an app whose whole point is certified actions

`frontend/src/services/api.client.ts` keeps both the access and refresh token in `localStorage`. Copying that into Vihara would be the path of least resistance and is worth naming before it happens by default: Vihara renders certified surfaces and drives T2/T3 step-up, so an XSS on it is worth materially more than an XSS on a settings page — and a manifest layer that renders **generated** content is a larger injection surface than the legacy app has (this is VG-23's point, arriving early).

**Not decided here** — it needs a backend change (cookie issuance, CSRF) and therefore belongs to D5 with a costed option. Recorded now so that G0 does not settle it by copying.

## 6. Running and deploying

| | Legacy | Vihara |
|---|---|---|
| Dev port | 3000 | **4044** *(owner decision 2026-07-29; was 3001 in v1.0)* |
| Vhost | `app.hirebuddha.com` → `:3000` | **`vihara.hirebuddha.com`** → `:4044` (dev) / static build (prod) |
| Prod shape | Apache `ProxyPass` | Apache serving the built bundle; **HTTPS required** — a service worker and Web Push do not exist without it |

Both run **in parallel**, which is not a convenience: spec §12 makes a **30-day parallel run with pilot tenants** a cutover criterion, so two live surfaces against one backend is the designed end state of this increment, not a transitional mess.

**Cutover** is then a vhost change, not a migration: `app.hirebuddha.com` starts serving Vihara, and the legacy app keeps a hostname of its own for the partner and platform-admin consoles that §14.2 ratified as staying on legacy React. Those consoles are **out of scope, not retired** — the distinction D8's parity register exists to keep honest (VR-10).

`start_services.sh` gains a sixth step for Vihara's dev server, guarded by the same port check the others use.

## 7. What this deliberately does not decide

* **The scaffold itself** — no directory is created and no dependency installed in Phase A.
* **VP-01** — token storage, deferred to D5 with a costed option.
* **Workstream decomposition** — how G0–G6 split into branches is written after Phase A exits (overview §5).

---

## 8. Build notes — SUB, 2026-07-29 (T1–T8 on `inc7/sub`)

Eight tasks, a commit per task (T1+T2 shared one — the build needs the
tokens). Final measures: **117 vitest** (7 files) including **40 structural
goldens** · `tsc --noEmit` strict with `noUncheckedIndexedAccess` · eslint
with both boundary rules · **shell 84.7 KB gz against the 220 KB hard gate**,
world chunk 0 (three.js is not yet a dependency) · backend suite **2132
unit** (+5: the OpenAPI drift gate and the four wire-fixture gates).

### 8.1 What shipped

`vihara/` — scaffold on **port 4044** · the brand tokens mirrored
byte-for-byte with a sync gate · the client manifest layer (registry
resolver, Zod wire schemas, identity-fixed fill merge, the D4 §7 refusal
ladder) · the API client (in-memory access token, cookie-mode refresh with
CSRF echo, a storage pin over all of `src/`) · the Sheet/Card region engine
with the v1 primitives + `still-line` · **the ten certified components**,
golden-rendered with the cross-context assertion and two mutation refusals
each · pre-session screens + the app-owned shell + the Still Surface round
trip. `start_services.sh` gained its Vihara step.

### 8.2 Deltas worth keeping

1. **The wire contract is pinned cross-language.** Beyond §5's `gen:api`
   types, the backend captures its composer's exact NDJSON into
   `vihara/tests/fixtures/` (gate-tested against drift on the backend side)
   and the client suite parses those real bytes through its own ladder,
   asserting zero placeholders. If either end of D4 drifts, one suite goes
   red in the same commit range.
2. **The OpenAPI drift gate is a backend unit test**, not an npm CI step —
   regenerating needs the backend anyway, and a failing test that names the
   two regeneration commands beats a red pipeline step nobody can run
   locally.
3. **Password reset is a named absence** on the pre-session screen: the
   backend ships no reset endpoint (only email verification), so the screen
   says "ask your administrator" instead of pretending. The endpoint
   belongs to DRIVER's Study.
4. **three.js is deliberately not installed yet.** The W renderer is a
   stub that hands off to its L9 sheet; the `manualChunks` quarantine and
   the eslint confinement rule are already in place, so WORLD adds the
   dependency into a cage that predates it.
5. **The consent asymmetry is rendered, not just registered** (D3 §3.4):
   `certified.consent` with `direction: grant` wears the ceremony frame;
   `revoke` renders deliberately plain — pinned by test.

### 8.3 Honest limits

Registered-but-unimplemented components (`register`, `record-sheet`,
`chart-set`, `kanban`, …) render **named placeholders** — visible, and
exactly the list DRIVER owes. Certified components render their decisions
but do not yet drive their gates (the `/respond` wiring is DRIVER's; the
step-up ceremony is STEWARD's). There is **no SSE client yet** — the stream's
first consumer is WORLD's territory, so the EventSource wrapper lands there.
The Line entry (`line.html`) is LINE's first task. And the G0 demo is proven
by tests and captured wire fixtures, not by a browser walk — both dev
servers exist (`./start_services.sh`), and the walk is the owner's to take.

## Change Log

| Date | Change |
|---|---|
| 2026-07-29 | v1.2 — **BUILT.** SUB T1–T8 shipped the substrate (§8 build notes): the app on 4044, tokens mirrored with a sync gate, the client manifest layer with the refusal ladder, the memory-only-token API client, the S/C region engine, the certified set with 40 goldens + cross-context + per-component mutation refusals, pre-session, and the Still Surface round trip — proven cross-language by captured wire fixtures. Shell 84.7 KB gz of the 220 budget. |
| 2026-07-29 | v1.1 — **Vihara's dev port is 4044** (owner decision), replacing v1.0's 3001; the §6 table updated in place. SUB's scaffold and the `start_services.sh` step must use 4044. |
| 2026-07-28 | v1.0 — stack and repo ratified. `vihara/` as a separate app in one repo, with a lint-enforced import boundary (a convenience import is how a boundary dies). The Line-as-PWA collapses spec §12's shared token *package* into a module, because platform WebAuthn already serves an installed PWA. Golden renders specified as structural snapshots plus a cross-context assertion rather than pixel diffs, with the reason stated. Raised **VP-01**: `localStorage` tokens are a worse trade in an app that renders generated UI and drives step-up than in the app that shipped them. |
