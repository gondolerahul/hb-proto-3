# Increment 2 — 🎯 The Solo Pack (the sellable MVP): Overview

> **Document Class:** Increment Design & Implementation Plan (index)
> **Author:** Buddha Cognitive Lab (drafted by Claude, decisions by Rahul)
> **Created:** 2026-07-20 · **Status:** Draft — for brainstorm review before development begins
> **Parent:** [build_roadmap.md](../build_roadmap.md) §4 (Increment 2, size L–XL) · supersedes [00_charter.md](./00_charter.md)
> **Prerequisite:** Increment 1 complete (SIG, GOV, SCH, LOOP+ENV live on master).
> **Design authority:** Blueprint §14 (Wave-0 Solo Pack), §7.3 (agent registry), §9 (governance); Functional §2.1 (bundles), §4.3 (engagement flow), §6 (tools), §8 (channels); Technical §11 (Pragya), §18–§24 (Inc-1 substrate). Self-contained per workstream doc; the technical doc is corrected first on any divergence.

---

## 1. Goal

The sellable moment. A solopreneur signs up, runs a guided wizard, activates the **Solo Pack**, and their business starts answering email/WhatsApp, qualifying and quoting, chasing invoices, reconciling, and reporting — every external effect governed at **A1** with a HITL card, all riding the Increment-1 substrate (signal bus, PolicyGate, tenant records, Loop heartbeat, wallet holds).

**Exit demo (sellable):** an inbound email becomes a `email.inbound` signal → the trigger fires **P03**'s Inbound Deal Closer → it reads/writes the tenant record graph (Signal→Lead→Opportunity→Quote) → drafts a quote → the PolicyGate raises an **A1 HITL card** before it sends → the owner approves in the wizard-installed console → the Loop heartbeat rolls the cost into the envelope. Then the same tenant activates a second bundle and a second process comes alive with zero new plumbing.

## 2. Decisions Taken (Rahul, 2026-07-20 — do not re-open during build)

1. **Thin vertical slice first.** Build ONE channel + ONE process end-to-end (email → P03 acquisition) before broadening to the full 12 agents / 6 processes. De-risk integration early; first sellable demo soonest.
2. **Async-first MVP; voice deferred.** The Solo Pack ships on **email + WhatsApp** (both wired, enter via SIG). The Karuna **Voice** Gateway (KAR-01) is a **stub**; the realtime voice profile + the open **B7** collapsed-loop/warm-transfer design land in a follow-on increment (proposed Increment 2.5 / folded into Inc 3).
3. **Curated hand-authored agent templates.** The 12 Solo Pack agents + 6 Wave-0 processes are deterministic, reviewable entity definitions checked in as the product's quality bar (like the approved HBS spine) — authority bands + `sod_class` + `karuna_profile` set. The Meta-Agent Board stays for tenant-**custom** agents (later).
4. **Wizard-driven onboarding; Pragya in Inc 3.** A guided setup wizard (connect channels → upload KB → confirm A1 governance → activate bundle). The conversational nine-stage Pragya flow (functional §4.3) wraps/replaces it in Increment 3 over the same APIs.
5. **Global-neutral market.** Jurisdiction-agnostic consent/DNC (pluggable registries), multi-currency from day one — no single hard-coded compliance target. (Chose breadth over the India-first shortcut; the shipped Razorpay/Tata/GST pieces become *one* pluggable profile, not the assumption.)
6. **Graduated dunning.** Wallet/subscription lapse flows: dunning notifications → configurable grace window → **degraded read-only mode** (tenant reads/exports, agents stop acting) → only then hard suspend. Protected processes (P14/P17) keep their reserved envelope through grace. Closes C5.
7. **First slice = email → P03 acquisition** (Wave-1 anchor: high volume, low blast radius — drafts, not money).

## 3. Workstreams

| # | Doc | Workstream | Closes | Depends on |
|---|---|---|---|---|
| 1 | [01_slice_email_to_quote.md](./01_slice_email_to_quote.md) | **SLICE** — email → P03 acquisition, end-to-end (the spine) | C1 (P03) | Inc 1 (all) |
| 2 | [02_kar_gateways.md](./02_kar_gateways.md) | **KAR** — Karuna gateway agents (email, WhatsApp; voice stub) | part of B7 (async only) | SLICE, SIG |
| 3 | [03_pack_agents_processes.md](./03_pack_agents_processes.md) | **PACK** — 12 curated agents + 6 Wave-0 process sheets + 7 bundles | C1 (all 6), Inc-1 owner-id resolution | SLICE, GOV, SCH |
| 4 | [04_onboard_wizard.md](./04_onboard_wizard.md) | **ONBOARD** — setup wizard + Inc-1 admin UI (signals/triggers/envelopes) | — | PACK, KAR |
| 5 | [05_trust_billing_safety.md](./05_trust_billing_safety.md) | **TRUST** — dunning/degraded, consent/DNC, HITL SLAs, platform-spend budget, economics | C5, D6, C3, B13, E1, E2, E4 | GOV, LOOP+ENV |
| 6 | [06_retrieval_upgrade.md](./06_retrieval_upgrade.md) | **RETR** — §24.4 hybrid retrieval + structure-aware chunking + goldens (Inc-1 carryover) | closes B8's retrieval half | SCH, control-plane KB |

## 4. Build Order

Vertical-slice-first, then broaden, then package, then make-safe-to-sell, then quality:

1. **SLICE** (`inc2/slice`) — prove the whole path carries a real sale end-to-end.
2. **PACK** + **KAR** (`inc2/pack`, `inc2/kar`) — broaden the slice to all 12 agents / 6 processes / both async channels (KAR generalizes what SLICE built for email; PACK authors the rest).
3. **ONBOARD** (`inc2/onboard`) — the wizard packages activation; the Inc-1 admin UI (deferred from Increment 1) lands here.
4. **TRUST** (`inc2/trust`) — dunning/degraded, consent/DNC, platform-spend caps, abuse controls: the billing-safety and compliance floor a real launch needs. Its billing-safety pieces (C5/E2/B13) gate GA; runs partly in parallel with ONBOARD.
5. **RETR** (`inc2/retr`) — the retrieval-quality upgrade; last, gated by its own goldens.

Each branch merges when its acceptance criteria pass and eval/parity gates stay green.

## 5. Register Findings — where each closes

| Finding | Workstream | Note |
|---|---|---|
| **C1** process design sheets | SLICE (P03) + PACK (the other 5) | authored per-process as each is built |
| **C3** per-checkpoint HITL SLAs | TRUST | per-checkpoint SLA + auto-park/deny fallback |
| **C5** dunning/degraded mode | TRUST | graduated: notify→grace→read-only→suspend |
| **D6** consent/DNC/unsubscribe registry | TRUST | pluggable/jurisdiction-agnostic (global-neutral) |
| **B7** realtime voice vs loop | **deferred** | async-first MVP; voice profile is a follow-on |
| **B13** platform-initiated spend | TRUST | "platform-initiated" budget class + caps + attribution |
| **E1** idle-cost model | TRUST | takes the measured Inc-1 tenant-DB idle cost as input |
| **E2** free-credit abuse controls | TRUST | verification gates + throttles |
| **E4** fee formula edge cases | TRUST | log/alert on clamped negatives; ordering intent |

**B7 is explicitly deferred** (decision 2) — the only Inc-2-charter finding not closed here; the roadmap's Increment-2 mapping in the gap register is updated to move B7 to the voice follow-on.

## 6. Standing Rules (from the roadmap)

1. **Nothing ships flag-OFF into the sellable path** — the Solo Pack is the sellable path, so its agents, governance, and dunning are ON at GA.
2. **Autonomy starts at A1 everywhere** — every Solo Pack agent is A1; raises route through checkpoint 17 (Inc-1 GOV).
3. **Docs move with code** — flip maturity tags + add a §N build-note delta log per workstream on merge.
4. **Curated templates are reviewed like the HBS spine** — each agent/process definition is checked in and Rahul-reviewed before it's seed data (the pack is the product).
5. **Eval/parity gates non-negotiable** — new agents get behavioral goldens (the eval layer, technical §22).

## 7. Carried from Increment 1 (must land in Inc 2)

* **Admin UI** for signals / triggers / envelopes (Inc-1 was API-only) → ONBOARD.
* **Owner-process-id resolution** — the 27 HBS defs store canonical process *codes*; when PACK seeds the 6 Wave-0 PROCESS entities, resolve `owner_process_code` → `owner_process_id` (Inc-1 SCH decision) → PACK.
* **Governance seeding completeness** — every channel-facing Solo Pack entity gets explicit **authority bands** + real **`sod_class`** (Inc-1 GOV left unset bands pass-through) → PACK.
* **§24.4 retrieval upgrade** → RETR.

## 8. Brainstorm Decisions (Rahul, 2026-07-20) — cross-workstream

Per-workstream decisions live in each doc's final section; the cross-cutting ones:

1. **Voice folds into Increment 3** (with Pragya, who needs the same realtime/collapsed-loop path) — not a separate Increment 2.5. The KAR-01 voice stub keeps the registry complete meanwhile.
2. **Bundles are pure activation sets, included at all subscription tiers** — no per-tier bundle gating; pricing/tiers differ on other dimensions (credits, Growth+ features, hibernation), not on bundle availability.
3. **The wizard is the Inc-2 stand-in for Pragya's HUB** — no Pragya entity ships in Inc 2; the wizard's step APIs are authored as the stage APIs Pragya drives in Inc 3.
4. **Consent is tenant-configured from day one** — the platform imposes no global opt-in default; each tenant sets and owns their per-purpose posture, enforced by the registry and logged at onboarding ([05](./05_trust_billing_safety.md) §2).
