# Increment 3 — 🪷 Pragya v1 (talk to your account manager): Overview

> **Document Class:** Increment Design & Implementation Plan (index)
> **Author:** Buddha Cognitive Lab (drafted by Claude, decisions by Rahul)
> **Created:** 2026-07-22 · **Status:** Design locked — decisions taken in the charter's questions round (2026-07-22)
> **Parent:** [build_roadmap.md](../build_roadmap.md) §4 (Increment 3, size L) · supersedes the stub in [00_charter.md](./00_charter.md)
> **Prerequisite:** Increment 2 complete on `master` (Solo Pack + wizard step APIs + TRUST + RETR; ONBOARD FE on `inc2/onboard-fe`).
> **Design authority:** Technical §11.3 (inward-channel authentication — the design is done, this increment builds it), §20 (authority taxonomy / PolicyGate); Functional §4.2–§4.4 (Pragya, the nine-stage flow); Blueprint §9.5 (Karuna's outward mirror), §14 (Wave-0). Self-contained per workstream doc; the technical doc is corrected first on any divergence.

---

## 1. Goal

The **"talk to your account manager"** experience, safely authenticated, running a consulting-grade onboarding. A tenant owner opens the console and *converses* with **Pragya** — she researches their business, states her assumptions, ingests their documents, engineers a solution *with* them, activates it, and then operates it: reporting KPIs, surfacing approvals, and taking commands — where every command is authenticated to the **T0–T3 impact tiers** before it acts, because an unauthenticated inward face is a full-company compromise (register D1).

**Exit demo:** a bound owner asks Pragya (console chat) *"how did we do this week, and pause invoice chasing while I'm away"*. Pragya reports the week's KPIs (C6 definitions, computed not asserted), classifies the pause command as **T2**, prompts a **passkey step-up**, executes it after verification, and posts the confirmation — while the *same* command from an unbound session gets a polite refusal + enrollment path. A payment approval she surfaces routes to the Judgment Desk console, never to her own chat ("Pragya can't approve herself").

## 2. Decisions Taken (Rahul, 2026-07-22 — do not re-open during build)

1. **Console-first channel.** Pragya v1 ships as web-console chat inside the shipped React app (SSE, same auth/session substrate). Voice (KAR-01 real + B7) and WhatsApp adapters follow *inside this increment* but do not gate the console release.
2. **Platform-built WebAuthn for step-up.** Full passkey/FIDO2 in-house (`py_webauthn` server-side + the browser WebAuthn API), TOTP as the §11.3 fallback. No auth vendor — no external identity dataflow (mirrors TRUST's global-neutral posture).
3. **Rahul reviews the stage 1–5 scripts.** The consulting-quality bar: scripts are drafted from the Blueprint's discovery protocol, and each ships only after a named Rahul review checkpoint (like the curated-template review in PACK).
4. **ONBOARD FE lands in parallel** — Pragya's console rides the restored FE gate and the same step APIs the wizard drives; Inc 3 is a conversation over the Inc-2 contract, not a rebuild.

## 3. Workstreams

| # | Doc | Workstream | Closes | Depends on |
|---|---|---|---|---|
| 1 | [01_auth_inward_channel.md](./01_auth_inward_channel.md) | **AUTH** — channel bindings, T0–T3 tier classifier, WebAuthn/TOTP step-up, session elevation, out-of-band T3 | **D1** (build; design closed 2026-07-18) | Inc-1 GOV (§20 taxonomy), shipped auth/session |
| 2 | [02_pragya_v1.md](./02_pragya_v1.md) | **PRAGYA v1** — the nine-stage engagement flow over the Inc-2 stage APIs, console chat, stage 1–5 scripts, KPI reporting, demotion triggers | **C4**, **C6**, C8's script half | AUTH, ONBOARD (step APIs + console FE) |
| — | *(folds into 2)* | **VOICE** — KAR-01 real + the B7 realtime/collapsed-loop path, as Pragya's second channel | **B7** | PRAGYA core, KAR |

## 4. Build Order

1. **AUTH** (`inc3/auth`) — the safety floor first: nothing conversational ships before commands are tiered and step-up works. Pure-policy pieces (tier classifier) land before ceremonies (WebAuthn), mirroring TRUST's policy-then-enforcement shape.
2. **PRAGYA core** (`inc3/pragya`) — the nine-stage state machine + console chat over the wizard's stage APIs, stages 1–5 scripts behind Rahul review checkpoints, C6 KPI definitions, C4 demotion triggers.
3. **VOICE** (`inc3/voice`) — KAR-01 becomes real on the same session/auth model; B7's collapsed-loop profile. Last because the console proves the flow first (decision 1).

Each branch merges when its acceptance criteria pass and the eval/parity gates stay green (the §22 harness; parity is the billing canary).

## 5. Register Findings — where each closes

| Finding | Workstream | Note |
|---|---|---|
| **D1** inward face unauthenticated | AUTH | design resolved 2026-07-18 (technical §11.3); Inc 3 is the build |
| **C4** autonomy demotion triggers | PRAGYA | demotion policy wired to agent SLOs + random deep-audit sampling on promotion evidence |
| **C6** KPI metric definitions | PRAGYA | formula + data prerequisites + baseline method per KPI; Pragya's stage-9 reporting computes these, so they must exist first |
| **B7** realtime voice vs loop | VOICE | deferred from Inc 2 by decision; Pragya needs the same realtime path |

## 6. Standing Rules (carried forward)

1. **One taxonomy, two enforcement points** — the tier classifier reuses the §20 authority-matrix categories the PolicyGate already evaluates; no parallel command vocabulary.
2. **Pragya can never satisfy her own checkpoint** — PolicyGate HITL cards route to the Judgment Desk (`/ai/approvals`), never to a confirmation spoken back over the possibly-compromised channel that asked.
3. **Channel identity is a hint, never proof** — caller ID / WhatsApp sender / email `From` route, they do not authenticate (the inward mirror of Karuna's SKL-X04).
4. **Autonomy starts at A1; demotion is automatic, promotion is evidenced** — C4's triggers make §9.7's reversibility claim real.
5. **Docs move with code** — maturity tags + §N build-note delta logs per workstream on merge; scripts are reviewed assets like the HBS spine.
