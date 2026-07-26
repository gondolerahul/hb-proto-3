# Increment 6 / STRAT — Appendix 04a: The Seven Planning Object Sheets

> **Status:** 🟡 **DRAFT — awaiting Rahul's review.** This document *is* STRAT **T2**, the blocking owner review. Build (T3 onward) does not start until it closes.
> **Parent:** [04_strat.md](./04_strat.md) §5 · **Precedent:** [increment-1/03a_hbs_spine.md](../increment-1/03a_hbs_spine.md) (the 27-object spine, approved 2026-07-19) and [increment-3/02a_stage_scripts.md](../increment-3/02a_stage_scripts.md) (the Pragya stage scripts, approved 2026-07-22) — the two prior artifacts that got this treatment.
> **Closes:** the review gate on gap-analysis **VG-11**.
> **Created:** 2026-07-26

---

## 1. Why this needs your review rather than my judgement

Everything else in Increment 6 is machinery — a reaper, a canary, a taint ladder. A tenant never sees those words. **These seven objects are different: they become forms, list columns and report headings that a business owner reads.** `Proposition.case` is not an implementation detail; it is a label on a screen.

The spine got this treatment in Increment 1 and the Pragya stage scripts got it in Increment 3, for the same reason. Field names a tenant will read are not an engineer's guess.

**How to review:** §4 is the substance — seven sheets, one per object. §7 lists what drafting them surfaced, and **§8 is eleven numbered questions**, each with a recommendation. If you agree with every recommendation, "approve as drafted" is a complete answer and I build §4 verbatim.

---

## 2. Conventions (inherited unchanged from 03a §1)

**System fields, never declared.** `id`, `company_id`, `entity_def_id`, `version` (CAS), `def_version`, `updated_by_run_id`, `created_at`, `updated_at`, `deleted_at`, plus the implicit `notes: text` and `tags: string[]` and the `sor`/`external_ref` blocks.

**Field types (closed set).** `string` · `text` · `integer` · `decimal` · `boolean` · `date` · `datetime` · `enum(...)` · `money` · `email` · `phone` · `url` · `json` · `artifact` · `ref(Target)`.

**Ref notation.** `→ rel` means the link row is *this record → target*; `← rel` means *target → this record*. **Every ref below uses the existing seed vocabulary** (`converted_to` · `belongs_to` · `attached_to` · `fulfilled_by` · `billed_by` · `paid_by` · `derived_from`) — STRAT extends `SEED_REL_TYPES` by nothing, which is a small but real sign the objects sit naturally in the spine rather than beside it.

**Owner process.** All seven are owned by process **11** (Planning & Budgeting), stored numerically and rendered `P{n:02d}` at seed — the same de-canary dodge `Budget` already uses. §7.1 explains what that ownership actually does at runtime, and it is not what the design doc assumed.

**Memory domain.** All seven carry a **new** tag `strategy`, added to `DOMAIN_TAGS`. New rather than reusing `financial` because the domain viewport is exactly the mechanism that should keep board minutes out of a collections agent's retrieval.

---

## 3. Object index

| # | Object | HBS module | Memory domain | Owner | Loop step |
|---|---|---|---|---|---|
| 28 | **Objective** | Planning | `strategy` | P11 | *(frame)* |
| 29 | **Target** | Planning | `strategy` | P11 | *(frame)* |
| 30 | **Forecast** | Planning | `strategy` | P11 | *(frame)* |
| 31 | **Minutes** | Planning | `strategy` | P11 | **Notice** |
| 32 | **Proposition** | Planning | `strategy` | P11 | **Strategize** |
| 33 | **Resolution** | Planning | `strategy` | P11 | **Decide** |
| 34 | **Mandate** | Planning | `strategy` | P11 | **Act** |
| 34+ | **Review** | Planning | `strategy` | P11 | **Close** |

> Eight rows, seven new objects — `Review` shares the count line because the spine goes **27 → 34**. Counting: Objective, Target, Forecast, Minutes, Proposition, Resolution, Mandate, Review is **eight**. **This is a genuine discrepancy in the design doc and it is question §8.1.**

The three "frame" objects (Objective / Target / Forecast) are not steps in the loop — they are what the loop *aims at*. A Mandate must move a Target; a Target serves an Objective; a Forecast is what we expect the Target's KPI to do. The five loop objects reference them.

---

## 4. The sheets

### 4.1 Objective

*What the business is trying to achieve over a horizon. The thing Targets serve and Resolutions advance.*

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| narrative | text | why this matters, in the owner's words |
| horizon | enum(quarter, year, multi_year) | |
| status | enum(draft, active, achieved, abandoned) | default `draft` |
| owner | ref(Employee) | `→ attached_to`, optional — who is accountable |

**Notes.** `abandoned` is deliberately in the set beside `achieved`. An objective quietly dropped is the most common outcome in a small business and a status vocabulary that cannot express it produces a permanently "active" list nobody trusts. The design doc called this field `owner_ref`; `owner` reads better on a form and collides with nothing (the system field is `owner_process_code`) — see §8.2.

---

### 4.2 Target

*A number, a direction and a date. The measurable commitment inside an Objective.*

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| kpi_key | string | a key from the shipped C6 registry — see the ten below |
| direction | enum(increase, decrease, hold) | |
| target_value | decimal | |
| by_date | date | |
| objective | ref(Objective) | `→ belongs_to`, optional |
| status | enum(open, met, missed, withdrawn) | default `open` |

**The ten valid `kpi_key` values today** (`ai/kpi/definitions.py`): `open_pipeline_value` · `lead_response_time` · `quote_acceptance_rate` · `receivables_outstanding` · `overdue_receivables` · `days_sales_outstanding` · `collections_recovered` · `ticket_resolution_time` · `gross_margin` · `agent_hitl_load`.

**Notes.** `kpi_key` is a plain `string`, not an `enum`, on purpose: the C6 registry is the single source of truth (decision 3.2 — *"two stores for one number is how a review ends up arguing with the dashboard"*), and freezing an enum copy of it in the tenant schema would create exactly the second store the decision forbids. Validation happens against the registry at write time, not in the field type. **`direction` is not decoration** — `days_sales_outstanding` improving means going *down*, and a review that does not know that will report a genuine success as a miss.

---

### 4.3 Forecast

*What we expect a KPI to do over a period — a committed number the business plans against.*

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| kpi_key | string | as Target |
| method | enum(manual, twin_forecast, external) | |
| value | decimal | |
| interval_low / interval_high | decimal | the honest band, not a point |
| for_period_start / for_period_end | date | |
| twin_run_id | string | nullable — the Glasshouse run this came from |
| target | ref(Target) | `→ attached_to`, optional — **new, see §8.3** |

**Notes.** `twin_run_id` is a **string, not a ref or an FK**: TWIN's `twin_runs` lives in the control plane and this record lives in the tenant plane. There is no cross-plane foreign key in this architecture and inventing one here would be the wrong precedent.

**This object is not TWIN's forecast** and the design doc names the risk (§11): TWIN's is an ephemeral run result, Planning's is a committed number. They are related, not the same. `method='twin_forecast'` plus `twin_run_id` is the join between them, and it is deliberately loose.

---

### 4.4 Minutes — **Notice**

*What was said and noticed in a session, whether with Pragya or with the owner thinking alone.*

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| held_on | datetime | required |
| attendees | text | free text — a sole trader's "me" is a legitimate value |
| body | text | |
| decisions_summary | text | what the room concluded, before any of it becomes a Resolution |
| objective | ref(Objective) | `→ attached_to`, optional |

**Notes.** `attendees` is text rather than a multi-ref to Employee because the most common Solo Pack meeting has one attendee who is not an Employee record, and the second most common includes a customer who is a Contact. A ref list would make the honest answer unrepresentable.

`decisions_summary` and `Resolution.decision` are **not** duplicates: the first is what a meeting felt like it concluded, the second is what was formally adopted. Meetings routinely conclude things nobody ever adopts, and that gap is information.

---

### 4.5 Proposition — **Strategize**

*A candidate course of action, with its case and its cost. Agents may raise these; only humans adopt them.*

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| case | text | the argument for doing it — **naming question, §8.4** |
| expected_effect | text | |
| cost_estimate | money | |
| honesty_grade | enum(replay, forecast, unknown, untested) | default `untested` |
| twin_run_id | string | nullable |
| minutes | ref(Minutes) | `→ derived_from`, optional |
| status | enum(draft, tabled, adopted, rejected, withdrawn) | default `draft` |

**`honesty_grade` has four values where TWIN's `Grade` has three**, and the fourth is load-bearing:

| Value | Means |
|---|---|
| `untested` | **Planning-only.** Never taken to the Glasshouse. The default, and the honest state of most propositions |
| `unknown` | TWIN ran it and could not grade the result |
| `forecast` | TWIN projected it — softer evidence |
| `replay` | TWIN replayed real historical signals — the strongest grade available |

Conflating `untested` with `unknown` would let "we never checked" and "we checked and could not tell" render identically, which is precisely the softening TWIN's grading exists to prevent. **The grade is copied from the twin run, never typed by a human** — the same rule TWIN enforces by reflection ([03](./03_twin.md) §5.4), and STRAT must not become the back door around it (§8.5).

---

### 4.6 Resolution — **Decide**

*A decision the business formally adopted. The monument on the lawn.*

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| decision | text | required — what was decided, in plain words |
| adopted_on | date | required |
| adopted_by | ref(Employee) | `→ attached_to`, optional |
| proposition | ref(Proposition) | `← converted_to`, optional |
| district | string | the HBS module it concerns — **naming question, §8.6** |
| engraved_at | datetime | when it was pinned to the Seasons timeline |
| status | enum(active, superseded, revoked) | default `active` |

**Notes.** `proposition` is optional because an owner may resolve something no agent ever proposed, and forcing a Proposition record first would make the honest path the slow one. The `← converted_to` direction is the shipped `Quote.opportunity` pattern.

**Adopting is a certified human act (T2)** — `IntentKind.STRATEGY_RESOLUTION` through `inward_auth/guard.enforce_kind`, in the handler body, never a `Depends` (the VG-05 lesson: this repo's router tests call handlers directly, so a decorator-shaped gate is invisible to them and can be deleted without failing one).

**Revoking is not gated.** The same asymmetry VG-05 established: the safe direction must never be harder than the unsafe one.

---

### 4.7 Mandate — **Act**

*What a Resolution actually obliges: which Process, which Target, by when.*

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| resolution | ref(Resolution) | `→ belongs_to`, **required** |
| owning_process | string | a process code — `P03`, `P08`, … |
| target | ref(Target) | `→ attached_to`, optional |
| review_due | date | **required** — the promise to come back |
| status | enum(issued, in_flight, reviewed, closed) | default `issued` |

**Notes.** `owning_process` is a string code rather than a ref because Processes are tenant-plane *entities* (`hierarchical_entities`), not HBS records — there is nothing to `ref` at. This mirrors how `owner_process_code` is already stored on every entity def.

`review_due` is required and it is the only required date in the seven sheets. A mandate without a review date is a wish, and the whole point of the fifth loop step is that the loop closes.

---

### 4.8 Review — **Close**

*Predicted versus realized, honestly — including when the honest answer is "we cannot tell".*

| Field | Type | Notes |
|---|---|---|
| mandate | ref(Mandate) | `→ belongs_to`, **required** |
| reviewed_on | date | |
| predicted_value | decimal | the Target's value, or the Forecast's if one was attached |
| realized_value | decimal | **nullable — None means not measurable, never zero** |
| measurable | boolean | |
| missing | text | what was absent, in words — **shape question, §8.7** |
| verdict | enum(on_track, off_track, met, missed, not_measurable) | |
| notes | text | |

**Notes.** This sheet is where the C6 honest-absence rule earns its place. `KpiResult` already carries exactly this shape — `value: float | None` with the comment *"``None`` means not measurable. It never means zero"* plus a `missing: list[str]` and a `measurable` property — and `Review` mirrors it deliberately rather than inventing a parallel vocabulary.

**`not_measurable` is a first-class verdict, not an error state.** A fabricated KPI prompts a decision while a missing one prompts a question, and a strategy review is precisely where a fabricated number does the most damage. It will also be the *most common* verdict for the first quarter after deploy, because `kpi_snapshots` starts empty by construction — see §7.4.

The review reports the originating Proposition's `honesty_grade` beside the verdict. *"This bet was graded `forecast` when it was made"* is what makes a track record honest rather than flattering.

---

## 5. The two joins, worked

The loop is a loop because of two ref walks, and both are already-existing `tenant_record_links` traversals — **no new join machinery**.

**Backward — *"why does this process exist?"***

```
Mandate ──belongs_to──► Resolution ──converted_to──► Proposition ──derived_from──► Minutes
```

> *"P08 is chasing receivables weekly because Resolution #14 (adopted 12 Mar) issued it, off Proposition 'tighten collections' (graded `replay`), which came out of the 3 Mar minutes."*

**Forward — *"did that decision work?"***

```
Resolution ──► Mandate ──► Review ──► kpi_snapshots (LEARN) via Target.kpi_key
```

> *"Resolution #14 promised DSO down to 35 by 30 Jun. Realized 41. Verdict `missed`. The bet was graded `replay` when made, so the model was sound and the execution was not."*

That last sentence is the product. Neither walk is possible today because none of these objects exist.

---

## 6. Spine bookkeeping (what T3 touches)

| Change | Where |
|---|---|
| 7 new object dicts + `HBS_SPINE` entries | `ai/tenant_schema/hbs_seed/__init__.py` |
| `DOMAIN_TAGS` += `strategy` | same file, line 19 |
| `assert len(HBS_SPINE) == 27` → `== 34` | same file, line 365 |
| `assert len(HBS_SPINE) == 27` → `== 34` | `tests/unit/test_tenant_validation.py:109` |
| `assert len(bundle["tenant_db"]["entity_defs"]) == 27` → `== 34` | `tests/integration/test_tenant_records_db.py:229` |
| Appendix update (object index + field defs) | `increment-1/03a_hbs_spine.md` |

**Three assert sites, not two.** The design doc named the source assert and the 03a appendix; the export-bundle integration test is a third and would have failed the run. The asserts exist to make exactly this change deliberate, and they worked.

**No migration, no backfill.** `seed_hbs_spine` is additive and idempotent — it inserts only the defs a tenant is missing, and `ensure_ready` calls it on the next provisioning touch after deploy. Existing tenants pick up all seven quietly. (The private helper is named `_seed_if_empty`, which is a misnomer worth knowing: it is a sync, not a first-run seed.)

---

## 7. What drafting these surfaced

### 7.1 P11 is not seeded, and that changes what "agents may draft" means

The design (§8) says *"Agents may draft Propositions, never adopt"*, enforced by *"the record service's existing owner-writes/others-propose rule"*. Tracing it through the shipped code, the mechanism is **stronger than described**, and the difference is worth a decision rather than a discovery in month two.

`bootstrap.py:52` stamps `owner_process_code = "P11"` on all seven objects. `record_service._owner_gate` (line 383) then reads:

* `actor_process_code is None` → **direct write**. This is the human/API/seeding path.
* owner set and `!= actor` → **`PROPOSED`**, emitting `object.change_proposed`.

**P11 has no agent.** Wave 0 seeded P03, P06, P08, P10, P14 and P19 (`templates/__init__.py:106-111`); `P11` appears only as a *number* in the `fiscal` bundle's membership. So no agent anywhere carries actor code `P11`, and therefore **every agent write to any of the seven objects proposes — none writes directly.**

For **Proposition** that is arguably perfect: a proposition *is* a proposal, and having an agent-authored one arrive as `object.change_proposed` for a human to accept is the semantics, not a tax. For **Minutes** it is heavier than intended — §4 of the design says *"agents may attach observations"*, and under this mechanism an observation becomes a proposal a human must accept. See **§8.8**.

### 7.2 The seven objects need no new rel vocabulary

Every ref in §4 uses one of the seven existing `SEED_REL_TYPES`. I expected to need something like `advances` or `obliges` and did not. That is weak evidence the objects belong in the spine rather than in a control-plane table beside it — which was decision 1.

### 7.3 `honesty_grade` needs a fourth value TWIN does not have

Covered in §4.5. TWIN's `Grade` is `replay | forecast | unknown`; Planning needs `untested` as well, and as the *default*. The risk is the reverse direction: a human typing `replay` into a Proposition that never went near the Glasshouse would launder an untested bet into the strongest available grade. §8.5 asks how hard to close that.

### 7.4 Most reviews will say `not_measurable` for a quarter, and that will look broken

`kpi_snapshots` began collecting on the day LEARN deployed (2026-07-25) with no backfill, by construction. A Mandate issued today with a 90-day `review_due` reviews against roughly a quarter of history — thin, but real. A Mandate issued today with a *one-year* window has almost nothing.

The design names this risk (§11) and says *"the copy must explain why"*. The copy is Increment 7's, but the **data** that makes the explanation possible is STRAT's: the Review should record *why* it could not measure, not just *that* it could not. That is what `missing` is for, and it is why §8.7 argues about its shape.

---

## 8. Review questions

Each has a recommendation. Agreeing with all eleven is a complete review.

**8.1 — Seven objects or eight?** The design says "seven new HBS objects" and "spine 27 → 34", but §5 of the design lists **eight** (Objective, Target, Forecast, Minutes, Proposition, Resolution, Mandate, Review). 27 + 8 = **35**, not 34. One of the three numbers is wrong.
→ **Recommend: eight objects, spine 27 → 35.** All eight are load-bearing — dropping any one breaks a ref in §5's walks. The "seven" and the "34" are the arithmetic slip, not the object list. *(Everything downstream in this document uses 35; if you prefer to cut one, Forecast is the only candidate, and §8.3 is where that argument lives.)*

**8.2 — `Objective.owner` or `owner_ref`?** The design says `owner_ref`.
→ **Recommend `owner`.** `_ref` suffixes are engineer-speak; the spine has none (`Contact.account`, `Employee.reports_to`, `Opportunity.primary_contact`). Nothing collides — the system field is `owner_process_code`.

**8.3 — Should `Forecast` exist at all, and should it link to `Target`?** The design gives it no ref, which leaves it a floating number.
→ **Recommend: keep it, and add `target ref(Target) → attached_to, optional`.** Without the link, `Review.predicted_value` cannot find "the Forecast's value if one is attached" (design §7.3) — the rule is unimplementable as written. If you would rather cut an object to reach seven, this is the one, and `Review.predicted_value` then always comes from the Target.

**8.4 — `Proposition.case`?** Ambiguous — "case" reads as a support case in a product that also ships Tickets.
→ **Recommend `rationale`.** Alternatives: `business_case` (clearer, longer), or keep `case` if the board-paper connotation is what you want.

**8.5 — How hard do we stop a human typing `honesty_grade = replay`?** Options: (a) leave it writable and trust the UI; (b) refuse any write that sets a non-`untested` grade without a matching `twin_run_id`; (c) make it fully read-only, settable only by TWIN's hookup (T9).
→ **Recommend (b).** (c) is cleanest but blocks the legitimate case of a grade arriving from an external simulation; (a) is how track records get flattering. (b) is mutation-testable and states the actual rule: *a grade must have a run behind it*.

**8.6 — `Resolution.district`?** "District" is Vihara/Atlas vocabulary from the spec. A tenant reading a form field labelled **District** on a board resolution will not know what it means.
→ **Recommend `concerns_module`**, holding an HBS module name (`CRM`, `Accounting`, …). Vihara can render whatever it likes from that; the record should carry business vocabulary, not map vocabulary. *(This is the clearest instance in the whole sheet of spec-speak leaking into a tenant-facing label.)*

**8.7 — `Review.missing` as `text` or `json`?** C6's `KpiResult.missing` is a `list[str]`.
→ **Recommend `text`,** holding the reasons joined into a readable sentence. A Review is read by a human, and the 03a convention restricts `json` to line-item lists. The structured list stays available on `KpiResult` for anything that needs to branch on it.

**8.8 — Should Minutes be agent-writable directly?** Per §7.1, every agent write to a Planning object proposes. For Minutes that means an agent attaching an observation raises a proposal a human must accept. Options: (a) accept it — uniform, safest, slightly heavy; (b) seed a P11 process + agent in the Solo Pack roster so planning work has a real owner; (c) give **Minutes alone** no owner code, so any agent may write it directly (`_owner_gate` returns `None` when owner is `None`).
→ **Recommend (a) for now.** It is the shipped mechanism with no special case, and for the first tenants the volume is tiny. (b) is the right long-run answer but it is a Solo Pack roster change, which is a different workstream's blast radius. (c) creates a novel "ownerless HBS object" precedent for one convenience.

**8.9 — `strategy` as a new domain tag?** It adds an eleventh member to `DOMAIN_TAGS`, and every existing agent's `memory_domains` allow-list omits it, so **board minutes will be invisible to every currently-seeded agent's retrieval** until someone grants it.
→ **Recommend yes, and treat the invisibility as the feature.** That is precisely why it should not reuse `financial`. But it does mean a Planning-aware agent needs the tag added explicitly, and if that surprises you later, this paragraph is where it was decided.

**8.10 — Should `Objective.status` include `abandoned`?** It is unusual to ship a status that admits failure.
→ **Recommend yes** (§4.1's reasoning). A vocabulary that cannot express the most common real outcome produces a list nobody trusts.

**8.11 — Anything missing from the eight?** Candidates I considered and left out: a `Stakeholder` object (Contact/Employee already serve), an `Assumption` object (belongs in `Proposition.case`), a `Milestone` (Mandate + `review_due` covers it), and a tenant `KPI` object (**explicitly excluded by decision 3.2** — reference the C6 registry, never mirror it).
→ **Recommend: no additions.** But this is the question where your business knowledge beats mine, and adding an object now is far cheaper than adding one after tenants have data.

---

## 9. What happens when you approve

T3 onward, in the design's order: spine additions + the three asserts + the 03a appendix (T3) · the pure five-step transition functions (T4) · `STRATEGY_RESOLUTION` T2 + the agents-may-not-adopt rule, mutation-tested (T5) · the 02:20 review sweep (T6) · predicted-vs-realized incl. `not_measurable` (T7) · the API surface (T8) · the TWIN grade hookup (T9).

**No Alembic migration in this workstream** — the largest domain-model change to the tenant schema since Increment 1 adds none, because new HBS objects are seed data.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-26 | v0.1 — drafted for owner review (STRAT T1). Eight sheets written against the shipped spine format; ref directions checked against `SEED_REL_TYPES` (no vocabulary extension needed); `kpi_key` values checked against the shipped C6 registry; the `honesty_grade` vocabulary reconciled with TWIN's three-value `Grade`; the P11 ownership consequence traced through `_owner_gate`; a third spine-assert site found in the integration export test; the seven-vs-eight arithmetic discrepancy in [04](./04_strat.md) §5 raised as §8.1. |
