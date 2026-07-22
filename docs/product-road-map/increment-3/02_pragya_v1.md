# Increment 3 / PRAGYA — Pragya v1: The Nine-Stage Engagement over the Wizard's APIs

> **Status:** ✅ BUILT (2026-07-22) — T1–T7 complete, all gates green · **Branch:** `inc3/pragya` · build notes in §7
> **Design authority:** Functional §4.2–§4.4 (Pragya + the nine-stage flow, closed C8 at protocol level); Blueprint §14 (Wave-0 HUB role); Technical §11 (account-manager sessions). Closes **C4** (autonomy demotion) + **C6** (KPI definitions) + C8's per-stage-script half.
> **Depends on:** AUTH (`require_tier` — no Pragya command executes without it), Inc-2 ONBOARD (the stage APIs + console FE), SIG (reporting/notifications), RETR (stage-3 ingestion quality).

---

## 1. Design (self-contained)

Pragya is the **one relationship** through which a tenant runs their AI workforce. v1 is **console chat** (decision: console-first): a conversation surface in the shipped React app, backed by an orchestration loop that walks the **nine-stage engagement flow** (functional §4.3) — the same flow the Inc-2 wizard walks as buttons, over the *same* APIs (`solo_pack/onboarding.py` was authored as her stage contract; Inc 3 is a conversation over it, not a rebuild).

**The stance per stage** (functional §4.3, normative):

| Stage | What Pragya does | Backend she drives |
|---|---|---|
| 1. Baseline knowledge | ingest company basics + deep research *before asking anything she could answer herself* | company profile + web research tools |
| 2. Working assumptions | an explicit, **reviewable** hypothesis of the business, mapped onto the 19 processes; assumptions stated as assumptions | conversation state (session artifacts) |
| 3. Deep ingestion | KB build: uploads + connected sources → chunked, indexed | shipped documents/KB + RETR chunking |
| 4. Revised analysis | test stage-2 assumptions against evidence; surface open questions rather than guess | KB retrieval + session artifacts |
| 5. Solution engineering | structured brainstorm *with* the user: priorities, pains, KPIs, budget envelope | conversation + envelope admin view |
| 6. Blueprint finalization | which bundle/processes/agents activate; anything missing → Meta-Agent (later) | `list_bundles` + `governance_preview` |
| 7. Integration | connect email/WhatsApp (voice when VOICE lands) | shipped connection routers (wizard step 2) |
| 8. Test & deploy | activate at A1, verify triggers armed | `activate_for_company` + `onboarding_status` |
| 9. Operate | monitor, **report KPIs**, surface HITL, take commands; stages 4–6 revisited continuously | signals, approvals, KPI registry (§3) |

**Command handling (the AUTH contract):** every user turn passes intent extraction; a command intent is classified by `inward_auth.tiers.classify_intent` and **executed only behind `require_tier`** — T2 prompts the step-up modal in-console; T3 adds out-of-band. Approvals Pragya surfaces link to the Judgment Desk; she never collects an approval in-chat (standing rule 2).

**Stage 1–5 scripts (decision: Rahul reviews).** Each of stages 1–5 gets a per-stage script/prompt asset — drafted from the Blueprint's discovery protocol, checked in like curated templates, and shipped **only after a named Rahul review checkpoint** (T4 below blocks on it). Script quality is regression-pinned by eval goldens over recorded stage transcripts.

## 2. C4 — Autonomy demotion triggers (closed here)

Promotion exists (checkpoint 17 + §9.7 evidence); demotion was undefined — and "≥98% unedited acceptance" invites rubber-stamping. The policy (in `governance/demotion.py`, TRUST's policy-then-enforcement shape):

* **Triggers** (any ⇒ automatic demotion one level + a `governance.autonomy_demoted` signal + Pragya reports it in stage-9): sustained SLO breach (per-agent p95 latency/failure over its sheet's floor), complaint spike (counterparty negative-sentiment rate over baseline), critic-block surge (PolicyGate/Pre-Critic block rate over threshold), a hard_block incident at T3 severity, or an owner command ("demote X" is T2).
* **Anti-rubber-stamp:** promotion evidence must include **mandatory random deep-audit sampling** — N sampled outputs re-reviewed blind; acceptance-rate alone is insufficient by construction.
* **Enforcement:** a sweep in the existing cron family (beside `apply_checkpoint_timeouts`) evaluates triggers from `usage_logs`/run outcomes/signals; demotion writes the entity's governance and emits the signal. Pure policy unit-tested without DB.

## 3. C6 — KPI definitions (closed here)

Blueprint gives KPIs sources but no formulas ("gross_margin, source: P10 — computed how?"). Pragya *reports* KPIs, so definitions must exist before her stage-9 lines are trustworthy. Deliverable: **[03_kpi_definitions.md](./03_kpi_definitions.md)** (authored with PRAGYA T5) — per KPI: **formula** over the HBS record graph (SCH objects), **data prerequisites** (which objects/fields must be populated; what the Solo Pack captures today vs Inc-4 connectors), **baseline method** (trailing window vs cohort), and **honest-absence rule** — a KPI whose prerequisites are unmet reports "not yet measurable: missing X" (never a fabricated number). Code: `ai/kpi/definitions.py` (typed registry) + `ai/kpi/compute.py` (queries over tenant records + billing), exposed at `/ai/kpi/business` for both Pragya and the dashboards. "Week 12 > Week 1" becomes measurable against these definitions.

## 4. Code Mapping

| Piece | Where | Notes |
|---|---|---|
| Package | `backend/src/ai/pragya/` (new; strict allowlist) | orchestration + stages, no new agent-loop machinery |
| Session/state | `pragya/models.py` — `account_manager_sessions` is AUTH's table (she reads/writes `auth_level` via AUTH's API only); `pragya_engagements` (company_id, stage, artifacts JSON, updated_at) | migration `prag001` (off `iauth001`) |
| Stage machine | `pragya/stages.py` — stage enum + advance/revisit rules (9 stages, 4–6 re-enterable) | pure |
| Scripts | `pragya/scripts/stage_{1..5}.py` — reviewable per-stage script assets (Rahul checkpoint) | like curated templates |
| Intent → tier | `pragya/intents.py` — extract command intents; classify via `inward_auth.tiers`; execute behind `require_tier` | one taxonomy (§20) |
| Chat transport | `pragya/api.py` — `/ai/pragya/chat` (POST turn + SSE stream), company-scoped | FE `useSSE` hook exists |
| Stage calls | `solo_pack/onboarding.py` functions (unchanged), connection routers, documents/KB | the Inc-2 contract, decision 4 realized |
| C4 | `governance/demotion.py` + sweep beside `checkpoint_sla`; `governance.autonomy_demoted` SignalType | policy pure; enforcement at cron |
| C6 | `ai/kpi/{definitions,compute}.py` + `/ai/kpi/business` + [03_kpi_definitions.md](./03_kpi_definitions.md) | honest-absence rule |
| FE | `PragyaConsole` page (chat + stage rail + step-up modal + approval links) | rides `inc2/onboard-fe` |

## 5. Task Plan

| # | Task | Acceptance |
|---|---|---|
| T1 | ✅ Package + `prag001` + stage machine (pure) + engagement persistence | stage transitions unit-pinned; revisit 4–6 legal |
| T2 | ✅ Chat transport + FE console (SSE) + intent extraction behind `require_tier` (T0/T1 only until T3 lands) | bound owner converses; unbound refused (golden) |
| T3 | ✅ Stages 6–9 conversationally over the wizard APIs | exit-demo path: converse → activate → status, equal to wizard output |
| T4 | ✅ Stage 1–5 scripts drafted → **Rahul review checkpoint passed 2026-07-22** → shipped ([02a](./02a_stage_scripts.md), source `pragya/scripts/`) | no script ships unreviewed (decision 3) |
| T5 | ✅ **C6** KPI registry + compute + doc 03; stage-9 reporting uses it | unmet prerequisites report honestly; formulas unit-tested |
| T6 | ✅ **C4** demotion policy + sweep + signal; Pragya reports demotions | trigger goldens; demotion visible in stage-9 |
| T7 | ✅ T2/T3 command execution wired to AUTH step-up (pause/resume, approve-via-desk links) | exit demo end-to-end; parity/eval green |

## 6. Brainstorm Decisions (Rahul, 2026-07-22)

1. **Console chat first**; voice/WhatsApp adapters arrive with VOICE over the same session + `require_tier` seams.
2. **Rahul is the stage-script quality reviewer** — T4 has a hard review checkpoint; drafts come from the Blueprint's discovery protocol.
3. Carried: the wizard's step APIs are Pragya's stage APIs (Inc-2 decision 4 — no contract fork); every agent she activates starts at A1.

---

## 7. Build Notes (2026-07-22) — delta log

All seven tasks landed on `inc3/pragya`. Gates at merge: **1325 unit** (+95), 16 parity/eval, **152 integration** (+11), mypy `--strict` over **211** files (allowlist gained `pragya` + `kpi`), layout lint exit 0, `prag001` up/down/up clean, frontend build green.

### 7.1 What shipped

| Task | Module | Note |
|---|---|---|
| T1 | `pragya/{stages,models,engagement}.py`, `prag001` | 9-stage machine, pure; `pragya_engagements` + `pragya_turns` |
| T2 | `pragya/{intents,conversation,api}.py` | `/ai/pragya/chat` + SSE; extraction → tier → `require_tier` |
| T3 | `pragya/deployment.py` | stages 6–9 over the *unchanged* Inc-2 wizard functions |
| T4 | `pragya/scripts/stage_{1..5}.py` | **reviewed and approved by Rahul 2026-07-22**; [02a](./02a_stage_scripts.md) |
| T5 | `ai/kpi/{definitions,compute,api}.py`, [03](./03_kpi_definitions.md) | 10 KPIs; honest-absence rule |
| T6 | `governance/{demotion,demotion_sweep,crons}.py` | C4 triggers + daily sweep + anti-rubber-stamp |
| T7 | `pragya/commands.py`, `PragyaConsole.tsx` | pause/resume/demote behind step-up; console + stage rail |

### 7.2 Design deltas (decided during build)

1. **Classification happens before generation, not after.** A turn resolves its tier and authorisation *first*, and only then writes prose. Generating first invites a model that has already promised to pause a process to then discover it may not — the refusal has to be the thing that gets said, not a correction to something already said.
2. **The keyword screen runs alongside the model and can only raise.** `intents.screen_text` is independent of extraction. If the raw text says "pause" and the model called it a read, the pause wins. Extraction failure is not a pass-through either: no reading → `UNKNOWN` → T3. Both directions defend the same property — *a command must never be tiered lower than its words suggest*.
3. **An unscoped pause asks instead of assuming "everything".** Found by the integration test, and it was a genuine safety bug: with no LLM extraction, "pause invoice chasing" produced `target=None`, and the executor read that as *all triggers*. Now only the kill switch and an owner who literally said "everything" reach `ALL_TRIGGERS`; an unresolved target gets a clarifying question. Resolving ambiguity toward the broadest destructive action is the worst available guess.
4. **Pausing disarms triggers; it does not delete them.** Inbound work still arrives and parks, so resuming picks up rather than starting from a gap — the same parked-not-dropped posture as C5's read-only dunning state.
5. **Promotion is not executable by chat command.** `execute_command` runs demotion but refuses "promote X", because raising autonomy needs §9.7 evidence *and* the random deep-audit sample. A conversational promote is precisely the shortcut C4's anti-rubber-stamp rule exists to prevent.
6. **The demotion sweep is daily, not on the 60-second signal sweeper.** Its window is 7 days, so the answer cannot change between two minutes, and the queries are per-agent aggregates over `execution_runs`. Running it on the fast sweeper would repeat the most expensive query in the system 1,440× for an identical result.
7. **`func.case` does not exist — it is `sqlalchemy.case`.** mypy passed it happily because `func.*` is `Any`; the integration test caught it. Worth remembering: **strict typing does not cover SQLAlchemy's `func` namespace**, so anything built there needs a test that actually executes the query.
8. **SSE streams a resolved turn, not live generation.** The turn completes (including authorisation) and is then chunked to the client. Streaming generation directly would let tokens reach the wire before the tier was checked, so a refusal could arrive mid-sentence.
9. **`gross_margin` ships deliberately uncomputable.** Registered with `captured_today=False` and reporting what it needs. Dropping it would hide the gap; approximating it would fabricate. It is the worked example of C6's whole point — see [03](./03_kpi_definitions.md) §5.

### 7.3 What is NOT wired yet

* **Stage advancement is manual.** `engagement.advance` is exposed and unit-pinned, but no conversational trigger decides "stage 2 is complete, move on" — the exit criteria in each script are prose the model reads, not a checked predicate. A turn does not currently move the stage on its own.
* **Stage 1's research is not automated.** The script says "you researched the company"; nothing calls the Web Intelligence Suite to actually do it yet. `baseline.research_summary` is an artifact key waiting for a producer.
* **Eval goldens over stage transcripts** (T4's second half) are not written. Script *structure* is pinned by `test_pragya_stage_scripts.py`; script *quality* is not regression-tested.
* **Voice/WhatsApp adapters** are the VOICE workstream. `handle_turn` already takes `channel_kind`/`channel_address` and resolves bindings, so the seam exists.
