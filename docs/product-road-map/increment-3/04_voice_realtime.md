# Increment 3 / VOICE — Realtime Voice, the Collapsed Loop, and Live Transfer

> **Status:** ✅ BUILT (2026-07-22) — V1–V7 complete, all gates green · **Branch:** `inc3/voice` · build notes in §8
> **Design authority:** Functional §8.1 (voice stack), Blueprint §7.3 (KAR-01), Technical §12.1 (the eight-stage loop), §20.3 (PolicyGate). Closes register **B7**.
> **Depends on:** AUTH (`require_tier`, channel bindings), PRAGYA (`handle_turn` already accepts `channel_kind`/`channel_address`), KAR (the KAR-01 stub this replaces), shipped `src/voice/` (Twilio + Tata streams, Gemini Live + Azure realtime clients).

---

## 1. The problem (B7, verbatim)

> *"Realtime voice vs the 8-stage loop unreconciled. A strict-latency voice turn cannot run 8 model stages. Which stages are skipped live? How does a Karuna Voice Gateway warm-transfer a live call to a Process agent mid-conversation?"*

Two questions. The first is about **latency**, the second about **continuity**. They have separate answers and this document gives both.

The shipped voice stack already works — Twilio/Tata media streams, Gemini Live and Azure realtime clients, session manager, transcripts. What it does *not* do is run inside the governed loop, which is why KAR-01 shipped as a stub in Increment 2. Making it real means reconciling a ~500 ms conversational turn with a pipeline whose Pre-Critic alone is a model call.

## 2. Question one — the collapsed loop

### 2.1 The insight that makes this tractable

The eight stages are not equally expensive. Exactly one of the governance controls is a **pure function**:

| Stage | Cost | Live? |
|---|---|---|
| 1. Perceive | cheap — the session context is already warm | ✅ inline |
| 2. Strategize | **model call** (planner) | ⏸ deferred |
| **PolicyGate** (§20.3, runs inside the critic pipeline) | **pure function, microseconds** | ✅ **inline — never skipped** |
| 3. Pre-Critic | **model call** | ⏸ deferred |
| 4. Act | the realtime model *is* the act | ✅ inline |
| 5. Observe | cheap — parse the tool result | ✅ inline |
| 6. Post-Critic | **model call** | ⏸ deferred |
| 7. Reflect | **model call** + CORTEX write | ⏸ deferred |
| 8. Decide | cheap, but meaningless without 2/6/7 | ⏸ deferred |

**Governance is not what gets skipped.** The PolicyGate is deterministic data-plus-comparison — it costs nothing on a voice turn's budget, so it stays inline and a voice agent is governed exactly like a text one. What gets deferred is **LLM judgment**: planning, criticism, reflection.

This is the whole B7 answer, and it inverts the naive assumption that realtime means "fewer guardrails". Realtime means *fewer model calls*; the guardrails that survive are the ones that were never model calls.

### 2.2 The honest consequence

At A1 — where every Solo Pack agent starts — a categorised external effect raises a HITL card. The PolicyGate raises it inline, in the middle of a phone call, and **a phone call cannot wait for a human to approve something in a console.**

So the normative rule is:

> **A voice turn may not complete a governed external action synchronously.** It may promise one. The PolicyGate's HITL card is raised during the call, the caller is told plainly that it needs a sign-off, and the action completes (or doesn't) after the call.

This is a limitation to state, not to engineer around. An agent that could complete a payout mid-call because waiting was inconvenient is precisely the failure D1 and §20.3 exist to prevent. What the caller hears is *"I've put that through for approval — you'll have it within the hour"*, which is both true and what a competent human assistant would say.

Uncategorised acts (reads, lookups, drafting, note-taking, record writes the agent owns) run live and complete live. That covers most of what a voice call actually needs.

### 2.3 The deferred run

Nothing is lost, it is moved. When the call ends, a **deferred run** executes the full eight-stage loop over the transcript: Strategize/Pre-Critic/Post-Critic/Reflect/Decide against what was actually said. That run writes CORTEX reflections and learning signals exactly as a text run would, so quality improvement and the §7 learning loop keep working — asynchronously.

Cost attribution: the deferred run is **tenant-initiated** (the tenant's own call caused it), so it stays *out* of `PLATFORM_INITIATED_ATTRIBUTIONS`. Same rule RETR's reranker followed.

## 3. Question two — live transfer

### 3.1 What "warm transfer" means here

The naive reading is telephony: bridge the call to another number. That is the wrong mechanism for agent-to-agent handoff — it adds carrier complexity, drops the media session, and loses context at the exact moment context matters.

**The design: a context-preserving handoff on the same media stream.** The call never moves. What changes is which entity's system prompt, tools and governance are driving the realtime model. A `VoiceHandoff` record carries forward:

* the transcript so far (summarised, not replayed),
* resolved record references (the Lead, the Invoice, the Account already identified),
* the caller's authenticated identity and tier ceiling,
* why the handoff happened.

The receiving agent opens with an acknowledgement that demonstrates continuity — *"I've got the invoice in front of me"* — rather than re-asking. A handoff the caller has to repeat themselves through has failed regardless of how cleanly it executed.

### 3.2 Governance across the handoff

The receiving agent's governance applies from the moment of handoff; the originating gateway's does not carry over. The tier ceiling *does* carry — the caller does not become better authenticated by being transferred, which would make transfer an escalation path.

### 3.3 Human escalation is out of scope for v1

Transferring to an actual person is a real telephony bridge and a different problem (availability, hold, carrier). v1 takes a message and raises it. Parked deliberately.

## 4. Authentication on a voice call

Caller ID is the *most* spoofable identity the platform accepts, so the AUTH rules bind hardest here:

* An inbound number resolves a verified `channel_bindings` row → the session is **T1**. Unresolved → **T0**, and Pragya declines anything tenant-specific with the enrollment path.
* **A voice channel can never reach ELEVATED by voice alone.** No spoken passphrase, no DTMF PIN, no voice print as a sole factor (§11.3). A T2 command over voice sends a step-up link to the caller's registered console/WhatsApp channel and waits.
* **T3 is unavailable on voice, full stop.** It needs step-up *plus* out-of-band confirmation on a second channel; originating from the most spoofable channel is not the place to start that.

## 5. Code Mapping

| Piece | Where | Notes |
|---|---|---|
| Realtime profile | `ai/voice_loop/profile.py` — which stages run live, pure | the §2.1 table as data |
| Live gate | `ai/voice_loop/live_gate.py` — PolicyGate inline on a voice tool call | reuses `governance.policy_gate.evaluate_policy` (already pure) |
| Deferred run | `ai/voice_loop/deferred.py` + arq job | full loop over the transcript, post-call |
| Handoff | `ai/voice_loop/handoff.py` — context-preserving agent switch | `voice_handoffs` table, migration `voice001` |
| Voice auth | `ai/voice_loop/identity.py` — binding resolution + tier ceiling | over AUTH's `resolve_inbound` / `require_tier` |
| Signal producer | `signals/voice_inbound.py` — `voice.inbound`, subscription-gated, SID dedupe | mirrors `whatsapp_inbound.py` |
| KAR-01 real | `solo_pack/templates/gateways.py` — replace the stub | roster stays 18 |
| Wiring | `src/voice/websocket_handler.py` | fail-safe cutover, like the WhatsApp one |

## 6. Task Plan

| # | Task | Acceptance |
|---|---|---|
| V1 | ✅ Realtime profile (pure) + goldens: the §2.1 table pinned; PolicyGate provably inline | unit goldens; no model-call stage marked live |
| V2 | ✅ Live gate — a categorised voice act raises HITL and does **not** complete inline | golden: A1 payout attempt over voice → promised, not done |
| V3 | ✅ Voice identity: binding resolution, T0/T1, the elevation ceiling | unbound caller refused (golden); voice can't self-elevate |
| V4 | ✅ `voice.inbound` producer + KAR-01 real template + handler cutover | subscription-gated, SID-deduped, falls through when unsubscribed |
| V5 | ✅ Context-preserving handoff + `voice001` | receiving agent has records + transcript; tier ceiling carries |
| V6 | ✅ Deferred post-call run (full 8 stages over the transcript) | reflections written; attributed tenant-initiated |
| V7 | ✅ Integration + all gates green; build notes; B7 closed | parity/eval unchanged |

## 7. Decisions

1. **Governance stays inline; LLM judgment defers.** The PolicyGate is pure, so "realtime" costs it nothing.
2. **A voice turn cannot complete a governed action synchronously** — it promises and the HITL card resolves after the call. Stated as a product limit, not engineered around.
3. **Handoff preserves the media session**, switching the driving entity rather than bridging the call.
4. **Voice can never self-elevate.** Step-up is a console ceremony; T3 is unavailable on voice entirely.
5. **Human escalation deferred** — a real telephony bridge, and a different problem.

---

## 8. Build Notes (2026-07-22) — delta log

All seven tasks landed on `inc3/voice`. Gates at merge: **1364 unit** (+39), 16 parity/eval, **164 integration** (+12), mypy `--strict` over **219** files (allowlist gained `voice_loop`), layout lint exit 0, `voice001` up/down/up clean. **Register finding B7 is closed.**

### 8.1 What shipped

| Task | Module | Note |
|---|---|---|
| V1 | `voice_loop/profile.py` | the §2.1 table as data; goldens assert no model-call stage is live |
| V2 | `voice_loop/live_gate.py` | reuses `evaluate_policy` **unchanged**; adds the promise/decline shape |
| V3 | `voice_loop/identity.py` | caller resolution + the T1 ceiling + T3 unavailable |
| V4 | `signals/voice_inbound.py`, `templates/gateways.py` | producer + **KAR-01 real** (stub replaced); webhook cutover |
| V5 | `voice_loop/handoff.py`, `voice001` | context-preserving switch; ceiling clamps downward only |
| V6 | `voice_loop/deferred.py` | post-call queue with claim/retry semantics |
| V7 | `tests/integration/test_voice_loop_db.py` | 12 DB tests |

### 8.2 Design deltas (decided during build)

1. **The profile lives on the KAR-01 template, not only in the module.** `metadata_extensions` carries `live_stages`, `deferred_stages`, `turn_budget_ms` and `tier_ceiling`, so B7's answer is visible in the governance preview at activation rather than buried in code an owner never reads.
2. **The gateway's prompt quotes `LIVE_COMPLETION_RULE` verbatim**, and a test asserts it. An agent whose instructions describe a different rule from the one `live_gate` enforces will eventually promise something the code then refuses — the drift is silent and only shows up in front of a caller.
3. **The tier ceiling is checked *before* the session state**, not after. Ordering is the property: checked second, an elevation earned in the console would carry onto the next phone call. `test_an_elevation_earned_elsewhere_does_not_reach_the_phone` pins it.
4. **A handoff clamps the ceiling downward only.** If transfer could raise it, "put me through to someone with more authority" becomes an escalation path for a caller whose number was spoofed.
5. **Deferred runs are deduped on `call_sid`.** Carriers fire end-of-call webhooks more than once, and a duplicate would charge the tenant twice for the same reflection. Short calls (< 3 turns — wrong numbers, hangups on the greeting) are never queued at all.
6. **`voice_loop/__init__` re-exports only `profile`.** Importing `identity` there closed the cycle `bindings → consent → templates → profile → identity → bindings`. Same rule the Solo Pack tools follow: an init must not import back toward its own consumers.
7. **The `KAR_01_VOICE_STUB` name is kept as an alias** of the real gateway, so any pinned reference resolves rather than silently disappearing.

### 8.3 What is NOT wired yet

* **The deferred *runner* is a queue, not an executor.** `queue_deferred_run` / `claim_next` / `mark_done` are built and tested, and the webhook queues on call end — but no arq worker drains the queue into an actual eight-stage run yet. Reflections are therefore still not being written from calls. This is the largest remaining gap and the obvious next task.
* **Handoff is recorded, not triggered.** `record_handoff` persists the switch and `opening_line` gives the receiving agent its first sentence, but nothing in the realtime stack *decides* to hand off mid-call — the websocket handler does not yet consult `latest_handoff` to swap the driving entity.
* **Step-up links are described, not sent.** `STEP_UP_REDIRECT` is the copy; wiring it to actually deliver a console link over the caller's registered channel reuses AUTH's signal seam and is not done.
* **Human escalation** (a real telephony bridge) stays deferred by decision 5.
