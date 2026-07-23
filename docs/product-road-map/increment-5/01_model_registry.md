# Increment 5 / REG — The Model Registry (closes B12)

> **Status:** ✅ **BUILT** (2026-07-23, branch `inc5/reg`) — all of T1–T5, gates green. Build notes §12.
> **Closes:** register **B12** (model registry too coarse). **Depends on:** the shipped `IntegrationRegistry` / `ModelTaskDefault` / `UsageLog` billing seam. **Feeds:** RTR ([02](./02_router.md)), FLEET ([03](./03_fleet_expansion.md)), EVX ([04](./04_eval_extensions.md)).

---

## 1. The finding this workstream exists to fix

**B12 (Medium):** *Model registry too coarse. Keys like `"gpt"`, `"gemini"` carry no version, region, or price effective-dating — breaks billing reproducibility, deprecation handling, and the "full attribution" audit promise.*

What ships today is **not** a fleet registry — it is a per-company **binding** table:

* `config/models.py::IntegrationRegistry` — one row per (company, `service_sku`) with `provider_name`, `model_name` (e.g. `gemini-2.0-flash`), `internal_cost`, `cost_unit`, encrypted credentials, and a `service_metadata` blob that happens to hold region/project. There is **no version column, no effective-dated price, no capability profile, no global catalog** — every tenant re-declares the same fleet facts, and a price change silently rewrites history so a June invoice can no longer be reproduced.
* `config/models.py::ModelTaskDefault` — maps `task_type → integration_id` with a `routing_mode` of `'single' | 'router'` (the `'router'` value is a stub; the router does nothing today).
* `ai/orm/usage.py::UsageLog` — the billing source-of-truth, keyed to a `sku_id` (FK → `IntegrationRegistry`). It records *what was charged* but cannot answer *which model version, in which region, at what point-in-time price*.

## 2. Decision (Rahul, 2026-07-23)

**Global catalog + per-company binding.** A new **control-plane** table `model_registry` is the fleet catalog. `IntegrationRegistry` keeps per-company credentials and gains a nullable FK into the catalog. Chosen over evolving `IntegrationRegistry` in place because the catalog is the *single* source the router's `eligible()` query reads, and because effective-dated pricing needs a **history table**, not a mutable column — a per-company evolution would duplicate fleet pricing across every tenant and still couldn't reproduce a past invoice.

## 3. The two new control-plane tables

Both are **global** (control-plane Alembic, not tenant-bootstrapped) — the fleet is the same fleet for every tenant; only credentials and allow-listing are per-company.

### 3.1 `model_registry` — the fleet catalog

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `model_key` | String, unique-per-(provider, version, region) | The router-facing stable key, e.g. `claude-opus`, `gemini-2.5-flash`, `mistral-large`, `glm-4.6`, `qwen-2.5-72b`. Family+profile, **not** the raw SDK id. |
| `provider` | String | `anthropic` · `google` · `openai` · `azure_openai` · `mistral` · `zhipu` · `alibaba` · `internal` (the BabyBuddha hole). |
| `model_name` | String | the concrete SDK id, e.g. `claude-opus-4-8`, `gemini-2.5-flash-002`. This is what the adapter is handed. |
| `version` | String | the snapshot/version tag, e.g. `4-8`, `002`, `2025-01`. B12's missing axis. |
| `region` | String | deployment region, e.g. `us-east5`, `us-central1`, `eu-west1`, `global`. B12's missing axis. |
| `capability_profile` | JSONB | `{reasoning_strength: 0..1, tool_reliability: 0..1, max_context: int, latency_class: "strict"|"standard"|"batch", modalities: ["text"|"vision"|"realtime_audio"], supports_tools: bool}` — what the router scores against (§3.2 of the tech doc). |
| `data_flow` | JSONB | D5 sovereignty facts: `{data_region, subprocessor, trains_on_customer_data: bool, default_allowed: bool}`. Read by FLEET's allow-list; see [03](./03_fleet_expansion.md). |
| `status` | String | `preview` · `active` · `deprecated` · `retired`. Only `active` rows are router-eligible. A flip to `active` is a §22.4 admission event (EVX). |
| `created_at` / `updated_at` | DateTime | |

Uniqueness: `(provider, model_name, version, region)` — the same model in two regions is two rows (they price and route differently).

### 3.2 `model_prices` — effective-dated pricing (the reproducibility fix)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `model_registry_id` | UUID FK → `model_registry` | |
| `component_type` | String | `input_token` · `output_token` · `minute` · `character` · `image` · … (mirrors `IntegrationRegistry.component_type`). |
| `unit_price` | Numeric(18,6) | price per `cost_unit`. |
| `cost_unit` | String | e.g. `1k_tokens`, `minute`. |
| `currency` | String(3) | default `USD`. |
| `effective_from` | DateTime (UTC) | inclusive. |
| `effective_to` | DateTime (UTC), nullable | exclusive; `NULL` = current. |

**The invariant:** for a given `(model_registry_id, component_type)` the `[effective_from, effective_to)` windows are non-overlapping and gap-free going back. A price change **closes** the current row (`effective_to = now`) and **inserts** a new open row — it never mutates a price in place. Billing for an event at time *t* resolves the row whose window contains *t*. That is what makes a past invoice reproducible.

### 3.3 The binding edit — `IntegrationRegistry.model_registry_id`

`IntegrationRegistry` gains a **nullable** `model_registry_id` FK → `model_registry`. Nullable is load-bearing: every existing per-company row keeps working un-bound (the router simply won't route it — it falls through to the shipped single-model path). A backfill maps existing rows to catalog rows by `(provider_name, model_name)` where a catalog row exists; unmatched rows stay `NULL` and are logged for ops to reconcile. **Credentials never move to the catalog** — they are per-company and stay on `IntegrationRegistry`.

## 4. Billing reproducibility — how the price flows

Cost is computed today from `IntegrationRegistry.internal_cost` × quantity (the per-company `internal_cost`/`cost_unit`). REG makes this **reproducible without breaking the un-bound path**:

* If the integration is catalog-bound (`model_registry_id` set) → resolve the effective `model_prices` row for `(model, component, event_timestamp)` and price against it. Record the resolved `model_prices.id` in `usage_logs.log_metadata` so the invoice line can be re-derived exactly.
* If un-bound → the current behavior (per-company `internal_cost`) is unchanged.

This is the same "policy in the new package, enforcement at the existing call site" shape TRUST used — the price resolver lives in `ai/intelligence/registry.py`; the billing call site gains one branch.

## 5. The catalog as declared data

Following the connector catalog precedent ([increment-4/02](../increment-4/02_conn_sor.md) §4.1), the fleet is **declared data**, not rows hand-inserted per environment:

* `ai/intelligence/catalog.py` — `FLEET: list[ModelSpec]` declaring the shipped providers (Anthropic / Google / Azure-OpenAI) with `capability_profile`, `data_flow`, `status='active'`, and an initial `model_prices` window. FLEET ([03](./03_fleet_expansion.md)) appends GLM/Qwen/Mistral rows (`status='preview'`, `default_allowed=False`).
* `ai/intelligence/registry.py::install_model_catalog()` — idempotent seeder (upsert by the uniqueness key), called at `main.py` + `worker.py` boot beside the other installers. Re-running never duplicates a row and never rewrites a price window (it opens a new one only when the declared price differs from the current open row).

## 6. The registry service — what the router calls

`ai/intelligence/registry.py::RegistryService`:

* `eligible(modality, min_context, allow_list) -> list[CatalogModel]` — the router's candidate query: `status='active'`, modality supported, `max_context ≥ min_context`, provider in `allow_list`. **This is the only place candidate filtering happens**, so a disallowed provider is never a candidate (§3.4 of the tech doc, D5's "filter before scoring").
* `resolve_price(model_registry_id, component_type, at: datetime) -> ModelPrice` — the effective-dated lookup for billing.
* `capability_profile(model_registry_id) -> dict` — what `scoring.utility()` reads.
* `bind_price(...)` / `deprecate(...)` — admin mutations (the price-window close+insert; the status flip that EVX gates).

## 7. Code Mapping

| Path | What |
|---|---|
| `ai/intelligence/__init__.py` | package init — re-exports **only** the router entry; must not import back toward `ai/llm` (cycle rule, §9). |
| `ai/intelligence/models.py` | `ModelRegistry`, `ModelPrice` ORM (control-plane `Base`, SQLAlchemy 2.0 `Mapped[…]`). |
| `ai/intelligence/catalog.py` | `FLEET` declared data + `ModelSpec` dataclass. |
| `ai/intelligence/registry.py` | `RegistryService` + `install_model_catalog()`. |
| `config/models.py` | **edit** — add nullable `model_registry_id` FK to `IntegrationRegistry`. |
| `migrations/versions/reg001_*.py` | control-plane migration: `model_registry` + `model_prices` + the `IntegrationRegistry` FK; off `conn002`. |
| `billing/*` (price call site) | **edit** — one branch: catalog-bound → effective-dated price; else unchanged. |
| `scripts/typecheck_ai.py` | **edit** — add `"intelligence"` to `CLEAN_PACKAGES`. |

## 8. Testing

* `tests/unit/test_model_registry.py` — the price-window invariant (close+insert, no overlap, point-in-time resolution returns the right window; a change never mutates history); `eligible()` filtering (status, modality, context, allow-list).
* `tests/integration/test_model_registry_db.py` — `install_model_catalog()` idempotence (re-run = no dup rows, no new price window unless the price changed); the `IntegrationRegistry` backfill maps a known `(provider, model_name)` and leaves an unknown one `NULL`.
* `tests/integration/test_billing_reproducibility_db.py` — a usage event priced at time *t₀*, then a price change, then re-derive the *t₀* invoice line and assert it is unchanged (the B12 reproducibility promise, executed).
* **Parity/eval:** the catalog is additive and the billing branch is inert for un-bound rows — but any billing-path change is a parity canary, so `tests/parity tests/eval` runs green before REG merges (§5 convention, [HANDOFF](../HANDOFF.md) §5).

## 9. Risks & gotchas

* **Cycle discipline** (the §5 VOICE lesson): `ai/intelligence/__init__` re-exports only the router; everything else imports submodules directly. `ai/llm/router.py` will import `ai/intelligence/router` — so `ai/intelligence` must never import `ai/llm`.
* **`func` vs `sqlalchemy`** (the §5 PRAGYA lesson): the price-window query uses real column comparisons and a `case`/range test — import `sqlalchemy.case`, not `func.case`, and cover the query with a test that *executes* against Postgres.
* **The nullable FK is not optional.** A non-null FK would require binding every legacy row before the migration applies — it would fail every existing tenant's model resolution. Nullable + backfill + fall-through is the safe path.
* **Never mutate a price row.** The whole reproducibility fix is the close+insert discipline; a test asserts an in-place `UPDATE unit_price` is impossible through the service API.

## 10. Task Plan

1. **T1** — ORM (`models.py`) + migration `reg001` (both tables + the FK), applies/rolls back clean.
2. **T2** — `catalog.py` (shipped providers as declared data) + `RegistryService.install_model_catalog()` idempotent seeder.
3. **T3** — `RegistryService.eligible()` / `resolve_price()` / `capability_profile()` + the price-window invariant tests.
4. **T4** — the `IntegrationRegistry` backfill + the billing price-resolution branch + the reproducibility test.
5. **T5** — add `intelligence` to the strict allowlist; gates green (`typecheck_ai`, layout lint, unit, parity/eval, `*_db`).

## 11. Brainstorm Decisions (Rahul, 2026-07-23)

1. **Global catalog + per-company binding** — decision §2 (Overview §2.1). Not evolving `IntegrationRegistry` in place.
2. **Effective-dated pricing is a history table** (`model_prices`), not a column — reproducibility requires history.
3. **Credentials stay per-company** on `IntegrationRegistry`; the catalog is credential-free.
4. **The FK is nullable + backfilled** — no big-bang binding; un-bound rows fall through to the shipped single-model path.

## 12. Build Notes (2026-07-23) — delta log

### 12.1 What shipped
* `ai/intelligence/` (new strict-typed package): `models.py` (`ModelRegistry` + `ModelPrice` + `ModelStatus`), `catalog.py` (the 8-model shipped fleet as declared data — Anthropic/Google/Azure-OpenAI across reasoning/fast/multimodal tiers), `registry.py` (`RegistryService`: `install_model_catalog`, `backfill_integration_bindings`, `eligible`, `resolve_price`, `capability_profile`).
* Migration **`reg001`** (off `conn002`): `model_registry` + `model_prices` + the nullable `integration_registry.model_registry_id` FK. Apply/rollback/re-apply verified clean.
* `scripts/seed_model_catalog.py` — the reconciling ops seeder (install + backfill).
* Tests: `test_model_catalog.py` (unit, catalog well-formed) · `test_model_registry_db.py` (idempotence, the price-window invariant + reproducible history, `eligible` filtering) · `test_reg_billing_db.py` (backfill binds known / leaves unknown NULL; bound usage stamped, un-bound untouched).

### 12.2 Design deltas (decided during build)
1. **Billing reproducibility is a parity-safe *snapshot*, not a price-source switch.** §4 read "bound rows price against `model_prices`." A bound company's `internal_cost` can differ from the catalog reference price, so switching the charge source would move their bill — a parity-canary violation. Instead: `internal_cost` stays the charge authority (unchanged), and `usage_service.log_usage` snapshots the bound model + the applied unit price into `log_metadata`. Reproducibility comes from the snapshot (immune to later config changes) + the version link; `model_prices` remains the effective-dated *reference* for router cost-estimation and reporting. The un-bound path is byte-identical — parity/eval stayed green.
2. **`intelligence/models.py` imports no consumer model.** §9's "FK target must be registered" was copied from the connector pattern, but the binding FK runs the *reverse* way (`integration_registry → model_registry`), resolved by table name at DDL. So the module imports nothing back toward `config`/`auth`, and a minimal test context (registry-only) needn't register the whole mapper graph. (This was the fix for a mapper-config error the first test hit.)
3. **The seeder is an ops script, not an import-time boot call.** §5 said "called at `main.py` + `worker.py` boot." The shipped boot installers are all in-memory (no async DB startup hook exists), and an import-time DB write breaks on an unmigrated DB. So the idempotent reconciler is `scripts/seed_model_catalog.py` (re-run on deploy) + directly callable by tests — the pattern this codebase already uses for control-plane reference data (the HITL-checkpoint seed).
4. **A legacy-`Column` write needs `setattr`.** `config.IntegrationRegistry` is old-style (`Column`, not `Mapped`), so the backfill's cross-boundary write uses `setattr` to stay `mypy --strict` clean without a `type: ignore`.

### 12.3 Gate results
`typecheck_ai` (250 files, strict, incl. `intelligence`) · layout+de-canary lint · **1499 unit + 2 skipped** · **16 parity/eval** (billing canary intact) · **9 REG tests** (4 unit + 5 `*_db`) · `reg001` apply/rollback/re-apply · seeder idempotent (8 models / 16 price windows; dev-DB backfill bound 6 existing integrations, 12 old models left NULL for ops). **B12 closed** — the fleet now carries version + region + effective-dated price, and a usage row re-derives point-in-time.
