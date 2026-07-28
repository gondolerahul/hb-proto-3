# Increment 7 — Prerequisite Plan: Voice Go-Live (VG-08 / VR-11)

> **Status:** 🚧 **IN PROGRESS — gaps 1–5 closed 2026-07-28; the live transports remain.** Everything that does not need credentials is built and tested. **Resume at Phase 1** (§5): confirm the two products, then implement the two `NotImplementedError` transports in `channels/adapters.py`. Nothing else stands between here and a call.
> **Closes:** gap-analysis **VG-08** (voice is a tested seam, not a live call) + **VR-11** (voice go-live is a G3 prerequisite, not an ops remainder), and the Increment-4 remainder recorded in [01_pragya_runtime.md](../increment-4/01_pragya_runtime.md) §12.5.
> **Gates:** Vihara **G3** — *"the steward is present"*, which cannot pass on a tested seam.
> **Parent:** [00_charter.md](./00_charter.md) §Prerequisites.

---

## 1. The scoping correction — read this first

**VG-08 is not "voice". Business voice is already live.**

`src/voice/websocket_handler.py` carries real Twilio and Tata Smartflo media into `GeminiLiveClient` / `AzureRealtimeClient` through `LiveClientFactory`, with credit gating, call recording and disposition all working on real calls. Outbound campaigns, the CRM lead→call pipeline and KAR-01's outward face all run on it today.

What has never made a live call is **Pragya's inward face** — the number an owner dials to reach their account manager. That is what Inc-4 §12.5 documented, what VG-08 records, and the whole of what this plan covers.

Anyone resuming this should not go looking for a broken telephony stack. There isn't one.

## 2. Verified current state (2026-07-26)

Measured against the running dev database and `master` @ the Increment-6 merge, not taken from a doc.

| Thing | State |
|---|---|
| `integration_registry` | **19 rows.** GCP project `hirebuddha-production`, region `us-central1`, keys present. Gemini 2.5 (flash/lite/pro), `gemini-3.1-flash-live-preview` (`use_ai_studio: true`) for speech-to-speech, Azure `gpt-5.5`, imagen/veo/lyria, Tata Tele (`COMMUNICATION`, live credentials) |
| ASR / TTS rows | **None.** No `pragya-asr-whisper-vertex`, no `pragya-tts-gemini`, no `AUDIO_GENERATION` row of any kind |
| `model_task_defaults` | 8 task types configured, including `speech_to_speech` |
| `channels/speech.py` | `Transcriber` / `Speaker` **Protocols only** — no implementation anywhere |
| `channels/voice.py` | `drive_call` complete; consumes and emits audio frames; **nothing feeds it** |
| `channels/routing.py` | `route_for_number` complete and tested |

## 3. The four gaps

Increment 4 §12.5 named three. Tracing the code for this plan found a fourth, and it is the one that would waste a session if nobody knew:

| # | Gap | Evidence | State |
|---|---|---|---|
| 1 | **No registry rows** for the two speech SKUs | The SKU strings existed only in `speech.py` | ✅ **closed 2026-07-28** — rows seeded by the owner; the code's SKUs were wrong and were corrected to them (§3.1) |
| 2 | **No concrete `Transcriber` / `Speaker`** | The Protocols had no implementors | ✅ **closed** — `channels/adapters.py`, transport injected |
| 3 | **`drive_call` is not connected to carrier media** | `drive_call` was a second consumer of the media stream that was never attached | ✅ **closed** — `voice/pragya_stream_handler.py` + `/stream/pragya/{id}` |
| 4 | **`route_for_number` has no effect** | `webhook_router.py` resolved the face, **logged it, and fell through to the gateway path anyway** | ✅ **closed** — `_connect_pragya` |
| 5 | **No Pragya entity exists, and nothing creates one** | Found 2026-07-28. `PRAGYA_ENTITY_NAMES` was only ever *read*; `assign_pragya_number` refuses without her | ✅ **closed** — `ai/pragya/seed.py` |
| — | **The live ASR/TTS transports** | Both raise `NotImplementedError` pointing here | ⏳ **open — the only remaining work.** Needs Phase 1's answer |

**Gap 5 was not in the original four** and sat ahead of all of them: every resolver was written as *"the tenant's Pragya entity, **if one is seeded**"* and nothing ever seeded one. It went unnoticed from Increment 3 until a phone number needed somewhere to point.

**Gap 4 was the one to fix first**, and the reason is worth keeping: until that branch diverged, gaps 1–3 could all be complete and a call to Pragya's number would still land on the legacy speech-to-speech stack, with nothing obviously wrong in the logs.

### 3.1 What building it changed

* **The SKUs in code were wrong, not the owner's rows.** `speech.py` hardcoded `pragya-asr-whisper-vertex` and a single `pragya-tts-gemini`; the rows created were `pragya-asr-chirp-vertex` and the `pragya-tts-gemini-in`/`-out` **pair**. The pair is this registry's convention for every token-billed service (`gemini-2.5-flash-in`/`-out`, `gpt-5.5-in`/`-out`) and Gemini TTS bills per token both ways — the single-SKU assumption was simply wrong about the product. ASR stays one row because Chirp bills per minute, and that asymmetry is the billing model rather than an inconsistency.
* **Chirp, not Whisper** (owner decision) — for the §5 Phase 1 reason: Whisper on Model Garden is a self-deployed endpoint billed per node-hour, a standing charge for a line idle most of the day.
* **One shared line, inverting decision 5** (owner decision) — see §4.3.
* **A test was passing for the wrong reason.** `test_voice_is_refused_when_the_speech_skus_are_unconfigured` asserted the *absence of global configuration* rather than a property of the tenant: it passed only while no speech rows existed anywhere, because `_resolve` deliberately falls back to the platform row. It broke the day voice was configured — the day the feature started working, which is the worst possible moment for a test to fail. It now injects the missing SKU.

## 4. Decisions (locked 2026-07-26 — do not re-litigate)

**1. ASR-LLM-TTS as designed, not speech-to-speech.**

Two architectures exist in this repo and they are not interchangeable:

* *Legacy / KAR-01* — **speech-to-speech**: one realtime model session does hear → think → speak internally. Proven and live.
* *Pragya (Inc-4 T5)* — **ASR → LLM → TTS** as three pieces, with her turn loop running *between* hearing and speaking.

The split is not stylistic. Pragya's turn loop is where `require_tier`, the nine-stage machine and tool execution live. A speech-to-speech model completes the whole turn *inside* the model, so **there is no seam to insert the tier gate into** — which is exactly why decision 7 chose ASR-LLM-TTS in the first place.

The rejected option is worth recording because it will look attractive again: running her on the existing live stack would take days rather than weeks, but her turn loop would be bypassed, so on voice she could only *promise* actions through the Inc-3 live gate and never execute them. An account manager who cannot action *"pause the invoice chaser"* is a demo, not a steward — and it would reopen D1 on the voice channel, which is closed end-to-end today.

**2. GCP is already in use** — project `hirebuddha-production`, service account and billing live. The two speech rows go against that project; no procurement needed.

**3. One shared number for every tenant** (owner decision, 2026-07-26). Pragya answers on a single line rather than one number per tenant.

This **inverts decision 5** — *"the number is the routing discriminator … deciding by destination rather than by caller matters because the caller is the untrusted half"* — and the inversion is recorded rather than drifted into. With one number the destination says only which *face*; the caller's own verified binding says which *business*, and a caller can spoof their own address.

What keeps it acceptable is unchanged and enforced elsewhere: an **unbound caller is capped at T0** and reads nothing, **T2+ never runs on voice**, and **T3 is refused outright** as "the most spoofable" channel. The residual exposure is a spoofed caller ID reading tenant data at T1 — which existed already with per-tenant numbers; what a shared line removes is one weak factor, since an attacker no longer needs to know which number belongs to which tenant.

**4. An address belongs to at most one tenant** (owner decision, 2026-07-26), enforced by a **partial unique index** (`iauth002`) rather than resolved at call time. The alternatives were asking the caller "which business?" or picking their most recently active tenant, and a wrong pick there is a cross-tenant disclosure read aloud over the phone. Same reasoning as LEARN's B10 guarantee: make it impossible to represent rather than merely impolite to do. Partial on `revoked_at IS NULL`, so somebody who genuinely leaves one business for another can register the same phone at the new one.

## 5. The plan

**The sequencing insight: gaps 2, 3 and 4 need no credentials.** This repo has a settled precedent for exactly this shape — FLEET's `openai_compat_adapter`, TWIN's tool substitution, LIB's `DriveSource` — build against an **injected transport**, test against fakes, and the live call becomes a config step rather than a build step. Phase 1 and Phases 3–4 run in parallel.

### Phase 1 — pick the two speech services *(owner, ~1 hour, blocking only Phase 2)*

Decision 7 named "Whisper on Vertex AI" and "Gemini TTS". **Confirm those are the right products before enabling anything** — this is an hour well spent because the wrong choice is expensive and awkward to reverse:

* **Whisper on Vertex Model Garden is a self-deployed endpoint** — provisioned per node, billed per node-hour rather than per minute. For a phone line idle most of the day that is a standing charge for nothing.
* **Google Cloud Speech-to-Text (Chirp)** is the managed streaming alternative: a real streaming API, per-minute pricing, and native handling of 8 kHz telephony audio — which is what the carrier actually hands over.

The same question applies to TTS (Cloud Text-to-Speech streaming vs Gemini audio output).

> ⚠️ **Verify against current GCP documentation.** The above reflects a model knowledge cutoff and GCP moves quickly. Check streaming support, telephony sample-rate handling and current pricing directly.

**Output needed to unblock Phase 2 and finish Phase 3:** the two product names, and whether each authenticates by API key or by ADC / service account.

### Phase 2 — seed two registry rows *(owner, 15 min — after Phase 1)*

Shape fixed by `channels/speech.py`:

| Field | ASR | TTS |
|---|---|---|
| `service_sku` | `pragya-asr-whisper-vertex` | `pragya-tts-gemini` |
| `service_category` | `AUDIO_GENERATION` | `AUDIO_GENERATION` |
| `component_type` / `cost_unit` | `minute` | `character` |
| `service_metadata` | `{"project_id": "hirebuddha-production", "region": "us-central1"}` | same |

> **`AUDIO_GENERATION`, not `AUDIO_GEN`** — corrected 2026-07-26. The first draft of this plan took `AUDIO_GEN` from a stale comment in `config/models.py` that listed categories which had never existed in the data. The value that works is the one in the UI's `SERVICE_CATEGORIES`, which follows the `IMAGE_GENERATION` / `VIDEO_GENERATION` convention. Note the category is **descriptive only** for this purpose: `speech.py::_resolve` filters on `service_sku` and `status`, so voice resolution is unaffected either way.

**Seed on the APP company, not a tenant.** `_resolve` already falls back to the platform-owned row, so one pair serves every tenant until one brings its own — the same fallback the usage service uses.

*(If Phase 1 changes the products, the SKU **strings** stay as they are — they are identifiers, not descriptions, and renaming them means touching code for no behavioural gain. Record the actual product in `provider_name` / `model_name`.)*

### Phase 3 — the two adapters ✅ *(built 2026-07-28; live transports open)*

Concrete `Transcriber` and `Speaker` behind an injected transport. Two properties the Protocols already demand:

* **Both stream.** A non-streaming TTS makes a call feel broken regardless of model speed — the caller hears nothing until the whole reply is synthesised.
* **ASR yields partials.** `stream()` returns `(text, is_final)`; barge-in and responsive endpointing are impossible without partials, and an adapter that only ever yields a final transcript turns every turn into a wait.

Tested against a fake transport, exactly as FLEET's GLM/Qwen/Kimi adapter is. Only the final auth call needs Phase 1's answer.

### Phase 4 — media wiring, and making the route actually route ✅ *(built 2026-07-28)*

1. **Gap 4 first** — ten lines, and everything downstream is invisible without it. The `VoiceFace.PRAGYA` branch has to actually diverge instead of logging.
2. **Gap 3** — attach `drive_call`'s frame in/out to the websocket media stream. This is a *second consumer* of plumbing that already exists, not new infrastructure.

### Phase 5 — the first real call *(owner + build session)*

Assign a number to the tenant's Pragya entity via `assign_pragya_number`, which reuses the shipped `available → claimed → assigned` lifecycle rather than adding a parallel flag that could disagree with it. Then dial it.

**Acceptance — deliberately narrower than it first appears:**

* She answers, and identifies the caller from a verified `channel_bindings` row.
* She handles **T0/T1** work on the call: answering questions, reading tenant data, routine assignment.
* Anything **T2+** she declines *on the phone* and sends to the console.

That last point is **not a gap to close later.** `voice_tier_ceiling` caps the channel at T1 and applies the cap *before* session state, so an elevation earned in the console cannot ride onto the next phone call. A Pragya who could authorise a payout over the phone would be the defect.

### Phase 6 — close it out

Build notes, **VG-08 and VR-11 marked closed** in [00a_genui_backend_gap_analysis.md](../increment-6/00a_genui_backend_gap_analysis.md), the Inc-4 §12.5 limit struck, HANDOFF refreshed, and whatever limit genuinely remains recorded rather than buried.

## 6. Effort

| Phase | Owner | Rough |
|---|---|---|
| 1 — choose the services | Rahul | ~1 hour, mostly reading pricing pages |
| 2 — registry rows | Rahul | 15 min |
| 3 — adapters | build | one session |
| 4 — media + routing | build | one session, two if the frame conversion is fussier than it looks |
| 5 — first call | both | an afternoon with a phone in hand |
| 6 — close out | build | short |

## 7. Risks

| Risk | Why it is real |
|---|---|
| **Frame format mismatch** | The carrier hands 8 kHz mulaw; the ASR may want 16 kHz linear PCM. Conversion is routine, but it sits on the hot path of a live call and a bug there sounds like a broken line rather than an error |
| **Latency budget is not yet measured** | ASR-LLM-TTS is three hops where speech-to-speech is one. `THINKING_FILLER` and `FILLER_AFTER_SECONDS = 1.2` exist in `channels/voice.py` because ~1 s of silence reads as a dropped call — but nobody has measured the real round trip, so the filler is tuned against a guess |
| **Phase 1's answer may invalidate part of Phase 3** | Building the adapters before the products are chosen risks writing to the wrong API surface. Mitigated by the injected transport: the seam survives, only the concrete call changes |
| **The dev DB holds live carrier credentials** | Noticed while verifying §2 — the Tata Smartflo row carries a real auth JWT and `business_id` in a *dev* database. Not this plan's problem to solve, but worth knowing before anyone shares a dump |

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-28 | v2.0 — **gaps 1–5 closed; only the live transports remain.** Adapters (`channels/adapters.py`, transport injected), media wiring (`voice/pragya_stream_handler.py` + `/stream/pragya/{id}`), the webhook branch that finally diverges (`_connect_pragya`), and **gap 5** — the Pragya seeder, a blocker that was not in the original four. Two further owner decisions recorded in §4: one shared number (inverting decision 5, with the security consequence stated) and one-address-one-tenant enforced by a partial unique index. §3.1 records what building it changed, including a test that was passing only because voice had never been configured. |
| 2026-07-26 | v1.0 — planned and **parked**. Scope corrected (VG-08 is Pragya's inward face, not voice generally — business voice is already live); current state verified against the running registry; a **fourth gap found** (`route_for_number` computes the face and discards it); two decisions locked (ASR-LLM-TTS as designed; GCP already in use); six phases with the credential-independent work identified so Phases 3–4 need not wait on Phase 1. |
