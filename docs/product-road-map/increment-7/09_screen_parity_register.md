# Increment 7 / Phase A — D8: The 59-Screen Parity Register

> **Deliverable D8** of [01_phase_a_overview.md](./01_phase_a_overview.md). Closes the **VR-10** amendment.
> **Status:** ✅ complete 2026-07-28. Engineering artifact.
> **Why it exists:** spec §14.2 ratified that partner and platform-admin consoles stay on legacy React. The cutover criterion "feature-parity checklist against the 59 legacy screens (or explicit retirement of each)" is therefore **wrong as written** — it would count screens Vihara was never meant to replace as parity debt. VR-10's fix is to mark those *out of scope* rather than *retired*, and this register is that mark.

---

## 1. Two corrections before the table

**"59 screens" is a file count, not a screen count.** `find frontend/src/pages -name '*.tsx' | wc -l` returns 59, and **five of those files are not screens**: two React Flow node types, a shared dashboard module, a modal, and a tab strip. The honest denominator is **54 screens**, and every future statement of parity should use it.

**Three tenant functions have no Vihara surface at all** — and that is a gap in the ratified spec, not in this register. See **VP-03** (§4).

## 2. The register

Dispositions: **⇢ replaced** by a named Vihara surface · **⊘ out of scope** (§14.2 — stays on legacy React, rebuilt later from the same Sheet/Card registries) · **✂ retired** (the function ceases to exist) · **VP-03** (a tenant function Vihara has nowhere to put) · **— not a screen**.

| # | Legacy screen | Disposition | Vihara home |
|---|---|---|---|
| 1 | `Dashboard.tsx` | ⇢ | Still Surface (depth 0) + Terrace (depth 1) |
| 2 | `IntegrationsPage.tsx` | ⇢ | Bridges & Gates board |
| 3 | `KnowledgeBase.tsx` | ⇢ | The Library |
| 4 | `OnboardingWizard.tsx` | ✂ | Retired — onboarding is staged in the world (spec §15.1, D6 §19). The step APIs survive; the screen does not |
| 5 | `PartnerDashboard.tsx` | ⊘ | Partner console |
| 6 | `PhonePool.tsx` | ⊘ | Platform admin |
| 7 | `PlatformManagement.tsx` | ⊘ | Platform admin |
| 8 | `UserSettings.tsx` | **VP-03** | — (identity, passkeys, channel bindings, notification prefs) |
| 9 | `admin/CostAttributionDashboard.tsx` | ⊘ | Platform admin |
| 10 | `admin/FeatureFlagsPage.tsx` | ⊘ | Platform admin *(tenant-visible flags appear in the Undercroft)* |
| 11 | `admin/LoopOpsPage.tsx` | ⇢ | The Undercroft — signals, triggers, envelope |
| 12 | `admin/MetaIntelligencePage.tsx` | ⊘ | Platform admin |
| 13 | `admin/RiskAndExitPage.tsx` | ⊘ | Platform admin |
| 14 | `ai-config/AIModelConfigPage.tsx` | ⊘ | Platform admin *(routing attribution appears in the Undercroft)* |
| 15 | `ai/CortexExplorer.tsx` | ⇢ | The Library + Undercroft (chunks/embeddings one flip away) |
| 16 | `ai/CortexTreeDetail.tsx` | ⇢ | The Library + Undercroft |
| 17 | `ai/EntityBuilder.tsx` | ⇢ | Talent Office (design & hire) + dossier (charter) |
| 18 | `ai/EntityConfigurationTabs.tsx` | — | Not a screen — a tab strip |
| 19 | `ai/EntityFlow.tsx` | ⇢ | District room, and the org-chart *flip* (L4 — the chart is a lens, never a place) |
| 20 | `ai/EntityLibrary.tsx` | ⇢ | Talent Office + The Gallery |
| 21 | `ai/ExecutionDetail.tsx` | ⇢ | `trace-viewer`, one flip from the dossier; Undercroft |
| 22 | `ai/ExecutionHistory.tsx` | ⇢ | The Undercroft |
| 23 | `ai/ExecutionPage.tsx` | ⇢ | District room — live runs |
| 24 | `ai/HITLPanel.tsx` | ⇢ | **The Tray.** The single most consequential replacement in the product |
| 25 | `ai/PragyaConsole.tsx` | ✂ | Retired **as a place**. L2/L3: she is the still line, the beam, the thread and the channel — a steward with a screen of her own is a chatbot |
| 26 | `ai/TemplateMarketplace.tsx` | ⇢ | Talent Office — candidates |
| 27 | `ai/ToolManagement.tsx` | ⇢ | Dossier competencies + Undercroft |
| 28 | `ai/builder-nodes/EntityNode.tsx` | — | Not a screen |
| 29 | `ai/builder-nodes/ToolNode.tsx` | — | Not a screen |
| 30 | `artifacts/Artifacts.tsx` | ⇢ | The Library — generated artifacts collection |
| 31 | `assets/AssetLibrary.tsx` | ⇢ | The Library |
| 32 | `auth/LoginPage.tsx` | **VP-03** | — |
| 33 | `auth/OAuthCallback.tsx` | ⇢ / **VP-03** | Connector OAuth returns to the Bridges board; *login* OAuth has no home |
| 34 | `auth/PasswordReset.tsx` | **VP-03** | — |
| 35 | `auth/RegisterPage.tsx` | **VP-03** | — |
| 36 | `billing/BillingSettings.tsx` | **VP-03** | — |
| 37 | `billing/WalletPage.tsx` | **VP-03** | — |
| 38 | `dashboards/AppAdminDashboard.tsx` | ⊘ | Platform admin |
| 39 | `dashboards/AppUserDashboard.tsx` | ⊘ | Platform |
| 40 | `dashboards/DashboardShared.tsx` | — | Not a screen |
| 41 | `dashboards/KPIDashboard.tsx` | ⇢ | District plinths + the Terrace + the Gallery's Seasons |
| 42 | `dashboards/PartnerAdminDashboard.tsx` | ⊘ | Partner console |
| 43 | `dashboards/PartnerUserDashboard.tsx` | ⊘ | Partner console |
| 44 | `dashboards/TenantAdminDashboard.tsx` | ⇢ | Still Surface + Terrace |
| 45 | `dashboards/TenantUserDashboard.tsx` | ⇢ | Still Surface + Terrace |
| 46 | `reports/AppAdminReports.tsx` | ⊘ | Platform admin |
| 47 | `reports/AppUserReports.tsx` | ⊘ | Platform |
| 48 | `reports/BillingReport.tsx` | **VP-03** | — (billing family) |
| 49 | `reports/CostingReport.tsx` | ⇢ | The Undercroft — routing attribution and cost |
| 50 | `reports/PartnerAdminReports.tsx` | ⊘ | Partner console |
| 51 | `reports/PartnerUserReports.tsx` | ⊘ | Partner console |
| 52 | `reports/TenantAdminReports.tsx` | ⇢ | Registry Hall analytics rooms (chart ⇄ query by flip) |
| 53 | `reports/TenantUserReports.tsx` | ⇢ | Registry Hall analytics rooms |
| 54 | `streaming/CallDetailPage.tsx` | ⇢ | Dossier trace + Undercroft |
| 55 | `streaming/CampaignCreateModal.tsx` | — | Not a screen — a modal |
| 56 | `streaming/CampaignDetailPage.tsx` | ⇢ | District room (Growth quarter) + Registry Hall |
| 57 | `streaming/CampaignsPage.tsx` | ⇢ | District room (Growth quarter) |
| 58 | `streaming/PhoneNumbersPage.tsx` | ⇢ | Bridges & Gates board — the gatehouses |
| 59 | `streaming/StreamingSessionsPage.tsx` | ⇢ | The Undercroft |

## 3. The reckoning

| Disposition | Count | Of 54 screens |
|---|---|---|
| ⇢ **Replaced** by a Vihara surface | **28** | 52% |
| ⊘ **Out of scope** — partner / platform-admin, stays on legacy React (§14.2) | **16** | 30% |
| ✂ **Retired** — the function ceases to exist | **2** | 4% |
| **VP-03** — a tenant function with no Vihara surface | **8** | 15% |
| — Not a screen | 5 | *(excluded from the denominator)* |

**Cutover parity is 28 of 30**, not 28 of 59. The 16 out-of-scope screens keep running on legacy React by ratification, and the two retired ones are retired on purpose. **The VP-03 eight are the real debt**, and they were invisible until this table existed — which is the argument for building the register in Phase A rather than at G6, where it would have been a discovery two weeks before launch.

**Amended cutover criterion**, replacing spec §12's line:

> Feature-parity checklist against the **30 in-scope tenant screens** — each ⇢ replaced or ✂ explicitly retired — plus a resolved home for every VP-03 function. The 16 out-of-scope screens are **not** parity debt; they are the partner and platform-admin consoles, ratified in §14.2 as a later track from the same Sheet/Card registries.

## 4. VP-03 · Vihara has nowhere to put "me"

The spec's surface inventory (§5) is an inventory of **the estate**. Walking the legacy screens against it exposes three tenant functions that are not about the estate at all and therefore have no home:

| Family | Screens | Why it cannot just go in the Undercroft |
|---|---|---|
| **Pre-session** | Login, register, password reset, login OAuth callback | These exist *before* a session, and the estate starts at depth 0 of a session. L1 says nothing else is ever the home screen — but something has to be on screen before there is a home |
| **Account & security** | `UserSettings` (identity, **passkey enrolment**, channel bindings, notification prefs, density override) | Depth 3 is operator-density by design and is desktop-only. **Passkey enrolment is a prerequisite for every T2 act**, so putting it at depth 3 makes the most important safety surface the hardest to reach — and it is needed on the Line, where depth 3 does not exist |
| **Billing & wallet** | `BillingSettings`, `WalletPage`, `BillingReport` | Money the tenant owes *the platform* is not estate business. It is also where dunning (`read-only` state) has to be explicable, and a tenant in read-only mode needs to understand why the estate has gone quiet |

**✅ Decided at R2 (2026-07-29): The Study, as proposed.** One depth-2 surface holding identity, security (passkey enrolment included), notifications, density and billing & wallet, reachable from the shell rather than from the territory (it is not a place in the estate, it is the desk you sit at). Pre-session surfaces stay conventional and unthemed beyond the brand: a login screen that tries to be an estate is a login screen that is slow. The eight VP-03 rows above resolve to the Study (six) and the pre-session set (login, register, reset, login-OAuth callback). The Study joins D6's inventory as the eighteenth surface, drafted by its owning workstream before it is built.

---

## 5. The G6 reckoning (POLISH P10, 2026-07-29)

The amended §3 criterion, walked against the **shipped** app rather than against build notes:

* **All 28 ⇢ rows have their Vihara surface live** — verified by opening each named home in the built app's source and its structural goldens: Still/Terrace (1, 44, 45) · Bridges & Gates (2, 58) · Library (3, 15, 16, 30, 31) · Undercroft (11, 21, 22, 49, 59) · Talent Office + Gallery (17, 20, 26) · district rooms + halls (19, 23, 41, 52, 53, 56, 57) · dossier/trace (27, 54) · **the Tray (24)**.
* **Both ✂ rows are now retired in fact, not only on paper.** Onboarding is staged in the world at the shell level (P7 — depth 0 unreachable before stage 9; the wizard screen has no Vihara counterpart and never will), and Pragya has no place of her own — she is the still line, the dock, the thread and the channel (STEWARD).
* **VP-03: six of eight rows closed by the Study** (8, 36, 37, 48, and the settings halves of 33) — identity, passkeys, notifications, density, billing & wallet, all reachable from the shell and inside the structural goldens. **Pre-session closes login and register (32, 35).**
* **Two named residuals, neither silent:** **password reset (34)** — the backend ships no reset endpoint, and the pre-session screen says so instead of pretending (its docstring records the absence); and **login OAuth (33's login half)** — no Vihara home and no backend contract yet. Both are backend-first work and neither blocks the parallel run: the legacy React login continues to serve both paths for the 30-day overlap.

**Verdict: the amended cutover criterion is met except for the two named residuals above**, which are recorded here rather than discovered at the vhost flip.

## Change Log

| Date | Change |
|---|---|
| 2026-07-29 | v1.3 — **the G6 reckoning** (§5, POLISH P10): all 28 ⇢ rows verified live, both ✂ rows retired in fact (onboarding staged in the world at shell level), VP-03 six-of-eight closed by the Study + two by pre-session, and **two named residuals** — password reset and login OAuth — recorded as backend-first work that does not block the parallel run. |
| 2026-07-29 | v1.2 — **DRIVER built** ([11_driver.md](./11_driver.md) §6). Of the ⇢ rows: the Tray (row 24 — the most consequential replacement), Registry Halls (incl. rows 52–53's analytics flip in v1 form), dossier/trace rows, the Boardroom, Talent Office (17/20/26), Gallery, Library (3/15/16/30/31), Undercroft (11/21/22/49/59), Bridges & Gates (2/58) now have working Vihara surfaces; the **Study is drafted and built**, resolving the six VP-03 Study rows at build level (pre-session was SUB's). District rooms (19/23/56/57) have their furnished sheets; their W rooms are WORLD's. |
| 2026-07-29 | v1.1 — **VP-03 resolved: The Study** (owner decision at R2). The §4 proposal accepted as written; the eight VP-03 rows now have a named home, so the amended cutover criterion's "resolved home for every VP-03 function" clause is met at design level. |
| 2026-07-28 | v1.0 — all 59 files dispositioned. Two corrections: **"59 screens" is a file count** and five of them are not screens, so the honest denominator is **54**; and cutover parity is **28 of 30 in-scope tenant screens**, not 28 of 59, because 16 are partner/platform-admin consoles ratified as out of scope. Raised **VP-03**: three tenant functions — pre-session, account & security, billing & wallet — have **no Vihara surface**, and passkey enrolment being among them matters, because it is the prerequisite for every T2 act and the spec's only candidate home for it is operator-density and desktop-only. Invisible until this table existed. |
