# Increment 7 / Phase B — The Workstream Decomposition

> **Status:** ✍️ written 2026-07-29, the day Phase A exited (R1 + R2 passed). This is the artifact [01_phase_a_overview.md](./01_phase_a_overview.md) §5 deliberately deferred: the split of G0–G6 into named workstreams with branches, sized against the Phase-A **contracts** (D1–D8) rather than against the spec's prose.
> **Follows the repo rhythm:** branch per workstream (`inc7/<ws>`), build task-by-task, gates green throughout, a §Build-notes delta log added on merge, maturity tags flipped.
> **Read first:** [02 stack](./02_stack_and_repo.md) · [04 registry](./04_component_registry.md) · [05 manifest](./05_manifest_contract.md) · [06 backend contracts](./06_backend_api_contracts.md) · [07 wireframes](./07_surface_wireframes.md) · [08 device matrix](./08_device_matrix.md).

---

## 1. The shape, and why it is eight workstreams and not seven gates

The spec's G0–G6 are **proof points**, not units of work: G0's "substrate stands" spans the backend and the new app, and G2 alone contains nine surfaces. A workstream needs one branch, one build-notes log and one merge — so the decomposition cuts along *what is built where*, and each gate becomes the **exit demo** of the workstream that completes it.

| WS | Name | Branch | Builds | Exits |
|---|---|---|---|---|
| 1 | **SEAM** ✅ **BUILT 2026-07-29** | `inc7/seam` | `backend/src/ai/genui/` — every D5 endpoint, the manifest service, migration `genui001`, VP-01. Build notes: [06](./06_backend_api_contracts.md) §12 | G0's backend half |
| 2 | **SUB** ✅ **BUILT 2026-07-29** | `inc7/sub` | The `vihara/` app: scaffold, tokens, registry + Zod manifest, renderer skeletons, API client + auth, pre-session screens, certified set + goldens, CI gates. Build notes: [02](./02_stack_and_repo.md) §8 | **G0** |
| 3 | **WORLD** ✅ **BUILT 2026-07-29** *(G1 exit: three owner-side items — [08](./08_device_matrix.md) §9.3)* | `inc7/world` | The walkable estate: territory + weather + traffic + beacons over the estate model and stream, day–night as luminance, tier probe + demotion, seals, L9 toggle. Build notes: [08](./08_device_matrix.md) §9 | **G1** |
| 4 | **DRIVER** | `inc7/driver` | Trays · Registry Halls · dossiers · Standup · Boardroom · Talent Office · Undercroft · Library · Gallery · **The Study** | **G2** |
| 5 | **STEWARD** | `inc7/steward` | Pragya present: the WS channel client, presence/focus/narration, materialize, cross-device session, T2/T3 ceremonies, voice | **G3** |
| 6 | **LINE** | `inc7/line` | The pocket: PWA + service worker, thread, Morning Story, Pocket Desk, biometric certified cards, push client, WhatsApp read-mirror, **its backend (VG-20)** | **G4** |
| 7 | **GLASS** | `inc7/glass` | The Glasshouse: **wire TWIN's scenario runner end-to-end (backend)**, then mirror, levers, four honesty grades, Scenario Shelf, divergence ribbon, promotion into SEGA/EVX | **G5** |
| 8 | **POLISH** | `inc7/polish` | Onboarding-as-world-building, zero-training test, WCAG 2.2 AA audit, p75 performance floor, parity reckoning, parallel-run start | **G6** |

**Order:** SEAM → SUB → WORLD → DRIVER → STEWARD, with **LINE parallelisable after SUB** (spec §12: "G4 can proceed in parallel from G0") and **GLASS after DRIVER** (its surfaces reuse DRIVER's sheet grammar; its backend half may start any time after SEAM). POLISH is last by definition. SEAM and SUB overlap deliberately: SUB's scaffold needs nothing from SEAM, and the first **atomic contract+consumer commit** (the repo's Inc-4 discipline) is the registry — authored in `vihara/`, served by SEAM, checked identical by CI (D3 §7).

## 2. SEAM — the backend seams (D5 made real)

**Everything Vihara reads or writes that the platform does not have.** One new package `ai/genui/` on the strict-typing allowlist; router at `/api/v1/ai/genui`; **no domain logic** — every endpoint is a projection over shipped services (the TRUST/STRAT shape: policy in the owning package, projection at a thin seam).

| T | Task | Contract |
|---|---|---|
| T1 | Package scaffold · allowlist · `GET /genui/registry` (ETag, long-cache) · the CI authored-vs-served registry diff gate | D3 §7 |
| T2 | The manifest service: composition validated against the registry before emit · intent-shape cache (Redis, 15min, the D4 §5 key) · two-part streamed response · the D4 §7 refusal ladder · **taint: an `external_unverified` composition may not emit `certified.*`** (VG-23) · `CostAttribution.MANIFEST_GENERATION`, **tenant-initiated** | D4 · D5 §10–11 |
| T3 | The estate read model: `GET /genui/estate` + `/estate/district/{code}` — company from session, never a param; **weather projected on read, never stored** | D5 §2 (VG-02) |
| T4 | The live stream: `GET /genui/stream` SSE — scoped at connect, aggregated server-side, sampled events drop / beacons+trays replay from `Last-Event-ID` | D5 §3 (VG-03) |
| T5 | The tray composer: `GET /genui/trays` — the five-field §6.1 order; `paths[].cost: null` admitted honestly, never invented | D5 §4 (VG-04) |
| T6 | The echo bus: `POST /genui/echo` · `ui_echoes` table, 90-day reaper **in the producer's own job** · fan to the Pragya channel | D5 §6 (VG-06) |
| T7 | Push: `POST·DELETE /genui/push/subscriptions` · VAPID sender in `genui/push.py` imported by **exactly one module**, enforced by an import-boundary test verified to fail on an injected violation | D5 §7 (VG-19) |
| T8 | Pragya's event channel: `/ai/pragya/channel` WS — attaches to the existing `account_manager_sessions` row; **never elevates**; only Pragya writes the client leg, by construction | D5 §5 (VG-07) |
| T9 | **VP-01**: refresh token as `HttpOnly; Secure; SameSite=Strict` cookie behind `X-Token-Delivery: cookie`, CSRF double-submit on refresh; **legacy header path untouched** | D5 §9 |
| T10 | Migration **`genui001`** (`ui_echoes`, `push_subscriptions`) off `iauth002` · integration suite · **`tests/parity` stays 16 green** (the B13 canary for T2's new attribution) | repo convention |

**Honest scope limits, stated now:** the manifest *composer* ships heuristic-first (intent-shape → composition rules derived from D6's layouts); an LLM composes only novel shapes, and the cache is the cost control. Per-path cost (`paths[].cost`) stays absent until DRIVER's estimator task decides whether to build it.

## 3. SUB — the substrate app (G0)

`vihara/` per D1: Vite 5 · TS strict + `noUncheckedIndexedAccess` · React 18 · r3f · Zod · Vitest. Tasks: scaffold + CI gates (typecheck/lint/test/build, the **≤220 KB shell budget as a hard fail**, the frontend-import and world-import boundary lints) · the tokens module from the brand CSS · the 45 registry entries authored + Zod manifest schema with the D4 §2/§3 refusals · S and C renderers real, W a ground-plane stub · the API client (access token in memory, cookie refresh, `gen:api` diff gate) · session + **pre-session screens** (login, register, reset, OAuth callback — VP-03's conventional half, without which nothing else can be reached) · the **ten certified components** with structural goldens, the cross-context assertion, and a refusal test each, mutation-tested one at a time.

**G0 exit demo:** a manifest requested from SEAM renders through S and C, a manual act emits an echo that lands in `ui_echoes` and on the Pragya channel, and every certified golden is green.

## 4. WORLD — the walkable estate (G1)

The 13 world components over the estate read model and stream; the territory per art bible §13's construction language (plinths, holographic volumes, surface-printed UI, the energy floor re-keyed warm-white); day–night as luminance; the five weather states as texture+motion+icon+sentence; traffic from the stream's aggregated rates; beacons with the breathing glow; the depth ladder (still → terrace → district) with camera flights; **the tier probe** (probed, never sniffed, stored in `surface.*`), demotion offered-not-imposed, the context-loss switch; **every W surface's L9 sheet real**.

**Pre-G1 obligation (charter decision 8):** the A-direction portrait rasters. Owner-side production (ADC or the owner's image tool); the procedural seal renders for every entity from day one, so nothing blocks on the rasters except the busts themselves.

**G1 exit demo:** the estate walkable on a tier-A laptop and a tier-B phone; the D7 §8 matrix run on real devices; a tier-C device provably never fetching three.js; the seventeen surfaces reachable with the W renderer disabled.

## 5. DRIVER — the daily driver (G2)

The nine working surfaces, trays first — `HITLPanel` → the Tray is the single most consequential replacement in the product (D8 row 24). Then Registry Halls (full CRUD over the record service, schema-derived, re-deriving on `tenant_entity_defs` version — D4 §8), dossiers, the Standup, the Boardroom (STRAT's surfaces — the increment where Planning records finally get their producer), the Talent Office, the Undercroft, the Library, the Gallery, and **The Study** — VP-03's resolution, **drafted as D6's eighteenth surface first** (it was never wireframed; drawing before building is the phase's whole lesson), holding identity, passkeys, notifications, density and billing & wallet, reachable from the shell.

Owns two named gaps: **VG-18** (the termination workflow — Talent Office/Gallery; design task first) and the **per-path cost estimator** (D5 §4.1 — a G2 design of its own; until it exists the tray renders the path without a cost line).

**G2 exit demo:** a pilot tenant runs a business day entirely in Vihara — approves from the tray, edits a record in a hall, reads a dossier, adopts nothing without a ceremony.

## 6. STEWARD — the steward present (G3)

The channel client over SEAM T8: presence states, `focus`/beam, `narrate` with anchors, `materialize`, `viewport` sent on every depth change, one session across devices; the T2 ceremony (`certified.step-up`) and T3 (`certified.second-channel-wait`) driving `/ai/authn/*` — elevation only ever through AUTH's own routes; voice on the channel over the shipped realtime stack.

**Blocked on, stated honestly:** the **voice go-live live call** ([00a](./00a_voice_go_live_plan.md) §8 — two config items and a phone, owner-side). STEWARD may start and finish everything but its voice leg on a tested seam; **G3 cannot pass on one** (charter §Prerequisites). The live call is the gate's key.

**G3 exit demo:** ask aloud → she walks the map → a tray → a passkey ceremony → the act executes — voice and text, desktop and a second device joining the same session.

## 7. LINE — the pocket (G4)

The Card renderer served as an installable PWA (`line.html`, manifest, service worker); the thread; the Morning Story; the Pocket Desk; biometric certified cards (platform WebAuthn in the installed PWA — the decisive reason for charter decision 6); the push client over SEAM T7; the WhatsApp read-mirror (read + notify only, approvals never on WhatsApp — spec §14.3).

**Owns VG-20** (the Private Line backend — D5 §0 names it uncovered): Morning Story composition and thread persistence are LINE backend tasks, designed inside this workstream against LEARN's morning-set machinery, in `ai/genui/` beside the seams they extend.

**G4 exit demo:** installed on a real Android and a real iPhone; a push arrives as a tray; a payment approved with a fingerprint; iOS's install-first push ceiling demonstrated rather than discovered.

## 8. GLASS — the Glasshouse opens (G5)

**Backend first: the assembly TWIN honestly declared unbuilt** ([03_twin](../increment-6/03_twin.md) §14.7) — an agent loop bound to a twin-plane session with the substituted tool registry, writing real `TwinRun` rows; scenario spend drawn through wallet holds, tenant-initiated. Then the room: the mirror pane, scenario levers, the **four** honesty grades (`untested` must not render like `unknown` — D4 §3.1), the Scenario Shelf, the divergence ribbon, desaturation applied by the renderer at the plane boundary, and the promotion pipeline — a winning scenario taken to SEGA's entity canary through EVX admission, which is what VR-01 said G5 consumes.

**G5 exit demo:** a real scenario replays against yesterday, is graded by the machinery that refuses supplied grades, and one winning change is promoted through a staged rollout with B11's limits visibly holding.

## 9. POLISH — launch quality (G6)

Onboarding staged in the world over the unchanged step APIs (spec §15.1; the wizard screen retires) · the §10.4 **zero-training test with five naive users** · WCAG 2.2 AA audit on S and C · the p75-on-tier-B performance floor measured against D7 §3.1 · the art bible applied everywhere and checked against its own rules · the parity reckoning against D8 (**28 of 30 in-scope screens + the Study + pre-session**) · the 30-day parallel run started with pilot tenants. Cutover itself (the vhost flip) is a launch decision outside the increment.

## 10. What this increment closes

* **Gap-analysis findings built here:** VG-01 (registry+manifest, SEAM/SUB) · VG-02/03/04/06/07/19 (SEAM) · VG-18 (DRIVER) · VG-20 (LINE) · VG-22 (WORLD proves D7) · VG-23 (SEAM T2). VG-05/VG-21 were closed in Inc 6; VG-08 (voice) is built and awaits its call.
* **Phase-A findings:** VP-01 (SEAM T9) · VP-02 (closed at R1) · VP-03 (DRIVER — The Study).
* **The D3 obligation the charter names:** the certified-set boundary as a **tested invariant** — R5's cross-repo correspondence test lands in SUB and runs in both CIs.

## 11. Standing risks

| Risk | Held by |
|---|---|
| The manifest composer is the one genuinely novel machine here; everything else is projection and rendering | SEAM T2 ships heuristic-first with the LLM only on novel shapes; D4 §7's refusal ladder means a bad composition fails visible, never silent |
| A careless static import puts three.js in the tier-C bundle | The ≤220 KB hard build gate from SUB's first day, not from G1 |
| Two API clients drift | The `gen:api` diff gate (D1 §5), in CI from SUB's first day |
| G3 waits on a phone call | STEWARD builds everything but the live leg; the call is owner-side and already fully planned ([00a](./00a_voice_go_live_plan.md) §8) |
| Certified rendering is the security surface | Goldens + refusal tests are SUB tasks, mutation-tested the way this repo tests every control — before any surface consumes them |

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-29 | v1.0 — the decomposition, written the day Phase A exited. Eight workstreams cut along *what is built where* rather than along the gates, each gate becoming its owning workstream's exit demo. The consequential choices: SEAM and SUB overlap with the registry as the first atomic contract+consumer commit; LINE owns VG-20 and GLASS owns TWIN's unwired scenario runner, so neither gap can be assumed handled elsewhere; The Study is drafted as a wireframe before it is built; and the certified-set correspondence test (R5) lands in SUB and runs in both CIs from the start. |
