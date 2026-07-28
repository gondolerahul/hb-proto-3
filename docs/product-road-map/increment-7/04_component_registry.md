# Increment 7 / Phase A — D3: The Component Registry

> **Deliverable D3** of [01_phase_a_overview.md](./01_phase_a_overview.md). Spec §9.2 made into a schema; half of VG-01.
> **Status:** 🚧 **complete but not final** — §8 is the delta section D6 (the wireframes) writes back into. A registry declared final before anything was drawn against it is a registry that is wrong and says it isn't.
> **Consumed by:** [05_manifest_contract.md](./05_manifest_contract.md) (a manifest references entries here) · D6 · G0.

---

## 1. What a registry entry is

One JSON object per component type, versioned, checked into `vihara/src/manifest/registry/`. The registry is **the frontend's contract with the manifest service** — the service may only emit component types that resolve here, and the client refuses a manifest that names one it cannot resolve.

```jsonc
{
  "type": "certified.approval",       // globally unique; class prefix is part of the name
  "class": "certified",               // primitive | certified | world | narrative
  "version": 1,                       // integer; frozen once published (§4)
  "renderers": ["S", "C"],            // which renderers implement it
  "props":    { /* JSON Schema for the static half */ },
  "bindings": { /* JSON Schema for the live half — see D5 */ },
  "density_variants": ["novice", "operator"],
  "a11y": { "role": "region", "label_from": "props.title" },

  // present only on class: "certified"
  "certified": {
    "intent_kind": "categorised_action",              // src/ai/inward_auth/tiers.py
    "gate": "POST /api/v1/ai/approvals/{id}/respond", // the enforce_* call site it drives
    "goldens": ["goldens/certified.approval.v1.S.novice.json", "…"]
  }
}
```

The split between `props` and `bindings` is load-bearing: **props are what the manifest says, bindings are what the client fetches.** A component that renders a figure takes it as a *binding*, never as a prop — which is how spec §12.1's "figures always from deterministic queries; prose frames, never asserts numbers" becomes a schema rule instead of a review habit (§5, rule R7).

## 2. The four classes and the rules that separate them

| Class | May take generative props | Renderers | May import Three.js | Golden-rendered |
|---|---|---|---|---|
| `primitive` | yes | S, C, (W as an inset) | no | no |
| `certified` | **never** (L5) | S, C | no | **yes, all variants** |
| `world` | yes | **W only** | **yes — and only these** | no |
| `narrative` | prose templates only (§5 R7) | S, C | no | no |

Each class is a directory (D1 §3), because a directory boundary is the cheapest place to make a lint rule bite.

## 3. The certified set — frozen, and derived rather than chosen

Spec §9.2 lists six certified components. Walking that list against the shipped tier gate found **four it does not have**, which is this deliverable's finding.

### 3.1 The rule that defines the set

> **A component is certified if and only if it drives a backend endpoint that calls `enforce_tier` or `enforce_kind`.**

Certification is not a taste judgement about which screens feel important. `ai/inward_auth/guard.py` already decides which acts cost a ceremony, and it decides it *once* for both Pragya's path and the console's — the module's own docstring says so: *"If the console and Pragya ever disagree about a tier, it is a bug in one call site's intent, never in two copies of the rules."* Vihara adopting a different list would be exactly that second copy.

This gives the set a **correspondence test** (§5, rule R5) rather than a convention.

### 3.2 The set, as it stands today

Six `enforce_*` call sites exist on `master` (measured 2026-07-28, not read off a doc):

| # | Backend call site | Intent kind | Certified component |
|---|---|---|---|
| 1 | `ai/router.py:491` — approval respond | `categorised_action` (or `work_assignment`) | `certified.approval` · `certified.payment` |
| 2 | `ai/router.py:140` — autonomy raise | `autonomy_raise` | `certified.autonomy-change` |
| 3 | `ai/connectors/router.py:102` — credential bind | `connector_binding` | `certified.connector-binding` |
| 4 | `ai/connectors/router.py:174` — master apply | `connector_binding` | `certified.mastering-declaration` |
| 5 | `ai/intelligence/api.py:160` — provider opt-in | `binding_change` | `certified.provider-opt-in` |
| 6 | `ai/strategy/api.py:82` — resolution adopt | `strategy_resolution` | `certified.strategy-resolution` |
| — | `ai/inward_auth/api.py` — the T2 ceremony itself | *(renders the gate's refusal)* | `certified.step-up` |
| — | the T3 out-of-band leg | *(renders the gate's refusal)* | `certified.second-channel-wait` |
| — | consent grant / revoke (asymmetric — §3.4) | `binding_change` on grant only | `certified.consent` |

**Ten certified components.** Spec §9.2 named six; the four it lacks (`connector-binding`, `mastering-declaration`, `provider-opt-in`, `strategy-resolution`) all arrived after the spec was ratified, in Increments 4, 5 and 6. That is not a spec error — it is the spec being nine months older than the code, and it is exactly why the set is derived from the gate rather than transcribed.

### 3.3 A correction the HANDOFF will need

The HANDOFF and the gap analysis both say **five** certified endpoints ("approval respond · connector bind · master apply · provider opt-in · autonomy raise"). STRAT added a **sixth** on 2026-07-26 — resolution adoption, with `IntentKind.STRATEGY_RESOLUTION` — and no document records it as certified. Not a defect in the code, which is correct and tested; a defect in the count, which R5 will now keep honest automatically.

### 3.4 `certified.consent` renders both directions and gates only one

The guard gates **only the raising direction** — autonomy up, consent in — because "the safe direction must never be harder than the unsafe one". So `certified.consent` is a single component with two behaviours: granting consent opens a ceremony, revoking it does not.

This is worth stating in the registry rather than leaving to the implementer, because the natural instinct when building a certified component is to make the whole thing ceremonious, and a revoke that demands a passkey is a revoke people abandon halfway.

### 3.5 What "frozen" means

A certified entry's `version` is **immutable once published**. A change to an approval's layout, wording or fields is a **new version**, and the previous version's golden stays in the tree.

The reason is the same one that made REG's pricing effective-dated rather than mutable: a past approval must render the way it was approved. An audit that replays a decision through today's component is not replaying that decision.

## 4. Versioning

* Every entry carries an integer `version`. Manifests pin `type@version` (D4).
* **Non-certified** components may publish a new version freely; the previous version stays resolvable until no cached manifest references it.
* **Certified** components: new version only, never an edit (§3.5).
* The registry ships a `min_supported` per type. A client older than `min_supported` refuses the manifest and asks Pragya to render the sheet equivalent — never renders a component it half-understands.

## 5. The rules that are tested

Written as tests, because a rule nobody can observe failing is a rule that returns `True`.

| # | Rule | How it fails |
|---|---|---|
| **R1** | **Totality.** Every `type@version` in any manifest — including every golden and every fixture — resolves in the registry | Manifest validation error at the client boundary; CI fails on the fixture set |
| **R2** | **Certified purity (L5).** A `certified` entry's `props` schema declares `additionalProperties: false`, and no property carries `x-generative: true`. The client rejects a certified component carrying an undeclared prop rather than dropping it | A refusal test per certified component: a manifest with an injected prop must be *rejected*, not rendered |
| **R3** | **Renderer confinement.** `class: "world"` ⟹ `renderers == ["W"]`, and only files under `components/world/` may import `three` / `@react-three/*` | ESLint boundary rule + a registry assertion |
| **R4** | **Honesty (L6).** Any entry whose `bindings` schema can resolve against a twin-plane source declares `honesty_grade` as **required** | Enforced at manifest level in D4; asserted here as a registry property |
| **R5** | **Certified ↔ gate correspondence (§3.1).** The set of `certified.*` entries equals the set of backend `enforce_tier`/`enforce_kind` call sites | A test that greps `src/ai/**` for `enforce_tier(`/`enforce_kind(` and diffs the resulting intent set against the registry. **A new certified endpoint with no component, or a component with no gate, fails CI** |
| **R6** | **Goldens.** Every certified entry has a golden per renderer × density, and the same certified manifest renders an identical certified subtree through S, C and the Line entry | Snapshot diff (D1 §4.1) |
| **R7** | **Narrative components frame, never assert.** A `narrative` prose prop is a template with `{slot}` placeholders resolved from bindings, and **the template itself may contain no digit** | A regex assertion over every narrative fixture. `"₹{collected} collected this week"` passes; `"₹2.4L collected this week"` fails |

**R5 is the one worth defending.** It is the only rule here that spans the repo boundary, and it is the reason this registry cannot silently fall behind the backend the way the "five certified endpoints" line did (§3.3). Everything else in this document could be maintained by discipline; R5 replaces discipline with a red build.

**R7 is the one most likely to be argued with.** A digit ban reads as fussy until you consider the failure it prevents: a narrative component whose prose says `₹2.4L` is a component that will one day say `₹2.4L` when the real figure is `₹9.1L`, and it will look completely normal doing it. The template rule makes that unrepresentable.

## 6. The inventory

Thirty-five entries at Phase A. D6 will change this list (§8).

### 6.1 `primitive` (13)

`register` (table over a `tenant_entity_def`) · `record-sheet` (schema-derived form) · `chart-set` · `kpi-dial` · `timeline` · `kanban` · `document` (viewer) · `diff` · `trace-viewer` · `gauge` · `prose` · `figure` (one number with its source, always a binding) · `empty-state`

Spec §9.2 named ten. `prose`, `figure` and `empty-state` are added because every surface needs them and leaving them undeclared means each surface invents its own — which is how a design system becomes a suggestion. `figure` exists specifically so that R7's slot resolution has one component to resolve *into*.

### 6.2 `certified` (10)

`approval` · `payment` · `consent` · `autonomy-change` · `connector-binding` · `mastering-declaration` · `provider-opt-in` · `strategy-resolution` · `step-up` · `second-channel-wait`

Derived, not chosen (§3).

### 6.3 `world` (10)

`district` · `workplace` (a colleague at their place of work) · `gatehouse` · `road` (with traffic) · `beacon` · `weather` · `monument` · `plinth` (KPI) · `treasury-gauge` · `glasshouse-pane`

Exactly spec §9.2's list, which survived the walk unchanged — the §4 ontology is the World renderer's contract and it was written against the shipped platform.

### 6.4 `narrative` (5)

`story-card` · `standup-line` · `review` · `season-marker` · `mandate`

All five are R7 templates.

## 7. Where the registry physically lives

Two copies, one source. The registry JSON is authored in `vihara/src/manifest/registry/*.json` and **served by the backend** at `GET /api/v1/ai/genui/registry` (D5), because the manifest service must validate its own output against the same registry the client validates against. A service that emits manifests it has not checked is a service that discovers its bugs in a renderer.

The build step that copies the authored JSON into the backend's static registry is checked by CI the same way `gen:api` is (D1 §5): regenerate, fail on diff.

## 8. § Delta — written by D6

*This section is deliberately empty. The wireframes will need components this inventory does not have, and each addition is recorded here with the surface that demanded it, so the registry's growth is traceable to a drawn surface rather than to a hunch.*

*D3 is not final until D6 is complete (overview §3).*

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-28 | v1.0 — the registry schema, the four classes and their separating rules, and seven tested invariants. The finding: **the certified set is derived from the tier gate, not chosen** — a component is certified iff it drives an `enforce_tier`/`enforce_kind` call site — which turns spec §9.2's six into today's **ten** and gives rule **R5**, a correspondence test spanning the repo boundary. That also surfaced a documentation correction: STRAT's resolution adoption is a **sixth** certified endpoint, and every document still says five. |
