# Increment 6 — GenUI (Vihara) Backend & Roadmap Gap Analysis

> **Document class:** pre-design analysis — what the ratified Vihara spec asks the *backend* for that does not exist, and what the *road map* never scoped.
> **Author:** Buddha Cognitive Lab (analysis by Claude, decisions by Rahul)
> **Created:** 2026-07-24 · **Status:** v1.5 — analysis complete; **eleven of the 23 VG findings are closed** — ten by Increment 6 (✅ in §3) and **VG-21 by LEARN**, which had been closed for three days before anybody noticed (see its section). **VG-08** — voice go-live — is **built and awaiting a live call**, no longer parked. **VG-22** is specified but unbuilt. The rest (VG-01…04, 06, 07, 18…20, 23) are Increment 7's substrate work, now contracted in [increment-7/06_backend_api_contracts.md](../increment-7/06_backend_api_contracts.md).
>
> **One correction from Increment-7 Phase A:** this document and the HANDOFF both say the tier gate has **five** certified endpoints. STRAT added a **sixth** on 2026-07-26 — resolution adoption, `IntentKind.STRATEGY_RESOLUTION`. The count is now kept honest by CI rather than by memory ([04_component_registry.md](../increment-7/04_component_registry.md) rule R5).
> **Inputs:** [genui_design_gate_spec.md](../genui_design_gate_spec.md) v1.2 (Vihara, ratified) · [genui_design_gate_concepts.md](../genui_design_gate_concepts.md) §6 (owner selection) · [build_roadmap.md](../build_roadmap.md) §4 Inc-6 · [00_charter.md](./00_charter.md) · the shipped code on `master` @ `a403cda`
> **Method:** every Vihara law (§2), depth level (§3), ontology row (§4), surface (§5), contract (§7–§9) and journey (§15) was walked against the code and each was marked *built* / *partial* / *absent*, with the file that proves it.

---

## 1. Verified current state (2026-07-24, `master` @ `a403cda`)

Re-measured this session, not taken from the HANDOFF:

| Gate | Result |
|---|---|
| `scripts/typecheck_ai.py` (mypy `--strict`) | ✅ **259 files**, 0 issues — 17 packages on the allowlist |
| `scripts/lint_ai_layout.py` | ✅ exit 0 |
| `pytest tests/unit` | ✅ **1523 passed**, 2 skipped |
| `pytest tests/parity tests/eval` | ✅ **16 passed** (the billing canary) |
| `pytest tests/integration` (live PG :5433) | ✅ **281 passed** |
| `alembic heads` | ✅ **`fleet001`** (single head) |

Two corrections to the HANDOFF:

1. **§1's standing push action is CLOSED.** `git ls-remote origin master` → `a403cda`, byte-identical to local `master`; `git rev-list --left-right --count origin/master...master` → `0 0`. Increments 1–5 and the Design Gate docs are all on the remote. The HANDOFF still says "66 commits ahead".
2. **The integration count is 281, not 232.** 232 is the count for the narrower `tests/integration/test_*_db.py` selector the HANDOFF quotes; the whole directory collects 281. Both pass.

**Increments 1–5 are genuinely complete** — every workstream named in the HANDOFF §2 map was found in the tree at the stated path. Increment 6 is a **charter stub**; `LEARN`, `SEGA`, `GENUI` and dynamic-schema evolution have **no code**. Open register findings for Inc 6: **B10**, **B11**, **D3**.

The frontend is **59 hand-built React pages** (`find frontend/src/pages -name '*.tsx' | wc -l` → 59) — exactly the number the spec §5 says Vihara replaces.

---

## 2. Headline finding

> Vihara is specified as *a pure function of platform state*. The platform state largely exists; **the function does not, and neither does about a third of the state it is supposed to be a function of.**

The gap splits cleanly in three:

* **(a) The rendering substrate — 100% absent.** Manifests, the component registry contract, the echo bus, the event-shaped Pragya channel, live world bindings, the density store. This is expected (technical §8 calls itself "a conceptual sketch") and is the G0 workstream.
* **(b) Read models over state that exists but is not queryable.** Weather, traffic, per-district KPI/treasury, the district topology, the autonomy roster, gatehouse health. The data is in Postgres; nothing projects it. Medium effort, low risk.
* **(c) Net-new business capability the spec introduces and the road map never scoped.** The **Glasshouse** (a simulation subsystem), the **strategy pipeline** (Minutes→Propositions→Resolutions→Mandates→Reviews), the **Library**'s provenance/influence machinery, the **Gallery**'s version ledger, **push notification** infrastructure, and the **Private Line**. These are not UI features — they are domain models, stores and workflows, and several are comparable in size to LEARN itself.

Category (c) is the one that changes Increment 6's shape, and it is the subject of §4.

---

## 3. Backend gap inventory

Severity: **B** = blocks the named gate · **M** = major, gate degrades without it · **m** = minor/contained.
"Gate" refers to the spec §12 G0–G6 internal gates.

| # | Gap | Gate | Sev | Evidence |
|---|---|---|---|---|
| VG-01 | Manifest substrate absent | G0 | **B** | no `src/ai/genui/`, no `ui_manifests` table, no manifest anywhere in `src/ai/` |
| VG-02 | No estate read model | G1 | **B** | §4 ontology has ~10 scattered sources and several with none |
| VG-03 | No company-scoped live event stream | G1 | **B** | only per-object SSE exists |
| VG-04 | The tray is not a composed object | G2 | **B** | `router.py:422` returns raw approval rows |
| VG-05 ✅ | Certified actions ungated outside Pragya | G2/G3 | **B** | `require_tier` has no REST call sites |
| VG-06 | Echo bus (L10) absent | G0 | **M** | no `action_echo` endpoint or store |
| VG-07 | Pragya channel is chat-shaped, not event-shaped | G3 | **B** | `pragya/api.py` has no §7 events |
| VG-08 🚧 | Voice is a tested seam, not a live call | G3 | **B** | Inc-4 §12.5. **BUILD COMPLETE 2026-07-28** — all six gaps closed, both live transports written, migration `iauth002`; **awaiting a live call**: [increment-7/00a](../increment-7/00a_voice_go_live_plan.md) §8 |
| VG-09 ✅ | Glasshouse has no backend at all | G5 | **B** | nothing simulation-related in `src/ai/` |
| VG-10 ✅ | No canary for agent/process changes | G5 | **M** | `intelligence/canary.py` is model-only |
| VG-11 ✅ | Strategy pipeline has no domain model | G2 | **M** | HBS Planning module has one object |
| VG-12 ✅ | No KPI history store | G1/G2 | **M** | `ai/kpi/` has no `models.py` |
| VG-13 ✅ | Library provenance / influence / staleness absent | G2 | **M** | `orm/document.py` has 8 columns |
| VG-14 ✅ | Connected drives cataloged only generically | G2 | m | one `notion_knowledge` row |
| VG-15 ✅ | Broadcast gates have no KAR family | G1/G2 | **M** | roster is 18, KAR-01/02/03 only |
| VG-16 ✅ | Bridge credential expiry has no tray path | G2 | m | no expiry field or sweep |
| VG-17 ✅ | No entity version ledger | G2 | **M** | `version` is one `String` column |
| VG-18 | No termination workflow | G2 | m | soft-delete only |
| VG-19 | No notification / push infrastructure | G4 | **B** | no device tokens, no broker |
| VG-20 | Private Line has no backend | G4 | **B** | Morning Story, Pocket Desk, read-mirror |
| VG-21 ✅ | No per-user density / preference store | G0/G2 | **M** | LEARN dependency, nothing today — **closed by LEARN 2026-07-25**, found 2026-07-28 (§VG-21) |
| VG-22 | No manifest latency budget / cache | G6 | m | §12.1 asks <300ms first-scaffold |
| VG-23 | D3 (context taint) is load-bearing under GenUI | all | **M** | generative output now chooses UI |

### VG-01 · The manifest substrate does not exist

Nothing named *manifest* exists in `src/ai/` outside the Meta-Agent's platform-schema cache and the Solo Pack's template manifest — both unrelated. Technical §8 sketches `GET /api/v1/ui/manifest?context=…` and a `ui_manifests` table; neither is built. Needed for G0:

* a manifest **service** (intent → manifest) and a **versioned store**;
* **one component registry contract** shared by the W/S/C renderers (spec §9.2's four classes) — this is a schema artifact the backend owns and the frontend consumes;
* the **certified set** (L5) as fixed, versioned manifests with golden renders in CI;
* **`honesty_grade` required at schema level** on any Glasshouse-derived component (L6) — the spec is explicit that this is enforced by the manifest layer, not by convention;
* the **intent-shape cache** so the same ask yields the same surface (muscle memory), and **schema-derived re-derivation** when `tenant_entity_defs` versions.

### VG-02 · No estate read model

The spec's §4 table is the World renderer's contract. Walking it row by row against the code:

| §4 row | Source today | Verdict |
|---|---|---|
| Sheel / the estate + Pulse | `loop/heartbeat.py`, `loop/models.py` | built, not exposed as an estate view |
| Quarters (bundles) / Districts (19 processes) | `solo_pack/bundles.py`, `templates.PROCESS_GROUPS` | **Python-resident, no API** |
| Colleagues at workplaces | `GET /ai/entities` | built (flat list; no district placement) |
| Gatehouses (KAR-01/02/03) | entities + `signals/*_inbound.py` | partial — no channel-health projection |
| Signals as road traffic | `signals` table, `GET /ai/signals` | built as a list; **no aggregation, no live feed** |
| Parked signals at the siding | `signals` parked state + `sla_seconds` | built |
| Registry Halls (27 HBS objects) | `GET /ai/tenant-schema/{defs,records}` | **built** — the strongest existing surface |
| Treasury gauges per district | `GET /ai/loop/envelope` | partial — one envelope, no per-district rollup |
| KPI plinths per district | `GET /ai/kpi/business` | partial — **Loop-level only**, no per-process |
| HITL beacons | `GET /ai/approvals/pending` | built |
| Runs / traces | `GET /ai/executions/{id}/trace` | built |
| Autonomy ladder position | `governance` JSON on the entity | data exists, **no roster projection** |
| Talent Office | Meta-Agent Board (7 roles incl. TestDriver) | built |
| Monuments (strategy decisions) | — | **absent** (see VG-11) |
| The Glasshouse | — | **absent** (see VG-09) |
| Bridges (connector bindings) | `GET /ai/connectors/{catalog,bindings,status}` | built |
| Broadcast gates | legacy `social_router.py` | **outside the governed roster** (see VG-15) |
| The Library | `GET /ai/documents` | partial (see VG-13) |
| The Gallery | soft-delete only | **absent** (see VG-17) |
| The Undercroft | `signals/api.py`, `intelligence/api.py`, … | built, scattered |
| **Weather** (fog / heat-shimmer / storm / moonlit) | KPI + envelope + `governance_service` breaker + hibernation flags | **derivable, never derived** |

**The recommendation:** one `estate` read-model service that composes these into the §4 shape, rather than 20 bespoke endpoints. It is the single most load-bearing missing piece for G1, and it is also what makes L9 (every world view has a sheet equivalent) cheap — both renderers read one projection.

### VG-03 · No company-scoped live event stream

Two SSE endpoints exist and both are per-object: `ai/router.py:325` (`/executions/{id}/stream`) and `pragya/api.py:223` (`/chat/stream`). The territory needs a **multiplexed, company-scoped** stream (signal traffic, beacon raise/clear, weather transitions, run state, envelope burn). Per §9.4 all bindings are company-scoped **by construction** — the frontend must hold no cross-tenant capability, so this stream's scoping is a security boundary, not a filter.

### VG-04 · The tray is not a composed object

`GET /ai/approvals/pending` (`ai/router.py:422`) returns approval rows. §6.1 requires, in order: what happened (one sentence + linked object) → **Pragya's recommendation and why** (with honesty grade if Glasshouse-informed) → **the paths, each with cost/consequence** → certified action block → "talk to me about it".

Present: the checkpoint registry (19 defs), `sla_seconds` + `on_timeout` (TRUST `trust002`) for the quiet countdown, the approve/decline path (`/approvals/{id}/respond`).
Absent: the composed manifest, the recommendation, and **per-path cost** — `planning/cost_estimator.py` estimates plan steps, not the consequences of the branches of one decision.

### VG-05 · Certified actions are not tier-gated outside Pragya — ✅ **CLOSED 2026-07-24**

> **Built ahead of the Inc-6 design round** (charter decision 5). See §7 below for the build note. A second, more serious defect was found while mapping the work: `respond_to_approval` had **no company scoping at all** — a cross-tenant IDOR on the HITL approval path. Both are fixed.

The analysis that produced the task, kept for the record:

`require_tier` is called from exactly three places: `inward_auth/api.py:135,199` (the step-up ceremony itself) and `pragya/{commands.py:207, runtime.py:320,342}`. **No other REST endpoint is tier-gated.** Concretely, today:

* `POST /ai/approvals/{id}/respond` — approve a payment: `Depends(get_current_user)` only;
* `POST /ai/connectors/{connector_id}/bind` — **submit third-party credentials**: `get_current_user` only;
* `PUT /ai/entities/{id}` — raise an autonomy band: `get_current_user` only;
* `POST /ai/onboarding/activate` — activate a bundle: `get_current_user` only.

The classifier already names these (`tiers.py`: `AUTONOMY_RAISE`, `BULK_DATA_OPERATION`, `BINDING_CHANGE`, `CATEGORISED_ACTION` are all T2 floors). The HANDOFF §5 convention "AUTH's two gates are different gates" is right, and it is exactly why this is a hole: the PolicyGate asks whether the *agent* may act, and nothing asks whether the *human* proved enough when the human clicks instead of speaks.

Vihara §8 makes this structural — every certified action is a UI action. The fix is a reusable FastAPI dependency (`require_tier_for(intent)`) applied at each certified endpoint, plus `step_up_result` in the §7 contract. **Recommend pulling this forward as its own small task rather than waiting for G2**, since it hardens the shipped React app too.

### VG-06 · The echo bus (L10) does not exist

No endpoint, no store, no path into Pragya's context. L10 is constitutional ("every manual act is echoed as the sentence it was") and the echo stream is simultaneously the richest input LEARN will have. Building it in G0 rather than later means LEARN trains on it from day one.

### VG-07 · Pragya's channel is chat-shaped, not event-shaped

Built: `/ai/pragya/{engagement,advance,history,blueprint,readiness,report,chat,chat/stream}`; cross-device continuity via `account_manager_sessions` (`iauth001`) + CORTEX.
Missing, server→client: `deliver_tray`, `focus(target_ref, narration?)`, `materialize(surface_manifest)`, `narrate(text, audio_ref, anchors[])`, `presence(state)`.
Missing, client→server: `utterance` exists as `/chat`; `action_echo` (VG-06), `depth_change`, **`viewport(context_ref)`**, `step_up_result` do not.

`viewport` is the load-bearing one — it is what makes "conversation is always about what's on screen" true, and it is the difference between a chat widget and a steward.

### VG-08 · Voice is a tested seam, not a live call

Already recorded (Inc-4 [01_pragya_runtime.md](../increment-4/01_pragya_runtime.md) §12.5) and already roadmap "next up" #2: registry rows for `pragya-asr-whisper-vertex` + `pragya-tts-gemini`, concrete Vertex/Gemini `Transcriber`/`Speaker` adapters, carrier-media wiring into `drive_call`. **G3 ("the steward is present") cannot pass on a seam** — voice go-live is a hard Inc-6 prerequisite, not an ops remainder.

### VG-09 · The Glasshouse has no backend — the largest single gap

Nothing simulation-related exists anywhere in `src/ai/`. G5 needs, all net-new:

1. **A scenario model + store** (the Scenario Shelf), tournament comparison.
2. **A replay engine** — re-run historical signals against a modified configuration in an isolated plane. Note `POST /ai/signals/{id}/replay` (`signals/api.py:226`) replays into the **live** plane; it is not a twin and must not be mistaken for one.
3. **A forecast engine** over KPI series — which needs VG-12's history to exist first.
4. **Honesty grading** (`replay | forecast | unknown`) enforced at manifest-schema level (L6).
5. **A twin data plane** — a shadow tenant schema. `tenant_schema/data_plane.py`'s two-backend design (schema / container) is the natural host; a third "twin" mode is plausible but unbuilt.
6. **The promotion pipeline** — diff → certified approval → Board build → canary → GA (see VG-10).
7. **Twin spend under B13.** Per the HANDOFF §5 convention, a new `CostAttribution` member must be *classified* — twin runs are tenant-asked-for, so the decision of whether they belong in `PLATFORM_INITIATED_ATTRIBUTIONS` is a real one (§12.1's risk row says "twin spend visible under the platform-initiated budget class", which contradicts the tenant-asked-for rule and needs resolving).
8. **Simulated people** (owner override, concepts §6.4) — `persona_service.py` builds *agent* personas; simulating a customer or counterparty is new.

### VG-10 · No canary for agent/process changes

`intelligence/canary.py` watches/rolls back/promotes over a **routed model cohort**. The Glasshouse's promotion pipeline and SEGA both need the analogous machinery for an **entity change** (charter, policy, band) with B11 blast-radius limits. Building it once, in SEGA, and having the Glasshouse call it is the right factoring — which is also why **G5 depends on SEGA, not only on LEARN/EVX** (see VR-01).

### VG-11 · The strategy pipeline has no domain model

§15.3 specifies **Minutes → Propositions → Resolutions → Mandates → Construction → Review**, navigable in both directions, with plans persisted "as records in the Planning Registry Hall". Today the HBS Planning module contains exactly one object — `Budget` (`tenant_schema/hbs_seed/__init__.py:346`). Nothing captures minutes, nothing models a proposition, a resolution, a mandate, or a monument; nothing schedules a review or computes predicted-vs-realized.

This is a **business capability, not a screen**. It needs: HBS Planning depth (Objective/Target, Forecast, KPI record, Minutes, Proposition, Resolution, Mandate), a monument store with a backlink to its resolution, review scheduling on the signal bus, and the predicted-vs-realized join (which needs VG-09's grades and VG-12's history).

Note the road map's Inc-4 line "HBS module depth (§10.3) lands here — Accounting/HRMS/ERP/Legal" **did not include Planning**, and Inc-4 shipped without it.

### VG-12 · No KPI history store

`src/ai/kpi/` is `definitions.py` + `compute.py` + `api.py` — **no `models.py`, no persistence**. Every KPI is computed on demand from current records. That means there is nothing behind:

* the Gallery's **Seasons timeline** ("vital signs + monuments + mandates = cause and effect");
* trend lines on district plinths;
* mandate **predicted-vs-realized** (§15.3 step 5);
* the "Week 12 > Week 1" promise itself, which Increment 6 exists to *measure*.

A daily KPI snapshot table is small, cheap, and unblocks four surfaces. It is arguably a **LEARN** deliverable rather than a GENUI one.

### VG-13 · The Library's provenance, influence and staleness are absent

`documents` (`orm/document.py`) has: `company_id`, `entity_id`, `filename`, `file_type`, `file_size`, `upload_status`, `memory_domain`, timestamps. §15.4 requires, none of which exist:

* **Collections by source** — `source_kind ∈ {upload, connected_drive, generated_artifact, conversation_derived}` plus the source URI/external ref and who ingested it.
* **Influence** — "which colleagues cite this, how often retrieval used it". This needs a **retrieval-usage log**: nothing today records which chunk served which run. New store on the hot path — and the HANDOFF §5 warning that RETR's three stages are deliberately separate applies: the log belongs at the *caller*, not inside `hybrid_search`.
* **Staleness & contradiction flags**, with supersede-keeps-versions.
* **Generated artifacts filed in the Library and linked to their record.** `artifacts` (`artifact_models.py`) is a legacy-style table with **no FK to `documents`** and no tenant-record link.
* **Citations that open the source at the passage.** Retrieval returns chunks; the answer path has no citation contract.

Built and reusable: `memory_domain` + the RETR domain viewport give §15.4's "scoping made visible" almost for free.

### VG-14 · Connected drives are cataloged only generically

The §6.6 catalog (18 rows, `connectors/catalog.py`) has one knowledge row: `notion_knowledge` — "Knowledge Source Connectors", MCP_SERVER, `server_ref="notion"`. §15.1 stage 3 and §15.4 name **SharePoint, Notion and Google Drive with live sync into the Library**. Beyond catalog rows, `connectors/sync.py` syncs **records** (`object.synced`) — a document-sync path is new.

### VG-15 · Broadcast gates have no KAR gateway family

The governed roster is **18** — KAR-01 (voice), KAR-02 (email), KAR-03 (WhatsApp) in `solo_pack/templates/gateways.py`. §4 and §15.2 require LinkedIn / Instagram / X / Google Ads / YouTube as **Karuna-governed broadcast gates** operated by a "KAR-05 family" that does not exist. The shipped `social_connection_service.py` / `social_router.py` are legacy and sit **outside** SIG, the Karuna profile and the consent/DNC registry — and `social_publishing` in the connector catalog points straight at that legacy service. Routing outbound social through ungoverned code would violate the same posture KAR-03 was built to establish.

### VG-16 · Bridge credential expiry has no tray path

`connector_bindings` has `status` (`BindingStatus`) but no credential-expiry field and no sweep. §15.2's "expired credentials render as a bridge under repair (tray to re-authenticate)" needs an expiry stamp + a cron that raises the tray.

### VG-17 · No entity version ledger — the Gallery cannot keep its promise

`hierarchical_entities` carries a single `version: String` (default `"1.0.0"`), a `status` (DRAFT/ACTIVE/DEPRECATED/ARCHIVED) and `deleted_at` for soft delete. **Editing an entity overwrites its JSON blocks.** The Gallery's "portraits of colleagues past, **every version inspectable**" is therefore impossible today, and so is the Glasshouse's *diff* step in the promotion pipeline. B11's own text references `tool_versions` for tools; entities have no analogue.

### VG-18 · No termination workflow

§5's Talent Office: "Termination = exit interview + handover memo; portrait moves to the Gallery." Soft-delete exists; the ceremony, the memo artifact, and the handover of in-flight work do not.

### VG-19 · No notification / push infrastructure

No device tokens, no push service, no notification broker anywhere in the tree. L2 ("only Pragya interrupts") and L8 ("a push is either a tray-worthy event or it does not exist") require a **single broker only Pragya writes to** — the law is architectural, not a UI convention, and it is easiest to enforce if there is exactly one writer by construction. `alerting` is a `PLATFORM_INTERNAL` catalog row with no user-facing implementation behind it.

### VG-20 · The Private Line has no backend

G4 needs: the **Morning Story** (a daily narrative generation job over the estate read model), the **Pocket Desk** (pinned live cards), the **WhatsApp read-mirror** (outbound notify — `signals/whatsapp_inbound.py` is inbound only), and mobile device registration/attestation so biometric certified cards can meet the T2 bar.

### VG-21 · No per-user density / preference store — ✅ **CLOSED by LEARN 2026-07-25** (found 2026-07-28)

§6.3's persistent density scalar, plus desk order and the morning set, are shown in the §9.1 architecture as **LEARN outputs**. No user-preference store existed when this was written, and the recommendation was to make it an explicit LEARN deliverable rather than discover it at G2.

**It was.** `ai/learning/preferences.py` shipped with LEARN on 2026-07-25: `get_preferences` / `set_preference` / `learn_preference` / `observe_density`, three namespaces (`density`, `notify`, `surface`), a three-observation threshold before the platform sets anything on a person's behalf, and `GET`/`PUT /ai/learning/preferences` + `POST /ai/learning/preferences/observe-density`. Vihara needs **no new preference endpoint** — see [increment-7/06_backend_api_contracts.md §8](../increment-7/06_backend_api_contracts.md).

Recorded here rather than silently: this finding sat marked open at severity **M** for three days after the code that closed it merged, which is the ordinary way a gap register goes stale.

### VG-22 · No manifest latency budget or cache — 📐 **specified 2026-07-28**

§12.1 sets <300ms first-scaffold, streamed manifests, intent-shape cache, optimistic skeletons. Nothing exists; it is a G0/G6 engineering task, listed for completeness.

**Phase A specified it**: per-surface budgets measured at p75 on tier B, four device tiers, frame budgets and demotion rules in [increment-7/08_device_matrix.md](../increment-7/08_device_matrix.md); the two-part streamed manifest and the intent-shape cache key in [increment-7/05_manifest_contract.md](../increment-7/05_manifest_contract.md) §5–§6. Still unbuilt — the finding stays open — but it is no longer under-determined.

### VG-23 · D3 becomes materially more load-bearing under GenUI

D3 (full context taint) is already Inc-6 scope. Under a manifest architecture, model output chooses **what UI renders** — a new and direct injection surface. L5 (certified surfaces are deterministic) is the correct mitigation for the money/legal set, but everything outside that set is generative. Recommend D3's taint rules explicitly cover the manifest path, and that the certified-set boundary be a tested invariant rather than a convention.

---

## 4. Road-map gaps

Gaps in the *plan*, not the code. These are the ones that need an owner decision before Inc-6 design starts.

| # | Road-map gap | Recommendation |
|---|---|---|
| VR-01 | **G5 depends on SEGA, not only LEARN/EVX.** Spec §12 says "G5 consumes Inc-6 LEARN/EVX". The promotion pipeline (diff → certified approval → Board build → canary → GA) *is* SEGA's machinery with B11 blast-radius limits (VG-10). | Amend spec §12 sequencing to LEARN + SEGA + EVX; keeps the charter's LEARN → SEGA → GENUI order valid |
| VR-02 ✅ | **The Glasshouse is not in the road map at all.** build_roadmap §4 Inc-6 lists LEARN → SEGA → GENUI → schema evolution. The Twin is a simulation subsystem (twin plane, replay, forecast, honesty grading, scenario store) comparable in size to LEARN — introduced by the Design Gate, never scoped. | Add **TWIN** as a named Inc-6 workstream, or defer the Glasshouse past the flagship launch and drop G5 |
| VR-03 ✅ | **The strategy pipeline is not in the road map.** §15.3's Minutes→Propositions→Resolutions→Mandates→Reviews plus HBS Planning depth (VG-11). Inc-4's "HBS module depth" line named Accounting/HRMS/ERP/Legal — **not Planning**. | Add **STRAT** as an Inc-6 workstream (or an Inc-4 carry-over), sized separately from GENUI |
| VR-04 ✅ | **The Library's influence machinery needs a retrieval-usage log** (VG-13) — a new store on the hot path, in neither RETR's five tasks nor the road map. | Fold into the GENUI Library workstream; design it at the caller, per the RETR three-stage rule |
| VR-05 ✅ | **Connected drives are not in the §6.6 catalog** (VG-14) yet §15.1 stage 3 depends on them for the onboarding theatre. | Add catalog rows + a document-sync path; small, but it gates the onboarding journey |
| VR-06 ✅ | **Broadcast gates need a KAR-05 family** (VG-15) — the spec names it, the roster is 18, the shipped social path is ungoverned. | Add to Inc-6 scope, or explicitly cut social from the flagship |
| VR-07 | **Push infrastructure is in no increment** (VG-19) and G4 blocks on it. | Scope with the Private Line; the single-writer constraint is architectural |
| VR-08 ✅ | **No KPI history store** (VG-12) — the increment whose goal is "Week 12 > Week 1, *measured*" has nothing that records week 1. | Make it an early **LEARN** deliverable; four surfaces unblock at once |
| VR-09 ✅ | **Entity version ledger is unowned** (VG-17). The Gallery needs it, the Glasshouse diff needs it, SEGA needs it for rollback. | Build once in SEGA; GENUI consumes |
| VR-10 ✅ | **"GenUI replaces the React app" is now false by ratification.** Spec §5 scope call + §14.2: partner and platform-admin consoles stay on legacy React and are rebuilt later. | **Closed 2026-07-28** by [increment-7/09_screen_parity_register.md](../increment-7/09_screen_parity_register.md): all 59 files dispositioned, the amended cutover criterion written. Two corrections — "59 screens" is a **file** count (five are not screens; the denominator is **54**), and parity is **28 of 30 in-scope tenant screens**. It also raised **VP-03**: three tenant functions have no Vihara surface at all |
| VR-11 🚧 | **Voice go-live is a G3 prerequisite, not an ops remainder** (VG-08). | Promoted, planned, and **built 2026-07-28** — six gaps closed (two of them found while building), both live transports written, migration `iauth002`. **Awaiting a live call**: [increment-7/00a](../increment-7/00a_voice_go_live_plan.md) §8. The scope correction there stands: business voice is already live — VG-08 is Pragya's inward face alone |
| VR-12 ✅ | **Certified-action step-up is a gap in the shipped product today** (VG-05), not only in Vihara. | Pull forward as an independent hardening task, ahead of the Inc-6 build |

---

## 5. What this implies for Increment 6's shape

The charter's three-workstream order (LEARN → SEGA → GENUI) survives, but GENUI as written is not one workstream — it is a flagship with at least three net-new subsystems inside it. A shape that matches the findings:

```
LEARN   — learning store on the signal bus + charter tuning under EVX + B10 policy
          + KPI history (VR-08) + the per-user density/preference store (VG-21)
          + the echo bus as its input (VG-06)

SEGA    — self-evolution GA: independent-suite rule, entity-change canary (VG-10),
          B11 blast radius, the entity version ledger (VG-17), + D3 taint (VG-23)

TWIN    — [NEW, VR-02] the Glasshouse subsystem: twin plane, replay, forecast,
          honesty grading, scenario shelf, promotion pipeline over SEGA's canary

STRAT   — [NEW, VR-03] the strategy pipeline + HBS Planning depth

GENUI   — Vihara G0–G6 over all of the above, plus its own substrate:
          manifests, estate read model, live stream, trays, Pragya event contract,
          Library, Private Line + push, and the surfaces
```

Plus two items that should land **before** the Inc-6 build starts, because both harden what is shipped:

* **Voice go-live** (VG-08 / VR-11) — already roadmap "next up" #2.
* **Certified-action step-up** (VG-05 / VR-12) — a live authorization gap in the React app today.

Sequencing note: **the Vihara G0 substrate can genuinely start in parallel** (the spec's §13 amendment says so) — VG-01, VG-02, VG-03 and VG-06 depend on nothing from LEARN/SEGA/TWIN. Only VG-21 (density) and G5 (the Glasshouse) truly serialize.

---

## 6. Open questions — ALL ANSWERED (2026-07-24)

Every question this analysis raised was resolved in the clarifying round. Recorded here with its answer; the authoritative list is [00_charter.md](./00_charter.md) §Decisions.

| # | Question | Answer |
|---|---|---|
| 1 | Flagship scope (VR-02/VR-03) — are TWIN and STRAT built? | **Both in.** Named Increment-6 workstreams |
| 2 | Cross-tenant learning policy (B10) | **Split** — platform-level pools, tenant-level private, enforced at schema level |
| 3 | Learning-store shape | **Reuse** the signal bus + CORTEX Intelligence trees |
| 4 | Twin spend's budget class (VG-09) | **Tenant-initiated** — out of `PLATFORM_INITIATED_ATTRIBUTIONS`, **overriding spec §12.1** |
| 5 | Social / broadcast gates (VR-06) | **Build KAR-05** — workstream GATE |
| 6 | Certified-action step-up (VR-12) | **Pulled forward** — ✅ built, §7 below |

**And one the analysis did not ask, which the owner raised:** GENUI is too large and too dependent to sit inside Increment 6 — it consumes *every other* workstream here. It became **[Increment 7](../increment-7/00_charter.md)** (Vihara), opening with the design phase the ratified spec defers, and Scale & Enterprise renumbered to Increment 8. This analysis's VR-01 (G5 depends on SEGA) is what made the dependency visible; the split is the honest conclusion of it.

---

---

## 7. Build note — VG-05 / VR-12 closed (2026-07-24)

The first Increment-6 code. Owner decision 5 in the [charter](./00_charter.md) pulled this forward because it is a live gap in the shipped React app, not only a Vihara gap.

### 7.1 What was wrong

1. **No step-up on the REST path.** `require_tier` had exactly three call sites — the step-up ceremony itself (`inward_auth/api.py`) and Pragya (`pragya/{commands,runtime}.py`). Approving a payout, submitting a connector's OAuth credentials, flipping an HBS object's master, consenting to a foreign model provider, and raising an autonomy band were all reachable with a plain logged-in session. The classifier already called every one of them T2 — **only the console disagreed**, so the cheapest way to skip a ceremony was to stop talking and start clicking.
2. **A cross-tenant hole on the approvals path** (found while mapping the work, not in the original analysis). `AIService.respond_to_approval` selected the approval **by id alone**, while `get_pending_approvals` immediately above it had always joined `ExecutionRun` to filter by company. Any authenticated user holding an approval UUID could approve or reject **another tenant's** HITL card, including a payment. An unguessable identifier is not an authorization control.

### 7.2 What was built

* **`ai/inward_auth/guard.py`** — the missing half of the Inc-3 gate. It owns **no policy**: it carries an intent to `classify` and the answer to `require_tier`, so console and Pragya cannot drift. `enforce_tier` (payload-dependent tier), `enforce_kind` (tier fixed by the route), `intent_for_approval` + `raises_autonomy` (the two pure mappings), `tier_refusal` (one refusal shape, carrying `needs_step_up` / `needs_oob` / `locked` so the caller opens the right ceremony).
* **Scoping fix** — `AIService.get_approval_for_company` (the explicit scoped read) plus an optional `company_id` filter on `respond_to_approval` itself, so the path is scoped twice. A cross-tenant probe gets **404, not 403**: it must not learn that the id exists elsewhere.
* **Five certified endpoints gated** — `POST /ai/approvals/{id}/respond` (tier from the approval's own category/amount/band), `POST /ai/connectors/{id}/bind`, `POST /ai/connectors/master/{def}/apply`, `POST /ai/intelligence/providers/{p}/opt-in`, and `PUT /ai/entities/{id}` **only when the edit raises the autonomy band**.
* **`IntentKind.CONNECTOR_BINDING`** (T2) — added to the classifier, to Pragya's `INTENT_SCHEMA`, and to the keyword screen, so "connect my Zoho Books" screens the same whether typed, spoken or clicked. The `INTENT_SCHEMA` totality test caught the omission, which is what that test is for.
* **`GateDecision.amount`** — the PolicyGate already computed the amount to compare against the band and then discarded it. It now travels into `context_snapshot`. Without it every high-impact approval failed up to **T3 by artifact rather than by policy**; the fix is the gate supplying the number, never the guard relaxing the rule. This also pre-builds part of what VG-04's tray needs (§6.1 wants each path's cost).

### 7.3 Four design deltas

1. **Imperative call, not a FastAPI dependency.** The first cut used `dependencies=[Depends(CertifiedAction(...))]`. It was replaced because this repo's router tests **invoke handler functions directly** (`test_connectors_router.py`), and a declarative dependency does not run on a direct call — the gate would have been invisible to every test claiming to cover the route, and deleting it would have broken nothing. One mechanism now, in the handler body, where a reader looks.
2. **An uncategorised approval is T1, not T3.** "Ambiguity fails up" governs an *unknown category string*; the **absence** of a category means a non-policy checkpoint that never passed the §20 matrix and carries no external effect. Treating those as ambiguous would have put a passkey prompt in front of every routine confirmation a Solo Pack tenant sees — a regression disguised as rigour. Pinned by a test.
3. **Only an autonomy *raise* is gated.** Renaming an agent or tuning a band **downward** stays ungated. A gate that fires constantly is a gate people learn to click through.
4. **Revocation is never gated.** `/providers/{p}/revoke` stays open on purpose: withdrawing consent must never be harder than giving it, and the safe direction must not be blocked by a step-up lockout.

**One existing suite had to change.** `test_connectors_router.py` bound a connector with a fixture user holding no ceremony — correct before, wrong now. Its fixture creates a real user (the session row FKs to `users`) and elevates it, so those tests exercise connector behaviour *on the far side* of the gate; the refusal path lives in `test_certified_actions_db.py`. A test that had to change is the honest signal that the behaviour changed.

### 7.4 Verification

Gates green: typecheck **260 files** strict · layout lint · **1550 unit** (+27 new) · **16 parity/eval** · **288 integration** (+7 new). No migration — the change is behavioural.

The three security controls were **mutation-tested**, per the repo convention that a checker never observed to fail is a function that returns `True`: removing the approvals gate, removing the connector gate, and restoring the un-scoped approval lookup each made their own test fail with `DID NOT RAISE`, and only their own. The cross-tenant test needed **both** scoping layers removed to fail, which is what proved the second layer is real defence rather than decoration.

**Honest limit:** the gate is enforced server-side and returns a machine-readable refusal, but **the React frontend does not yet handle it** — today a user hitting a gated action sees a generic 403 rather than a step-up modal. `StepUpModal.tsx` and `authn.service.ts` shipped in Inc-3 and have the pieces; wiring them to this refusal shape is a small frontend task, and it is a prerequisite for the shipped console to stay usable on those five endpoints.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-26 | v1.4 — **VG-11 closed** (STRAT built; Increment 6 complete). **VG-08 / VR-11 planned and parked** as [increment-7/00a](../increment-7/00a_voice_go_live_plan.md), with the scope correction that matters recorded there: business voice is already live, so VG-08 is *Pragya's inward face* alone. |
| 2026-07-26 | v1.3 — findings marked closed as Increment 6 shut them: **VG-09** (TWIN), **VG-10**/**VG-17** (SEGA), **VG-12** (LEARN), **VG-13**/**VG-14**/**VG-16** (LIB), **VG-15** (GATE), plus **VR-04**/**VR-05**/**VR-08**/**VR-09**. This file is the register for the Design-Gate findings (the road-map gap register predates them and is not retro-fitted), so the marks belong here. |
| 2026-07-24 | v1.2 — all six §6 questions **answered**; VR-02/03/06/12 resolved. GENUI split into **Increment 7** (Vihara), Scale & Enterprise → Increment 8; twin spend ruled **tenant-initiated**, correcting ratified spec §12.1. |
| 2026-07-24 | v1.1 — **VG-05 / VR-12 closed** (§7): `ai/inward_auth/guard.py`, five certified endpoints gated, the PolicyGate now carries the amount, `IntentKind.CONNECTOR_BINDING` added — plus a **cross-tenant IDOR fix** on `respond_to_approval` found while mapping the work. Four design deltas; three controls mutation-tested. One honest limit: the React app does not yet render the step-up refusal. |
| 2026-07-24 | v1.0 — first full gap analysis of the ratified Vihara spec against `master` @ `a403cda`: 23 backend gaps (VG-01…VG-23) and 12 road-map gaps (VR-01…VR-12); state re-verified (all gates green, push landed, integration 281); proposed Inc-6 workstream shape with TWIN and STRAT added. |
