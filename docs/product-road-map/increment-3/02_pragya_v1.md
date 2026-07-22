# Increment 3 / PRAGYA — Pragya v1: The Nine-Stage Engagement over the Wizard's APIs

> **Status:** ⬜ Design (2026-07-22) — decisions locked, ready to build after AUTH · **Branch:** `inc3/pragya`
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
| T1 | Package + `prag001` + stage machine (pure) + engagement persistence | stage transitions unit-pinned; revisit 4–6 legal |
| T2 | Chat transport + FE console (SSE) + intent extraction behind `require_tier` (T0/T1 only until T3 lands) | bound owner converses; unbound refused (golden) |
| T3 | Stages 6–9 conversationally over the wizard APIs | exit-demo path: converse → activate → status, equal to wizard output |
| T4 | Stage 1–5 scripts drafted → **Rahul review checkpoint** → shipped + eval goldens over stage transcripts | no script ships unreviewed (decision 3) |
| T5 | **C6** KPI registry + compute + doc 03; stage-9 reporting uses it | unmet prerequisites report honestly; formulas unit-tested |
| T6 | **C4** demotion policy + sweep + signal; Pragya reports demotions | trigger goldens; demotion visible in stage-9 |
| T7 | T2/T3 command execution wired to AUTH step-up (pause/resume, approve-via-desk links) | exit demo end-to-end; parity/eval green |

## 6. Brainstorm Decisions (Rahul, 2026-07-22)

1. **Console chat first**; voice/WhatsApp adapters arrive with VOICE over the same session + `require_tier` seams.
2. **Rahul is the stage-script quality reviewer** — T4 has a hard review checkpoint; drafts come from the Blueprint's discovery protocol.
3. Carried: the wizard's step APIs are Pragya's stage APIs (Inc-2 decision 4 — no contract fork); every agent she activates starts at A1.
