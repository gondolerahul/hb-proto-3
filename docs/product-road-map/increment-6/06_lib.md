# Increment 6 / LIB — The Library Data Layer (closes VG-13, VG-14)

> **Status:** v1.1 — design locked (§3). **T1 + T2 BUILT 2026-07-25** (branch `inc6/lib`, pulled forward — see §13). T3–T8 not started.
> **Closes:** gap-analysis **VG-13** (provenance, influence, staleness, artifact linkage, citations) + **VG-14** (connected drives cataloged only generically). Optionally **VG-16** (§8) — otherwise unowned.
> **Depends on:** RETR's shipped retrieval stack (`memory/{hybrid_retrieval,chunking,retrieval_filters,reranker}.py`), the connector catalog (`connectors/catalog.py`), `orm/document.py`, `artifact_models.py`.
> **Independent** of LEARN/SEGA/TWIN/STRAT — but **start early**: the retrieval-usage log is a time series with the same "worthless empty" problem as KPI history ([00_overview](./00_overview.md) §3).
> **Parent:** [00_overview.md](./00_overview.md) · ratified spec §15.4.

---

## 1. The findings

**VG-13.** `documents` has eight columns: `company_id`, `entity_id`, `filename`, `file_type`, `file_size`, `upload_status`, `memory_domain`, timestamps. Spec §15.4 wants a Library that knows, for every document: **where it came from**, **who uses it and how much**, **whether it is still true**, and **how to open it at the passage that answered the question**. None of those four exist.

**VG-14.** The §6.6 catalog has exactly one knowledge row — `notion_knowledge` (MCP_SERVER, `server_ref="notion"`). SharePoint and Google Drive, which §15.1 stage 3 depends on for the onboarding journey, are absent. And `connectors/sync.py` syncs **records** (`object.synced`); a **document** sync path does not exist at all.

What RETR already built and this reuses: structure-aware chunking with `heading_path`, hybrid+RRF retrieval, `memory_domain` + the domain viewport (which gives §15.4's "scoping made visible" almost for free), and the lazy re-chunk sweep.

## 2. The one architectural constraint

The HANDOFF §5 convention on RETR is explicit: **retrieval has three deliberately separate stages** — `hybrid_search` fuses, the viewport filters inside it, the reranker runs at the caller — and the reranker was kept out of `hybrid_search` because it would cycle on `RetrievedChunk` and would put per-query spend inside a function other callers assume is cheap.

The retrieval-usage log has exactly the same shape, so it gets exactly the same answer: **it is written at the caller**, `memory_service.py:228` — the single call site of `hybrid_search`, after the rerank and the `top_k` cut. What gets logged is what an agent actually *received*, not what the fusion happened to surface. Those are different sets, and only the first is "influence".

## 3. Decisions

1. **Log at the caller, after rerank** (§2).
2. **Logging never fails a retrieval.** The write is fire-and-forget in its own transaction; an exception is swallowed with a debug log. A library-analytics feature must not be able to break the answer path.
3. **Supersede keeps versions.** A superseded document is marked, never deleted, and stays retrievable when explicitly asked for. This is what makes "was this true in March?" answerable.
4. **Staleness is *stated*, never inferred silently.** A stale document is flagged with the rule that flagged it; the flag is a fact about our knowledge, not a claim about the document's content.
5. **A generated artifact is filed as a Document.** One Library, not two.
6. **Connected-drive sync is platform-initiated**, reusing the existing `CostAttribution.CONNECTOR_SYNC` (already in `PLATFORM_INITIATED_ATTRIBUTIONS`) — no new classification, and the tenant's envelope is not charged for a background mirror.

## 4. Provenance

`documents` gains:

| Column | Type | Notes |
|---|---|---|
| `source_kind` | String(24) | `upload` · `connected_drive` · `generated_artifact` · `conversation_derived` — a closed set, matching §15.4's collections |
| `source_uri` | Text, nullable | the drive path, the URL, the artifact path |
| `external_ref` | String(255), nullable | the source system's own id, for re-sync and dedupe |
| `content_hash` | String(64), nullable | sha-256 of the extracted text; change detection without re-reading |
| `ingested_by_user_id` | UUID FK → `users`, nullable | |
| `ingested_by_run_id` | UUID FK → `execution_runs`, nullable | which agent filed it |
| `effective_from` | Date, nullable | what period the content describes — *not* when it was uploaded |
| `superseded_by_id` | UUID FK → `documents`, nullable | §3.3 |
| `staleness_state` | String(16) | `fresh` · `aging` · `stale` · `superseded` · `contradicted` |
| `staleness_reason` | String(255), nullable | the rule that set it (§3.4) |

`effective_from` is the column that earns its place: a price list uploaded today may describe last year, and staleness computed from `created_at` would call it fresh. Where it is unknown it stays NULL and staleness falls back to `created_at` — with `staleness_reason` saying so.

Existing rows backfill to `source_kind='upload'`, everything else NULL — which is honest: we genuinely do not know where they came from, and SEGA's taint ladder ([02](./02_sega.md) §7.3) reads absent provenance as `external_verified` for precisely that reason.

## 5. Influence — the retrieval-usage log

### 5.1 The raw log

`retrieval_usages`: `id`, `company_id`, `document_id`, `chunk_id`, `entity_id` (the colleague that asked), `run_id` (nullable — a Pragya turn has none), `query_hash` (sha-256 of the normalised query; **never the query text** — a query is tenant content and this table does not need it), `rank`, `used_at`.

Written in a batch of ≤ `top_k` rows per retrieval, at the caller, non-blocking (§3.2).

### 5.2 Bounded by construction

An honest look at volume: one row per returned chunk per query, typically ≤ 5. Two mechanisms keep it bounded:

* **Daily rollup** — `document_influence_daily` (`document_id`, `day`, `retrievals`, `distinct_entities`), built by a cron at **02:40 UTC**. This is what answers *"this pricing sheet answered 40 customer questions this month"* without scanning the raw log.
* **A reaper** — raw rows past `LIB_USAGE_RETENTION_DAYS` (default 30) are deleted; the rollup is kept indefinitely because it is tiny. A log with no reaper is an unbounded archive (the lesson `voice_deferred_reap` records).

### 5.3 What influence is for

Two surfaces read it: the Library's per-document influence panel (Vihara, Inc 7), and staleness — a document with *high* influence and *old* content is the one worth flagging first, because it is actively shaping answers.

## 6. Staleness and contradiction

`library/staleness.py`, a daily sweep at **02:50 UTC**, applying rules in order and stopping at the first that fires:

| Rule | Sets |
|---|---|
| `superseded_by_id` is set | `superseded` |
| A contradiction flag was raised against it (§6.1) | `contradicted` |
| Age past the per-`source_kind` threshold (uploads 365d, connected drives 180d, conversation-derived 90d) measured from `effective_from` or `created_at` | `stale` |
| Within 30 days of that threshold | `aging` |
| otherwise | `fresh` |

Each write records `staleness_reason` in words — *"no effective_from; 400 days since upload"* — because a flag whose basis is invisible is a flag people learn to dismiss.

**6.1 Contradiction** is raised, not detected here: the dreaming engine and the critics already read retrieved context, and when two retrieved chunks assert incompatible facts the run flags the pair. LIB owns the *store* and the *state*; it does not own a new detector. Building a contradiction detector inside a data-layer workstream would be the wrong place and the wrong scope.

Staleness never removes a document from retrieval. It travels **with** the chunk into the result, so the answer path can say "this is from a document flagged stale". Silently withholding a stale document would replace a slightly wrong answer with a confidently empty one.

## 7. Artifacts and citations

**7.1 Artifacts into the Library.** `artifacts` (`artifact_models.py`) is a legacy-style table with no link to `documents` and no tenant-record link. It gains `document_id` (FK → `documents`, nullable) and `record_ref` (JSONB: `{object, record_id}` — **no FK**, because records live in the tenant plane and this row does not).

Filing means creating a `Document` with `source_kind='generated_artifact'`, `source_uri` = the artifact path, and `ingested_by_run_id` = the producing run. Text-shaped artifacts (documents, text) are chunked through the RETR chunker so they are retrievable; recordings, images and video are filed but not chunked — there is no honest text to embed.

**7.2 Citations.** Retrieval already returns enough to cite: `document_id`, `chunk_index`, `heading_path`. What is missing is a contract and a way to *open* it. LIB adds:

* a `Citation` shape (`document_id`, `chunk_id`, `heading_path`, `rank`) carried alongside the answer;
* `GET /ai/documents/{id}/passage?chunk={n}&context=1` — the chunk plus its neighbours, so a citation opens at the passage rather than at the top of a 40-page PDF.

## 8. Connected drives (VG-14)

**Catalog rows** in `connectors/catalog.py`, category `knowledge`: `sharepoint_drive` and `google_drive` (both `OAUTH2`), joining the existing `notion_knowledge`. They declare no `masters` — a drive masters no HBS object; it is a source of documents, not of records.

**`connectors/document_sync.py`** — deliberately separate from `sync.py`, which syncs records and emits `object.synced`:

1. list files in the bound scope (a folder, a site, a database);
2. for each, compare `content_hash`; unchanged files are skipped without a fetch;
3. new/changed files → extract (the shipped `text_extractor.py`) → `Document` with `source_kind='connected_drive'`, `external_ref`, `source_uri` → chunk through the RETR chunker;
4. a file deleted at the source is marked `superseded` locally, **never deleted** (§3.3);
5. emits `document.synced`.

Attributed `CONNECTOR_SYNC` (decision 6) and admitted at the platform budget, exactly as the record sweep is — a perpetual mirror refresh must not burn tenant credits (B13).

**Transport injected, no live call** — the Inc-4/Inc-5 precedent.

**VG-16, optionally.** `connector_bindings` has `status` but no credential-expiry field and no sweep, and §15.2's "bridge under repair" tray needs one. It is unowned by any workstream and it is ~30 lines: `credentials_expire_at` + a daily check emitting `connector.credentials_expiring`. Included here as **T8** because LIB is already in this file; cut it first if the increment runs long.

## 9. Data model

| Change | Migration |
|---|---|
| 10 provenance columns on `documents` | `lib001` |
| `retrieval_usages` + `document_influence_daily` | `lib001` |
| `artifacts.document_id`, `artifacts.record_ref` | `lib001` |
| `connector_bindings.credentials_expire_at` (T8) | `lib001` |
| Catalog rows `sharepoint_drive`, `google_drive` | none (declared data) |
| `document.synced`, `connector.credentials_expiring` signal types | none |

New package **`ai/library/`** → `CLEAN_PACKAGES`.

## 10. Task plan

| # | Task | Gate |
|---|---|---|
| **T1** | Provenance columns + `lib001` + the `upload` backfill; ingest paths stamp `source_kind` | unit + `*_db` |
| **T2** | **The usage log, early** — write at the caller after rerank, non-blocking; a test proves a logging failure does not break retrieval | unit + `*_db`, **mutation-tested** (make the log raise; retrieval must still return) |
| **T3** | Daily rollup + reaper crons | `*_db` |
| **T4** | `library/staleness.py` — the ordered rules, `staleness_reason`, the daily sweep; staleness travels with the chunk | unit + `*_db` |
| **T5** | Artifact→Document filing + `record_ref`; chunk only text-shaped artifacts | unit + `*_db` |
| **T6** | The citation shape + `GET /ai/documents/{id}/passage` | router + unit |
| **T7** | Catalog rows + `connectors/document_sync.py`, transport injected | unit + `*_db` |
| **T8** | *(optional)* VG-16 credential expiry + tray signal | `*_db` |

T2 as early as the plan allows — every week without it is a week of influence data that cannot be reconstructed, the same argument LEARN's KPI history makes.

## 11. Honest risks

| Risk | Why it is real |
|---|---|
| **A write on the hot path** | Mitigated by fire-and-forget, batching and a mutation test — but it is still a new write per retrieval, and it should be watched on the first busy tenant |
| **`query_hash` is not fully anonymous** | A hash is reversible for short, guessable queries. It exists for de-duplication, not privacy; the privacy claim is that the *text* is not stored. Do not oversell it |
| **Staleness thresholds are guesses** | 365/180/90 days are defensible, not measured. They are settings for that reason, and `staleness_reason` makes a wrong one visible rather than mysterious |
| **Backfilled provenance is `NULL`, and honestly so** | Every pre-LIB document reads as unknown provenance — which SEGA's taint ladder treats as `external_verified`. That is a real behaviour change for existing tenants and belongs in release notes |
| **Chunked artifacts can be noise** | An auto-generated report chunked into the Library competes with authored documents for result slots. If it degrades retrieval goldens (RETR T5, MRR 1.000), file artifacts *unchunked* by default and let the tenant opt in |

## 12. Brainstorm decisions

*(Answered — do not re-litigate.)*

1. **Where the usage log is written:** at the caller, after rerank (§2).
2. **Query text stored:** never — hash only (§5.1).
3. **Superseded documents:** kept (§3.3).
4. **Stale documents withheld from retrieval:** no — flagged and carried (§6).
5. **Contradiction detection:** raised by the existing critics; LIB stores state only (§6.1).
6. **Artifacts:** filed as Documents, one Library (§3.5).
7. **Drive sync budget class:** platform-initiated, reusing `CONNECTOR_SYNC` (§3.6).

---

## 13. Build notes — T1 + T2 only (2026-07-25, branch `inc6/lib`)

**T1 and T2 are built. T3–T8 are not.** Pulled forward at the owner's direction on the §10 argument: both are time series, and a time series started later cannot be backfilled — every week without the usage log is a week of influence data that does not exist. The rest of LIB follows the normal order.

### 13.1 What shipped

| Task | Where |
|---|---|
| T1 | 10 provenance columns on `orm/document.py`; `library/provenance.py` (`SourceKind`, `StalenessState`, `content_hash`); migration **`lib001`** with the `upload` backfill |
| T2 | `library/models.py` (`RetrievalUsage`), `library/usage_log.py` (`query_hash`, `log_retrieval_usage`), the call in `memory/memory_service.py` after rerank |
| supporting | `document_id` added to the hybrid-retrieval projection; `library` added to `CLEAN_PACKAGES` and to `migrations/env.py` |

### 13.2 Four design deltas

1. **`lib001` carries T1 + T2 only.** §9 scoped `document_influence_daily`, `artifacts.document_id`/`record_ref` and `connector_bindings.credentials_expire_at` into the same migration. They are not here: shipping tables nothing writes to is dead schema that reads as a built feature. They land with the tasks that use them (`lib002`).

2. **Retrieval had to start carrying `document_id`.** `RetrievedChunk.metadata` carried `memory_domain` and the retriever scores but not the document — so the usage log had nothing to attribute to, and §7.2's citations would have had nothing to open. Both retrieval SQL statements already `JOIN documents`, so it is one extra column in the projection and no new query.

3. **The guard is duplicated at the call site, on purpose — and a mutation test is why.** `log_retrieval_usage` swallows its own exceptions, so in principle the call site needs nothing. The T2 mutation test (make the log raise, assert retrieval still returns) **failed**: `search_semantic` wraps its whole v1 path in a catch-all that returns `[]`, so anything escaping the logger surfaced not as an error but as *the agent retrieving nothing, silently*. That is the worst available outcome and exactly what decision 2 forbids. The answer path must not depend on the analytics path's internal discipline, so it now guards independently.

   This is the clearest case so far of a mutation test paying for itself: every unit test passed, the logger's own `try` looked sufficient, and the defect was visible only by breaking the thing on purpose.

4. **`query_hash` normalises case as well as whitespace.** §5.1 says "the normalised query"; lower-casing is part of it, because "What is our refund policy?" and "what is our refund policy?" are the same question asked twice, and counting them separately understates a document's influence. The privacy claim is unchanged and deliberately narrow — the *text* is not stored; the hash is for de-duplication, not anonymity (§11 says so and the module docstring repeats it).

### 13.3 Honest limits

* **Nothing reads the log yet.** T3's rollup and reaper are not built, so `retrieval_usages` grows unbounded until they are. At ≤ `top_k` rows per retrieval this is fine for a while and is not fine forever — **T3 is the first thing LIB should build next**, and the index the reaper needs (`ix_retrieval_usages_doc_day`) is already in place.
* **The series starts empty**, by construction — the same property LEARN's KPI history has, and the reason both were pulled forward.
* **Provenance detail is only stamped by the column defaults.** T1 ships the vocabulary and the backfill; wiring each ingest path to record a real `source_uri` / `content_hash` / `ingested_by_*` belongs with T5 and T7, which create those paths. Today every row honestly reads `upload` with unknown detail.
* **`staleness_state` is stored but never computed** — that is T4. Everything is `fresh` because nothing has looked yet, which is a fact about the sweep's absence rather than about the documents.

### 13.4 Gates

typecheck **289** files strict · layout lint · **1847 unit** · **16 parity/eval** (retrieval goldens unregressed — the log sits after the measured path) · **391 integration** · `lib001` applies, rolls back and re-applies · migration head **`lib001`**.

---

## 14. Build notes — T3–T8 (2026-07-26, branch `inc6/lib-rest`)

**LIB is complete.** T3 (rollup + reaper), T4 (staleness), T5 (artifact filing), T6 (citations + the passage read), T7 (connected drives, VG-14) and T8 (credential expiry, VG-16 — kept rather than cut) all built. Migration **`lib002`**, off `twin001`.

### 14.1 What shipped

| Task | Where |
|---|---|
| T3 | `library/influence.py` (`roll_up_day`/`roll_up_pending`/`reap_usage_log`/`influence_for_document`), `DocumentInfluenceDaily`, the 02:40 cron, `LIB_USAGE_RETENTION_DAYS` |
| T4 | `library/staleness.py` (the pure `assess` ladder, `sweep_company`/`sweep_all`, `raise_contradiction`/`clear_contradiction`), the 02:50 cron; `staleness_state` added to both retrieval projections |
| T5 | `library/filing.py`, `artifacts.document_id` + `artifacts.record_ref` |
| T6 | `library/citations.py` (`Citation`, `citations_from_hits`, `read_passage`), `library/api.py` → `GET /ai/documents/{id}/{passage,influence}`; `chunk_index`/`filename`/`heading_path` added to both retrieval projections |
| T7 | `connectors/document_sync.py`, the `sharepoint_drive` + `google_drive` catalog rows, `document.synced` |
| T8 | `connectors/credential_expiry.py`, `connector_bindings.credentials_expire_at`, `connector.credentials_expiring`, the 03:10 cron |

### 14.2 Six design deltas

**1. The rollup needed a third counter, because the design's own headline sentence is not what its two counters measure.** §5.2 specifies `(document_id, day, retrievals, distinct_entities)` and §5.3 says the rollup answers *"this pricing sheet answered 40 customer questions this month"*. It cannot. `retrievals` counts **rows**, and one question routinely returns three chunks of the same document — so a document that answered one question reports three retrievals. Worse, the overstatement is proportional to how finely the *chunker* happened to split that document, which is a property of RETR's configuration rather than of the document's usefulness. `distinct_queries` (a `COUNT(DISTINCT query_hash)`) is the counter the sentence describes, and it ships alongside the other two rather than replacing them — "chunks returned" and "questions helped with" are both real, and conflating them is the whole defect.

**2. The reaper cannot outrun the rollup, and that clamp is the load-bearing line in T3.** A reaper and a rollup on independent clocks eventually meet in the wrong order: the worker is down a fortnight, the rollup covers only yesterday, and the reaper then deletes a fortnight of raw rows nothing ever aggregated. Both jobs did exactly what they were told and the influence history has a hole in it that nothing reports. So `reap_usage_log` clamps its cutoff to the day *after* the last rolled-up day, and **refuses entirely** when nothing has ever been rolled up. The consequence is deliberate and stated: if the rollup stops, the log grows. That is a visible, recoverable failure; silent data loss is neither. Three tests pin it — no rollup → nothing deleted, rollup behind → clamped, rollup current → normal.

Two smaller pieces of the same reasoning: the rollup processes a **7-day lookback window**, not just yesterday (a missed night is recovered rather than lost forever), and **today is excluded** (a day cannot be aggregated until it is over — LEARN's pooling rule).

**3. `document_influence_daily` carries `company_id` although `document_id` implies it.** Without it, every influence read must join `documents` to scope itself, and a scoping rule that depends on remembering a join is the exact shape of both cross-tenant disclosures Increment 6 has already fixed — the VG-05 approval IDOR and SEGA T0's tool registry. The column is redundant in normal form and load-bearing in practice.

**4. Contradiction had to become *sticky*, and the design does not say where it lives.** §6.1 is clear that LIB owns the store and the state while the critics own the detection — but the ordered rules then ask, on every nightly sweep, "was a contradiction raised?", and there is nowhere to read that from. If the age rules can overwrite `contradicted`, then every sweep silently resolves every contradiction nobody has got to yet. So the ladder reads the *current* state: `contradicted` persists until a human clears it or a supersession settles it, and `raise_contradiction`/`clear_contradiction` are the store API the critics call. It needs no new column, and stickiness is asserted directly (`assess` at +400 days still returns `contradicted`).

**5. Retrieval had to start carrying three more columns** — `staleness_state`, `chunk_index`, `filename`/`heading_path` — for the same reason T2 had to add `document_id`. Staleness that does not travel with the chunk is a sweep whose output is invisible at the only moment it matters; and without `chunk_index` a citation has nothing to open at, because `read_passage` takes one. Both retrieval statements already `JOIN documents`, so this is projection width, not new queries. The retrieval goldens are unregressed.

**6. `AGE_THRESHOLD_DAYS` needed a fourth entry the design omitted.** §6 gives thresholds for uploads (365d), connected drives (180d) and conversation-derived (90d) but not for `generated_artifact` — which T5 then creates. A generated report describes the business at the moment it was produced, so it ages like a mirrored drive file: 180 days. A **totality test** over `SOURCE_KINDS` now fails if a new kind arrives without one (the discipline GATE's 64 tools taught), and an unknown kind falls back to the *most generous* threshold rather than the strictest — a gap in our configuration must not accuse a tenant's document of being out of date.

### 14.3 The defect the tests found

**A file that vanished from a connected drive and came back stayed flagged `superseded` forever.** §8 rule 4 says a deleted file is marked, never deleted — which the sync did. But the next pass compared content hashes, found the returning file unchanged, and *skipped* it: present in the drive, invisible in the Library, with nothing anywhere reporting the inconsistency. Every other drive-sync test passed.

The fix revives the document **in place** rather than creating a replacement, and that choice matters more than it looks: the document keeps its id, and with it every `retrieval_usages` row and every rolled-up day of influence history pointing at it. Re-creating would have orphaned the entire influence record of a document whose only offence was being briefly invisible — which is precisely the history this workstream exists to accumulate.

Worth recording as a species: it is the third time in Increment 6 that a **"nothing happened" path** turned out to be the broken one. LIB T2's mutation test found retrieval silently returning `[]`; GATE found the taint firewall silently permitting; this one silently keeps a live file hidden. All three read as *working* from every other angle.

### 14.4 Honest limits

* **No live SharePoint or Google Drive call.** `DriveSource` is a Protocol and every test injects a fake — the Inc-4/Inc-5 precedent. Live binding is activation-time ops, the same discipline voice go-live and the Zoho flagship carry.
* **`document_sync` has no scheduled poller.** Exactly GATE's `emit_broadcast_inbound` limit: the machinery works when something calls it, and nothing yet calls it on a timer. A poller needs a per-binding scope and cadence that belongs with the live adapter, not ahead of it.
* **Nothing calls `raise_contradiction` yet.** The store and the state are built and tested; the critics that should call it are unchanged. LIB deliberately does not own the detector (§6.1), so this stays open until someone wires the dreaming engine's contradiction finding into it.
* **Nothing calls `file_artifact` automatically.** T5 ships the filing path and `file_pending` for a bounded backlog pass, but no producer files on creation — an artifact still has to be filed deliberately. Wiring it into artifact creation would put an embedding call inside every tool that writes a file, which is a decision about cost, not about plumbing.
* **`credentials_expire_at` is never populated by anything.** T8 builds the column, the sweep and the tray signal; the OAuth flows that would know an expiry do not write it. So the sweep is correct and, today, always empty — the honest state, and the reason the sweep skips NULLs rather than treating them as expired.
* **Influence is only as deep as the log.** `retrieval_usages` started 2026-07-25 and the rollup starts the day this deploys. No backfill, by construction — the same property LEARN's KPI history has.

### 14.5 Gates

typecheck **308** files strict · layout lint · **1958 unit + parity/eval** (16 parity/eval green — retrieval goldens unregressed) · **464 integration** (+43: 13 influence, 16 documents, 14 connectors) · `lib002` applies, rolls back and re-applies · migration head **`lib002`**.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-26 | v1.2 — **T3–T8 BUILT; LIB complete.** §14 added: build notes, six design deltas (the third rollup counter the headline claim actually needs; the reaper's clamp to the rollup; `company_id` on the rollup; sticky contradictions; three more retrieval projection columns; the fourth staleness threshold + a totality test), the returning-drive-file defect the tests found, and six honest limits. T8 (VG-16) kept rather than cut, at the owner's direction. |
| 2026-07-25 | v1.1 — **T1 + T2 BUILT** (pulled forward: both are time series that cannot be backfilled). §13 added: build notes, four design deltas (`lib001` scoped to what is used; retrieval now carries `document_id`; the call-site guard a **failing mutation test** forced; case-normalised `query_hash`), and the honest limits — chiefly that T3's rollup and reaper are the next thing LIB must build. |
| 2026-07-25 | v1.0 — design written. The retrieval-usage log placed at `memory_service.py`'s single `hybrid_search` call site per the RETR three-stage rule, made non-blocking and bounded by a rollup plus a reaper; provenance given an `effective_from` distinct from `created_at`; staleness made a stated flag with its reason, never a silent withholding; artifacts filed as Documents; a passage endpoint so citations open where the answer came from; SharePoint/Google Drive catalog rows plus a document-sync path separate from the record sweep; VG-16 picked up as an optional task since no workstream owned it. |
