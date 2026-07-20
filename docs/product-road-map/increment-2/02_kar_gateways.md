# Increment 2 / KAR — Karuna Gateway Agents (the outward face)

> **Status:** ✅ **Built (2026-07-20)** — T1–T5 done on `inc2/kar`; gates green (mypy `--strict` incl. `solo_pack`+`signals`, unit + integration, parity, eval; layout clean). WhatsApp enters through SIG (governed loop), the voice stub keeps the registry complete, and a counterparty-trust injection can never reach money. See §5 build notes. · **Branch:** `inc2/kar` · **Register:** async half of the outward face (voice/B7 deferred).
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

## 4. Brainstorm Decisions (Rahul, 2026-07-20)

1. **Within-session WhatsApp replies only** for Inc 2 — no template management; templated outbound (outside the 24h session window) is a later pack.
2. **Voice follow-on folds into Increment 3** (alongside Pragya, who needs the same realtime/collapsed-loop path) — not a separate Increment 2.5. The KAR-01 voice stub keeps the registry structurally complete until then.

## 5. Build Notes — deltas discovered during implementation (2026-07-20)

1. **A shared `_karuna_gateway` builder, not a `gateways/` package.** With only three gateways (two live, one stub), the doc's proposed `solo_pack/gateways/` behavior package was over-structure. The Karuna posture — `karuna_profile: true`, **no authority bands**, CRM-scoped memory — is enforced *by construction* in one builder in `templates/gateways.py`; KAR-02 stays hand-authored in `acquisition.py` as the reference. The posture is unit-asserted (every gateway is profiled + money-less).

2. **KAR-03/01 are the first entities the deploy Karuna-gate actually fires on.** KAR-02's channel was implicit (no provider metadata), so `_has_external_binding` returned false and the gate passed *trivially*. KAR-03 (`whatsapp_provider`) and KAR-01 (`telephony_provider`) declare providers → the gate treats them as externally bound and *requires* `karuna_profile`. A unit test proves a bound gateway that dropped the profile fails to publish — the gate is now proven live.

3. **WhatsApp enters via a subscription-gated cutover, not a rewrite.** The shipped `src/voice/whatsapp_handler.py` replies with Gemini directly, bypassing SIG/governance. Rather than rip that out, `signals/whatsapp_inbound.py` mirrors `email_poll`: an inbound message becomes a `message.inbound` signal (`trust: counterparty`, SID-deduped) **only when the tenant has an enabled `message.inbound` trigger** (Solo Pack activated). The handler calls it first and returns early on success (governed reply is async); tenants not on SIG and any error fall through to the legacy path untouched. The roster grows to **18** (3 gateways + 6 processes + 9 agents), and `activate_slice` now seeds email-only so the email→quote slice stays exactly 4.

4. **The injection golden is a pure gate check, not an LLM run.** `evaluate_policy(intent, gov)` is IO-free, so the §18.6 trust down-payment — a `counterparty`-trust signal can never drive payout/refund/contract/vendor, *blocked before autonomy is considered* — is a parametrised unit test. Combined with gateways carrying no money tools, a hostile message is harmless by two independent guarantees.

5. **Consent is a seam KAR ships and TRUST fills.** `solo_pack/consent.py` is the outbound `check_outbound_consent` hook with a pluggable checker (`set_consent_checker`) and a permissive default (decision 8: consent is tenant-configured, no global opt-in default). The jurisdiction-agnostic DNC/consent **registry (D6) and the wiring into send paths are TRUST** — the seam + contract + tests are here so that lands without touching callers.

**Task plan status:** T1 ✅ (shared gateway base + posture) · T2 ✅ (KAR-03 WhatsApp template + `message.inbound` producer + cutover) · T3 ✅ (trust stamping + injection golden + no-monetary-authority) · T4 ✅ (KAR-01 voice stub) · T5 ✅ (consent seam + gates green + this log). **Deferred:** real realtime voice + B7 → Increment 3; WhatsApp *outbound* templated sends + the full legacy-handler retirement → later.
