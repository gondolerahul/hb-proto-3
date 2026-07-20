# Increment 2 / ONBOARD — The Setup Wizard + Admin Surfaces

> **Status:** ✅ **Backend built (2026-07-20)** — the wizard **step APIs** (Pragya's Inc-3 stage contract) + the admin-surface backends are done and green (mypy `--strict`, unit + integration, layout clean). The **frontend** (React wizard, approvals console, FE gates) is a **separate track, out of scope on this backend VM**. See §6 build notes. · **Branch:** `inc2/onboard` · **Register:** delivers the Inc-1 admin-UI carryover (backend).
> **Design authority:** Functional §4.3 (the nine-stage flow the wizard previews), §11 (GenUI is Inc 6 — these are hand-built screens). Wizard-driven, Pragya in Inc 3 (decision 4).
> **Depends on:** PACK (bundles to activate), KAR (channels to connect).

---

## 1. Design (self-contained)

A deterministic, hand-built React wizard (GenUI is Inc 6) that gets a solopreneur from sign-up to a live Solo Pack. It is the Inc-2 **stand-in for Pragya's HUB role** (overview Q3) — the conversational nine-stage flow (functional §4.3) wraps/replaces it in Inc 3 over the same APIs, so the wizard's steps map 1:1 onto Pragya's stages.

**Wizard steps** (each maps to a nine-stage Pragya stage):

1. **Connect channels** — OAuth/connect email (IMAP/SMTP) + WhatsApp (Twilio/Tata); each connection registers the KAR gateway triggers. *(Pragya stage 7: integration.)*
2. **Upload knowledge** — drop docs into the KB (shipped documents/chunks, control-plane); tenant business context for the agents. *(Stages 3–4: ingestion → analysis.)*
3. **Confirm governance** — show the A1 defaults + authority bands per the activated bundle; the owner confirms (raising above A1 is checkpoint-17, not a wizard toggle). *(Stage 5: solution engineering with the user.)*
4. **Activate the bundle** — pick the Solo Pack (default) or a starter bundle; activation seeds the agents/processes/triggers (PACK). *(Stages 8–9: deploy → operate.)*
5. **Go live** — a summary + the console link where HITL cards land.

## 2. Admin surfaces (the Increment-1 carryover)

Increment 1 shipped signals/triggers/envelopes as **API-only**. ONBOARD builds the minimal operator UI over those APIs:

* **Signals inspector** — status counts (the coverage KPI), parked/escalated/dead queues, replay.
* **Trigger registry editor** — list/enable/disable/priority (over the Inc-1 trigger API).
* **Budget envelope view** — Sheel's envelope: utilization, reserve, downshift state (over the LOOP data).
* **The approvals console** — where PolicyGate HITL cards land (extends the shipped approvals panel; the exit-demo's approve step).

## 3. Code Mapping

| Piece | Where | Notes |
|---|---|---|
| Wizard | `frontend/` new onboarding flow | hand-built; calls activation + connection + KB APIs |
| Activation API | `ai/solo_pack/activation.py` (PACK) exposed via a router | POST activate bundle for the tenant |
| Admin surfaces | `frontend/` admin area over Inc-1 signals/tenant/loop APIs | read-mostly; the signals API gains list endpoints if missing |
| Connections | shipped email/WhatsApp connection routers | wizard wraps them + registers triggers |

## 4. Task Plan (outline)

| # | Task | Acceptance |
|---|---|---|
| T1 | Activation API + bundle-activation endpoint | wizard can activate the Solo Pack for a tenant |
| T2 | Wizard steps 1–5 (channels, KB, governance, activate, go-live) | a new tenant completes onboarding → Solo Pack live |
| T3 | Admin surfaces (signals inspector, trigger editor, envelope view) | operator can see parked signals + envelope utilization |
| T4 | Approvals console (HITL cards) | the SLICE exit-demo approve step works in the UI |
| T5 | Frontend gates (Storybook/Playwright per the shipped P-O3 track) + e2e | onboarding e2e green |

## 5. Brainstorm Decisions (Rahul, 2026-07-20)

1. **The wizard's step APIs are authored as Pragya's stage APIs** — activation/connection/governance endpoints are designed as the stage APIs Pragya will drive in Inc 3, so Inc 3 is a UI swap over the same contract, not a rebuild.
2. **Zero KB required to go live** — agents work from the HBS + curated templates; KB is optional and improves quality.

## 6. Build Notes — deltas discovered during implementation (2026-07-20)

**Backend built; frontend is a separate track** (Node/browser toolchain, out of scope on this VM — HANDOFF §7). What landed:

1. **The wizard steps are a service + a thin router, so the contract is testable without a browser.** `solo_pack/onboarding.py` holds the four steps as functions — `list_bundles` (step 4 picker), `governance_preview` (step 3, **pure** over the curated templates), `activate_for_company` (step 4, over PACK's `activate_bundle`), `onboarding_status` (step 5). `solo_pack/onboarding_router.py` is the company-scoped FastAPI wrapper (`/ai/onboarding/{bundles,governance-preview,activate,status}`). Unit tests drive the pure steps; an integration test activates a tenant and reads status back. This *is* decision 1 realised — the same functions become Pragya's stage calls in Inc 3.

2. **The bundle picker exposes future bundles honestly.** `list_bundles` returns the Solo Pack default + all 7 §2.1 bundles, each with `available_now` — Fulfillment/Talent (no Wave-0 process yet) show `false` and an empty `process_codes` while still advertising their full §2.1 membership, so the wizard can show the roadmap without pretending they activate.

3. **Two of the three admin backends were already shipped in Inc 1.** The signals inspector (`/ai/signals` list + `/coverage` + `/replay`) and the trigger-registry editor (`/ai/signals/triggers` CRUD) exist. The gap was the **budget-envelope view** — added `loop/api.py` `GET /ai/loop/envelope` (read-only): utilization, the protected reserve, and downshift/cap state over the Inc-1 LOOP data. The approvals console is the shipped `human_approvals` panel (frontend).

**Task plan status:** T1 ✅ (activation step API) · T2 ✅ (wizard step APIs — the backend of steps 1–5) · T3 ✅ (admin surfaces: signals + triggers already shipped, **budget-envelope GET added**) · **T4/T5 (React wizard + approvals console UI + FE gates) → frontend track, deferred off this VM.**
