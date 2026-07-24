# Data-Flow Disclosure — Model Subprocessors, Regions & Training Policy

> **Document Class:** Standing tenant-facing disclosure (the subprocessor/DPA-shaped artifact register finding **D5** asks for)
> **Version:** `2026-07-23` — this string is `allow_list.CURRENT_DISCLOSURE_VERSION`. An opt-in recorded against an older version is **refused**; bump both together whenever a material fact below changes.
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

## 6. Platform certification posture

Stated honestly, current state first:

* **Today:** the platform is **not yet** SOC 2 Type II or ISO 27001 certified. It ships the controls those audits look for — per-tenant data isolation (schema/container data plane), encrypted credential storage (AES-256-GCM), 4-level tenancy with role-scoped access, full per-call cost/model attribution, an auditable governance + HITL trail, and egress allow-listing for sandboxed execution.
* **Trajectory:** SOC 2 Type II readiness is the target ahead of enterprise GA; ISO 27001 follows. Neither is claimed until the report exists.
* **Sub-processor changes** will be published here with a version bump, which — by construction — re-prompts every affected tenant to acknowledge before their opt-in continues to count as informed.

---

## Change Log

| Version | Change |
|---|---|
| `2026-07-23` | Initial publication (Increment 5 / FLEET). Six providers listed; conservative default = Anthropic/Google/Azure-OpenAI; GLM (Zhipu), Qwen (Alibaba) and Kimi (Moonshot) registered as `preview` + opt-in only. Closes register **D5**'s publication half. |
