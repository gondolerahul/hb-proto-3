# Increment 6 / GATE — KAR-05, the Governed Broadcast Gates (closes VG-15)

> **Status:** v1.1 — **BUILT 2026-07-25** (branch `inc6/gate`, T1–T7 complete). Build notes + six design deltas in §11.
> **Closes:** gap-analysis **VG-15** (broadcast gates have no KAR family) — charter decision 9.
> **Depends on:** the shipped Karuna gateway builder (`solo_pack/templates/gateways.py`), the signal bus, the PolicyGate's `CATEGORY_RULES` / `TOOL_CATEGORY_MAP`, TRUST's consent registry (D6).
> **Independent:** touches nothing LEARN, SEGA, TWIN or STRAT modify — buildable at any point in the increment ([00_overview](./00_overview.md) §3).
> **Parent:** [00_overview.md](./00_overview.md) · [00_charter.md](./00_charter.md) decision 9.

---

## 1. The finding, stated precisely

The charter says `social_connection_service.py` "sits outside SIG, Karuna and consent". Walking the code, the exposure is larger and more specific than that sentence implies.

**`src/ai/tools/social/` ships 64 tools across 16 platforms** — LinkedIn, X/Twitter, Facebook, Instagram, TikTok, YouTube, Pinterest, Reddit, Quora, plus the ad surfaces (Meta Ads, LinkedIn Ads, Google Ads, YouTube Ads, X Ads, Snapchat Ads) and LinkedIn Sales Navigator. Among them: `linkedin_create_post`, `instagram_publish_media`, `tiktok_publish_video`, `quora_post_answer`, `meta_ads_create_campaign`, `google_ads_*`.

**Not one of them appears in `TOOL_CATEGORY_MAP`.** The PolicyGate only gates *categorised* acts (the HANDOFF §5 convention says so in as many words), so every one of these resolves to `PASS`:

* an agent at **A1** — the band where *every* categorised external effect raises a HITL card — can publish to the public internet with no card;
* an agent can create an ad campaign with a budget, and no amount band is consulted, because ad spend is not a category;
* nothing checks consent or DNC on an audience upload;
* nothing emits a signal, so there is no outbound audit trail and no inbound path back;
* a counterparty-trust signal (a hostile DM) can drive all of it — `HIGH_IMPACT_CATEGORIES` cannot refuse a category that does not exist.

Compare the outbound email path, which the SLICE governed on day one: `send_email` → `email_dispatch` → HITL card at A1. Broadcast is the same act with a larger audience and less governance.

## 2. Three separate holes, three separate fixes

| Hole | Consequence | Fix |
|---|---|---|
| **No category** | No band check, no HITL card, invisible to `HIGH_IMPACT_CATEGORIES` | §4 — two new categories + tool mappings |
| **No consent posture** | Nothing decides whether this tenant broadcasts on this channel for this purpose; audience uploads bypass DNC entirely | §5 |
| **Not on the bus** | No outbound audit, and inbound mentions/comments/DMs never reach an agent | §6 — the KAR-05 gateway |

They are genuinely independent, and the first is worth shipping even if the third slips.

## 3. Decisions

1. **Broadcast and ad spend are two categories, not one.** Publishing a post and committing money are different acts with different bands. Merging them would either under-govern spend or make every post cost an approval.
2. **`ad_spend` joins `HIGH_IMPACT_CATEGORIES`.** A counterparty-trust signal must not be able to drive money into an ad platform, for the same reason it cannot drive a payout.
3. **The KAR-05 gateway holds no ad tools.** The Karuna builder enforces "no monetary authority" by construction; ad tools belong to a marketing process agent, never to the inbound face.
4. **Credentials do not move.** `social_connections` keeps the OAuth tokens. Migrating live third-party tokens into `connector_bindings` is real risk for no governance gain — GATE's subject is governance, consent and the bus. Consolidation is a later CONN pass, and it is recorded as an honest limit (§9).
5. **Inbound polling ships as a tested seam** — the Inc-4/Inc-5 precedent (Zoho, the expansion fleet). No live platform API call is made in this workstream; the transport is injectable.

## 4. Governing the outbound act

### 4.1 Two categories

Added to `governance/authority.py::CATEGORY_RULES`:

* **`broadcast`** — publishing to a public or semi-public audience. Shaped like `email_dispatch`: no amount band, so at A1 every publish raises a card and at A2+ it is autonomous comms. The checkpoint is a new HITL checkpoint definition, `before_public_broadcast` — the 20th.
* **`ad_spend`** — committing budget on an ad platform. Carries an **amount band** like `payout` does, so a small boost is autonomous at A3 while a large campaign is not, and it is added to `HIGH_IMPACT_CATEGORIES` (decision 2).

### 4.2 The tool mappings

`TOOL_CATEGORY_MAP` gains entries following the connector precedent exactly: **write verbs map, read verbs deliberately do not.** Reading a platform's analytics is not an external effect and must stay `PASS`, or every dashboard refresh becomes an approval.

| Maps to `broadcast` | Maps to `ad_spend` | Stays uncategorised |
|---|---|---|
| `linkedin_create_post`, `instagram_publish_media`, `tiktok_publish_video`, `facebook_*_post`, `twitter_*_post`, `pinterest_create_pin`, `reddit_*_submit`, `quora_post_answer`, `youtube_*_upload`, `*_manage_comments` | `meta_ads_create_campaign`, `linkedin_ads_create_campaign`, `google_ads_*_campaign`, `youtube_ads_create_campaign`, `x_ads_*_campaign`, `snapchat_ads_create_campaign`, `*_manage_adsets`, `*_manage_ad_groups`, `*_manage_audiences` | `*_get_analytics`, `*_report`, `*_get_profile`, `*_search_*`, `*_get_videos`, `linkedin_sales_get_*` |

`*_manage_comments` maps to `broadcast` because a public reply is a public statement. `*_manage_audiences` maps to `ad_spend` rather than `broadcast` because an audience is who the money reaches, and it is also where §5's consent check bites.

**The mapping must be total over the shipped tool set**, asserted by a test that walks `ai/tools/social/` and fails on any tool name matching neither an outbound nor a read pattern. A new social tool added later without a category is the exact bug this workstream exists to fix, and it should fail in CI rather than in production.

## 5. Consent, and what it means for a broadcast

A broadcast is not person-addressed, so `check_outbound_consent(company, channel, to_address, purpose)` does not fit as-is. Two distinct checks:

**5.1 Channel posture (for `broadcast`).** Per-tenant, per-platform, per-purpose: *may this tenant publish to LinkedIn for marketing purposes?* This is the tenant's own policy — some businesses are regulated out of public statements, some want a human on every post regardless of band. Stored the way the consent registry already stores tenant posture (`ai/trust/consent_registry.py`), checked before the tool executes. The default follows decision 8 of Increment 2 — **consent is tenant-configured from day one**, no imposed global default — which here means: absent an explicit posture, `broadcast` is allowed and governed by band alone, and the tenant may tighten it.

**5.2 DNC on audiences (for `ad_spend`).** An ad "custom audience" upload is a list of real people's emails or phone numbers, and it is the one place in the broadcast surface where the shipped DNC registry applies literally. Every identifier in an audience payload is checked through `check_outbound_consent`; suppressed identifiers are **removed and counted**, and the count travels into the HITL card's `context_snapshot`. Refusing the whole upload because of one unsubscribed address would push tenants to do it by hand outside the platform, which is worse for the person who unsubscribed.

## 6. KAR-05 — the gateway

Built with the shipped `_karuna_gateway` builder, so the posture comes by construction: `karuna_profile: true`, **no authority bands**, CRM-scoped memory, counterparty text as *data* and never as prompt directive.

* **Consumes** `broadcast.inbound` — mentions, public comments, and platform DMs.
* **Emits** `lead.inbound` / `ticket.opened`, the same shape KAR-02 (email) and KAR-03 (WhatsApp) emit. A comment asking about pricing becomes a lead; a comment reporting a broken order becomes a ticket. Nothing new downstream.
* **Roster:** 18 → **19**. `activate_slice` still seeds email-only.
* **Metadata:** `broadcast_provider`, which makes the deploy Karuna gate treat it as externally bound — so a KAR-05 that lost its `karuna_profile` would fail to publish, exactly as KAR-01/03 do.

**The producer** `signals/broadcast_inbound.py` follows `whatsapp_inbound.py` and `voice_inbound.py` line for line: `trust: counterparty`, dedupe on the platform's own item id, subscription-gated, fail-safe cutover. Scope for this increment: the platforms a tenant actually holds a `social_connections` row for, transport injected (decision 5).

**Outbound audit:** a successful publish emits `broadcast.published` (trust `internal`), so the outbound half is on the bus even where the inbound half is not yet polled.

## 7. Data model

| Change | Where | Migration |
|---|---|---|
| `broadcast`, `ad_spend` in `CATEGORY_RULES` + `TOOL_CATEGORY_MAP` | `governance/authority.py` | none |
| `before_public_broadcast` — the **20th** HITL checkpoint | `governance/checkpoints.py` | **`gate001`** — a checkpoint backfill, exactly like `conn002`'s 19th |
| `ad_spend` in `HIGH_IMPACT_CATEGORIES` | `governance/authority.py` | none |
| `broadcast.inbound`, `broadcast.published` signal types | `signals/models.py` | none |
| KAR-05 template | `solo_pack/templates/gateways.py` + `GATEWAYS` | none |
| Channel posture | reuses the consent registry's tenant-posture storage | none |

One small migration — the checkpoint backfill — for the same reason `conn002` existed: existing tenants need the new checkpoint row or their governance preview is missing a checkpoint that the gate can raise.

## 8. Task plan

| # | Task | Gate |
|---|---|---|
| **T1** | The two categories + the 20th checkpoint + `gate001`; `ad_spend` into `HIGH_IMPACT_CATEGORIES` | unit + `*_db` |
| **T2** | `TOOL_CATEGORY_MAP` entries + **the totality test** over `ai/tools/social/` | unit |
| **T3** | Channel posture in the consent registry + the pre-execute check | unit + `*_db` |
| **T4** | Audience DNC filtering, with the suppressed count on the HITL card | unit + `*_db` |
| **T5** | KAR-05 template + roster 19 + the injection golden (the `test_kar_gateways.py` pattern) | unit |
| **T6** | `signals/broadcast_inbound.py` + `broadcast.published`, transport injected | unit + `*_db` |
| **T7** | End-to-end: an A1 agent calling `linkedin_create_post` raises a card; an A3 agent's card-free publish still emits the audit signal | `*_db`, **mutation-tested** (drop the category mapping and the "A1 publish raises a card" test must fail, alone) |

T1+T2 are the ones that close the live hole; T5–T7 are the inbound half. If the increment runs long, the overview names GATE as a relief valve — the honest split is that **T1–T4 should not be deferred** (they close an ungoverned outbound path in shipped code) while T5–T7 can be.

## 9. Honest risks and limits

| Risk / limit | Statement |
|---|---|
| **No live platform call** | Decision 5. The transport is injectable and faked in tests, the same posture Zoho (Inc 4) and the expansion fleet (Inc 5) carry. Live go-live is activation-time ops |
| **Credentials stay in `social_connections`** | Decision 4. Two credential stores exist afterwards (`connector_bindings` and `social_connections`), which is a real inconsistency and is recorded rather than hidden |
| **Categorising 64 tools will break someone's flow** | That is the point — an A1 tenant whose agent has been posting freely will start seeing cards. It is a behaviour change and it belongs in release notes, not in a silent deploy |
| **Pattern-matched mappings can drift** | The totality test (T2) is the guard, and it is the load-bearing test in this workstream |
| **16 platforms is a lot of inbound surface** | T6 is scoped to platforms with an existing connection row. A tenant with no LinkedIn connection gets no LinkedIn polling and no empty error |

## 10. Brainstorm decisions

*(Answered — do not re-litigate.)*

1. **One category or two:** two (§3.1).
2. **Ad spend and hostile input:** `HIGH_IMPACT_CATEGORIES` (§3.2).
3. **Gateway holds ad tools:** never (§3.3).
4. **Credential consolidation:** out of scope, recorded (§3.4).
5. **Audience with an unsubscribed address:** filter and count, do not refuse (§5.2).
6. **Default posture:** tenant-configured, permissive until set — Inc-2 decision 8 (§5.1).

---

## 11. Build notes (2026-07-25, branch `inc6/gate`)

All of T1–T7. Migration **`gate001`** (off `sega002`, new head). Roster **18 → 19**.

### 11.1 What shipped

| Task | Where |
|---|---|
| T1 | `governance/authority.py` (`broadcast` + `ad_spend` rules, `ad_spend` → `HIGH_IMPACT_CATEGORIES`), `schemas/governance.py` (`AuthorityBands.ad_spend_usd`), `governance/checkpoints.py` (the 20th + 21st + their SLAs), migration `gate001` |
| T2 | `governance/authority.py` — 36 exact `TOOL_CATEGORY_MAP` entries; `tests/unit/test_gate_broadcast_categories.py` (the totality test) |
| T3 | `solo_pack/consent.py` (`check_channel_posture` seam), `trust/consent_registry.py` (`evaluate_channel_posture`, `set_channel_posture`, `CHANNEL_POSTURE_IDENTITY`) |
| T4 | `solo_pack/consent.py` (`filter_audience`, `AudienceFilter`) |
| T3+T4 enforcement | `trust/broadcast_guard.py` + the call in `ai/tools/social/base.py::run_with_context` |
| T5 | `solo_pack/templates/gateways.py` (`KAR_05_BROADCAST`), `templates/__init__.py` (`GATEWAYS`) |
| T6 | `signals/broadcast_inbound.py`, `signals/models.py` (two signal types), the publish audit in `base.py::_audit_publish` |
| T7 | `tests/unit/test_gate_kar05.py`, `tests/integration/test_gate_broadcast_{db,inbound_db}.py` |

### 11.2 Six design deltas

1. **Two checkpoints, not one.** §7 named only the 20th (`before_public_broadcast`), but `ad_spend` carries an amount band and needs a checkpoint to raise. Borrowing `before_outbound_payout_above_band` would have made an ad campaign **un-opt-out-able** (payout is `platform_mandatory`), AUTO_DENY in 4h rather than 8h, and mislabelled to the approver as an outbound payout. So `before_ad_spend_above_band` is the **21st**; seed 19 → 21.

2. **The taint firewall kept a hand-copied `HIGH_IMPACT_CATEGORIES`** while its own docstring claimed it imported one — and the copy drifted the first time it was tested. Adding `ad_spend` to the governance constant left the firewall permitting exactly the act governance had just forbidden. Now read live through a lazy import (so the module keeps no module-scope governance import, which is what SEGA §7 actually wanted) with a test pinning the two in sync. **This was a live latent defect, not a GATE-introduced one** — any future addition to the set would have half-landed the same way.

3. **Mappings are exact, not substring.** §4.2's pattern table (`google_ads_*_campaign`, `*_manage_ad_groups`) does not survive contact: `youtube_ads_manage_ad_groups` writes while `google_ads_get_ad_groups` reads, and one needle resolves the wrong one. 36 exact keys instead, with the totality test supplying the completeness that exactness costs.

4. **Two social tools are not broadcasts.** `facebook_send_message` is person-addressed, so it is ordinary outbound comms (`email_dispatch`, the category the SLICE gave `send_email`) and the person-addressed consent check applies to it literally. `linkedin_sales_save_lead` mutates an external system of record, which is Inc-4's `external_write`. Both would have failed the totality test as neither publish nor read, which is the test working as intended.

5. **T4 has no live feed, and this is recorded rather than hidden.** §5.2 assumed a custom-audience upload of emails/phone numbers. **No shipped audience tool accepts one** — `meta_ads_manage_audiences` builds from a `rule` object, `x_ads_manage_audiences` from an `audience_type`; the raw list never reaches the platform through this surface. The filter is built, tested and wired at the one point such a list would arrive, and a test fails if any social tool grows an audience parameter, so it is noticed rather than staying quietly decorative.

6. **The suppressed count cannot reach the HITL card.** §5.2 says it travels into `context_snapshot`, but the card is raised by the PolicyGate *before* execution and the filtering happens *at* execution. Surfacing it would need a gate-time hook; with no live feed (delta 5) there is nothing to display, so it was not built. `suppressed_count` is carried on the guard result and onto `broadcast.published`.

**Enforcement point.** The consent checks live in `SocialMediaTool.run_with_context` — the one method all 64 tools funnel through — so a platform module added later inherits them by construction rather than by remembering. Same reasoning as T2's totality test, and the same reasoning HANDOFF §5 records for putting security gates in the handler body.

### 11.3 Mutation tests

Four controls, each failing only its own tests:

| Mutation | Fails |
|---|---|
| drop the `linkedin_create_post` mapping | "A1 publish raises a card" + the totality test |
| drop `ad_spend` from `HIGH_IMPACT_CATEGORIES` | the firewall refusal + the high-impact assertions |
| add a new uncategorised social tool | the totality guard — **the exact bug this workstream exists to fix**, now caught in CI |
| delete the guard block from `base.py` | the two call-site tests, and nothing else |

The last is the one that matters most: without it the guard would be tested only through direct calls, and the wiring could be deleted without failing anything (HANDOFF §5, the VG-05 lesson).

### 11.4 Two shipped-code fixes found while building

* **`test_kpi_rollup.py`'s arq test was silently order-dependent** — it reaches the *global* engine while the `db` fixture wraps conftest's, and it never disposed. It passed or failed purely on suite composition, and the job swallows the error, so it was never asserting what it claimed. Fixed with the documented convention.
* **Roster and checkpoint counts were asserted as literals** in eight places (`18`, `16`, `19`, the gateway names spelled out). Every one failed on KAR-05 for a reason unrelated to what it tested. Rewritten to derive from `SOLO_PACK_TEMPLATES` / `GATEWAYS` / `CHECKPOINT_SEED`.

### 11.5 Honest limits

* **No live platform call** (decision 5). The producer takes already-fetched items; polling the sixteen platforms is an injected transport, the Zoho/expansion-fleet posture.
* **T6 has no poller.** `emit_broadcast_inbound` has no scheduled caller yet, so `broadcast.inbound` only flows when something calls it. The outbound audit half *is* live, wired at the tool base.
* **Credentials stay in `social_connections`** (decision 4) — two credential stores still exist. Recorded, not fixed.
* **Categorising 64 tools is a behaviour change.** An A1 tenant whose agent has been posting freely will start seeing cards. That is the point, and it belongs in release notes rather than a silent deploy.

### 11.6 Gates

typecheck **285** files strict · layout lint · **1834 unit** · **16 parity/eval** · **384 integration** · `gate001` applies, rolls back and re-applies · migration head `gate001`.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-25 | v1.1 — **BUILT (T1–T7).** §11 added: build notes, six design deltas (two checkpoints not one; the taint firewall's drifted duplicate; exact rather than substring mappings; two social tools that are not broadcasts; T4's absent live feed; the suppressed count that cannot reach the card), four mutation tests, two shipped-code fixes found while building, and the honest limits. |
| 2026-07-25 | v1.0 — design written. The finding sharpened against the code: **64 social/ad tools across 16 platforms, none categorised**, so the PolicyGate passes every public post and every ad-budget commitment. Split into three independent fixes; two new categories with `ad_spend` in `HIGH_IMPACT_CATEGORIES`; a totality test over the tool directory as the durable guard; consent split into channel posture and audience DNC; KAR-05 built with the shipped Karuna builder, roster 18→19; credentials deliberately left in place with the reason. |
