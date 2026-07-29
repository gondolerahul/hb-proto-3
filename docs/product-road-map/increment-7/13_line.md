# Increment 7 / Phase B — LINE: The Pocket (G4)

> **Status:** ✍️ workstream opened 2026-07-29, branch `inc7/line`.
> **Read first:** [10_workstream_decomposition.md](./10_workstream_decomposition.md) §7 (the scope) · [07_surface_wireframes.md](./07_surface_wireframes.md) §16–18 (the three Line surfaces) · [06_backend_api_contracts.md](./06_backend_api_contracts.md) §7 (push, VG-19) · [increment-6/00a](../increment-6/00a_genui_backend_gap_analysis.md) VG-20 · [12_steward.md](./12_steward.md) (the channel client and voice seam LINE reuses).

---

## 1. What LINE is, and what the assessment changed

The pocket: the Card renderer served as an installable PWA — the thread, the Morning Story, the Pocket Desk, biometric certified cards, the push client, the WhatsApp read-mirror. LINE **owns VG-20** (the Private Line backend), and walking VG-20's sketch against the shipped code shrank it considerably:

1. **The Morning Story needs no narrative-generation machinery.** DRIVER's Standup already composes the story client-side from three shipped reads (estate · yesterday's runs · pending trays) — `composeStandup` in `StandupSurface.tsx` is the composition, tested and pure. LINE ports it server-side (the audio job needs it there) and keeps it a **projection**: the story is composed from the estate's truth at read or synthesis time, never authored into a narrative store.
2. **Thread persistence already exists.** `pragya_turns` + `GET /ai/pragya/history` are the thread; delivered trays come from the tray list; live events ride STEWARD's channel client, which the Line reuses wholesale. **No new table for the thread.**
3. **Outbound WhatsApp send exists** (`src/voice/whatsapp_messaging.py`, Twilio/Tata — business messaging is live), and `ai/inward_auth`'s `channel_bindings` already holds *verified* per-user WhatsApp addresses. The read-mirror composes from shipped parts.
4. **Biometric certified cards need no attestation store.** The platform-built WebAuthn is platform-authenticator passkeys; in an installed PWA the same `StepUpCeremony` *is* Face/Touch ID. The passkey is the device registration — VG-20's "mobile device registration/attestation" line is answered by what AUTH already shipped.
5. **L8 answers a product question by construction:** a push is a tray or it does not exist, so there is no "morning story ready" push — the Morning Story is pull-open (and, per decision 3, mirrored to WhatsApp as the daily summary).

## 2. § Decisions (locked with Rahul 2026-07-29 — do not re-litigate)

1. **The WhatsApp mirror is the last resort in the one delivery door**: socket → push → WhatsApp → nowhere. At most one path, no double notification, and the India-first case (owner has WhatsApp, never installed the PWA) is served. Only to a **verified** WhatsApp binding, honoring the `notify.*` preference; read + notify only, never approvals (spec §14.3).
2. **The Morning Story ships with pre-generated daily audio.** A daily job synthesizes each tenant's story cards ahead of reading — the most ambitious option, chosen knowingly against the unproven-transport caution. Consequences owned in §5: a store (audio cannot be projected for free), a cost classification, and a text-degrade path for every failure.
3. **The daily WhatsApp morning summary ships now** — the mirror's "read" half: a few sentences of the morning state to the verified binding, from the same daily job. Tested seam; no live send in any test.

Standing constraints carried in: the PWA is charter decision 6; push is SEAM T7's self-hosted VAPID; echoes from the Line carry `renderer: "C"`; depth 3 does not exist on the Line.

## 3. The task plan

| L | Task | Where |
|---|---|---|
| L0 | This doc · branch `inc7/line` | docs |
| L1 | Server-side morning composition (the Standup ported) · `GET /ai/genui/line/morning` (compose-on-read, stored audio attached when present) | `genui/morning.py` |
| L2 | The **morning job**: daily arq cron — compose · TTS per card (injected transport, WAV) · store · WA summary · reaper in the same job · migration **`genui003`** (`morning_stories`) · `CostAttribution.MORNING_STORY` classified | `genui/morning_job.py` |
| L3 | The **WhatsApp tray mirror** — the door's third leg, import-boundary-tested | `genui/whatsapp_mirror.py`, `genui/channel.py` |
| L4 | `GET /ai/genui/push/vapid-public-key` · openapi + `gen:api` regen | `genui/router.py` |
| L5 | `line.html` PWA entry · web manifest · service worker (push → notification → open) · the **line bundle budget** | `vihara/` |
| L6 | The **Thread** — history + trays + the reused channel client; certified trays inline with the biometric ceremony | `vihara/src/line/` |
| L7 | The **Morning Story** — swipeable cards, per-card audio when present | `vihara/src/line/` |
| L8 | The **Pocket Desk** — pinned live cards, vitals on top, pins in the `surface.*` preference namespace | `vihara/src/line/` |
| L9 | The **push client** — VAPID key → subscribe → POST; the iOS install-first ceiling *stated* in the UI | `vihara/src/line/` |
| L10 | Gates · §Build notes · HANDOFF · merge | docs |

## 4. Design — the mirror in the one door (L3)

`deliver_tray` grows its third leg. The order is the decision: **socket → push → WhatsApp → "nowhere"** — each tried only when the previous reached no one, so the no-double-notification rule survives a third channel. The sender (`whatsapp_mirror.send_tray_notice`) refuses unless **all three** hold: a *verified* WhatsApp binding for that user (`channel_bindings`, the AUTH table — an unverified row is a claim, not a binding), the `notify.whatsapp_mirror` preference not disabled, and a configured messaging service. The message is the tray's one-sentence plus "open the Line to decide" — **never a button, never a reply path**; an inbound WhatsApp reply routes to the existing KAR-03 gateway like any message, and nothing in it can approve.

Structure is the push precedent applied twice: the sender lives in its own module, **imported by exactly one module** (`genui/channel.py` — the same import-boundary test family that guards `push.send_tray_push`), and the transport is injectable so no test sends a live message.

## 5. Design — the morning job (L2), and what decision 2 obligates

One daily arq cron (`morning_story_sweep`, 02:10 UTC, after the KPI snapshot at 01:40):

1. **Compose** each active tenant's story server-side (`genui/morning.py` — the ported Standup composition over `estate_view` + yesterday's runs + pending trays). Composition stays pure and is shared with the on-read path.
2. **Synthesize** one audio clip per card through the shipped `GeminiSpeaker` with conversion off, wrapped in a WAV header (24 kHz PCM — a RIFF header is twelve lines and buys native `<audio>` playback; no codec dependency). Transport injected in every test.
3. **Store** the cards and audio in `morning_stories` (migration **`genui003`**: company_id + story_date PK, cards JSONB, audio per card as base64-in-JSONB refs on the row† , generated_at). **30-day retention, reaped in the same job** — the LIB rule: a reaper on its own schedule is a reaper that eventually stops being deployed.
4. **Send the WhatsApp summary** (decision 3) — the story's first lines to the verified binding, same refusal ladder as the tray mirror.

† Audio bytes live on the row rather than in the artifact store deliberately: a story is 30 days ephemeral, per-tenant-private, and read through one authenticated endpoint — the artifact store's sharing and lifecycle machinery is the wrong weight. If clips outgrow row storage, that is a measured migration later, not a guess now.

**The cost classification** (the repo rule: classify, don't just add): `CostAttribution.MORNING_STORY`, **tenant-initiated — NOT in `PLATFORM_INITIATED_ATTRIBUTIONS`** — pinned by a named test. The reasoning against the `CONNECTOR_SYNC` precedent ("the tenant did not ask for this poll"): the morning story is a tenant-facing product feature the tenant turns off with a preference — a **standing instruction**, like a scheduled campaign, which bills the tenant. Putting a per-tenant daily benefit on the platform envelope would let the feature's success exhaust the cap that exists to protect tenants *from* platform work. Guard rails: the job **skips a tenant whose wallet cannot cover it** (story degrades to text, recorded honestly on the row), and `notify.morning_audio` disables synthesis per tenant. `tests/parity` stays 16 green (the job never runs in parity).

**Failure posture:** every failure path degrades to text — a broken TTS, an empty wallet, a missing speech row all produce a story with `audio: null` cards and a `degraded` reason on the row, never a missing story and never a blocked sweep. The endpoint composes on read when the job has not run (yesterday's audio never blocks today's text).

## 6. Design — the pocket app (L5–L9)

* **A second Vite entry** (`line.html`), sharing the C renderer, certified set, ceremony, API client and the steward channel client — and **never importing the world**: the eslint boundary and a new **line budget** in `check_bundle_budget.mjs` (hard fail) hold it. The Line is phone-first; its budget starts at the shell's 220 KB gz and the build prints the real number.
* **The service worker** does three things only: `push` → `showNotification(one_sentence)` (the payload is `{tray_id, one_sentence}` and nothing else — L8 made richer pushes unimplementable), `notificationclick` → focus/open the Line at the tray, and a small offline shell cache. No background sync, no offline queue — an offline approval would be a certified act with no server, which must not exist.
* **The Thread** renders history (`/ai/pragya/history`) + delivered trays + live channel events in one scroll; certified trays inline through the same `certifiedSet` components and `StepUpCeremony` — **the biometric bar is the platform passkey**, which in an installed PWA is Face/Touch ID. Echoes carry `renderer: "C"`.
* **The Pocket Desk** pins live cards (vitals always on top); pins are `surface.line_pins` in LEARN's preference store — the namespace exists, no new endpoint, and the store's refuse-unknown-namespace rule is why this is a code-reviewed key, not a new table.
* **The push client**: fetch the VAPID public key (L4's endpoint), `pushManager.subscribe`, POST to SEAM T7. On iOS the subscribe path is reachable only after install — the UI says so *before* the user hunts for the missing prompt (the exit demo's "demonstrated rather than discovered").

## 7. What G4's exit needs that this branch cannot supply

Real devices: installed on a real Android and a real iPhone, a push arriving as a tray, a payment approved with a fingerprint, the iOS ceiling demonstrated. All owner-side, like G1's matrix and G3's live legs. Everything else — the job, the mirror, the three surfaces, the ceremony, the budget — exits at the test level on this branch.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-29 | v1.0 — workstream opened. Three owner decisions locked (§2): the WhatsApp mirror is the one door's last resort · the Morning Story ships with **pre-generated daily audio** (the ambitious option, its obligations — store, cost class, text-degrade — owned in §5) · the daily WhatsApp morning summary ships now. The assessment shrank VG-20: the story is a projection (the Standup ported), the thread already persists (`pragya_turns`), outbound WhatsApp exists, and the passkey is the device registration. |
