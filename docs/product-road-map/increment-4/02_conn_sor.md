# Increment 4 / CONN + SOR — The Connected Business

> **Document Class:** Increment Design & Implementation Plan (workstreams 2 + 3)
> **Author:** Buddha Cognitive Lab (drafted by Claude, decisions by Rahul)
> **Created:** 2026-07-23 · **Status:** Design — decisions locked (§2), pre-build
> **Parent:** [00_overview.md](./00_overview.md) §3 (workstreams CONN + SOR) · [build_roadmap.md](../build_roadmap.md) §4 (Increment 4)
> **Prerequisite:** Inc-1 SCH (records/links, the reserved `sor` column) + SIG (signal bus) + the shipped **MCP adapter** (`ai/tools/mcp/`).

This one doc covers **both** charter workstreams — CONN (the connector catalog) and SOR (per-object mastering) — because they are one machine: you cannot master an object *through* a connector that does not exist, and the flagship vertical (Zoho Books) exercises both at once. The [00_overview.md](./00_overview.md) §3 rows for CONN and SOR both point here.

---

## 1. The finding this workstream exists to fix

The platform is an island. A tenant's Accounts, Invoices, and Vendors live in HireBuddha's tenant DB and *nowhere the tenant already works* — their QuickBooks, their bank feed, their calendar. Register **B4** named the system-of-record ambiguity; the roadmap's Increment 4 answers it: **the tenant's existing systems join the loop without a migration — or HireBuddha *is* all their systems.**

Two halves:

* **CONN** — the §6.6 connector catalog, so an agent can *reach* an external system through the governed tool path.
* **SOR** — per-object mastering (technical §21), so a reached object has one declared master, a mirror, write-back, and conflict resolution — never two silent copies drifting apart.

The standalone case stays the norm, not the fallback: a tenant with no external systems runs entirely on the predefined HBS (§10.3), HireBuddha mastering everything. CONN/SOR is what lets a tenant who *does* have a CRM keep it.

## 2. Decisions Taken (Rahul, 2026-07-23 — do not re-open during build)

The clarifying round (grounded in the shipped MCP seam + the SoR spec) resolved four questions:

1. **Breadth over depth — build the full §6.6 catalog**, not a single thin slice. The increment maximises integration *surface*. Concretely (given decisions 2–4 and the VM's credential limits, §9): build the catalog + binding + mastering **machine**, register **every** §6.6 row as a bindable catalog entry, and prove the machine end-to-end on **one deep vertical (Zoho Books)**. "Full catalog" = every row registered and bindable; not 19 live integrations wired on a credential-less dev box.
2. **Zoho Books is the flagship** first connector — Indian-ICP-aligned, modern REST + OAuth2, good sandbox.
3. **Prefer real external MCP servers**; fall back to our own adapter where none exists (Zoho Books has no canonical server today → it is an own-adapter). The `MCPClient` Protocol is the contract either way.
4. **Credentials are per-Company** (the shipped `IntegrationRegistry.encrypted_api_key` pattern). This is the simple path and reuses existing machinery.

**Two consequences, recorded honestly (not silently):**

* **D2 does not close here.** Per-company credentials are exactly what register **D2** flags as defeating entity-level SoD (vendor-onboarding and vendor-payment sharing one ERP credential). D2 moves to **deferred** — see §7. Closing it later is a per-Process credential-grant layer over the same binding table (§6.4), not a rebuild.
* **C2 (HUMAN_TASK step type + worker surface) is deferred.** The overview assigned it to SOR, but it is physical-fulfillment machinery, cleanly separable from mastering. It is not in this increment's scope; §7.

## 3. The seam — how a connector reaches the governed loop

The shipped `ai/tools/mcp/` is the substrate, and its shape is already right:

* **`MCPClient` is a transport-agnostic Protocol** (`list_tools()` / `call_tool()`). A real external server (official MCP SDK over stdio/HTTP/SSE) **or** an own-adapter wrapping a vendor REST API satisfies it *identically*. That is why decision 3 costs us nothing architecturally: both backends land behind one contract.
* **`bind_mcp_server` → `MCPToolAdapter`** already gives us: read-only-first posture (a destructive/un-hinted tool is refused unless named in `write_allow`), per-company `tool_allow`, `mcp` cost attribution, and registration as an EXPERIMENTAL tenant tool gated by the `tools.experimental.<name>` opt-in.

CONN's job is to make that seam **persistent, cataloged, and credentialed**; SOR's job is to put a **mastering discipline** behind the writes those tools perform. Neither replaces the seam.

**One governance path (standing rule 1).** A connector tool is a categorised external effect: it flows through the same PolicyGate every other tool does. A write-back to an external accounting system is a money/record act — it needs a `CATEGORY_RULES` + `TOOL_CATEGORY_MAP` entry (governance §5 gotcha) or it is ungoverned. CONN adds the categories; it does not add a second gate.

## 4. CONN — the connector catalog, binding, and credentials

### 4.1 The catalog (the ~19 §6.6 rows as declared data)

A `ConnectorCatalog` — a hand-authored, code-resident manifest (the same pattern as the Solo Pack's `PROCESS_GROUPS`), one entry per §6.6 row:

```python
@dataclass(frozen=True)
class ConnectorDef:
    connector_id: str          # "zoho_books", "plaid_bank_feed", "google_calendar", ...
    domain: str                # "finance", "legal", "sales", "operations", "knowledge", ...
    display_name: str
    backend: ConnectorBackend  # MCP_SERVER | OWN_ADAPTER
    server_ref: str | None     # for MCP_SERVER: the published server package / URL hint
    adapter: str | None        # for OWN_ADAPTER: the dotted path to the MCPClient impl
    masters: tuple[str, ...]   # canonical object names this connector can master (SOR)
    default_write_allow: tuple[str, ...]  # destructive tools permitted by default (usually empty)
    auth: AuthKind             # OAUTH2 | API_KEY | GATEWAY
    cost_sku: str              # the IntegrationRegistry SKU for `mcp` metering
```

All §6.6 rows are declared: Bank Feed (Plaid), Payout Rails (Stripe/Wise), Tax Matrix (Avalara), E-Signature (DocuSign), KYB (Middesk), Rich Comms (Slack/Teams), Helpdesk (Jira/Linear), Enrichment (Apollo), Calendar (Google/Graph), HRIS (Gusto/Rippling), Inventory (ShipStation/Shopify), Knowledge Connectors (Notion/Drive/SharePoint), Enterprise Systems (CRM/ERP/**Accounting=Zoho**/HRMS). Rows already backed by shipped platform primitives (Tenant Data Query, OCR, Translation, Evidence Store, Alerting, Social) are marked `backend=OWN_ADAPTER, adapter=<shipped>` — cataloged, not rebuilt.

Registering a row is data. **Binding** a row for a company is the live step, and that is where credentials and the transport enter.

### 4.2 Binding persistence

Today `MCPServerBinding` is an in-memory dataclass — a bound server evaporates on restart. CONN persists it:

```
connector_bindings         (control-plane)
  id, company_id, connector_id (→ catalog),
  transport_config JSON,        -- stdio cmd / HTTP URL / gateway host
  tool_allow JSON, write_allow JSON,
  credential_ref,               -- FK into the encrypted credential store (§4.3)
  cost_sku, status,             -- ACTIVE | PAUSED | ERROR
  created_at, updated_at
  UNIQUE (company_id, connector_id)
```

Boot (`main.py` + `worker.py`) rehydrates ACTIVE bindings into live `MCPServerBinding`s via `bind_mcp_server`, exactly the Solo-Pack-tools entry-point pattern (§5 gotcha). A bind failure marks the row `ERROR` and emits `incident.platform` — it never crashes boot.

### 4.3 Credentials — per-Company (decision 4)

Reuse the shipped encryption path (`common/security.py` + the `encrypted_api_key` pattern on `IntegrationRegistry`, and `social_connection_service` for OAuth token sets). A `connector_credentials` row holds the encrypted secret/OAuth token set per `(company_id, connector_id)`; `credential_ref` on the binding points at it. OAuth refresh rides the existing social-connection refresh discipline.

**Scope: per-company.** Every agent of the tenant that is permitted the connector tool uses the one tenant credential. Least-privilege *between agents* is not enforced at the credential layer in this increment — see D2 in §7.

### 4.4 The two backends

* **`MCP_SERVER`** — a real `MCPClient` over the official SDK transport (stdio for local servers, HTTP/SSE for hosted). The transport config lives on the binding. Preferred where a credible server exists.
* **`OWN_ADAPTER`** — an `MCPClient`-conforming class that wraps a vendor REST API and *presents* it as `list_tools()`/`call_tool()` with proper `readOnlyHint`/`destructiveHint` annotations, so the read-only-first posture and `write_allow` curation apply unchanged. **Zoho Books is the reference own-adapter** (`connectors/zoho_books/`): OAuth2, `list_invoices`/`get_invoice` (read-only) + `create_invoice`/`update_invoice` (destructive, write-back).

## 5. SOR — per-object mastering (technical §21)

### 5.1 Declaration — already pre-wired

`TenantEntityDef.sor` exists from Inc-1 SCH (the column comment reads *"reserved; unused until Increment 4"*). SOR gives it meaning: `{"master": "hirebuddha" | "external", "connector_id": "...", "write_back": true}`. Pragya's onboarding (functional §4.3 step 2) proposes it per object from the connected systems; the tenant confirms. Default stays `hirebuddha` (the standalone norm) — an object only becomes externally mastered when the tenant says so.

### 5.2 Mirror rows (external master)

`TenantRecord` gains `sor` + `external_ref` JSON (migration `sor001`):

```
sor          -- {"master": "external", "connector_id": "zoho_books"}
external_ref -- {"connector": "zoho_books", "external_id": "...", "etag": "...", "synced_at": "..."}
UNIQUE (company_id, entity_def_id, (external_ref->>'external_id'))  -- one mirror per external object
```

* **Reads serve the mirror.** Staleness is bounded by sync cadence (§5.4). No read blocks on a live external call.
* **Writes go through the connector first (write-back).** The record service, on a write to an externally-mastered object, calls the connector's write tool, and updates the mirror **only on confirmation** (the returned external id/etag). A failed write-back changes nothing locally and retries under §18 backoff — the local mirror never shows a write the master rejected.
* **Master wins conflicts.** A divergent concurrent external edit (detected by etag mismatch on sync) overwrites the mirror and raises **`sync.conflict`** carrying the losing local delta; the owning Process (or HITL) reviews it. No silent merge. This is stricter than the §23.2 CAS rule that governs HireBuddha-mastered records — external state never loses to a local write.

### 5.3 Signals

Two new `SignalTypes` beside the existing `object.change_proposed`/`object.write_conflict`:

* **`object.synced`** — an external change landed in the mirror (dedupe on the external event id). Enters the loop like any signal; a Process can trigger on it (e.g. "invoice paid externally → close the AR chase").
* **`sync.conflict`** — write-back lost to a concurrent master edit; carries the losing delta for review.

### 5.4 Sync jobs

Mastering needs the mirror kept fresh:

* **Webhook producer** — where the external system offers webhooks (Zoho, Stripe, DocuSign), a signal producer (the `signals/*_inbound.py` pattern) turns an external event into `object.synced`, counterparty-trust-stamped and dedupe-keyed on the external event id.
* **Cron sweep** — where it does not, a per-connector poll (the SIG sweeper cadence) diffs by etag/`updated_at` and emits `object.synced` for changes. Re-embedding/re-chunk of synced documents is **platform-initiated** and draws on B13's platform budget (the RETR precedent) — a tenant's mirror refresh must not silently burn the tenant's wallet.

### 5.5 Ownership migration (HITL-gated)

Flipping `sor.master` — the tenant retires a CRM, or adopts one later — is an explicit operation, never implicit: it backfills mirrors, rewrites links (§19), and is gated by a HITL checkpoint (`before_sor_migration`). A tenant going from HireBuddha-master to external-master imports the external objects as mirrors and rewrites the graph edges to point at them; the reverse promotes mirrors to native records. One direction at a time, always reviewed.

## 6. The flagship vertical — Zoho Books accounting

The one deep vertical that proves the whole machine, end-to-end, against a **fake Zoho client** (§9):

1. **Bind** `zoho_books` for a company (own-adapter, per-company OAuth credential).
2. **Declare** the canonical **Invoice** object `sor.master = external, connector = zoho_books, write_back = true`.
3. **Sync in**: a Zoho webhook / sweep emits `object.synced` → an Invoice **mirror** row with `external_ref`.
4. **Read**: the AR-chase Process (P10) reads the mirror — no live call on the read path.
5. **Write-back**: P10 marks an invoice reminded/updated → the record service calls Zoho `update_invoice` first → mirror updates on confirmation → PolicyGate saw the categorised write.
6. **Conflict**: a concurrent external edit → `sync.conflict` with the losing delta → HITL review.

This closes the SOR half of B4 for a real accounting object and deepens the Solo Pack's AR/bookkeeping immediately — the roadmap's stated reason accounting goes first.

## 7. Register findings — status after these decisions

| Finding | Charter said | Actual (per §2 decisions) |
|---|---|---|
| **B4** system-of-record | close (design already done) | **SOR machine built + proven on Zoho** — the mastering half lands; broaden per connector as bindings go live |
| **D2** per-agent credential scoping | "close here or never" | **Deferred.** Per-company creds chosen for simplicity; a shared credential leaves entity-SoD unenforced at the credential layer. Closing it later = a per-Process grant layer over `connector_bindings` (§4.4). Recorded in the register as deferred, not closed. |
| **C2** human-task step type | close (assigned to SOR) | **Deferred.** Physical-fulfillment machinery, separable from mastering; not in scope this increment. |

**This increment's CONN/SOR path closes no register finding outright** — it builds the connector+mastering machine and moves B4's implementation forward, while D2 and C2 are explicitly carried. That is a change from the charter's promise, made by decision §2 and documented here rather than glossed.

## 8. Code Mapping

| Piece | Where | Notes |
|---|---|---|
| Connector catalog | `ai/connectors/catalog.py` | the §6.6 manifest (`ConnectorDef`, `CONNECTOR_CATALOG`) |
| Binding persistence | `ai/connectors/models.py` (`connector_bindings`, `connector_credentials`) + migration `conn001` | control-plane |
| Binding service | `ai/connectors/service.py` | activate/pause/rehydrate; wraps `bind_mcp_server` |
| Credentials | `ai/connectors/credentials.py` | reuses `common/security` encryption + social OAuth refresh |
| Boot rehydrate | `main.py` + `worker.py` | ACTIVE bindings → live `MCPServerBinding`s (entry-point pattern) |
| Zoho own-adapter | `ai/connectors/zoho_books/` (`client.py` = `MCPClient` impl, `mapping.py` = Invoice↔canonical) | reference own-adapter |
| SOR mirror columns | `ai/tenant_schema/models.py` (`TenantRecord.sor`, `external_ref`) + migration `sor001` | tenant-DB |
| Write-back + master-wins | `ai/tenant_schema/record_service.py` (extended) | write-back-first on externally-mastered writes |
| SOR signals | `ai/signals/models.py` (`OBJECT_SYNCED`, `SYNC_CONFLICT`) | beside the SCH object.* signals |
| Sync producers/sweep | `ai/connectors/sync/` (`webhook.py`, `sweep.py`) | `object.synced` producer + cron |
| Ownership migration | `ai/connectors/sor_migration.py` | HITL-gated `sor.master` flip |
| Governance categories | `ai/governance/authority.py` | connector write categories → PolicyGate |
| Router / admin | `ai/connectors/router.py` (`/ai/connectors/*`) | catalog list, bind, status |

`ai/connectors/` is a new package → **add it to the strict-typing allowlist** (`scripts/typecheck_ai.py`).

## 9. Testing — against fakes, and the honest live-binding boundary

**What is built and tested here** (unit + integration, no external network):

* The catalog, binding persistence, rehydrate, credential encrypt/decrypt.
* The SOR machine — mirror create, reads-serve-mirror, write-back-first (success + write-back-failure-changes-nothing), master-wins conflict → `sync.conflict`, `object.synced` ingest + dedupe, ownership migration.
* The Zoho own-adapter **against a fake `MCPClient`/fake Zoho REST** with recorded payloads — the `test_solo_pack_slice_e2e` discipline (drive the real platform seams; supply the connector's responses as the unit of work).

**The honest limit (mirrors voice go-live §12.5): no live external call is made on this VM.** With "prefer real MCP servers" (decision 3) and no external credentials/network here, three things stand between this and a live connection, per connector, and none is wired:

1. **Real credentials** in the per-company store (OAuth client id/secret, tokens).
2. **The concrete transport** — a published MCP server actually running (stdio package installed / hosted URL reachable), or, for own-adapters, the vendor's live API.
3. **Webhook registration** with the external system pointing at the tenant's ingest endpoint.

This is deliberate and tracked, not smuggled into "done": the *machine* is proven against the `MCPClient` contract; live binding is an activation-time ops step done with credentials in hand. "Full catalog" is satisfied by every row being registered and bindable, with Zoho proven against fakes.

## 10. Risks

| Risk | Containment |
|---|---|
| **Ungoverned write-back** — an external write that skips the PolicyGate | Connector write tools are categorised in `authority.py`; the record service's write-back path is the *only* external-write route, and it runs after the gate |
| **Mirror drift** — reads serve a stale mirror | Cadence bounded by webhook (near-real-time) or sweep; `synced_at`/etag on every mirror; conflict is surfaced, never merged |
| **Shared-credential SoD hole (D2)** | Accepted for this increment (decision 4); documented deferred, not hidden; the grant layer is designed (§4.4) so closing it is additive |
| **Full-catalog throwaway** | Only the *machine* + Zoho are built deeply; the other rows are declarative catalog entries — cheap to hold, no per-connector code to rewrite when the seam settles |
| **Platform-budget burn on sync** | Re-embedding synced docs draws B13's platform envelope, not the tenant wallet (RETR precedent); a new sync attribution must be classified for B13 |

## 11. Task Plan

Branch `inc4/conn-sor` (both workstreams, one machine). Build task-by-task, gates green each step; §N build-note delta log + maturity flips on merge.

| # | Task | Acceptance |
|---|---|---|
| T1 | Connector catalog (`catalog.py`, all §6.6 rows) + `connectors` package on the typing allowlist | catalog imports, mypy-strict clean, every row has a backend + masters |
| T2 | Binding + credential persistence (`models.py`, `conn001`) + service + boot rehydrate | bind/pause/rehydrate a fake server; ACTIVE bindings live after restart; migration up/down clean |
| T3 | Governance categories for connector writes | a write-back tool raises a HITL card at A1 (PolicyGate test) |
| T4 | SOR mirror columns (`sor001`) + record-service write-back-first + master-wins | write-back success/failure + `sync.conflict` goldens (against a fake connector) |
| T5 | SOR signals (`object.synced`, `sync.conflict`) + sync producers/sweep | `object.synced` ingest + dedupe; sweep diff emits on change |
| T6 | Zoho Books own-adapter + Invoice mapping | the §6 flagship vertical end-to-end against a fake Zoho client |
| T7 | Ownership migration (HITL-gated `sor.master` flip) | flip both directions with backfill + link rewrite behind a checkpoint |
| T8 | `/ai/connectors/*` router (catalog list, bind, status) + admin surface note | company-scoped; catalog + binding status readable |
| T9 | Integration + all gates green; build notes; maturity flips; register + overview updated (D2/C2 deferred) | parity/eval unchanged; docs move with code |

---

## 12. Build Notes (2026-07-23) — delta log

All nine tasks landed on `inc4/conn-sor`. Gates on merge: **1495 unit** (+29 over
Inc-4 PRAGYA-RT), **16 parity/eval**, **257 integration**, mypy `--strict` over
**246** files (added the `connectors` package), layout lint exit 0, migrations
`conn001`/`conn002` up/down/up clean.

### 12.1 What shipped

| Task | Module(s) | Note |
|---|---|---|
| T1 | `connectors/catalog.py` | the §6.6 manifest — all ~22 rows, real HBS masters |
| T2 | `connectors/{models,service,resolver,credentials}.py`, `conn001` | durable bindings + encrypted creds + rehydrate |
| T3 | `governance/{authority,checkpoints,models}.py`, `conn002` | `external_write` category + the 19th checkpoint |
| T4 | `tenant_schema/{sor,record_service,data_plane,models}.py` | write-back-first + master-wins + the mirror columns |
| T5 | `connectors/sync.py`, `record_service.sync_mirror`, `cost_attribution` | `object.synced` + sweep + B13 class |
| T6 | `connectors/{writeback.py,zoho_books/}` + boot wiring | the Zoho adapter + the generic write-back bridge |
| T7 | `connectors/sor_migration.py` | the propose→confirm→apply ownership migration |
| T8 | `connectors/router.py` | the `/ai/connectors/*` admin API |
| T9 | this doc + register/overview/technical §21 + HANDOFF | gates, notes, maturity flips |

### 12.2 Design deltas (decided during build)

1. **`sor001` was not a migration.** Tenant tables are bootstrapped per-tenant
   (not control-plane Alembic), so `create_all` can't add a column to an
   existing tenant schema. The mirror columns land via an idempotent
   `ADD COLUMN IF NOT EXISTS` in the data-plane bootstrap
   (`data_plane._sync_columns`) — the tenant-schema **additive-evolution
   primitive** the platform lacked. Future tenant-table columns append there.
2. **The write-back seam is a pluggable provider, not an import.** `tenant_schema`
   must not import `ai.connectors` (a cycle), so `record_service` calls a
   `WriteBackProvider` installed at boot (`install_connector_writeback`) — the
   `install_consent_registry` pattern. With no provider installed an external
   write **fails safe** rather than writing an unconfirmed mirror.
3. **A 19th HITL checkpoint.** External write-back is an act class the original 18
   (all internal decisions) did not cover, so `before_external_system_write` was
   added — the assertion moved 18→19 and `conn002` backfills it idempotently.
4. **Ownership migration is a two-step API, not a HumanApproval.** `HumanApproval.run_id`
   is non-nullable and an owner-driven migration has no run, so the §21.4 HITL
   gate is `propose → owner-confirm → apply` (the router enforces auth) plus a
   `governance.sor_migrated` audit signal.
5. **Credentials inline on the binding** (the `IntegrationRegistry.encrypted_api_key`
   pattern), not a second table — a binding is 1:1 with its credential.
6. **The Zoho adapter carries two contracts** over one REST surface: `MCPClient`
   (agent tool path) + `SorConnector` (write-back + change feed). HTTP is an
   injectable transport, so the whole machine is provable against fakes.

### 12.3 Register status — what this workstream did and did not close

* **B4** (system-of-record) — the mastering **machine is built and proven** on
  the flagship (write-back-first, master-wins, sync-in, ownership migration);
  broaden per connector as live bindings come online.
* **D2** (per-agent credential scoping) — **deferred** (decision 4, §2):
  per-company credentials were chosen for simplicity, which is the exact shape
  D2 flags. Closing it later is a per-Process grant layer over `connector_bindings`.
* **C2** (human-task step type) — **deferred** (§2): physical-fulfillment
  machinery, separable from mastering; not in scope this increment.

So the CONN/SOR path as chosen **closes no register finding outright** — it
advances B4's implementation and carries D2 + C2. Recorded here rather than
glossed.

### 12.4 The honest limit — a tested machine, not a live integration

Every external call is faked (§9). **No live Zoho or external MCP-server call has
been made.** What remains, per connector, is activation-time ops: real
credentials in the per-company store, a reachable server / the vendor's live API
behind the transport, and webhook registration. The seam is right and tested;
the wire-level connection is a distinct step, done with credentials in hand —
the same discipline VOICE go-live carries.
