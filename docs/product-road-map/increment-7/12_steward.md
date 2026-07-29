# Increment 7 / Phase B — STEWARD: The Steward Present (G3)

> **Status:** ✍️ workstream opened 2026-07-29, branch `inc7/steward`.
> **Read first:** [10_workstream_decomposition.md](./10_workstream_decomposition.md) §6 (the scope) · [06_backend_api_contracts.md](./06_backend_api_contracts.md) §5 (VG-07, the channel contract) + §12 (SEAM build notes — what the channel already does) · [11_driver.md](./11_driver.md) §6.3 (the honest limits STEWARD inherits) · [00a_voice_go_live_plan.md](./00a_voice_go_live_plan.md) §8 (the live call that gates G3's *exit*).

---

## 1. What STEWARD is, and is not

DRIVER made the estate *workable*; STEWARD makes Pragya *present in it*. Until now she is a page (`PragyaConsole`, chat-shaped) and a phone number (VG-08, awaiting its call). After STEWARD she is a presence in the same room as the work: she announces a tray before you find it, walks the map to what she is talking about, opens a surface instead of describing one, and hears you say "approve it" out loud — with the ceremony still being the only path to the act.

What STEWARD is **not**: a new authority. The channel never elevates (SEAM's AST-pinned rule stands), ceremonies run only through `/ai/authn/*`, the certified set stays **ten**, and no new `enforce_*` call site is added — R5's correspondence test must exit this workstream byte-identical.

Three inherited debts are named in earlier build notes as STEWARD's, and this doc owns them explicitly:

1. **Nothing calls `deliver_tray` in production** (SEAM §12.3) — the approval watcher is S1.
2. **The tray's `recommendation` is null** ("nothing writes one until STEWARD", `genui/trays.py`) — S2.
3. **The tray panel opens its own SSE connection** beside the terrace's (DRIVER §6.3) — the one-connection consolidation lands with the channel client, S5.

## 2. § Decisions (locked with Rahul 2026-07-29 — do not re-litigate)

1. **The voice leg builds now, as a tested seam.** The FLEET/TWIN/LIB/VG-08 precedent: the browser voice loop is built against the same ASR/TTS registry rows through the injectable transports, no test reaches a live endpoint, and the live proof (the phone call *and* a real browser mic run) is owner-side. It gates **G3's exit, not the build**.
2. **The tray recommendation is LLM-generated.** One advisory sentence per delivered tray, written once at delivery time, in Pragya's voice, from the gate's own facts. Cost design in §5 — the notable consequence of choosing the LLM over the heuristic is that the recommendation needs a **cost attribution, a persistence row, and a failure posture** (null, never a blocked tray).
3. **The platform-voice gap stays parked.** Unknown phone callers keep getting silence + hangup (00a §8.4); fixing it needs a platform-billed TTS voice and that billing decision is deferred to the live-call session. Recorded here so it is a decision on file, not a forgotten TODO.
4. **This session is STEWARD only.** LINE and GLASS start in their own sessions, per the one-branch-one-merge rhythm.

## 3. The task plan

| S | Task | Where |
|---|---|---|
| S0 | This doc · branch `inc7/steward` | docs |
| S1 | The **approval watcher** — the production `deliver_tray` caller · the delivery ledger (`tray_deliveries`) · migration **`genui002`** | `genui/watcher.py`, `genui/models.py` |
| S2 | The **recommendation writer** — LLM one-liner, `TRAY_RECOMMENDATION` attribution, `tray_recommendations` (also `genui002`), read back by the tray composer | `genui/recommendation.py`, `genui/trays.py` |
| S3 | **Navigation** — `focus` / `materialize` / `narrate` anchors derived from the turn outcome; presence `speaking`/`away` semantics | `genui/navigation.py`, `genui/channel.py` |
| S4 | **Voice over the channel** — browser leg on the shipped adapters (conversion flags off), mic-framing protocol, ASR→turn→TTS, tested seam | `genui/voice_channel.py`, `genui/channel.py` |
| S5 | The **channel client** + the shared-stream consolidation + `viewport` on every depth change | `vihara/src/steward/` |
| S6 | **Presence mark · narration · beam/focus · materialize** rendering | `vihara/src/steward/`, `app/` |
| S7 | **Ceremonies over the channel** — T2 step-up, T3 second-channel-wait, retry-whole, cross-device | `vihara/src/steward/` |
| S8 | **Voice UI** — mic capture, playback, barge-in, speaking presence | `vihara/src/steward/voice/` |
| S9 | Suite hardening: mutation tests on the new controls, wire fixtures both sides | both |
| S10 | Gates · §Build notes · HANDOFF · merge | docs |

## 4. Design — the approval watcher (S1)

**The problem it solves.** SEAM built the single delivery door (`channel.deliver_tray`: sockets first, push when nobody listens, never both) and nothing in production calls it — the SSE stream mirrors `tray.delivered` from its own diff loop, which reaches only a client already looking at the estate. The watcher is the producer: a pending approval becomes a delivered tray within seconds, wherever the owner is.

**Where it runs, and why that is forced.** The socket hub is in-memory in the API process. An arq cron cannot reach it — so the watcher is an **asyncio background task started at app startup** in `main.py`'s lifespan, poll interval `TRAY_WATCHER_INTERVAL_SECONDS` (default 3s, the stream's own cadence). This also keeps it out of the arq worker, which the ops notes record as a single point of failure; a dead worker already stalls campaigns — it should not also silence approvals.

**The sweep, not a hook.** A creation hook inside `AIService`/PolicyGate would couple gate code to a UI concern and would miss approvals created by any path that forgets the hook. The sweep pattern is the repo's own (LEARN's outcome runner): select `PENDING` approvals through the company join (the VG-05 shape `trays._pending_with_entities` already uses), skip those already delivered, deliver the rest.

**Recipients, and the dedupe grain.** `deliver_tray` takes one `(company, user)`. The watcher resolves the recipient set per approval as: every user with an **open socket** in that company's hub sessions ∪ every user with an **active push subscription** in that company. The ledger `tray_deliveries` is unique on **(approval_id, user_id)** — so:

* a user reached once is never notified twice for the same card (restart-safe, the reason this is a table and not a cursor);
* a user who appears *later* — subscribes on a new phone, opens a first socket — still receives a still-pending card on the next sweep. A tray undeliverable today is not marked "nowhere" and forgotten; it retries until the approval stops being `PENDING`.

**Failure posture.** Push-transport errors mark the subscription revoked (S EAM's existing rule) and the row is simply not written — retried next sweep. The watcher must never raise out of its loop; one bad approval logs and skips (the "nothing happened" rule: a silent dead watcher is the failure mode to test for, so a tripwire test kills the loop body and asserts the loop survives).

**Migration `genui002`** (off `genui001`): `tray_deliveries` (id, approval_id, company_id, user_id, via `socket|push`, delivered_at; unique (approval_id, user_id)) and S2's `tray_recommendations`. No tenant-plane DDL.

## 5. Design — the recommendation writer (S2)

**What it is.** D5 §4.1 contracted the slot; §4.2 says why it is the one generated field on the tray: *the recommendation is Pragya's and the tray is not certified because of it*. The certified block's hash covers component+props only — the recommendation sits outside it, rendered as her prose, visually hers, never inside the ceremony.

**When it is written: once, at delivery.** The watcher asks the writer for a sentence *before* calling `deliver_tray`, and persists it in `tray_recommendations` (approval_id PK, sentence, model_used, cost_usd, created_at). `tray_list`/`tray_detail` LEFT JOIN it into the composed tray — the composer stays a pure function over rows; re-renders and re-reads never re-bill.

**What the model sees.** Only the gate's own snapshot facts — category, amount, band position, checkpoint key, the entity that raised it, the D2 observed-cost estimate, SLA. Never tenant free-text beyond the gate's `reason` (which the gate itself wrote), never the run transcript. One sentence out, length-capped, rendered as text. It is advisory by construction: nothing reads it back, no path executes from it.

**Cost classification (the repo rule: classify, don't just add).** `CostAttribution.TRAY_RECOMMENDATION`, and it stays **OUT of `PLATFORM_INITIATED_ATTRIBUTIONS`** — the card exists because the tenant's own agent raised it; the sentence is part of serving that tenant's approval flow, the same side of B13 as RETR's `rerank` and `MANIFEST_GENERATION`. `tests/parity` is the canary and must stay 16 green — which it will, because the writer runs only inside the watcher, and the watcher is an app-lifespan task no parity test starts.

**Failure posture: null, loudly logged, tray delivered anyway.** The echo-bus principle — a missing recommendation loses advice, not work. No credit, router failure, model refusal: the tray goes out with `recommendation: null` and the renderer already shows no line (DRIVER rule 3). The writer is retried on the next sweep **only if the tray itself has not yet been delivered to anyone**; once delivered without a recommendation, it stays without one — a recommendation appearing under a card the owner already read would look like the platform changing its mind after the fact.

## 6. Design — voice over the channel (S4/S8)

**The scope correction first** (00a's lesson): this is the **browser** leg — mic and speakers on a logged-in console session. It is *not* the phone leg. The consequences differ in the one place that matters: **the tier**. `voice_tier_ceiling` caps the *phone* channel at T1 because a caller is identified by caller-ID binding — a claim, not a proof. The browser channel is a JWT-authenticated console session where WebAuthn works; browser voice is an *input method*, not a channel, so console tier rules apply unchanged and the T2/T3 ceremonies remain available mid-conversation. Stated here because it would be easy to "inherit" the phone ceiling reflexively and wrong to.

**The wire.** JSON control frames + binary audio frames on the existing WS:

* client → server: `{"type":"mic","state":"open"}` · binary frames (**PCM16, 16 kHz, mono** — what the ASR transport already expects) · `{"type":"mic","state":"closed"}`
* server → client: `transcript(text, is_final)` as she hears · the normal `narrate` reply · binary frames (**PCM16, 24 kHz** — Gemini's native rate) while `presence: speaking`

**Adapter reuse is the whole design.** `ChirpTranscriber(convert_from_mulaw=False)` and `GeminiSpeaker(convert_to_mulaw=False)` — the flags exist precisely for a caller whose audio is not carrier μ-law. No new speech code; the browser does its own capture/playback rate handling (S8's AudioWorklet captures 16 kHz PCM16; playback runs the 24 kHz PCM through WebAudio). Billing rides the same voice attributions the phone leg logs.

**Barge-in is client-side.** The phone leg needed server energy VAD because a phone is a dumb pipe. A browser is not: S8 stops local playback the moment the mic detects speech and tells the server (`{"type":"mic","state":"open"}` doubles as the interrupt — the server stops streaming TTS for that turn). Simpler, and it keeps the server's synthesis loop out of the VAD business on this leg.

**Tested seam, no live call — enforced, not promised.** Every test injects `AsrTransport`/`TtsTransport` fakes (the VG-08 rule: the moment live transports stop raising, tests that construct them start needing credentials). The browser leg adds **no new live-transport code at all**; the live proof is owner-side and is G3's exit key together with the phone call.

## 7. Design — navigation: focus, materialize, narration anchors (S3/S6)

**Derived from the turn outcome, heuristic-first** — the SEAM manifest posture (no LLM composer; novel intent refuses) applied to navigation:

* **anchors** — `TurnOutcome.tool_results` and the command's record refs become `narrate.anchors[]` (`{label, kind, ref}`); the client renders them as chips that navigate and echo. An anchor is a *pointer to something that exists*, resolved from the outcome — never model-invented.
* **materialize** — when the extracted command is navigation-shaped ("show me…", "open…") and its target maps to a surface the manifest service already serves (`still` · `terrace` · `district.*` · DRIVER's sheets), the channel emits `materialize(manifest)` with the same manifest the surface path would return — the client renders it through the standard refusal ladder. A target with no manifest table entry gets her text answer, not a refusal card.
* **focus** — when the reply concerns one district/entity and no full surface is warranted, `focus(target_ref, narration)`: the W renderer flies the beam there; with W disabled the S surface for the target opens instead (the seventeen-surfaces-without-W parity rule).
* **At most one navigation event per turn** — focus *or* materialize, never both; a conversation that teleports the user twice per answer is worse than one that stays still.

**Presence semantics** (the contract's four states, honestly mapped): `listening` (idle, socket open) · `working` (a turn is executing) · `speaking` (TTS streaming on the voice leg) · `away` — the turn failed hard or the runtime refused to run (e.g. out of credit): she is *not able to be present*, and pretending to listen would be a lie. `away` clears on the next successful dispatch.

## 8. What G3's exit needs that this branch cannot supply

The live call (00a §8 — config items done, the call itself owner-side) and a real browser mic/speaker run against live transports. Everything else — the watcher, the recommendation, navigation, ceremonies over the channel, cross-device, the voice seam both sides — exits at the test level on this branch, the G0/G1/G2 pattern.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-29 | v1.0 — workstream opened. Four owner decisions locked (§2): voice now as a tested seam · the recommendation is LLM-written (with the §5 cost/persistence/failure design that choice obligates) · platform voice stays parked · STEWARD only this session. The designs that needed writing before code: the watcher is an API-process lifespan task because the socket hub is in-memory (and the arq worker is a known single point of failure); the delivery ledger's grain is (approval, user) so late-arriving devices still hear about still-pending cards; the recommendation is written once at delivery and never after; browser voice is an input method, not a channel — console tier rules, no T1 ceiling; barge-in is client-side on this leg. |
