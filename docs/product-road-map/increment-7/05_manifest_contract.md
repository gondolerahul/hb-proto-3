# Increment 7 / Phase A — D4: The Manifest Contract

> **Deliverable D4** of [01_phase_a_overview.md](./01_phase_a_overview.md). Spec §9.3 made real; the other half of VG-01.
> **Status:** ✅ complete 2026-07-28. Engineering artifact.
> **Depends on:** [04_component_registry.md](./04_component_registry.md). **Consumed by:** [06_backend_api_contracts.md](./06_backend_api_contracts.md) · G0.

---

## 1. The contract

Spec §9.3 sketches it in one line: `{surface_id, version, renderer: W|S|C, layout, components: [{type, props, bindings, density_variants, certified?, honesty_grade?}], context_ref}`. Made real:

```jsonc
{
  "manifest_version": 1,             // the contract's own version, not the surface's
  "surface_id": "district.collections",
  "surface_version": 3,              // bumps when the composition changes
  "renderer": "S",                   // W | S | C
  "plane": "live",                   // live | twin   ← §3
  "depth": 2,                        // 0..3, the ladder position this surface occupies
  "density": "novice",               // novice | operator — resolved server-side (§5)
  "context_ref": {                   // what this surface is *about*
    "kind": "process", "id": "P06", "company_id": "…"
  },
  "layout": { "kind": "stack", "regions": ["header", "body", "aside"] },
  "components": [
    {
      "id": "c1",                    // unique within the manifest; the echo target (L10)
      "type": "world.plinth@1",      // type@version — resolves in the registry (R1)
      "region": "header",
      "props":    { "title": "Collections" },
      "bindings": [
        { "source": "kpi.series", "params": { "kpi_key": "dso", "window": "90d" } }
      ]
    }
  ],
  "sheet_equivalent": "district.collections.sheet",   // required when renderer == "W" (§4)
  "intent_shape": "sha256:…",        // the cache key that produced this (§5)
  "issued_at": "2026-07-28T09:14:02Z",
  "ttl_seconds": 120
}
```

Nothing in a manifest is a value the user reads. **Props are labels and structure; every figure is a binding.** That separation is what makes spec §12.1's "prose frames, never asserts numbers" a property of the format rather than a review habit — a manifest physically cannot contain a stale number, because it contains no numbers.

## 2. Certified components in a manifest (L5)

Three rules, all enforced at the client boundary in Zod before a single component mounts:

1. **A component whose `type` begins `certified.` must match its registry `props` schema exactly** — `additionalProperties: false`. An undeclared prop causes the manifest to be **rejected**, not sanitised. Sanitising means rendering a certified surface that somebody tried to modify, which is the attack succeeding quietly.
2. **A certified component's props may not be generative.** The manifest service marks generated text with `x-generative` at emit time; the registry forbids that marker on certified entries (D3 R2).
3. **A certified component carries no `honesty_grade` and may not sit on a twin plane.** L5 is explicit: *"the Glasshouse can simulate but never execute a certified action."* A manifest with `plane: "twin"` containing a `certified.*` component is rejected at schema level — the two facts are mutually exclusive in the type, not merely discouraged.

## 3. `honesty_grade`, mandatory at schema level (L6)

Spec §9.3 says `honesty_grade` is "required on any Glasshouse-derived component (L6, enforced at schema level)". JSON Schema expresses that directly, so it is enforced by the validator rather than by the caller remembering:

```jsonc
{
  "$id": "vihara/manifest/component",
  "type": "object",
  "properties": {
    "id": {"type": "string"}, "type": {"type": "string"},
    "props": {"type": "object"}, "bindings": {"type": "array"},
    "honesty_grade": {"enum": ["replay", "forecast", "unknown", "untested"]},
    "twin_run_id": {"type": ["string", "null"]}
  },
  "required": ["id", "type"],
  "allOf": [
    {
      "if":   { "properties": { "plane": { "const": "twin" } }, "required": ["plane"] },
      "then": { "required": ["honesty_grade"] }
    },
    {
      "if":   { "properties": { "honesty_grade": { "enum": ["replay","forecast","unknown"] } },
                "required": ["honesty_grade"] },
      "then": { "required": ["twin_run_id"],
                "properties": { "twin_run_id": { "type": "string" } } }
    }
  ]
}
```

### 3.1 Four grades, not three — and the fourth is the one that matters

Spec §9.3 names three (`replay`, `forecast`, `unknown`). The shipped code has **four**, and the fourth arrived for a reason worth preserving in the manifest:

* `ai/twin/grading.py` computes exactly three — `Grade.REPLAY`, `Grade.FORECAST`, `Grade.UNKNOWN` — and refuses to *accept* a grade at all (asserted there by reflection, so adding a setter later fails a test).
* `ai/strategy/pipeline.py` adds **`untested`**, because Planning needs to distinguish *never tried* from *tried, ungradable*: `_GRADES_NEEDING_A_RUN = {replay, forecast, unknown}` and `UNTESTED` is the only value that needs no `twin_run_id` behind it.

The second `allOf` branch above is that rule, transcribed: **a grade asserting a simulation happened requires a run id.** Without it, a manifest could carry `replay` for something that never went near the Glasshouse — laundering an untested bet into the strongest grade the system has, which is exactly what STRAT's build refused at the record layer. The manifest layer must refuse it too, because the manifest is what a human actually reads.

`untested` and `unknown` **must not render alike** (art bible §5): one says nobody has tried, the other says we tried and cannot tell. Collapsing them is the single most likely rendering bug in the Glasshouse, and it is invisible unless the renderer is told they are different.

## 4. L9: every W manifest names its sheet

`renderer: "W"` ⟹ `sheet_equivalent` is **required** and must resolve to a real surface id.

L9 is a guarantee, and a guarantee whose exceptions are discovered at G1 is a convention. Making the pointer a required field means an unrepresentable world surface — one with no sheet — cannot be emitted at all, which is a stronger statement than "we will remember to build both".

## 5. The intent-shape cache

Spec §9.3: *"manifests are cached per intent-shape so the same ask yields the same surface (muscle memory)"*. The key:

```
intent_shape = sha256(
    intent_kind ‖ context_ref.kind ‖ sorted(binding sources) ‖
    depth ‖ density ‖ renderer ‖ tenant_entity_defs.version ‖ registry.version
)
```

Deliberately **not** in the key: the tenant id, the user id, the time, and every binding *value*. A manifest is a shape; two tenants asking the same question at the same depth get the same composition and different data. Including the tenant would make muscle memory per-tenant, which is not memory, it is coincidence — and it would multiply the cache by the tenant count for no gain.

Deliberately **in** the key: `tenant_entity_defs.version` and `registry.version`. Those are the two things whose change must invalidate a cached composition, and they are the two most likely to be forgotten.

**Storage:** Redis, TTL 15 minutes, keyed by `intent_shape`. No new table.

### 5.1 Why there is no `ui_manifests` table

Technical §8 sketched one and VG-01 repeats it. Walking it against what the manifests are actually for:

* **Generated (non-certified) manifests need no durability.** They are a cache of a pure function of platform state; losing one costs a re-derivation.
* **Certified manifests are already durable** — they are versioned files in the registry (D3 §3.5), frozen once published, in git.
* **What genuinely needs durability is audit:** *which* manifest was on screen when a human approved something. That is one column, not a table — the certified manifest's `type@version` and its content hash stamped onto the approval record and onto the echo (D5).

So: **no `ui_manifests` table.** A table would have stored, per tenant per surface per render, a document reconstructible from three ids — and the thing the audit actually needs (what the approver saw) would still have been missing, because that is a property of the *response*, not of the manifest store.

## 6. Streaming, and the 300ms floor

Spec §12.1 budgets <300ms to first scaffold. A manifest arrives in **two parts over one response**:

| Part | Contains | Budget |
|---|---|---|
| **Scaffold** | `surface_id`, `renderer`, `layout`, and each component's `id` + `type` + `region` | first byte → paint |
| **Fill** | `props` and `bindings` per component, streamed in region order | after paint |

The client mounts skeletons from the scaffold, then hydrates. Two rules keep this from becoming a source of flicker:

1. **Component identity is fixed in the scaffold.** A fill may not add, remove or retype a component — only fill it. A layout that reshuffles after paint is worse than a slower one.
2. **Certified components do not stream.** They arrive whole or not at all. A half-rendered approval is a certified surface in an unverified state, and L5 does not have a partial mode.

## 7. Refusal, and the "nothing happened" rule

This repo has found the same class of bug three times in one increment: a path whose failure mode is *quietly doing less*. LIB's `search_semantic` returned `[]` through a catch-all so a broken analytics feature looked like agents retrieving nothing; GATE's taint firewall silently permitted; LIB's returning drive file silently stayed superseded. All read as working from every other angle.

A manifest renderer is exactly that shape of code, so the failure modes are specified rather than left to a `try`:

| Situation | Behaviour |
|---|---|
| Unknown component `type` | Render a **visible placeholder** naming the type and the surface, and report it. Never skip it |
| Known type, unsupported `version` < `min_supported` | Refuse the manifest; ask Pragya for the sheet equivalent |
| A binding fails to resolve | The component renders its **empty-state with the reason**, not an empty region |
| Schema validation fails on a `certified.*` component | **Reject the whole manifest.** Fail closed, loudly |
| Schema validation fails elsewhere | Drop the offending component to a placeholder; render the rest |

The asymmetry in the last two rows is deliberate and is the whole safety posture: **certified fails closed, everything else fails visible.** What is forbidden everywhere is failing *silent*.

## 8. Schema-derived re-derivation

Spec §9.3: *"schema-derived forms/tables re-derive automatically when `tenant_entity_defs` versions — new fields appear without any frontend change."*

Mechanism: a `register` or `record-sheet` component's binding carries `entity_def_version`. The version participates in the cache key (§5), so a schema evolution invalidates every cached manifest that reads that object and the next ask re-derives. No frontend deploy, no migration, no manual cache bust.

This is what makes SEGA's T8 schema proposals visible: a field an agent proposed and a human approved appears in the register the next time it is asked for.

## 9. Open item carried into D5

**VP-01** (token storage, D1 §5) lands here with a second reason: a manifest layer that renders generated content is a larger injection surface than the legacy app has — which is VG-23's point, arriving earlier than the gap analysis expected. §2's reject-don't-sanitise rule is the mitigation *inside* the manifest; VP-01 is about what an attacker gets if they nonetheless win.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-28 | v1.0 — the manifest contract. Three things it decides beyond transcribing §9.3. **`honesty_grade` has four values, not three** — `untested` (never tried) must not render like `unknown` (tried, ungradable), and a grade asserting a simulation requires a `twin_run_id`, transcribing STRAT's record-layer refusal into the layer a human actually reads. **There is no `ui_manifests` table** — generated manifests are a cache of a pure function, certified ones are already versioned files in git, and the thing audit genuinely needs (what the approver saw) is a hash on the approval record, not a document store. And **the failure modes are specified**: certified fails closed, everything else fails *visible*, because this repo has now found three bugs whose entire signature was a path quietly doing less. |
