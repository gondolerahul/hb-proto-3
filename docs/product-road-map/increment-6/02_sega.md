# Increment 6 / SEGA — Self-Evolution, Bounded (closes B11, D3)

> **Status:** v1.1 — design locked (§3). **T0–T2 BUILT** (2026-07-25, branch `inc6/sega`) — build notes §13. T3–T8 pending.
> **Closes:** register **B11** (self-evolving code blast radius) + **D3** (context taint / tool-call firewall) + gap-analysis **VG-10** (no canary for agent/process changes) and **VG-17** (no entity version ledger).
> **Depends on:** LEARN ([01](./01_learn.md)) — SEGA consumes `learning.charter_tuning_proposed` · the shipped Meta-Agent surface (`ai/meta/`) · EVX's `require_independent_suites` + `intelligence/canary.py` (Inc 5) · the PolicyGate (`governance/policy_gate.py`).
> **Feeds:** TWIN ([03](./03_twin.md)) — the promotion pipeline **calls** this canary; the Glasshouse diff reads the version ledger · Vihara's Gallery (Inc 7).
> **Parent:** [00_overview.md](./00_overview.md) · [00_charter.md](./00_charter.md).

---

## 1. The findings this workstream exists to fix

**B11 (High):** *Self-evolving code blast radius. `tool_versions.company_id = null` denotes global tools; nothing forbids a self-heal triggered by one tenant's failures from mutating a **global** tool used by all tenants.*

**D3 (High):** *Prompt-injection defence is pattern-matching. Missing: privilege separation (contaminated context cannot invoke high-impact tools), provenance/taint on signal payloads, tool-call firewalls per trust zone.* The §18.6 trust field shipped in Increment 1 is the down-payment.

**VG-10:** `intelligence/canary.py` watches a **model** rollout only. An agent or process change — the thing this platform actually evolves — has no canary at all.

**VG-17:** `HierarchicalEntity.version` is a single `String` column defaulting to `"1.0.0"`. There is no history, so there is nothing to diff, nothing to roll back to, and nothing for the Gallery or the Glasshouse to show.

## 2. What ships today

The self-evolution surface is larger than the register implies, and **most of it is already careful**. Worth stating, because the temptation is to rebuild what is fine:

| Surface | Behaviour today | Verdict |
|---|---|---|
| `meta/tool_synthesis_pipeline.py` | Persists a `ToolRegistryEntry` with `company_id=company_id`, `is_enabled=False`, `configuration.status="DRAFT"`, sandbox-only runtime registration | **Safe** — tenant-scoped and opt-in by construction |
| `meta/prompt_evolution.py` | A critic-of-critic proposes a bounded prompt diff; output is a *candidate* needing HITL approval | **Safe** — non-autonomous by design |
| `meta/skill_library.py` | Repeated tool chains become `skill_candidate` nodes; never auto-promote | **Safe** |
| `meta_agent_prompt_evolution`, `skill_promotion_scan` crons | Weekly, candidate-producing only | **Safe** |
| `intelligence/canary.py` | Cohort fallback-rate watch, auto rollback/promote | **Model-only** (VG-10) |
| `HierarchicalEntity` | One `version` string; `deleted_at` soft-delete | **No ledger** (VG-17) |
| `governance/policy_gate.py` | A `counterparty`-trust triggering signal cannot drive `HIGH_IMPACT_CATEGORIES` | **D3's down-payment, and only that** |

So B11's specific claim needs restating against the code: the `tool_versions` table the register names **does not exist**; the shipped analogue is `tool_registry_entries`, and the synthesis pipeline already scopes writes to a company. B11's *risk* is nonetheless real — nothing **forbids** an unscoped write, the safety is a habit of the current call sites, and `ToolRegistryEntry.company_id` is still nullable with `null = system-wide`.

### 2.1 A live cross-tenant read found while mapping this work

`ToolRegistryEntry.name` is declared `unique=True` **globally**, and both read paths ignore company:

* `ToolManagementService.list_all_tools()` — `select(ToolRegistryEntry)` with no filter, reached by `GET /api/v1/ai/tool-registry` behind plain `get_current_user`;
* `ToolManagementService.get_tool(tool_id)` — selects by id alone, reached by `GET /api/v1/ai/tool-registry/{tool_id}`, also plain `get_current_user`.

> **Route paths corrected 2026-07-25** (v1.1): v1.0 of this doc wrote these as `/ai/tools` and `/ai/tools/{id}`. The router's prefix is `/api/v1/ai/tool-registry` — a wrong path in a security finding is a defect in the record, so it is fixed here rather than quietly.

So any authenticated user of any tenant can list and read **every other tenant's** custom and synthesized tool entries, including the `configuration` blob that carries the tool's `spec`, `source` and `audit`. Writes are `app_admin_only`, so this is disclosure rather than cross-tenant mutation — but a synthesized tool's spec describes how a competitor's business does something, which is exactly the material a tenant expects to be private.

It is the same shape as the VG-05 IDOR (a read beside a write, scoped differently) and it gets the same treatment: **scope first, then serve**, 404 on a cross-tenant miss. Fixed in **T0** — before any new self-evolution capability is added to a surface that leaks.

## 3. Decisions

1. **Self-evolution is tenant-scoped, period.** Any automated change targets a row carrying the initiating company's id. A target with `company_id IS NULL` (global tool, platform template, seeded spine) is refused — global changes go through the platform-admin pipeline with a human on it. This is B11's ask, taken literally.
2. **One ledger, one canary, both general.** The entity version ledger and the entity-change canary are built here and *consumed* by TWIN and by Vihara's Gallery. Building a second canary inside TWIN would duplicate blast-radius logic in the one place it must not be duplicated ([00_overview](./00_overview.md) §3).
3. **Taint descends and never recovers.** A run's trust level can only get worse as content enters it. There is no path that "cleans" context, because the only honest way to raise trust is a human looking at the content, and that is a HITL card, not a state transition.
4. **The independent-suite rule applies to entity changes too.** EVX's `require_independent_suites` is reused verbatim — the exam predates the student, whether the student is a model or an agent.

## 4. B11 — blast radius, made a predicate

`evolution/blast_radius.py` — pure, unit-testable, and the single thing every automated change must pass:

```
admit_change(target, *, initiator_company_id, kind) -> None   # raises BlastRadiusError
```

Five limits, in the order they are checked:

1. **Scope.** `target.company_id` must equal `initiator_company_id`. `NULL` is refused explicitly (not merely unequal) with its own message, because "this is a global row" is the case the register is about and it deserves to be legible in the logs.
2. **Field allow-list.** By `kind`: a charter tune may touch `goal`, `description` and Intelligence-tree rules; a schema proposal may add a tenant field. **`governance`, `capabilities` and `logic_gate` are on no allow-list** — autonomy, authority and the loop's own control flow are never self-modified. (LEARN refuses to *propose* these, §7 there; SEGA refuses to *apply* them. Both, deliberately: a refusal that exists once is a refusal one refactor away from gone.)
3. **Rate.** At most `SEGA_MAX_CHANGES_PER_DAY` (default 3) automated changes per company per day. A self-heal loop that has found a way to keep proposing is contained by arithmetic rather than by judgement.
4. **Cohort cap.** A canarying change may serve at most `SEGA_CANARY_FRACTION` (default 0.25) of the entity's runs (§6).
5. **Kill switch.** A company in read-only or suspended state (C5's ladder) admits no automated change at all. A tenant who has stopped paying should not discover their workforce rewrote itself while they were away.

**Mutation-test each limit separately.** Per the repo convention, a checker never observed to fail is a function that returns `True`: remove limit 1 and only the scope test fails; remove limit 3 and only the rate test fails.

## 5. The entity version ledger (VG-17)

**`entity_versions`** (control plane):

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `entity_id` | UUID FK → `hierarchical_entities` | |
| `company_id` | UUID FK → `companies` | denormalised so a scope check needs no join |
| `version` | String | the value that lands on `HierarchicalEntity.version` |
| `snapshot` | JSONB | the full block set — `identity`, `hierarchy`, `logic_gate`, `planning`, `capabilities`, `governance`, `io_contract`, `observability`, `metadata_extensions`, `goal`, `description` |
| `change_kind` | String(24) | `human` · `charter_tune` · `schema_proposal` · `template_apply` · `rollback` |
| `changed_by_user_id` | UUID FK → `users`, nullable | NULL when automated |
| `proposal_signal_id` | UUID FK → `signals`, nullable | the LEARN proposal this came from |
| `status` | String(16) | `canary` · `ga` · `rolled_back` · `superseded` |
| `created_at` | DateTime | |

Unique on `(entity_id, version)`; index on `(company_id, entity_id, created_at)`.

**A full snapshot, not a diff.** A diff chain is smaller and is the wrong choice here: rollback must work when the chain is broken, and the Glasshouse's diff view needs two complete states anyway. Entity blocks are small JSON.

**Every write goes through the ledger** — human edits included. A ledger that records only automated changes cannot answer "what did this agent look like last Tuesday", which is the question the Gallery and every incident review actually ask. The write happens in `AIService.update_entity`, beside the existing update, in the same transaction.

## 6. The entity-change canary (VG-10)

`evolution/entity_canary.py`, shaped after `intelligence/canary.py` and deliberately *not* merged with it: the model canary's cohort is companies, this one's cohort is **runs of one entity inside one tenant**, and folding them would make both harder to read.

* **Cohort.** After a change is applied at `status='canary'`, at most `SEGA_CANARY_FRACTION` of that entity's runs use the new version; the rest use the previous ledger row. Selection is a stable hash of the run's triggering signal id, so the same signal replayed lands the same side — otherwise a retry looks like a canary result.
* **Health, from telemetry that already exists.** Per version, over `execution_runs` + `human_approvals`: run failure rate, HITL rejection rate, critic BLOCK rate, mean cost per run, escalation rate. A version is unhealthy if any rate is materially worse than the incumbent's over the same window, with a `_MIN_SAMPLES` floor (below it the canary keeps observing — the same rule the model canary uses, for the same reason).
* **Verdict.** Unhealthy → `roll_back` (restore the previous snapshot, mark `rolled_back`, emit `governance.entity_rolled_back`). Clean over the window → `promote` to `ga`.
* **Admission first.** Promotion calls `require_independent_suites` — an agent change validated only by tests the change itself produced is refused. Behavioural goldens (PACK, `03b_pack_behavioral_goldens.md`) are the incumbent suite for the Wave-0 roster.

The daily sweep is one arq cron at **01:50 UTC**, after C4's demotion sweep — demotion is about *authority* and canary is about *version*, and running demotion first means a rolled-back entity is not simultaneously being demoted for the failures its rollback just removed.

## 7. D3 — context taint and the tool-call firewall

### 7.1 What exists and what is missing

`gate_and_maybe_stop` reads `context_state["signal"]["trust"]` and `evaluate_policy` refuses `HIGH_IMPACT_CATEGORIES` when it is `counterparty`. That is real and it is the *only* taint rule in the system. Its limits:

* taint is read **once, at the triggering signal**, and never updated;
* nothing lowers it when the run pulls in a web page, a scraped document, a mirrored external record or a child run's output;
* there are two levels in practice (`counterparty` / everything else) where the envelope declares four.

So a run triggered by an internal schedule that then *fetches* a hostile page is treated as fully trusted at the gate. That is D3.

### 7.2 The ladder

Reuse `SignalTrust`'s vocabulary — one taxonomy, not two:

```
counterparty (0)  <  external_verified (1)  <  internal (2)  <  platform (3)
```

`execution_runs.taint_level` (String, nullable) holds the run's current level; a column rather than a `context_state` key because `context_state` is rewritten wholesale and an audit needs to survive that.

### 7.3 Descent

`taint = min(taint, incoming)` at each entry point. It never rises. The entry points:

| Entry | Incoming level |
|---|---|
| Triggering signal | its `trust` |
| `web_search` / `scraper` / `batch_search` results | `counterparty` |
| A connector/MCP **read** result | `external_verified` |
| A retrieved document chunk | its LIB provenance (see [06](./06_lib.md)); **absent provenance reads `external_verified`** |
| A tenant record field whose origin is an inbound proposal | `counterparty` |
| A child run's result | the child's own taint |

The absent-provenance rule is the one to argue about, so it is stated outright: *"we do not know where this came from"* is not *"we wrote it"*. Defaulting unknown provenance to `internal` would make the whole ladder decorative, since most shipped documents predate LIB.

### 7.4 The firewall

`evolution/taint_firewall.py` — pure:

```
firewall(taint, category) -> ALLOW | HITL | REFUSE
```

| Taint | High-impact (`payout`, `refund`, `contract`, `vendor_creation`) | `external_write`, `email_dispatch` | Everything else |
|---|---|---|---|
| `counterparty` | **REFUSE** | **HITL** regardless of band | ALLOW |
| `external_verified` | **HITL** regardless of band | band-based | ALLOW |
| `internal` / `platform` | band-based | band-based | ALLOW |

The `counterparty` row reproduces today's behaviour exactly, which is how the change is proven non-regressive: the existing PolicyGate tests must pass unchanged.

**One enforcement point.** The firewall is called inside `evaluate_policy`, where the `counterparty_trust` special case lives now — replacing a special case with a table, not adding a second gate. Note `gate_and_maybe_stop` fails *open* on an exception (a gate bug must not wedge every run); that stays, and it is why the firewall itself must be pure and total — a pure function with a total mapping has nothing to throw.

## 8. Agent-proposed fields (§10.2)

The charter's carried-over question: dynamic-schema evolution splits across LEARN (learning-driven definition promotion) and SEGA (agent-proposed fields). SEGA's half:

An agent that repeatedly needs a field the HBS object lacks emits a proposal. Applying it is an **additive** tenant-schema evolution through the shipped `data_plane._sync_columns` primitive (Inc-4 precedent — tenant tables are bootstrapped, not migrated). Blast radius: additive only (**never drop, never retype, never rename**), tenant-scoped, and behind the same HITL card an owner already sees for a schema change. A dropped column is data loss that no rollback recovers, so it is not on the allow-list at any autonomy band.

## 9. Data model

| Change | Plane | Migration |
|---|---|---|
| `entity_versions` | control | `sega001` |
| `execution_runs.taint_level` (String, nullable) | control | `sega001` |
| `tool_registry_entries` read scoping | — | none (behavioural, T0) |

One migration off `learn001`. New package **`ai/evolution/`** → add to `CLEAN_PACKAGES` in `scripts/typecheck_ai.py`.

New signal types: `governance.entity_versioned`, `governance.entity_rolled_back`, `governance.schema_field_proposed`.

## 10. Task plan

| # | Task | Gate |
|---|---|---|
| **T0** ✅ | **Scope the tool registry reads** (§2.1) — company join on list + get, 404 on cross-tenant miss, platform (`company_id IS NULL`) rows stay visible to all | `*_db`, **mutation-tested** |
| **T1** ✅ | `evolution/blast_radius.py` — the five limits, pure | unit, **each limit mutation-tested** |
| **T2** ✅ | `entity_versions` + `sega001`; every `update_entity` writes a ledger row | `*_db` |
| **T3** | `evolution/entity_canary.py` — cohort split, health from shipped telemetry, roll_back/promote | unit + `*_db` |
| **T4** | Promotion calls `require_independent_suites`; PACK goldens registered as the incumbent suite | unit |
| **T5** | The 01:50 UTC sweep + `governance.entity_*` signals | `*_db` |
| **T6** | `evolution/taint_firewall.py` + `taint_level` + descent at the six entry points | unit (**existing PolicyGate tests must pass unchanged**) + `*_db` |
| **T7** | Consume `learning.charter_tuning_proposed` → ledger → canary, end to end | `*_db` |
| **T8** | Agent-proposed fields over `_sync_columns`, additive-only | unit + `*_db` |

T0 first on purpose: it is a live disclosure in shipped code, and adding capability to a leaking surface is the wrong order.

## 11. Honest risks

| Risk | Why it is real |
|---|---|
| **The canary needs traffic** | A Solo Pack tenant may run one entity a handful of times a week; at `_MIN_SAMPLES` the canary observes for a long time. That is the correct behaviour (a verdict on three runs is noise) but it means "canarying" is a state entities will sit in for weeks. The Gallery must show it as a *state*, not a *delay* |
| **Taint may prove too sticky** | `min()` and never recovering means one scraped page taints the rest of a long run. That is the intent, but if it turns out to block ordinary work the fix is a **narrower descent map** (fewer sources marked `counterparty`), never a recovery transition |
| **Full snapshots grow** | ~3 changes/day/company cap bounds it, and entity blocks are small. Revisit only with evidence |
| **Two refusal points for governance edits** | LEARN refuses to propose, SEGA refuses to apply. Deliberate duplication (§4 limit 2); a future reader may "simplify" one away — the tests name the other |

## 12. Brainstorm decisions

*(Answered — do not re-litigate.)*

1. **Global changes:** never automated (§3.1).
2. **One canary or two:** two implementations, one shape — the cohorts are different things (§6).
3. **Taint recovery:** none. A human looking at content is a HITL card, not a transition (§3.3).
4. **Diff chain vs snapshot:** snapshot (§5).
5. **Where the firewall runs:** inside `evaluate_policy`, replacing the `counterparty` special case (§7.4).
6. **Schema evolution:** additive only, never drop/retype/rename (§8).

---

## 13. Build notes (2026-07-25, branch `inc6/sega`)

### 13.1 T0 — the leak, closed

`_viewer_scope(user)` in the router decides what a reader may see: **`None` (unrestricted) only for `app_admin`**, every other role scoped to its own company plus the platform's own `company_id IS NULL` rows. The service's `list_all_tools` and `get_tool` take that scope; a cross-tenant `get_tool` is a **404, not a 403**, because a probe must not learn the id exists elsewhere.

**The admin write paths were deliberately left unscoped.** `update_tool` / `delete_tool` / `toggle_tool` load through the unrestricted read and are already `app_admin_only`. Scoping them would break platform administration to fix a hole that is not on that path — this is a disclosure fix, not a permissions rewrite.

**Two layers, mutation-tested separately.** Removing the router's scoping failed both leak tests; removing only the service's detail-read scoping failed only the detail test. A positive test also pins that a tenant still sees its own tools, the platform's, and the whole built-in catalogue — over-tightening is the failure mode a scoping fix most easily introduces.

### 13.2 T1 — five limits, five refusals watched

`evolution/blast_radius.py` is pure and total: `admit_change(ChangeRequest, Limits)` raises `BlastRadiusError` or returns. The facts it judges (changes today, subscription status, canary fraction) are gathered by the caller and carried on the request, which is what keeps the whole of B11's answer a function.

**One delta: rollback is exempt from the rate cap and the kill switch.** Undoing an automated change is the safe direction, and the safe direction must never be harder than the unsafe one — the asymmetry VG-05 established for consent revocation and autonomy lowering. A tenant at the daily cap, or read-only, must still be able to get back. **Rollback stays subject to scope**, because a rollback of another tenant's entity is not a safe direction; it is a cross-tenant write.

Each limit was mutation-tested on its own and failed **only** its own tests: the global-artifact check (3 tests), the rate cap (1), the cohort cap (2), the kill switch (2), and the rollback exemption (2). B11 says *nothing forbids* — the answer is only real if the suite has watched it forbid.

### 13.3 T2 — the ledger

`evolution/models.EntityVersion` + `evolution/ledger.py` + migration **`sega001`** (new head, off `learn001`; also adds `execution_runs.taint_level` for T6). `AIService.update_entity` now records a version **in the same transaction as the edit**, so there is no state where an entity has moved and its history has not.

**Three deltas.**

1. **`proposal_signal_id` carries no FK.** The ORM is import-light (the `intelligence/models.py` precedent) and an FK to `signals` made the mapper fail to configure in any context that had not imported the signal bus — caught immediately by the `*_db` suite. Dropped in both the model and the migration, following the shipped `CallLog.voice_session_id` precedent. There is a second, better reason: a signal can be reaped or replayed, and a version must outlive the proposal that caused it.
2. **`record_version` never raises.** A deliberate asymmetry with the rest of SEGA, where refusals are loud: a missing ledger row is a gap in an audit trail, while a failed save is a person's work lost. Recording history must never be the reason an edit fails.
3. **`next_version` is a patch bump, and says it is not semver.** Nothing here can tell a breaking charter change from a typo fix, and a scheme implying it could would be lying in a field people read. A malformed existing version starts a fresh `1.0.1` series rather than raising — a bad version string is not a reason to refuse to record history, which is the moment history matters most.

`SNAPSHOT_BLOCKS` fixes what a version *is*, so a block added to `HierarchicalEntity` later is a deliberate addition to history rather than a silent omission — and secrets or transient attributes cannot drift in. Note the ledger snapshots `governance` and `capabilities` **even though they are never self-modified**: the ledger records what happened, `blast_radius` decides what may happen, and conflating them would leave the most consequential human edits unrecorded.

### 13.4 Verification (T0–T2)

typecheck **276 files** strict · layout lint · **1691 unit** (+39) · **16 parity/eval** · **341 integration** (+12) · migration head **`sega001`**, applies/downgrades/re-applies.

**Honest limits.** `blast_radius.admit_change` is written and tested but has **no call sites yet** — nothing automated goes through it until T7 wires the LEARN proposal path, so today it is a guarantee waiting for a caller. The ledger is written by `update_entity` only; entity *creation* and soft-delete do not yet record versions.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-25 | v1.1 — **T0–T2 built** (§13). Route paths in §2.1 corrected (`/api/v1/ai/tool-registry`, not `/ai/tools`). Rollback made exempt from the rate cap and kill switch but never from scope; `proposal_signal_id`'s FK dropped for import-lightness; `record_version` made non-raising. |
| 2026-07-25 | v1.0 — design written. B11 restated against the code (the named `tool_versions` table does not exist; the risk does); **a live cross-tenant read of every tenant's tool entries found and scheduled as T0**; blast radius reduced to five checkable limits; the version ledger chosen as full snapshots; the entity canary kept separate from the model canary with the reason; D3 given a four-level ladder, a monotonic descent map and a pure firewall table that reproduces today's behaviour at `counterparty`. |
