# Increment 3 / AUTH — Inward-Channel Authentication & Command Tiers

> **Status:** ⬜ Design (2026-07-22) — decisions locked, ready to build · **Branch:** `inc3/auth`
> **Design authority:** Technical §11.3 (the decided design — this doc maps it to code), §20 (authority taxonomy). Closes register **D1** (build).
> **Depends on:** Inc-1 GOV (`governance/authority.py` categories, `hitl_checkpoint_defs`), shipped `src/auth/` (users, JWT sessions), shipped voice/WhatsApp/email inbound paths (KAR).

---

## 1. Design (self-contained)

**The problem (D1):** Pragya accepts owner commands over channels whose identities are spoofable (caller ID, WhatsApp sender, email `From`). "Pause any process in one sentence" from a spoofed number is a full-company compromise. The outward face got SKL-X04 counterparty verification in KAR; this is the inward mirror.

**The shape:** *channel identity routes, verification authorizes.* Every inbound Pragya contact resolves to an **enrolled channel binding** or is treated as unauthenticated (polite refusal of anything tenant-specific + an enrollment path). Commands are classified into **impact tiers**; the higher the blast radius, the stronger the verification demanded *at that moment* — identity is never carried further than its proof strength.

### 1.1 The four tiers (§11.3, normative)

| Tier | Commands | Verification |
|---|---|---|
| **T0** | General questions touching no tenant data | none |
| **T1** | Reads/reports on tenant state; routine work assignment | bound channel identity + session continuity |
| **T2** | Sensitive: payment approvals, autonomy raises, pausing/resuming processes, bank-detail changes, bulk data operations | **Step-up:** passkey/WebAuthn ceremony (TOTP fallback) → elevated session, default 10 min |
| **T3** | Critical/irreversible: loop kill-switch, above-band payouts, regulatory filings | Step-up **plus out-of-band confirmation** on a second registered channel |

**One taxonomy, two enforcement points.** The tier classifier maps command intents onto the *same* §20 categories the PolicyGate evaluates (`CATEGORY_RULES` in `governance/authority.py`: payout, refund, discount, contract, price_change, vendor_creation, data_deletion, employment_offer, public_statement, regulatory_filing, email_dispatch). Tiering rules:

* intent touches no tenant data → **T0**; reads/reports → **T1**
* intent maps to any `CATEGORY_RULES` category, or mutates governance/process state (pause/resume, autonomy raise, binding/enrollment changes, bulk data ops) → **T2**
* intent maps to a `HIGH_IMPACT_CATEGORIES` member above its band, the loop kill-switch, or `regulatory_filing` → **T3**
* **unresolvable/ambiguous intent → the highest tier it could be** (fail up, never down)

### 1.2 Channel bindings

Enrollment is a **verified handshake**: the user proves control of the channel (OTP to that channel) *from an already-authenticated console session* — bindings are created at T2 (a binding change is itself a sensitive command). Bindings live on the user record (new table, not columns — one user has many channels). An inbound contact resolves `(channel_kind, address) → user_id` or is unauthenticated. **Console sessions are born T1**: the JWT login *is* the bound identity for the console channel; phone/WhatsApp/email contacts must resolve a binding to reach T1.

### 1.3 Step-up: platform-built WebAuthn + TOTP fallback (decision 2026-07-22)

* **WebAuthn/passkeys in-house**: `py_webauthn` server-side; registration + authentication ceremonies over `/ai/authn/webauthn/*`; credentials stored per-user (public key, sign count, transports). The browser console runs the ceremonies natively; non-console channels receive a **step-up link** that opens the console's ceremony (the phone app *is* the registered authenticator).
* **TOTP fallback** (§11.3): standard RFC-6238 enrollment (QR at settings, encrypted seed at rest) for users without passkey-capable devices. A successful TOTP step-up elevates exactly like a passkey one; policy may later restrict T3 to passkey-only without schema change.
* **Session elevation**: a successful ceremony stamps `auth_level` + `elevated_until` (default **10 minutes**) on the session row. Expiry demotes silently; every T2/T3 command re-checks at execution time, not at classification time.
* **T3 out-of-band**: after step-up, a confirmation nonce goes to a *second* registered channel (different binding than the one that issued the command); the command executes only when both legs agree within the window.

### 1.4 Anti-spoof posture

* Channel identity is a routing hint; voice-print may add signal but is **never a sole factor**.
* **Repeated failed step-ups lock T2+** for that user (counter + cooldown on the session/user), and alert **all** registered channels.
* **Pragya can never satisfy her own checkpoint**: PolicyGate HITL cards route to the Judgment Desk (`/ai/approvals` console), never back over the channel that issued the command. The AUTH seam enforces this by construction — approvals are console-only artifacts; `respond` requires a console session at T2.

## 2. Code Mapping

| Piece | Where | Notes |
|---|---|---|
| Package | `backend/src/ai/inward_auth/` (new; add to `typecheck_ai.py` `CLEAN_PACKAGES`) | policy strict-typed + unit-testable, TRUST's shape |
| Models | `inward_auth/models.py` — `channel_bindings` (user_id, channel_kind, address, verified_at, last_seen_at), `account_manager_sessions` (user_id, company_id, channel_kind, `auth_level`, `elevated_until`, failed_stepups, locked_until), `webauthn_credentials`, `totp_secrets` | control-plane tables; migration **`iauth001`** (off `retr003`) |
| Tier classifier | `inward_auth/tiers.py` — `classify_intent(intent) -> Tier` over `governance.authority.CATEGORY_RULES` + `HIGH_IMPACT_CATEGORIES` | **pure**, no DB; the §20 reuse |
| Step-up ceremonies | `inward_auth/step_up.py` (WebAuthn via `py_webauthn`, TOTP via `pyotp`) | new deps in `pyproject.toml` |
| Session elevation | `inward_auth/sessions.py` — `elevate`, `demote_expired`, `require_tier(session, tier)` | the enforcement predicate every Pragya command calls |
| Out-of-band T3 | `inward_auth/oob.py` — nonce issue/verify over a second binding; delivery via SIG (`authn.oob_confirm` signal → existing outbound seams, consent-checked) | fail-closed on missing second channel |
| Router | `inward_auth/api.py` — `/ai/authn/{bindings,webauthn/register,webauthn/authenticate,totp/enroll,totp/verify,step-up,oob/confirm}` | company-scoped; registered in `main.py` |
| Enrollment OTP | reuse the shipped OTP/notification path for the channel handshake | no parallel sender |
| FE | passkey/TOTP enrollment in `UserSettings`; a step-up modal component the Pragya console invokes; lockout + "alert all channels" surfaces as notifications | rides `inc2/onboard-fe`'s restored gate |

## 3. Task Plan

| # | Task | Acceptance |
|---|---|---|
| T1 | Models + `iauth001` migration + strict-allowlist entry | migration up/down clean; mypy `--strict` green |
| T2 | **Tier classifier (pure)** + goldens: every §20 category lands on its tier; ambiguous → highest; the §11.3 examples table reproduced | unit goldens pin the tier table |
| T3 | TOTP enroll/verify + session elevation + `require_tier` + lockout/alerts | elevation expires; lockout after N failures alerts all bindings |
| T4 | WebAuthn register/authenticate ceremonies (py_webauthn) + FE enrollment + step-up modal | passkey step-up elevates a real console session |
| T5 | Channel-binding enrollment handshake (console-initiated OTP) + inbound resolution | unbound contact → polite refusal + enrollment path (golden) |
| T6 | T3 out-of-band confirmation over a second binding via SIG | both-legs-or-nothing golden; missing second channel fails closed |
| T7 | Integration: `test_inward_auth_db.py` (bindings, elevation, lockout), parity/eval unchanged | all gates green |

## 4. Brainstorm Decisions (Rahul, 2026-07-22)

1. **Platform-built WebAuthn now** (not TOTP-first, not a vendor): full passkey ceremonies in-house from day one; TOTP remains the §11.3 fallback. No external identity dataflow.
2. **Console-first** shapes the ceremonies: the browser is the primary authenticator surface; other channels step up via a console link. Voice/WhatsApp adapters (Inc-3 VOICE) reuse `require_tier` unchanged.
3. Carried §11.3 rules (2026-07-18, not re-opened): impact-tiered step-up; 10-min default elevation; Pragya-can't-approve-herself; identity-is-a-hint.
