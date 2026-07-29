# Increment 7 / Phase B — DRIVER: The Daily Driver (G2)

> **Workstream 4** of [10_workstream_decomposition.md](./10_workstream_decomposition.md) §5. Branch **`inc7/driver`**.
> **Status:** ✅ **BUILT 2026-07-29** — D0–D13, build notes §6. G2's exit met at the test level; the pilot walkthrough is owner-side (§6.3).
> **Builds against:** [07 wireframes](./07_surface_wireframes.md) (the layouts, R2-passed as drawn) · [04 registry](./04_component_registry.md) · [05 manifest](./05_manifest_contract.md) · [06 backend contracts](./06_backend_api_contracts.md) (D5 — every seam shipped by SEAM).
> **Exits:** **G2** — a pilot tenant runs a business day entirely in Vihara: approves from the tray, edits a record in a hall, reads a dossier, adopts nothing without a ceremony.

---

## 1. What DRIVER is, and is not

The working surfaces — everything between the walkable estate (WORLD) and the steward's presence (STEWARD). Trays first: **`HITLPanel` → the Tray is the single most consequential replacement in the product** (D8 row 24), and it is the surface the zero-training test turns on.

DRIVER is overwhelmingly **frontend over shipped seams**. The register that matters: of the eleven surfaces here, nine bind entirely to endpoints that already exist. The two backend additions are the **per-path cost estimator** (D5 §4.1's admitted gap, decision 2 below) and the **VG-18 termination workflow** (soft-delete exists; the ceremony does not). Both get a design section in this doc before code, per the decomposition.

**Scope note — the Bridges & Gates board is DRIVER's.** The decomposition's table names it nowhere; it is an in-scope depth-2 surface (D6 §14, R2-passed), and WORLD's build already points here (`vihara/src/estate/live.ts`: *"bridge.state belongs to the Bridges board (DRIVER)"*). Recorded so the gap is a line in this doc rather than a discovery at G6.

Not DRIVER's: Pragya's presence, narration, `materialize`, ceremonies driven over the channel (STEWARD); the Glasshouse room and the scenario runner (GLASS); the Line (LINE). Where a DRIVER surface *draws* one of those — the Boardroom's take-to-Glasshouse, the Standup's voice-over — it renders the affordance honestly disabled or hands off, never fakes it.

## 2. § Decisions (locked with Rahul 2026-07-29 — do not re-litigate)

1. **The Study is draft-and-build.** The eighteenth surface is drafted into D6's inventory first (drawing before building is the phase's lesson), but there is no blocking R-review; the owner reviews wireframe and build together at merge. A layout he dislikes gets rebuilt — accepted cost.
2. **The per-path cost estimator is designed *and built* in DRIVER** (§4). D5 §4.1's rule stands unweakened: a path whose cost the estimator cannot ground in observed data ships `cost: null`, and the renderer shows no cost line. The estimator narrows the nulls; it never fills them.
3. **VG-18 termination is a plain governed act, not a certified one** (§5). Stopping an agent is the safe direction, and the safe direction must never be harder than the unsafe one — the same principle that leaves autonomy-lowering and consent-revocation ungated. **The certified set stays at ten**; R5's correspondence test should not move this increment.

## 3. The task plan

Repo rhythm: task-by-task commits, gates green throughout (backend suites *and* `vihara/` vitest + the ≤220 KB shell budget), build notes in §6 on merge.

| T | Task | Builds | Contract |
|---|---|---|---|
| D1 | **The Tray** | The C-composed tray over `GET /genui/trays` + `tray.delivered`; the certified-act flow (gated call → `step_up_required` → WebAuthn ceremony via `/ai/authn/*` → retry once — the console's `useCertifiedAction` shape, rebuilt storage-pinned); every path echoes | D6 §4's four rules · D5 §4 |
| D2 | **Cost estimator** | `paths[].cost` from observed history (§4), wired into `genui/trays.py`; parity 16 stays green | D5 §4.1 |
| D3 | **Registry Halls** | `register`/`record-sheet`/`tracked-change` real; CRUD over `tenant-schema/defs`+`records`; owner-writes/others-propose as *editability filing proposals* (◧); master's seal ⊛; **bulk opens `certified.step-up`**; analytics flip | D6 §7 · D4 §8 |
| D4 | **District furnishing + dossier** | The district sheet's working half (live runs, colleagues); the dossier: portrait/seal, charter, KPI dials, decisions *told* as story-cards, trace one flip away, feedback → echo + SEGA proposal path (never a direct charter write) | D6 §5–6 |
| D5 | **The Standup** | `standup-line` sequence over `executions` (yesterday) + `trays` + `kpi.history` deltas, composed client-side; prepared-by the colleague, relayed by Pragya (voice itself is STEWARD's) | D6 §10 |
| D6 | **The Boardroom** | STRAT's missing producer: minutes, propositions (**UNTESTED rendered distinct from unknown**), `certified.strategy-resolution` adoption, Planning Hall flip; take-to-Glasshouse honestly disabled until GLASS | D6 §8 |
| D7 | **Talent Office + VG-18** | Brief → shortlist → interview → probation → confirm over the Meta-Agent Board; hire lands at A1 via `certified.autonomy-change`; termination per §5 | D6 §9 · §5 here |
| D8 | **The Gallery** | Seasons over `strategy` reviews/resolutions; SEGA version-ledger diffs; predicted-vs-realized over `twin` runs + `kpi.history`; colleagues past, desaturated; the no-backfill KPI series says so | D6 §11 |
| D9 | **The Library** | `document`/`provenance`/`citation`/influence gauge over LIB's columns + retrieval projections; **influence binds `distinct_queries`, never `retrievals`**; citations open at the passage; no contradiction section until one is produced | D6 §13 |
| D10 | **The Undercroft** | Depth-3 mono density: signals, triggers, envelope, traces, schema, routing attribution, consent/DNC, flags — plus the **manifest inspector** (manifest, `intent_shape`, cache age, registry versions) | D6 §15 |
| D11 | **Bridges & Gates** | Two registers over `connectors/*` + consent + `social_connections`; the three certified bindings wired; `sync.conflict` as a dispute at the bridge; an expiry-less bridge never implies it was checked | D6 §14 |
| D12 | **The Study** | Draft into D6 as the eighteenth surface, then build: identity · passkey enrolment (`/ai/authn/*`) · notifications (`notify.*` preferences) · density (`observe-density`) · billing & wallet with dunning explicable — shell-reachable, not a place in the estate | D8 §4 (VP-03) |
| D13 | **Close-out** | Build notes + § Delta here; parity-register flips; HANDOFF; merge | repo convention |

Order as numbered — trays first by decree; D2 lands behind D1 so the tray renders null-honest from day one and gains cost lines when the estimator earns them; the Halls next because their backend is the strongest that already exists. D5–D12 are largely independent and may reorder opportunistically if a seam surprises.

## 4. Design — the per-path cost estimator (D2)

**The sentence it answers:** *"what has saying yes to this kind of thing cost before?"* — and nothing else. Not a forecast, not a model guess: **an observed median, labeled as one**.

* **Source of truth:** `usage_logs` joined through the approval's own run. An approval at checkpoint `k` belongs to an `ExecutionRun`; the run's post-approval spend is what approving actually cost the wallet last time. The estimator aggregates per **(company, checkpoint_key)** over a trailing window (90 days): median run-spend, observation count.
* **Floor:** fewer than **5 observations → `null`**. Company-scoped only — no cross-tenant pooling (this is spend, not the LEARN telemetry split; a platform-wide median would leak nothing but would *describe* nothing either, and a number that describes nothing is a fabrication with a denominator).
* **The act's own amount stays first-class.** A payment's approve path costs the payment — the gate's number, `basis: "the payout itself"`, exactly as SEAM shipped it. The estimator adds a *second* kind of line — `basis: "observed: median of N similar decisions"` — and the two are never summed into one figure.
* **Decline costs `null`, not zero.** Declining has consequences the platform cannot observe; zero would be the fabrication.
* **Placement:** `ai/genui/cost.py`, computed on read inside the tray composer with a short cache. It is a projection over billing data — exactly what `ai/genui/` is for — and it adds **no migration, no cron, no new attribution** (reading `usage_logs` is free; the parity suite is still run as the canary because every credit-path *adjacency* has earned that reflex).
* **What would violate the design:** an LLM estimating a cost, a platform-wide fallback, summing bases, or a placeholder currency. The unit tests pin each.

## 5. Design — VG-18, termination as workflow (D7)

Spec §5's sentence: *"Termination = exit interview + handover memo; portrait moves to the Gallery."* Today: soft-delete. The gap is the ceremony — and by decision 3 the ceremony is **record-keeping, not a security gate**.

1. **The exit interview is the dossier's last one-on-one.** A tenure summary composed from what already exists — runs, decisions, KPI contribution, the charter's history — rendered by the dossier surface in past tense. Composed deterministically from shipped reads; no generative prose in v1.
2. **The handover memo is an artifact, filed to the Library.** What was in flight at termination: running/parked runs, pending approvals (which remain — they belong to the human), owned records and triggers, each with where it went. Deterministic composition; the memo's provenance row says `source_kind` accordingly.
3. **In-flight work parks before the entity goes.** Termination deactivates the colleague's triggers, then refuses while runs are live (the owner is told what is still running and may wait or pause) — a refusal, not a queue, because a termination that silently strands a half-done payment chase is the "nothing happened" bug this codebase keeps finding.
4. **The Gallery keeps the record.** Soft-delete stays the mechanism; termination stamps the entity's metadata (`terminated_at`, memo artifact ref) so "colleagues past" is a query, not a new table. **No migration expected**; if the stamp needs a column after all, that is a build-note delta.
5. **Governance unchanged:** no `enforce_tier`, no new checkpoint. Deleting *audit* is not part of termination — usage rows, echoes, version ledger and influence records all survive the colleague.

Backend placement is decided at the code face (wherever entity lifecycle actually lives — likely beside the Meta-Agent Board's service) and recorded in §6; the design constraint is only that `ai/genui/` stays projection-only, so the workflow does **not** live there.

## 6. § Build notes — ✅ BUILT 2026-07-29, D0–D13 (branch `inc7/driver`)

All thirteen tasks, one session, gates green throughout. Vihara **213**
vitest (was 145) · shell **107.1 KB gz** of the 220 hard budget (world
chunk untouched at 215.5) · backend **2145 unit** (+18) · **334 files**
mypy `--strict` (new package `ai/talent/`) · parity/eval **16** · new
integration suites for cost, bulk and termination. OpenAPI re-exported
both sides three times (bulk · talent · document provenance) with the
drift gate proving each.

### 6.1 What shipped, in one paragraph each

**D1 The Tray** — the C-composed tray over `GET /genui/trays` +
`tray.delivered`, with the four D6 §4 rules each pinned by a test: the
certified block renders through `implementationFor` (the SAME dispatch
manifests use) *and* through the refusal ladder, so a poisoned block
renders a refusal, never a lookalike; the countdown is a quiet timer; a
null cost is no line; the block renders whole. `useCertifiedAct` is the
legacy console's retry-whole-exactly-once closure rebuilt storage-pinned,
and `StepUpCeremony` drives `/ai/authn/*` (passkey, TOTP fallback, T3
rendered as the second-channel-wait state honestly deferred to STEWARD).
Every path echoes, including asking. The shell gained its two pieces of
tray chrome: the gold "N waiting" affordance (absent at zero) and the
echo ribbon.

**D2 The estimator** — `genui/cost.py` per §4's design: company-scoped
median of post-approval run spend, 90-day window, five-observation floor,
zero-spend approvals in the sample, decline never estimated, the gate's
own amount always winning, bases never summed. No migration, no cron, no
new attribution; parity stayed 16.

**D3 Registry Halls** — schema-derived CRUD over the shipped tenant API;
◧ from pending `object.change_proposed` signals with the delta takeable
into the draft; ⊛ from the new `sor`/`synced` fields on `_record_out`;
CAS conflicts said plainly. **Bulk became the seventh gated call site**:
`POST /ai/tenant/records/bulk` with `enforce_kind(bulk_data_operation)`
in the handler body, mutation-tested (refuses un-elevated before any
write; applies elevated; ghosts reported).

**D4–D5** — the district sheet App promised itself (colleagues, reserve,
weather, live runs) with the dossier as a one-on-one (work *told* as
sentences, trace one flip away, feedback echoed with the honest note
that the charter fold-in is SEGA's proposal path at G3); the Standup as
a pure composition over three shipped reads, waiting-first, quiet days
told rather than blank.

**D6 The Boardroom** — **STRAT's honest limit closes**: raising a
Proposition and opening Minutes are now producible acts, born
`untested`; UNTESTED renders as its own words distinct from UNKNOWN;
adoption drives the T2 certified endpoint; take-to-Glasshouse drawn and
honestly disabled until GLASS.

**D7 Talent + VG-18** — `ai/talent/` per §5's design: termination
refuses over live runs, files a deterministic handover memo as a real
artifact, stamps the Gallery record in `metadata_extensions`, soft
deletes, touches no audit, adds no `enforce_*`. Hire lands at A1 no
matter what the template says. The interview honestly disabled until G5.

**D8–D11** — the Gallery (seasons, mandates' predicted-vs-realized with
`not_measurable` as words + its `missing` list, colleagues past
desaturated by the twin's rule); the Library (provenance columns added
to `DocumentResponse` additively; the influence sentence binds
`questions_answered`, pinned against `retrievals`; the viewer is the
passage read); the Undercroft (mono, operator by decree, plus the
**manifest inspector** over a client-side log of every manifest asked
for, rejections included); Bridges & Gates (expiry-less credentials say
"not checked"; `sync.conflict` as a dispute keeping the losing delta;
binding through the ceremony).

**D12 The Study** — drafted into D6 §15a first (decision 1), then built
shell-reachable: identity, passkey enrolment (the depth-2 placement is
the point), density stated-vs-learned, `notify.*` toggles, and dunning
explained in words on the one surface where quiet must not read as calm.

### 6.2 § Delta log — where the build corrected the designs

1. **R5 gained a second exception family** (`CEREMONY_ONLY_GATES` in
   `genui/registry.py`): a gate whose certified surface is the generic
   step-up rather than a component of its own (bulk, per D6 §7 as
   drawn). Counted by the R5 test, not exempted — an unlisted
   `enforce_*` site still fails CI. The certified set stays **ten**.
2. **Termination's "park the triggers" step dissolved**: triggers are
   per-PROCESS rows; an agent has none, and roster removal is the
   stop-new-work step. (§5's other four steps shipped as designed.)
3. **Three additive read-shape changes** where a surface needed what the
   platform already knew: `_record_out` gained `sor`/`synced` (the ⊛),
   `DocumentResponse` gained the LIB provenance columns, and the talent
   router gained `GET /colleagues-past` (a query over the stamp).
4. **The manifest inspector lives client-side** — an in-memory log in
   the API client, capped at 50. Consistent with Phase A's "no
   `ui_manifests` table" ruling; what audit needs is still the hash on
   the approval record.
5. **The tray composer takes `observed_cost` as a parameter** rather
   than the estimator being called inside `compose_tray` — composition
   stays pure and the DB read stays at the two call sites.
6. **The shell nav grew room links** (halls · standup · board · talent ·
   gallery · library · bridges · undercroft · study) — a pragmatic
   stand-in until STEWARD's ⌘K palette, which D6 §1 makes the real
   navigation. Recorded so nobody mistakes the buttons for the design.

### 6.3 Honest limits (each deliberate, none silent)

* **The tray panel opens its own SSE connection** while open (beside the
  terrace's). One-connection-per-session consolidation lands with
  STEWARD's channel client, which needs a shared stream anyway.
* **Hall proposals are read off recent signals**, and "take into the
  draft" applies the delta as a front-door write — the signal itself is
  not consumed; a proposal store with acceptance state is not built
  anywhere.
* **The analytics flip counts loaded records client-side** (≤200) — a
  register lens, not a query room.
* **No per-colleague SLO is measured**; the dossier says so. Feedback
  echoes but nothing yet files a charter proposal from it.
* **Mastering declarations and consent grants have no board UI yet** —
  the certified endpoints and components exist; the Bridges board
  renders masters from the catalog and says what it cannot read.
* **The estimator fills only amountless checkpoints**, currency stays
  null everywhere, and its cache is per-process.
* **The Study's identity panel is read-only**; channel bindings and TOTP
  enrolment stay in the legacy console this increment.
* **G2's exit demo is met at the test level** — approve from the tray,
  edit in a hall, read a dossier, adopt nothing without a ceremony, all
  built and tested; the pilot-tenant walkthrough is owner-side, like
  G1's two items.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-29 | v1.1 — **BUILT, D0–D13.** Build notes §6 with the six-delta log (R5's ceremony-only gates; the trigger step dissolving; three additive read shapes; the client-side manifest inspector; the composer's `observed_cost` parameter; the stand-in shell nav) and the honest-limits list. The Study drafted (D6 §15a) and built the same session. VG-18 closed; bulk became the seventh gated call site with the certified set still ten. |
| 2026-07-29 | v1.0 — workstream opened. Three owner decisions locked (§2): the Study draft-and-build; the cost estimator designed **and built** here; termination a plain governed act (certified set stays ten). Scope correction recorded: the Bridges & Gates board, unassigned in the decomposition table, is DRIVER's. Two backend designs written before code (§4, §5): the estimator answers only "what has yes cost before" with observed medians and a 5-observation floor, and termination is a ceremony over soft-delete — parks triggers, refuses over live runs, files a handover memo to the Library, stamps the Gallery record — with governance untouched. |
