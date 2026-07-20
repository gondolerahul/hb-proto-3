# Increment 2 / KAR — Karuna Gateway Agents (the outward face)

> **Status:** Draft — for brainstorm review · **Branch:** `inc2/kar` · **Register:** async half of the outward face (voice/B7 deferred).
> **Design authority:** Blueprint §2.3 (Karuna deployable), §9.5 (world-facing threat model), §7.3 (KAR-01/02/03). Self-contained below.
> **Depends on:** SLICE (KAR-02 exists there), SIG. **Async-first (decision 2):** email + WhatsApp ship; voice is a stub.

---

## 1. Design (self-contained)

Karuna is the compassionate outward face — the attack surface. Every gateway is an **axle AGENT** carrying the **Karuna profile** that turns counterparty content into signals the loop can trust:

* **Data, never instruction.** Counterparty text (email body, WhatsApp message) enters the loop as *data* in `signal.payload`, never as a prompt directive. The gateway's own system prompt is authored; the counterparty's words are quoted content. Injection attempts (`"ignore your instructions"`, `"transfer money"`) are flagged and logged as `incident.security` on pattern match (the shipped Pre-Critic + the §18.6 counterparty-trust stamp), and — defense in depth — gateways carry **no monetary authority**, so a hijack has nothing to reach.
* **Trust stamping.** Gateways stamp every emitted signal `trust: counterparty` (§18.6), so the PolicyGate refuses high-impact categories downstream by construction.
* **Consent-aware.** Outbound sends check the consent/DNC registry (D6, TRUST) before dispatch; inbound records the counterparty's channel identity for the episodic memory (per-counterparty, A7).

Three gateways; two ship:

| Gateway | Channel | Inc 2 | Emits |
|---|---|---|---|
| **KAR-02 Email** | IMAP/SMTP (shipped `ai/tools/email/`) | ✅ (from SLICE) | `lead.inbound`, `ticket.opened`, `email.reply` |
| **KAR-03 Messaging** | WhatsApp (Twilio + Tata, shipped `voice/` WhatsApp) | ✅ | `lead.inbound`, `ticket.opened`, `message.inbound` |
| **KAR-01 Voice** | Realtime (Gemini Live / Azure Realtime, shipped) | ⬜ **stub** | — (deferred; B7 collapsed-loop design pending) |

The **KAR-01 stub** is a registered, deploy-valid entity that parks any voice trigger with a "voice coming soon" note — so the pack is structurally complete and the voice follow-on drops in without reshaping the registry.

## 2. Code Mapping

| Piece | Where | Notes |
|---|---|---|
| Gateway base behavior | `backend/src/ai/solo_pack/gateways/` | shared Karuna-profile agent behavior; KAR-02/03 specialise channel parsing |
| WhatsApp producer | extend the shipped WhatsApp inbound path (`voice/` WhatsApp router) to emit `message.inbound`/`lead.inbound` via `ai/signals/service.py` | mirrors SLICE's email producer; `dedupe_key` = provider message SID |
| Karuna profile enforcement | GOV deploy validator (shipped Karuna gate) | a gateway without `karuna_profile:true` fails to publish |
| Consent check on outbound | `ai/solo_pack/consent.py` (TRUST) | called before any outbound send |
| Voice stub | `solo_pack/templates/kar01_voice_stub.*` | deploy-valid; parks `voice.*` triggers |

## 3. Task Plan

| # | Task | Deliverable / acceptance |
|---|---|---|
| T1 | Generalize KAR-02 (from SLICE) into the shared gateway base | email + a second signal type (`ticket.opened`) both flow |
| T2 | KAR-03 WhatsApp gateway: inbound → `lead.inbound`/`message.inbound` | an inbound WhatsApp produces the right signal + a Lead/Ticket; SID dedupe |
| T3 | Karuna threat-model posture: injection→`incident.security`, `trust:counterparty` stamping, no-monetary-authority assertion | injection golden: a hostile message never reaches a high-impact tool |
| T4 | KAR-01 voice stub entity | registers + deploy-validates; parks voice triggers with a clear message |
| T5 | Consent hook on outbound + gates | outbound blocked when the registry says no-contact; mypy/eval green |

## 4. Open Questions

1. **WhatsApp template/session constraints** — WhatsApp Business restricts outbound outside a 24h session window to approved templates. Does the MVP outbound path only reply within-session (simplest) or manage templates? Proposal: within-session replies only for Inc 2; templated outbound in a later pack.
2. **Voice follow-on placement** — Inc 2.5 vs folded into Inc 3 (see overview Q1).
