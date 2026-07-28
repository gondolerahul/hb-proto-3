# Increment 7 — Prerequisite Plan: Voice Go-Live (VG-08 / VR-11)

> **Status:** 🅿️ **PARKED — planned 2026-07-26, execution deferred.** Two decisions locked (§4); nothing built. Resume at §5 Phase 1.
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

| # | Gap | Evidence |
|---|---|---|
| 1 | **No registry rows** for the two speech SKUs | Confirmed against the live table (§2). The SKU strings exist only at [`speech.py:51`](../../../backend/src/ai/pragya/channels/speech.py) |
| 2 | **No concrete `Transcriber` / `Speaker`** | The Protocols have no implementors |
| 3 | **`drive_call` is not connected to carrier media** | Frame plumbing exists in `websocket_handler.py` for the speech-to-speech path; `drive_call` is a second consumer that was never attached |
| 4 | **`route_for_number` has no effect** | `webhook_router.py` ~line 112 resolves the face, **logs `routes to Pragya`, and falls through to the gateway path anyway**. The routing decision is computed and discarded |

**Gap 4 is the one to fix first.** Until it does, gaps 1–3 can all be complete and a call to Pragya's number still lands on the legacy speech-to-speech stack, with nothing obviously wrong in the logs.

## 4. Decisions (locked 2026-07-26 — do not re-litigate)

**1. ASR-LLM-TTS as designed, not speech-to-speech.**

Two architectures exist in this repo and they are not interchangeable:

* *Legacy / KAR-01* — **speech-to-speech**: one realtime model session does hear → think → speak internally. Proven and live.
* *Pragya (Inc-4 T5)* — **ASR → LLM → TTS** as three pieces, with her turn loop running *between* hearing and speaking.

The split is not stylistic. Pragya's turn loop is where `require_tier`, the nine-stage machine and tool execution live. A speech-to-speech model completes the whole turn *inside* the model, so **there is no seam to insert the tier gate into** — which is exactly why decision 7 chose ASR-LLM-TTS in the first place.

The rejected option is worth recording because it will look attractive again: running her on the existing live stack would take days rather than weeks, but her turn loop would be bypassed, so on voice she could only *promise* actions through the Inc-3 live gate and never execute them. An account manager who cannot action *"pause the invoice chaser"* is a demo, not a steward — and it would reopen D1 on the voice channel, which is closed end-to-end today.

**2. GCP is already in use** — project `hirebuddha-production`, service account and billing live. The two speech rows go against that project; no procurement needed.

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

### Phase 3 — the two adapters *(no credentials needed)*

Concrete `Transcriber` and `Speaker` behind an injected transport. Two properties the Protocols already demand:

* **Both stream.** A non-streaming TTS makes a call feel broken regardless of model speed — the caller hears nothing until the whole reply is synthesised.
* **ASR yields partials.** `stream()` returns `(text, is_final)`; barge-in and responsive endpointing are impossible without partials, and an adapter that only ever yields a final transcript turns every turn into a wait.

Tested against a fake transport, exactly as FLEET's GLM/Qwen/Kimi adapter is. Only the final auth call needs Phase 1's answer.

### Phase 4 — media wiring, and making the route actually route

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
| 2026-07-26 | v1.0 — planned and **parked**. Scope corrected (VG-08 is Pragya's inward face, not voice generally — business voice is already live); current state verified against the running registry; a **fourth gap found** (`route_for_number` computes the face and discards it); two decisions locked (ASR-LLM-TTS as designed; GCP already in use); six phases with the credential-independent work identified so Phases 3–4 need not wait on Phase 1. |
