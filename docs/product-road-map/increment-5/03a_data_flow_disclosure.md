# Data-Flow Disclosure — Model Subprocessors, Regions & Training Policy

> **Document Class:** Standing tenant-facing disclosure (the subprocessor/DPA-shaped artifact register finding **D5** asks for)
> **Version:** `2026-07-25` — this string is `allow_list.CURRENT_DISCLOSURE_VERSION`. An opt-in recorded against an older version is **refused**; bump both together whenever a material fact below changes. *(Existing opt-ins keep working — the version is checked when an opt-in is **recorded**, not on every routing call. A bump means the next person to opt in must have read the current text, not that anyone loses access.)*
> **Author:** Buddha Cognitive Lab · **Parent:** [03_fleet_expansion.md](./03_fleet_expansion.md) §5
> **Scope:** where a tenant's prompt/context goes when the platform calls a model, and on what terms.

---

## 1. What leaves the tenant boundary

When an agent step calls a model, the platform sends **only** what that step needs to reason:

* the system prompt + the step's prompt, and the retrieved context assembled for it (KB chunks, record fields, conversation history in scope);
* tool *schemas* (names + parameter shapes) when the step may call tools.

The platform **never** sends: credentials or API keys of any kind, the tenant's encrypted secrets, whole-database or whole-KB dumps, another tenant's data, or the record store itself. Model calls are stateless request/response — no provider is given standing access to tenant systems.

Every call is attributed: which model, in which region, at what point-in-time price, and (when routing is active) *why that model was chosen* — see `routing_decisions` and `usage_logs` ([01](./01_model_registry.md), [02](./02_router.md)).

## 2. Subprocessor list

| Provider (catalog key) | Legal entity | Reached via | Data region | Default-allowed? |
|---|---|---|---|---|
| `anthropic` | Anthropic PBC — served through Google Cloud Vertex AI | Vertex AI endpoint | US (`us-east5`) | ✅ yes |
| `google` | Google LLC (Vertex AI) | Vertex AI endpoint | US (`us-central1`) | ✅ yes |
| `azure_openai` | Microsoft Corporation (Azure OpenAI Service) | Azure region-pinned endpoint | US / EU (per Azure deployment) | ✅ yes |
| `zhipu` | Zhipu AI / Beijing Zhipu Huazhang (BigModel) — **GLM** | OpenAI-compatible endpoint | China (`cn`) | ❌ **opt-in only** |
| `alibaba` | Alibaba Cloud (DashScope) — **Qwen** | OpenAI-compatible endpoint | China (`cn`) | ❌ **opt-in only** |
| `moonshot` | Moonshot AI — **Kimi** | OpenAI-compatible endpoint | China (`cn`) | ❌ **opt-in only** |

> **Status note:** the three opt-in providers are registered in the catalog as `preview`. A `preview` model is **never** a routing candidate. It can only serve traffic after (a) the tenant opts in here, **and** (b) the EVX admission gate flips it to `active` ([04](./04_eval_extensions.md) §3). Both gates must pass.

## 3. Data-region table

Each catalog row carries its `region`, so a residency-sensitive tenant can read its exposure directly off `model_registry` rather than trusting prose:

| `region` | Jurisdiction | Used by |
|---|---|---|
| `us-east5` | United States | Claude (Opus / Sonnet / Haiku) via Vertex |
| `us-central1` | United States | Gemini (Pro / Flash / Flash-Lite) via Vertex |
| `global` | US or EU, pinned per Azure deployment | GPT / GPT-mini via Azure OpenAI |
| `cn` | People's Republic of China | GLM, Qwen, Kimi |

A tenant that must not route outside a jurisdiction should simply not opt into providers outside it; the default set never includes `cn`.

## 4. Training-data policy

**Platform commitment:** HireBuddha does not sell tenant data, and does not use one tenant's data to serve or train anything for another tenant.

Per provider, the relevant question is whether the *vendor* may train on API traffic:

| Provider | Platform's contractual posture |
|---|---|
| Anthropic (via Vertex), Google (Vertex), Microsoft (Azure OpenAI) | **Does not train on our API/enterprise traffic** under the enterprise terms these are consumed on. Catalog flag: `trains_on_customer_data: false`. |
| Zhipu (GLM), Alibaba (Qwen), Moonshot (Kimi) | **Treated as training-capable until a signed DPA says otherwise.** Catalog flag: `trains_on_customer_data: true`. This is the platform's *conservative assumption*, not an assertion about the vendor's current terms — and it is precisely why these providers are opt-in rather than default-on. A tenant opting in is accepting that posture. |

**BabyBuddha / OmniBuddha (road map, Increment 7 — the statement D5 demands):** the planned in-house family is **post-trained on the platform's own agent traces**, under the export/retention policy, and **never on another tenant's data**. It is not built or trained today. Before any such model may be flipped `active`, this disclosure will be updated to state exactly what trace data was used, and it must pass the same EVX admission gate as any vendor model.

## 5. Why the default list is conservative

The default allow-list is exactly **the providers already carrying production traffic on enterprise terms with a US/EU data region** (Anthropic, Google, Microsoft). Everything else is registered but off.

This is a deliberate reversal of the state D5 flagged, where *every* provider — including China-hosted ones — was allowed by default. Growth of the fleet and the sovereignty decision now land together: adding a model to the catalog grants it nothing.

**Opting in is an explicit, recorded, revocable act.** `company_provider_optin` stores which provider, which disclosure version was acknowledged, by which user, and when. Revocation takes effect on the very next routing call (the allow-list is read live, never cached).

## 6. What the platform learns across tenants

*(Added 2026-07-25 — Increment 6 / LEARN. Increment-6 charter decision 8 requires this to be stated exactly, and it is the reason the pooled path carries **no opt-out**: there is nothing here to opt out of that is yours.)*

The platform improves its own model routing by watching how models behave across the whole fleet. **Learning is split at the schema level**, and the split is structural rather than a query convention:

**Pooled across tenants — platform telemetry only.** One table, `platform_observations`, whose entire column set is:

| Column | What it holds |
|---|---|
| `metric` | one of four fixed words (`route_outcome`, `model_failure`, `fallback_used`, `admission_score`) |
| `model_registry_id` | which model in the platform's own catalog |
| `task_type` | the kind of step, from a fixed vocabulary (`chat`, `extract`, …) |
| `reason` | why the router chose as it did (`pinned` / `rule` / `auto` / `fallback` / `downshift`) |
| `bucket_day` | the calendar day |
| `observations`, `successes`, `latency_ms_sum`, `cost_usd_sum` | counters |

**That is the whole table.** It has **no `company_id` column**, no free-text column, and no JSON column — so it is not that we choose not to put your business content there; there is nowhere to put it. A prompt, a customer name, a record or a document could not be written to this table without changing its schema, and a test asserts the column list exactly so that change cannot happen quietly.

Two further protections:

* **A k-anonymity floor.** Buckets are built by a daily job that reads per-tenant routing records and drops any group contributed to by fewer than **three** distinct companies. Below the floor the data is **discarded**, not held. This stops a bucket being attributable to you by inference — for example, if you were the only tenant using a particular model.
* **A bounded effect.** Pooled observations may adjust a model's *ranking* by at most ±0.2 on a 0–1 scale. They can never activate, deactivate or remove a model; that requires the separate EVX admission gate.

**Private to your tenant — never pooled.** Everything derived from what your business actually does stays inside your tenant and is scoped by a non-nullable company id: your KPI history, your agents' learned rules and charter tuning, per-agent behavioural series, and per-user interface preferences. None of it is aggregated across tenants, and none of it is used to serve any other tenant — the commitment in §4 above, applied to learning as well as to model calls.

**Why pooled telemetry has no opt-out.** It contains no tenant data, by the schema guarantee above, and an opt-out would degrade routing quality for everyone with no privacy gain to anyone. This is deliberately asymmetric with the opt-in for foreign providers (§5): that governs *where your data physically goes*; this governs aggregate telemetry that by construction contains none of it. **If the guarantee above ever fails, this justification fails with it** — the two are a single commitment, not two independent ones.

## 7. Platform certification posture

Stated honestly, current state first:

* **Today:** the platform is **not yet** SOC 2 Type II or ISO 27001 certified. It ships the controls those audits look for — per-tenant data isolation (schema/container data plane), encrypted credential storage (AES-256-GCM), 4-level tenancy with role-scoped access, full per-call cost/model attribution, an auditable governance + HITL trail, and egress allow-listing for sandboxed execution.
* **Trajectory:** SOC 2 Type II readiness is the target ahead of enterprise GA; ISO 27001 follows. Neither is claimed until the report exists.
* **Sub-processor changes** will be published here with a version bump, which — by construction — re-prompts every affected tenant to acknowledge before their opt-in continues to count as informed.

---

## Change Log

| Version | Change |
|---|---|
| `2026-07-25` | **§6 added — what the platform learns across tenants** (Increment 6 / LEARN, charter decision 8). Names the pooled table's complete column set, the absence of a company column, the three-contributor k-anonymity floor, the ±0.2 bound on its effect, and what stays private per tenant. States plainly that the no-opt-out posture rests on the schema guarantee and falls with it. Certification posture renumbered to §7. |
| `2026-07-23` | Initial publication (Increment 5 / FLEET). Six providers listed; conservative default = Anthropic/Google/Azure-OpenAI; GLM (Zhipu), Qwen (Alibaba) and Kimi (Moonshot) registered as `preview` + opt-in only. Closes register **D5**'s publication half. |
