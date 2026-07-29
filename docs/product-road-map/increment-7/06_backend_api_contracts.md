# Increment 7 / Phase A — D5: Backend API Contracts

> **Deliverable D5** of [01_phase_a_overview.md](./01_phase_a_overview.md). The seams Vihara needs that the platform does not have.
> **Status:** ✅ **BUILT 2026-07-29 — SEAM (`inc7/seam`, T1–T10) shipped every seam below.** Build notes + deltas: **§12**. Migration head **`genui001`**.
> **Covers:** VG-01 (serving) · **VG-02** · **VG-03** · **VG-04** · **VG-06** · **VG-07** · **VG-19** · VG-21 (found already closed) · VP-01 (resolved).
> **Does not cover** — named so the gaps are not assumed handled: VG-18 (termination workflow), VG-20 (Private Line backend), VG-22 (latency budget → D7), VG-23 (D3's taint under GenUI → §10).

---

## 1. Shape

One new package, `backend/src/ai/genui/`, added to the strict-typing allowlist in `scripts/typecheck_ai.py` (repo convention — a new `ai/` package that is not on the allowlist is a package that silently stops being type-checked). Router mounted at `/api/v1/ai/genui`.

The package owns **no domain logic**. Every endpoint below is a projection over shipped services — the estate read model composes `loop/`, `solo_pack/templates`, `kpi/`, `signals/`, `governance/`, `connectors/`; the tray composer reads the PolicyGate's own snapshot. This is the shape TRUST and STRAT both used: *policy in the owning package, enforcement (here: projection) at a thin seam*. A read model that starts computing business truth of its own is a second source of it.

| Endpoint | Method | Closes | Transport |
|---|---|---|---|
| `/genui/registry` | GET | D3 §7 | JSON, long-cached, ETag |
| `/genui/manifest` | GET | VG-01 | JSON, streamed in two parts (D4 §6) |
| `/genui/estate` | GET | **VG-02** | JSON |
| `/genui/estate/district/{process_code}` | GET | VG-02 | JSON |
| `/genui/stream` | GET | **VG-03** | **SSE** |
| `/genui/trays` · `/genui/trays/{id}` | GET | **VG-04** | JSON |
| `/genui/echo` | POST | **VG-06** | JSON |
| `/genui/push/subscriptions` | POST · DELETE | **VG-19** | JSON |
| `/ai/pragya/channel` | WS | **VG-07** | **WebSocket** |

### 1.1 Two transports, on purpose

**The estate stream is SSE.** One-way, reconnect and `Last-Event-ID` are in the protocol rather than in our code, and `src/gateway/app.py` already proxies `text/event-stream` — so the deployment path is proven rather than hoped for.

**Pragya's channel is a WebSocket**, because §7's contract is genuinely bidirectional and one leg of it is audio. This repo already runs WebSocket media handlers (`/stream/pragya/{id}`, `websocket_handler.py`), so barge-in latency is a solved problem on that transport and an unsolved one on any other.

Using one transport for both would mean either polling for `action_echo` or inventing a reconnect story for a socket carrying passive updates. Two transports, each doing what it is good at, is less machinery than one doing both.

## 2. VG-02 — the estate read model

Spec §4's ontology table is the World renderer's contract, and the gap analysis walked it row by row: about ten rows have a source, several are "derivable, never derived", and the recommendation was *one* read model rather than twenty bespoke endpoints. That recommendation stands, and the reason is L9: **both renderers read one projection**, so the sheet equivalent is free rather than a parallel implementation that drifts.

```jsonc
GET /api/v1/ai/genui/estate            // company-scoped from the session, never a param
{
  "estate":   { "loop_id": "…", "pulse": {"beat_at": "…", "healthy": true},
                "local_time": "2026-07-28T23:41+05:30", "phase": "night" },
  "quarters": [ { "code": "growth", "name": "Growth", "districts": ["P03","P04"] } ],
  "districts": [
    { "process_code": "P06", "name": "Customer Care", "quarter": "care",
      "colleagues":  [ { "entity_id": "…", "name": "Meera", "autonomy": "A2",
                         "hand_raised": true, "state": "running" } ],
      "kpi":         { "plinth": [ {"kpi_key": "…", "value": …, "measurable": true} ] },
      "treasury":    { "envelope_id": "…", "spent": …, "cap": …, "reserve_protected": true },
      "weather":     { "state": "fog", "since": "…", "sentence": "…", "icon": "cloud-fog" },
      "traffic":     { "in_1h": 42, "out_1h": 37, "parked": 3 } }
  ],
  "gatehouses": [ { "gateway_code": "KAR-03", "channel": "whatsapp",
                    "health": "ok", "inbound_today": 212 } ],
  "bridges":   [ { "binding_id": "…", "connector": "zoho_books", "state": "live",
                   "credentials_expire_at": null, "conflicts_open": 0 } ],
  "halls":     [ { "module": "CRM", "objects": ["Lead","Account"], "records": 1841 } ],
  "beacons":   [ { "approval_id": "…", "district": "P06", "sla_seconds_left": 12400 } ],
  "monuments": [ { "resolution_id": "…", "district": "P08", "adopted_at": "…" } ],
  "glasshouse":{ "open_scenarios": 2, "last_run_at": "…" },
  "gallery":   { "versions": 84, "terminated": 3 },
  "as_of": "…"
}
```

### 2.1 Weather is a projection, not a stored state

Four of §4's five weather states are derivable from data that already exists and none is stored anywhere:

| State | Derived from |
|---|---|
| Fog | `kpi/compute` — a district KPI below target for N consecutive daily snapshots (`learning/kpi_snapshot`, which is why LEARN had to ship first) |
| Heat-shimmer | `loop/envelopes` — district spend fraction vs days remaining in the period |
| Storm cell | `governance_service` circuit breaker open for the district's process |
| Moonlit | Hibernation flags on the process |
| Clear | None of the above |

**Weather is computed on read, never persisted.** A stored weather state is a state that can disagree with the numbers it describes — and a district shown as foggy whose KPI recovered an hour ago is worse than no weather at all, because it teaches the owner to distrust the map. The cost is a handful of aggregate queries per estate read, bounded by the district count (19 at most).

### 2.2 What this read model refuses to do

It does not accept a `company_id` parameter. Scoping comes from the session, exactly as spec §9.4 requires (*"all bindings company-scoped; the frontend holds no cross-tenant capability by construction"*). This is the VG-05 lesson applied before the fact: `respond_to_approval` shipped for months selecting by id alone while the read on the adjacent line joined on company. **When adding a read beside an existing read, copy the scoping** — and when there is no existing read, do not invent a parameter that makes cross-tenant access expressible.

## 3. VG-03 — the company-scoped live stream

```
GET /api/v1/ai/genui/stream        Accept: text/event-stream
```

Multiplexed, one connection per session. Event types, all carrying `as_of`:

`beacon.raised` · `beacon.cleared` · `traffic` (aggregated, ≤1/s) · `weather.changed` · `run.state` · `envelope.burn` · `pulse` · `bridge.state` · `tray.delivered` (mirror of the Pragya channel, so a desktop that is not in a conversation still sees its trays)

Three properties:

1. **Scoping is a security boundary, not a filter.** The subscription is built from the session's company at connect time and the emitter is fed only that company's events — there is no client-supplied selector to get wrong. A filter applied late is a filter that can be forgotten late.
2. **Aggregation happens server-side.** Signal traffic on a busy tenant is thousands of rows an hour; the road-traffic component needs a rate, not rows. Sending rows and counting them in the browser would put a tenant's whole signal log through the wire for a moving dot.
3. **Backpressure is dropping, not queueing.** `traffic`, `pulse` and `envelope.burn` are *sampled* states — a client that reconnects wants the current value, never the missed ones. `beacon.raised` and `tray.delivered` are **not** droppable and replay from `Last-Event-ID`.

## 4. VG-04 — the tray as a composed object

`GET /ai/approvals/pending` returns approval rows (`ai/router.py:422`). Spec §6.1 requires, in order: what happened → Pragya's recommendation and why → the paths with their costs → the certified block → "talk to me about it".

```jsonc
GET /api/v1/ai/genui/trays
[{
  "tray_id": "…", "approval_id": "…", "checkpoint_key": "before_outbound_payout_above_band",
  "what_happened": { "sentence": "…", "object": {"kind":"Invoice","id":"…","label":"KT-2291"} },
  "recommendation": { "sentence": "…", "why": "…",
                      "honesty_grade": "forecast", "twin_run_id": "…" },   // D4 §3, if twin-informed
  "paths": [ { "key": "approve", "label": "…", "consequence": "…",
               "cost": {"amount": 84200, "currency": "INR", "basis": "the payout itself"} },
             { "key": "decline", "label": "…", "consequence": "…", "cost": null } ],
  "certified": { "component": "certified.payment@1", "tier": "T2", "manifest_hash": "sha256:…" },
  "sla": { "seconds_left": 12400, "on_timeout": "auto_deny" },
  "prepared_by": { "entity_id": "…", "name": "Meera" }
}]
```

### 4.1 The honest gap: per-path cost

Three of the five fields compose from shipped data — the checkpoint registry (21 defs), `sla_seconds`/`on_timeout` from `trust002`, and the gate's `context_snapshot`. **`paths[].cost` does not exist anywhere.** `planning/cost_estimator.py` estimates plan steps, not the consequences of the branches of one decision, and the gap analysis said so.

Recorded, not papered over: a tray may ship with `cost: null` on a path, and the renderer shows the path without a cost line rather than inventing one. **A fabricated consequence on a certified surface is worse than an absent one** — it is the only field on that surface a human cannot check, which makes it the one that must never be guessed. Building a real per-decision cost estimator is a G2 task with its own design.

### 4.2 The recommendation is generated, and the tray is not certified because of it

The tray is a `C`-class composed object that *contains* a certified component. The prose (`what_happened`, `recommendation.why`) is generative; the certified block is not, and it is validated against its own registry schema (D4 §2). Keeping the boundary inside the tray rather than around it is what lets Pragya explain a payout in her own words without the approval itself becoming generative content.

## 5. VG-07 — Pragya's event channel

`/api/v1/ai/pragya/channel` (WebSocket). Today `pragya/api.py` offers `POST /chat` and `POST /chat/stream` — chat-shaped, not event-shaped. The existing endpoints stay (the legacy console uses them); the channel is additive.

**Server → client:** `deliver_tray(tray, sla)` · `focus(target_ref, narration?)` · `materialize(manifest)` · `narrate(text, audio_ref, anchors[])` · `echo_ack(echo_id)` · `presence(listening|speaking|working|away)`

**Client → server:** `utterance(audio|text)` · `action_echo(sentence, action_ref)` · `depth_change(level)` · `viewport(context_ref)` · `step_up_result(tier, ok)`

Four rules:

1. **One session across devices and channels.** The socket attaches to the existing `account_manager_sessions` row — the same row voice and the console already share. A second device joins the same session; it does not open a second one, or "zero repeated context" becomes a per-device promise.
2. **`viewport` is what makes conversation contextual**, and it is the client's job to send it on every depth change and every material scroll. A steward who has to ask "which invoice?" while it is on screen has failed §10.2.
3. **The channel may never elevate.** `step_up_result` is *reported* to the channel; elevation happens only through `/ai/authn/*`, because a failure must be counted against the lockout counter (the AUTH convention — never elevate inside a verify function). The channel's copy of the tier is a cache and is re-checked by the gate on every act.
4. **Only Pragya writes to the client leg (L2).** No other subsystem may push a tray or a narration. Enforced by construction: the emitter is a single function in `genui/channel.py` and nothing else holds a handle to the socket registry.

## 6. VG-06 — the echo bus (L10)

```jsonc
POST /api/v1/ai/genui/echo
{ "sentence": "filtered Invoices to overdue > ₹50k",
  "action_ref": {"kind": "register.filter", "surface_id": "hall.accounting", "params": {…}},
  "manifest_hash": "sha256:…", "component_id": "c4", "occurred_at": "…" }
```

Every manual act emits its sentence. The echo is stored (a small append-only table in the control plane, `ui_echoes`, 90-day retention with a reaper **in the same job as its producer** — a reaper on its own schedule is a reaper that eventually stops being deployed) and fanned to the Pragya channel so she sees what the user did.

**Echoes are not commands.** An echo describes an act that already happened; it never causes one. That is why the endpoint takes no authority, raises no PolicyGate decision and cannot fail in a way that blocks the UI: an echo that fails to record loses training data, not work. It is also why `undo` is **not** an echo-bus feature — undo is the surface's own inverse action, itself echoed.

**What the echo carries that matters later:** `manifest_hash` and `component_id`. Together they answer "what was on screen when the user did this", which is the audit question D4 §5.1 declined to build a table for.

## 7. VG-19 — push (charter decision 7)

```
POST   /api/v1/ai/genui/push/subscriptions   { endpoint, keys: {p256dh, auth}, ua }
DELETE /api/v1/ai/genui/push/subscriptions/{id}
```

Self-hosted Web Push / VAPID. A subscription is a row (`push_subscriptions`) scoped to user + company.

**L8's single-writer law is enforced structurally, not by policy.** The send function lives in `genui/push.py`, is imported by **one** module — Pragya's tray delivery — and an import-boundary test fails the build if anything else imports it. This is the same guard `ai/pragya/acting.py` carries as the only module permitted to reach the tool executor, and that guard was verified by injecting a violation.

**A push is a tray or it does not exist** (L8). The payload carries only `{tray_id, one_sentence}`; there is no digest path, no engagement path, and no "N updates" path — because none is *implementable*: nothing but tray delivery can call the sender.

Ceiling, stated: on iOS, push exists only after the user installs the PWA. An uninstalled iOS visitor gets the thread without notifications rather than an error.

## 8. VG-21 — already closed, and nothing records it

The gap analysis lists VG-21 (per-user density/preference store) as open, severity **M**, with "LEARN dependency, nothing today". **It is built.** `ai/learning/preferences.py` shipped 2026-07-25 with `get_preferences` / `set_preference` / `learn_preference` / `observe_density`, three namespaces (`density`, `notify`, `surface`), a three-observation threshold before the platform sets anything on a person's behalf, and `GET`/`PUT /ai/learning/preferences` + `POST /ai/learning/preferences/observe-density`.

Vihara needs **no new preference endpoint**. It reads `density.*` at session start, writes `observe-density` when a user overrides, and — usefully — `notify.*` is already the namespace L8's push preferences belong in.

That the store refuses an unknown namespace is worth keeping: *"the store cannot quietly become a general-purpose per-user JSON dump — which is what every preference table becomes without one."* Vihara must add a namespace by code change and review, not by writing a new key.

## 9. VP-01 resolved — token storage

Raised in D1 §5: `frontend/` keeps both tokens in `localStorage`, and copying that into an app that renders generated UI and drives T2/T3 step-up is a worse trade than it was where it shipped.

**Resolution: Vihara keeps the access token in memory only, and takes the refresh token in an `HttpOnly; Secure; SameSite=Strict` cookie.**

| | Cost | Where |
|---|---|---|
| Backend | Issue the refresh token as a cookie on `/auth/login` and `/auth/refresh` when the caller asks for it (`X-Token-Delivery: cookie`), plus a CSRF double-submit on the refresh route | ~half a day |
| Vihara | Access token in a module variable; a refresh call on 401; no storage read anywhere | included in G0's API client |
| Legacy | **Unchanged.** The header path stays; the cookie path is opt-in per caller | none |

Two reasons this is worth the half day rather than deferred: an XSS on Vihara can no longer *persist* a stolen session, and the certified-action surface is precisely where a stolen session is worth the most. The counter — "an XSS can still act as the user while the page is open" — is true and is why this is a mitigation rather than a fix; the fix is D4 §2's reject-don't-sanitise rule and §10 below.

## 10. VG-23 — D3's taint ladder under GenUI

Not an endpoint, but it lands on this seam and would otherwise be assumed handled by SEGA. SEGA's taint ladder (`evolution/taint_firewall.py`) governs what a *tainted* context may cause an agent to do. Under Vihara, generated output additionally chooses **what UI renders**, which is a second consumer of the same taint.

The manifest service must therefore carry the taint of the material it composed from, and a manifest composed from `external_unverified` material **may not emit `certified.*` components at all** — the certified set renders only from platform-fixed manifests (D3 §3.5), never from a generated one. That is already true by D3's construction; stating it here makes it a property somebody can test rather than an accident of the design.

## 11. Cost, and the B13 classification

Manifest generation uses a model **only for novel intents** — a cached intent shape (D4 §5) costs nothing. That makes the cache the cost control as much as the latency control.

New `CostAttribution.MANIFEST_GENERATION`, and per the repo convention it must be classified rather than merely added: **it stays OUT of `PLATFORM_INITIATED_ATTRIBUTIONS`.** A user asking for a surface is tenant-asked-for work, exactly like RETR's `rerank` and TWIN's scenario spend (Increment-6 charter decision 6). Putting it in the platform class would let ordinary browsing exhaust the cap whose whole purpose is protecting tenants *from* platform work.

`tests/parity` is the canary for this and must stay 16 green.

---

## 12. Build notes — SEAM, 2026-07-29 (T1–T10 on `inc7/seam`)

Ten tasks, a commit per task, every gate green throughout. Final measures:
**2127 unit** · 16 parity/eval · **523 integration** · mypy `--strict` **330
files** (`genui` allowlisted) · layout lint · migration head **`genui001`**
(applies / rolls back / re-applies, single head). One dependency added:
`pywebpush` (poetry, lock re-synced, suite re-run). One owner decision landed
mid-build: **Vihara's dev port is 4044** ([02](./02_stack_and_repo.md) §6).

### 12.1 What shipped, per seam

`backend/src/ai/genui/` — registry serving (T1) · estate read model (T3) ·
tray composer (T5) · echo bus + `genui001` (T6) · manifest service (T2) ·
SSE stream (T4) · push + the single-writer sender (T7) · Pragya's WS channel
(T8) · VP-01 cookie delivery in `src/auth/` (T9). The registry is authored in
`vihara/src/manifest/registry/*.json` (the first `vihara/` artifact) and
mirrored here, byte-equality test-enforced.

### 12.2 Deltas against the contracts — the ones that outlive the build

1. **The registry counts 48, not 45.** D3 §6's *named lists* sum to 38 → 48;
   its "35 → 45" headline miscounted by three — found the day a test counted
   the authored JSON (D3 §9). The per-class counts are CI-pinned now.
2. **Manifests are pure shapes.** The first composer draft read tenant state
   (measurable KPIs, live beacons) — which would have made the intent-shape
   cache tenant-dependent, exactly what D4 §5 forbids. Now every composition
   is a pure function of platform data (registry + KPI registry + the Wave-0
   table); all tenant variation arrives through bindings; the terrace-W
   manifest composes one component per *kind* of site and the renderer
   instantiates per bound datum. Corollaries: composition needs no DB, and
   the cache is consulted before any work. The D4 §5 key's binding-sources
   term belongs to the *intent* path; the surface path keys on the surface id.
3. **Fog is a named absence.** §2.1 derives fog from "KPI below target" and
   `KpiDefinition` declares no target and no direction — there is nothing to
   be below. The weather never claims fog; a tripwire test fires if someone
   adds it without a real target. The fix belongs to the KPI registry.
4. **Storm is estate-wide.** No per-process breaker state is stored anywhere
   (the credit breaker raises mid-run and persists nothing). The projectable
   storm is the company's own stop states (`read_only`/`suspended`) — and
   when it storms, it truthfully storms everywhere.
5. **Stream replay is snapshot-on-connect**, not a `Last-Event-ID` cursor
   (delta against §3): every (re)connect replays all pending beacons, so a
   sampled value can be superseded but a beacon can never be lost — and
   there is no durable per-event ordering to invent.
6. **The tray's three honest nulls**: `recommendation` (nothing writes one
   until STEWARD), `paths[].cost` beyond the act's own amount, and
   `currency` (the gate never stamps one). The certified block conforms to
   its registry schema by test — the composer can never emit a tray the
   client would reject.
7. **One delivery door.** `channel.deliver_tray` is both the only writer of
   the client leg (L2) and the only permitted importer of
   `push.send_tray_push` (L8, import-boundary test): sockets first, push
   only when nobody listens, never both.
8. **The channel never elevates** — pinned by an AST test (no elevation
   field touched, no `elevate` call), not by a string match; two tripwire
   tests this build caught their *own docstrings* first, which is why.
9. **VP-01 landed at the costed half-day.** Cookie mode omits the refresh
   token from the body (the body copy is the one localStorage keeps);
   refresh rides the cookie behind a CSRF double-submit; the legacy path is
   byte-compatible, pinned by test.

### 12.3 Honest limits

No LLM composer — the manifest table covers `still` · `terrace`(+sheet) ·
`district.*`, and a novel intent is an `UnknownSurface` refusal until
SUB/DRIVER grow the table (`MANIFEST_GENERATION` is registered and waiting).
**Nothing calls `deliver_tray` in production yet** — the approval watcher is
STEWARD's; the SSE stream mirrors `tray.delivered` from its own diff loop
meanwhile. The stream is a 3s poll-diff, not a push fabric. The channel's
`utterance` is text-only (voice is STEWARD's). `terrace.sheet` shows the six
Wave-0 envelope gauges, so custom processes are underrepresented in the L9
sheet until the composer learns context. Gatehouse `health` is constant
`"ok"` and bridge `conflicts_open` constant 0 (no per-binding conflict
attribution exists). Estate `local_time` is a deployment setting
(`VIHARA_ESTATE_TIMEZONE`), not per-tenant. The WS accept-loop itself is
thin and untested; every protocol rule underneath it is unit-tested via
`dispatch_message`.

## Change Log

| Date | Change |
|---|---|
| 2026-07-29 | v1.1 — **BUILT.** SEAM T1–T10 shipped every seam (§12 build notes). The deltas that matter: the registry counts **48**; **manifests are pure shapes** (the tenant-state composer draft would have made the cache a leak); fog and the per-process storm are **named absences** projected honestly; stream replay is **snapshot-on-connect**; the tray carries three honest nulls; one delivery door serves socket and pocket; the channel is AST-pinned never to elevate; VP-01 landed at its costed half-day. |
| 2026-07-28 | v1.0 — the six seams Vihara needs, contracted against shipped code rather than against the spec's prose. Decisions worth keeping: **weather is projected on read, never stored** (a stored state can disagree with the numbers it describes, and a district still foggy after its KPI recovered teaches the owner to distrust the map); **the estate read model takes no `company_id`** — the VG-05 IDOR lesson applied before the fact, by not making cross-tenant access expressible; **L8's single writer is an import-boundary test**, so a digest push is not forbidden but unimplementable; and **`paths[].cost` is admitted absent** rather than estimated, because a fabricated consequence is the one field on a certified surface a human cannot check. Two findings: **VG-21 is already closed** by LEARN's preference store and no document says so, and **VP-01 is resolved** — access token in memory, refresh token in an HttpOnly cookie, legacy untouched. |
