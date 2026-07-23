# Increment 5 / FLEET — Fleet Expansion + Data-Flow Disclosure (closes D5)

> **Status:** ✅ **BUILT** (2026-07-23, branch `inc5/rtr`) — all of T1–T5, gates green. Build notes §13.
> **Closes:** register **D5** (data-flow disclosure / sovereignty). **Depends on:** REG ([01](./01_model_registry.md)) for the catalog, RTR ([02](./02_router.md)) for the allow-list filter, **EVX ([04](./04_eval_extensions.md)) as the activation gate.** **Builds as a co-dependent pair with EVX** ([00](./00_overview.md) §4).

---

## 1. The finding this workstream exists to fix

**D5 (High):** *Data-flow disclosure gaps. Default `allow_list` includes every provider — Zhipu/Alibaba on by default is a data-sovereignty problem. No subprocessor list/DPA story; no statement on whether BabyBuddha trains on tenant data; no platform certification posture.*

The fix has three parts, all here: a **conservative default allow-list**, a **per-tenant opt-in with a recorded disclosure**, and a **published data-flow disclosure doc** (subprocessor list, data regions, training-data policy). The fleet grows — GLM (Zhipu), Qwen (Alibaba), Kimi (Moonshot AI) join the catalog — but growth and sovereignty land together, never fleet-first.

## 2. Decision (Rahul, 2026-07-23)

**Conservative default; GLM/Qwen/Kimi opt-in with disclosure.** The default allow-list is the providers already in production use — **Anthropic, Google, OpenAI/Azure**. **GLM (Zhipu), Qwen (Alibaba), and Kimi (Moonshot AI) are all registered but `default_allowed=False`** — each is China-hosted, so a tenant must opt in explicitly, and the opt-in records a disclosure. (Decision update, 2026-07-23: Kimi replaces the originally-scoped Mistral, so **all three** fleet-expansion providers are opt-in — there is no default-allowed EU provider, a strictly more conservative D5 posture.) Chosen over region-gating (a bigger config surface, needs a residency field per tenant we don't have yet) and over the doc-criticized all-on default.

## 3. The default allow-list + the opt-in

### 3.1 Where "default-allowed" lives

The catalog row carries it: `model_registry.data_flow.default_allowed` (bool), set in `catalog.py`. `RegistryService.eligible(...)` already filters on the allow-list *before scoring* ([02](./02_router.md) §4) — FLEET makes the **effective** allow-list for a company:

```
effective_allow(company) = { providers where default_allowed } ∪ { providers the company opted into }
```

### 3.2 `company_provider_optin` (the auditable disclosure, migration `fleet001`)

A small dedicated table — chosen over a JSON blob on `companies` because D5 wants an **auditable disclosure record** (who opted into what, when, having seen which disclosure version):

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `company_id` | UUID FK → companies | |
| `provider` | String | `zhipu` · `alibaba` · … |
| `disclosure_version` | String | the [03a](#3a) doc version the admin acknowledged. |
| `opted_in_by` | UUID FK → users | who accepted. |
| `opted_in_at` | DateTime | |
| `revoked_at` | DateTime, nullable | opt-in is revocable; a revoke drops the provider from `effective_allow` immediately. |

`ai/intelligence/allow_list.py::effective_allow(company_id)` resolves the union; the router calls it to build `signals.allow_list`. An opt-in with no matching current disclosure version is refused — you cannot opt into a provider without acknowledging its current data-flow terms.

## 4. The fleet adapter seam (tested, not live)

GLM (Zhipu), Qwen (Alibaba DashScope), and Kimi (Moonshot AI) all expose **OpenAI-compatible** chat endpoints. So one adapter serves all three:

* `ai/llm/openai_compat_adapter.py::OpenAICompatAdapter(base_url, api_key, model_name, service_metadata, transport=None)` — mirrors the shipped adapter interface (`generate`, `generate_with_tools_react`). The `base_url` selects the provider; the `transport` is **injectable** so tests run against fakes (the Zoho `MCPClient` pattern, [increment-4/02](../increment-4/02_conn_sor.md) §6). No live call is made in this increment.
* `ai/llm/router.py::_get_adapter` — **edit**: map `zhipu` / `alibaba` / `moonshot` → `OpenAICompatAdapter` with the provider's `base_url` (from `service_metadata`).
* `catalog.py` — append GLM/Qwen/Kimi rows with `capability_profile`, `data_flow` (`default_allowed`: **all `False`** — every one is China-hosted, opt-in), an initial `model_prices` window, and `status='preview'` (not `active` — only the EVX gate flips them to `active`, §6).

## 5. <a id="3a"></a>The data-flow disclosure doc (D5's publication half)

Authored during the build as `increment-5/03a_data_flow_disclosure.md` — the standing subprocessor/DPA-shaped artifact D5 asks for. Contents:

1. **Subprocessor list** — per provider: legal entity, the data region a call runs in, and what leaves the tenant boundary (prompt + context; never credentials or the record store).
2. **Data-region table** — each `model_registry.region` mapped to a jurisdiction, so a residency-sensitive tenant can read its exposure directly off the catalog.
3. **Training-data policy** — explicit per provider: does the vendor train on API traffic (Anthropic/OpenAI-API/Google-Vertex: no; GLM/Qwen/Kimi: stated per their terms and the reason they are opt-in). **And the BabyBuddha statement D5 demands:** the in-house family (Inc 7) post-trains on the platform's *own* agent traces under the export/retention policy — never on another tenant's data, and the fact is disclosed here before any such model can be `active`.
4. **Conservative-default rationale** — why Anthropic/Google/OpenAI are default-on and Zhipu/Alibaba/Moonshot are opt-in.
5. **Platform certification posture** — the SOC 2 / ISO 27001 roadmap statement (honest current state + trajectory), so the doc is the single place the compliance question is answered.

Publishing this doc + shipping the conservative default + the recorded opt-in is what closes D5.

## 6. Activation is gated by EVX (the co-dependency)

A catalog row ships `status='preview'`. **A provider becomes router-eligible only when its row flips to `status='active'`, and that flip is a §22.4 admission event** ([04](./04_eval_extensions.md)): the eval-harness delta runs the candidate against the incumbent on the affected task classes and admits only on non-inferiority within cost budget. So the FLEET adapters and rows can all land, but **no new provider actually serves traffic until EVX passes it** — and even then only to a canary cohort first (§22.3). This is why the build order is REG → RTR → EVX → FLEET-activation ([00](./00_overview.md) §4).

## 7. The honest limit (carried from Inc-4 precedent)

No live GLM/Qwen/Kimi call is made in this increment. Every external call is faked through the injectable transport. Live binding — real `base_url` + credentials + the EVX admission run against the live endpoint — is **activation-time ops**, the same discipline voice go-live and the Zoho connector carry ([increment-4/02](../increment-4/02_conn_sor.md) §12.4). The seam is proven; the wire is an ops step.

## 8. Code Mapping

| Path | What |
|---|---|
| `ai/llm/openai_compat_adapter.py` | the OpenAI-compatible adapter (injectable transport). |
| `ai/llm/router.py` | **edit** — `_get_adapter` maps zhipu/alibaba/moonshot. |
| `ai/intelligence/catalog.py` | **edit** — GLM/Qwen/Kimi rows (`status='preview'`, `default_allowed` per §4). |
| `ai/intelligence/allow_list.py` | `effective_allow(company_id)` + opt-in resolution. |
| `ai/intelligence/models.py` | **edit** — `CompanyProviderOptin` ORM. |
| `ai/intelligence/api.py` | **edit** — `/ai/intelligence/providers` (list + opt-in/revoke, disclosure-version-checked). |
| `migrations/versions/fleet001_*.py` | `company_provider_optin`; off `rtr001` (or `evx` head if EVX lands first). |
| `increment-5/03a_data_flow_disclosure.md` | the D5 disclosure doc (authored in this build). |

## 9. Testing

* `tests/unit/test_allow_list.py` — `effective_allow` = defaults ∪ opt-ins; a revoked opt-in drops immediately; an opt-in without a current disclosure version is refused; the router never scores a provider outside `effective_allow`.
* `tests/unit/test_openai_compat_adapter.py` — request shaping + tool-call parsing against a fake transport; a provider error surfaces to `fallback.py`.
* `tests/integration/test_provider_optin_db.py` — opt-in/revoke round-trip; the disclosure-version guard.
* `tests/eval` — a **fleet-selection golden**: with GLM opted in, a low-complexity no-tool step *may* route to the cheaper GLM (once `active`); with GLM not opted in, it never does. Proves D5's filter and the cost benefit in one test.

## 10. Risks & gotchas

* **Preview ≠ eligible.** The single most important invariant: a `preview` row is never a router candidate. A test asserts `eligible()` excludes non-`active` rows, so a half-onboarded provider can't leak into production routing.
* **Opt-in must be revocable and it must bite instantly** — `effective_allow` reads live, no cache that outlives a revoke.
* **New attribution check** — the fleet adapters make ordinary tenant LLM calls (tenant-initiated), so no new attribution; but the EVX admission runs they gate *do* (`MODEL_ADMISSION`, platform-initiated — [04](./04_eval_extensions.md)).
* **Credentials still per-company** — an opted-in provider needs a per-company `IntegrationRegistry` binding with credentials before it can serve; opt-in grants *permission*, not connectivity.

## 11. Task Plan

1. **T1** — `OpenAICompatAdapter` + `_get_adapter` mapping + the adapter tests (fake transport).
2. **T2** — GLM/Qwen/Kimi catalog rows (`preview`) + `capability_profile`/`data_flow`.
3. **T3** — `company_provider_optin` (migration `fleet001`) + `allow_list.effective_allow` + the opt-in API, disclosure-version-guarded.
4. **T4** — `03a_data_flow_disclosure.md` (subprocessor/region/training-data/cert posture).
5. **T5** — the fleet-selection eval golden; gates green; **provider activation stays behind EVX** (§6).

## 12. Brainstorm Decisions (Rahul, 2026-07-23)

1. **Conservative default; GLM/Qwen/Kimi opt-in with disclosure** — Overview §2.4. All three fleet-expansion providers are China-hosted → all opt-in; no default-allowed EU provider (Kimi replaced Mistral, 2026-07-23).
2. **Opt-in is an auditable table**, not a JSON flag — D5 wants a record of who accepted which disclosure, when.
3. **One OpenAI-compatible adapter** for the three, injectable transport, no live call — the Inc-4 tested-seam precedent.
4. **Activation is EVX-gated** — a provider flips to `active` only through the §22.4 admission check, then canary-first.

## 13. Build Notes (2026-07-23) — delta log

### 13.1 What shipped
* `ai/llm/openai_compat_adapter.py` — one adapter for the OpenAI-compatible fleet (GLM / Qwen / Kimi), `base_url` per provider, **injectable transport**; `_get_adapter` maps the three providers and their aliases (`glm`, `qwen`/`dashscope`, `kimi`).
* `catalog.py` — the three rows as `status='preview'`, `default_allowed=False`.
* `ai/intelligence/allow_list.py` — `effective_allow` (default-allowed ∪ opted-in), `opt_in` / `revoke`, `CURRENT_DISCLOSURE_VERSION`; wired into `IntelligenceRouter._enrich` so the filter runs **before scoring**.
* `company_provider_optin` + migration **`fleet001`**; `GET /ai/intelligence/providers`, `POST …/opt-in`, `POST …/revoke`.
* [03a_data_flow_disclosure.md](./03a_data_flow_disclosure.md) — the published D5 artifact (subprocessors, regions, training policy, BabyBuddha statement, certification posture).
* Tests: `test_openai_compat_adapter.py` (request shaping, tool-call parsing, ReAct loop, base-url resolution, router mapping) · `test_provider_optin_db.py` (defaults vs fleet, disclosure guard, opt-in/revoke, **the D5 property**) · `test_model_catalog.py` split into shipped/expansion cohorts.

### 13.2 Design deltas (decided during build)
1. **Kimi replaces Mistral (owner decision, 2026-07-23) — so *every* expansion provider is opt-in.** The design had Mistral default-allowed (EU-hosted, clears the conservative bar). With Kimi (Moonshot AI, China-hosted) in its place, all three of GLM/Qwen/Kimi are `default_allowed=False` and the default set is exactly the three shipped providers. This is **strictly more conservative** than designed and simplifies the D5 story: the opt-in cohort is uniform.
2. **`trains_on_customer_data=true` on the three is a *posture*, not a vendor claim.** Recorded as the platform's conservative assumption pending a signed DPA — which is the stated reason they are opt-in. [03a](./03a_data_flow_disclosure.md) §4 says so explicitly rather than asserting vendor behaviour.
3. **The allow-list is enforced in `_enrich`, not only in `eligible()`.** §3.1 put the filter in `RegistryService.eligible`; the router's real candidate path is `_candidates` (the company's *credentialed* models, [02](./02_router.md) §12.2 delta 1). So `_enrich` computes `effective_allow` and stamps `signals.allow_list`, which `_candidates` filters on — the filter lands on the path routing actually takes, and the allow-list is recorded in the decision's signal snapshot for audit.
4. **Two independent gates, deliberately.** Tenant consent (D5 allow-list) and EVX admission (`status='active'`, §22.4) are separate and both required. The D5 property test proves consent alone is checked even for a model that is already catalog-`ACTIVE` and fully credentialed.

### 13.3 The honest limit
**No live GLM / Qwen / Kimi call is made.** Every call in test goes through the injected transport; the live path (`AsyncOpenAI` against `base_url`) is written but unexercised. Live binding — real endpoint + credentials + an EVX admission run against the live model — is **activation-time ops**, the same discipline voice go-live and the Zoho connector carry.

### 13.4 Gate results
`typecheck_ai` (259 files, strict) · layout lint · **parity/eval 16** · **1523 unit** (+9) · **24 Inc-5 integration** (all workstreams together) · `fleet001` apply/rollback/re-apply. **D5 closed** — conservative default, auditable revocable opt-in, and the published disclosure.
