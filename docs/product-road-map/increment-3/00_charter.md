# Increment 3 — Pragya v1 — Charter

> **Status:** Questions round **done** (Rahul, 2026-07-22) — decisions locked below; full workstream docs follow ([00_overview](./00_overview.md) · [01_auth](./01_auth_inward_channel.md) · [02_pragya](./02_pragya_v1.md)).
> **Parent:** [build_roadmap.md](../build_roadmap.md) §4, Increment 3 (L). **Prerequisite:** Increment 2 (the wizard + dashboards Pragya replaces conversationally; SIG for her reporting).

## Goal

The "talk to your account manager" experience, safely authenticated, running a consulting-grade onboarding.

## Scope (from the roadmap)

* **AUTH** — inward-channel authentication (technical §11.3, design done): enrolled channel bindings, T0–T3 command tiers sharing the §20 authority taxonomy, passkey/OTP step-up, out-of-band confirmation for critical commands, Pragya-can't-approve-herself rule.
* **PRAGYA v1** — the **nine-stage engagement flow** (functional §4.3): baseline research → working assumptions → deep ingestion → revised analysis → solution engineering → blueprint finalization → integration → test/deploy → operate. Implemented as conversational orchestration over the same APIs the Inc-2 wizard uses. Stages 1–5 need per-stage scripts/prompts (built here; the protocol closed C8).
* `account_manager_sessions` (+ `auth_level`, `elevated_until`), channel adapters over shipped voice/WhatsApp/email paths.

## Register findings to close here

C4 (autonomy demotion triggers), C6 (KPI metric definitions — Pragya reports them, so they must be defined).

## Decisions (Rahul, 2026-07-22 — the charter's questions round; do not re-open)

1. **Channel: web-console chat first.** Pragya v1 ships as a chat surface in the shipped React app (reuses SSE/auth infra; easiest step-up UX). Voice and WhatsApp adapters follow inside Inc 3 — KAR-01-real + B7 remain in-increment but do not gate the console channel.
2. **Step-up: platform-built WebAuthn now.** Full passkey/FIDO2 in-house (`py_webauthn` server-side + browser WebAuthn API) with TOTP fallback, per technical §11.3. No auth vendor — no external identity dataflow.
3. **Stage 1–5 script quality: Rahul reviews drafts.** Scripts are drafted from the Blueprint's discovery protocol; Rahul reviews/edits as domain owner at named checkpoints in the Pragya task plan before they ship.
4. *(Sequencing, same round:)* the **ONBOARD frontend** is built **in parallel** with these Inc-3 design docs — Node is available on the dev VM after all (HANDOFF §1) — and the console channel builds on that restored FE gate.
