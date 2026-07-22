# Increment 4 / PRAGYA-RT — Pragya as a First-Class Runtime

> **Status:** ⬜ Design (2026-07-22) — seam locked, ready to build · **Branch:** `inc4/pragya-rt`
> **Design authority:** Technical §12.1 (the eight-stage loop this forks *from*), §20.3 (the PolicyGate it must not fork), §11.3 (tiers); Functional §4.2–§4.4 (Pragya), §8.1 (voice stack).
> **Depends on:** Inc-3 AUTH (`require_tier`), Inc-3 PRAGYA (stage machine, scripts, engagement state), Inc-2 ONBOARD (the wizard step APIs she drives).

---

## 1. The finding this workstream exists to fix

The shipped eight-stage loop is a **task** engine: perceive → strategize → act → observe → reflect, over a bounded unit of work with a beginning and an end. Increment 3 ran Pragya on it because it was there.

Pragya's unit of work is a **months-long relationship**. The mismatch shows up as symptoms that look like separate bugs and are not:

* Post-call "deferred runs" needed **Strategize** and **Decide** stages that have no post-hoc meaning — you cannot plan a conversation that already ended.
* Stage advancement had nowhere natural to live, because the loop's `Decide` decides about a *task*, not an engagement.
* Artifact extraction had no home for the same reason.
* Reflection over a *conversation* is a different operation from reflection over a *task*, and forcing one into the other produced a queue nobody could drain.

Four symptoms, one cause. This document forks the orchestration and keeps everything else.

## 2. The line

> **Pragya gets her own turn loop. She does not get her own governance, metering, memory, or tool execution.**

Forking the first removes a real impedance mismatch. Forking the second rebuilds register finding **D1** — a second, ungoverned path to the same tools — and punches a hole in the **E-series** billing safety work. There is no performance argument for skipping the PolicyGate: it is a pure function costing microseconds, which is precisely what Increment 3's VOICE profile established.

## 3. The seam — LOCKED (decision 2)

Every row marked 🔒 is a decision, not a guideline. Changing one is a charter amendment, not a refactor.

| Layer | Pragya-specific | Shared | Why |
|---|---|---|---|
| Turn orchestration | ✅ her own loop | | the mismatch this workstream fixes |
| Engagement / stage state | ✅ | | already hers (`pragya_engagements`) |
| Channel adapters (console, voice, WhatsApp) | ✅ | | a channel is a transport, not a policy |
| Context assembly (what enters the prompt) | ✅ | | conversation context ≠ task context |
| Artifact extraction | ✅ | | derived from her stage scripts |
| Stage advancement | ✅ | | engagement-level, not task-level |
| **PolicyGate + authority matrix** | | 🔒 | one taxonomy, one enforcement point |
| **`inward_auth` — tiers, `require_tier`, bindings** | | 🔒 | D1's mechanism; a second copy is a second bug |
| **Tool registry + tool executor + sandbox** | | 🔒 | two audit trails are worse than none |
| **Billing — `usage_logs`, wallet holds, envelopes, attribution** | | 🔒 | unmetered turns are invisible cost |
| **CORTEX / memory + retrieval** | | 🔒 | or her answers drift from the dashboards' |
| **Signal bus** | | 🔒 | delegation and reporting both ride it |
| **Meta-Agent (Architecture Board)** | | 🔒 | delegated to, never reimplemented |
| **HITL / Judgment Desk approvals** | | 🔒 | Pragya can never satisfy her own checkpoint |

**What "shared" means operationally:** Pragya *calls* these; she does not wrap, subclass, or shadow them. If a shared component needs a change to serve her, the change lands in the shared component and both callers get it.

## 4. Pragya's turn loop

```
Channel adapter (console SSE | voice ASR-LLM-TTS | WhatsApp)
        ↓ Turn(text, channel_kind, channel_address)
 1. resolve session + engagement          → inward_auth, pragya.engagement   [shared/hers]
 2. assemble context                      → CORTEX + artifacts + transcript  [shared retrieval]
 3. classify intent → tier                → inward_auth.tiers                [shared]
 4. authorize                             → require_tier                     [shared]
 5. LLM turn (streaming, tool-capable)    ← the only model call on the path
      per tool call:  PolicyGate → shared tool executor → observe            [shared]
 6. extract artifacts                                                        [hers]
 7. maybe advance the stage                                                  [hers]
 8. meter                                 → usage_logs, wallet               [shared]
        ↓
Response → channel adapter → TTS or SSE
```

Eight steps, like the task loop — but they are *conversation* steps. Exactly **one** model call sits on the latency path, versus the task loop's four (planner, pre-critic, post-critic, reflector). That difference is the entire reason for the fork.

**Ordering is a safety property**, carried forward from Increment 3: classify and authorise *before* generating. A model that has already promised to pause a process, and only then discovers it may not, has to be corrected in front of the user.

### 4.1 Where the four Inc-3 gaps land

| Gap | Now lives at | Note |
|---|---|---|
| Artifact extraction | step 6 | a per-stage tool-call schema built from the script's declared `artifacts` keys |
| Stage advancement | step 7 | see §4.2 |
| Conversation reflection | end-of-engagement-stage, not end-of-call | a *conversation* reflection, not a task one — see §4.3 |
| Script goldens | test-time over recorded turns | see §8 |

### 4.2 Advancement — artifacts gate, owner confirms

A stage becomes **eligible** to advance when the artifact keys its script declares are populated (deterministic, no model call). Eligibility is not advancement:

* **Stages 1, 3, 4** — advance on artifacts. Nothing is being agreed, only gathered.
* **Stages 2 and 5** — require **explicit owner confirmation**, because the owner's agreement *is* the deliverable (which assumptions were struck; which priority was chosen). Auto-advancing these would mean Pragya deciding the owner had agreed.
* **Stages 6–9** — mechanical, driven by the wizard APIs as today.

The prose `exit_criteria` in each script stay what they are: instructions the model reads. The **artifact keys** are the machine-checkable half. That split is deliberate — a predicate over prose would be an LLM grading itself.

### 4.3 Reflection, corrected

Increment 3's VOICE profile deferred five stages post-call. Two of them have no post-hoc meaning and are dropped:

| Stage | Post-hoc value | Verdict |
|---|---|---|
| Reflect | writes CORTEX + the §7 learning signal | **keep** — this is the point |
| Post-Critic | alignment supervision over a whole transcript | **keep** — better whole than per-turn |
| Pre-Critic | "would it have blocked this?" → `critic_calibration_job` | **optional**, calibration only, *not* governance |
| Strategize | planning a conversation that ended | **drop** |
| Decide | deciding on absent inputs | **drop** |

For Pragya this becomes a **stage-completion reflection** (what did we learn in this stage) rather than a call-completion one. The existing `voice_deferred_runs` queue stays with **KAR-01**, where per-call is the right granularity.

> **Operational note, independent of this build:** `voice_deferred_runs` currently fills and never drains. Whatever is built here, that table needs a drainer or a reaper — a table that only grows is a slow leak.

## 5. Tools and the Meta-Agent

### 5.1 Tool calls — a thin act path

Inside step 5, per tool call:

```
LLM proposes tool call
   → PolicyGate.evaluate_policy(intent, governance)     [shared, pure]
       PASS       → shared tool executor → observe → continue the turn
       RAISE_HITL → raise the card, tell the owner, do NOT execute
       BLOCK      → decline plainly
```

Four steps, all cheap except the tool itself. Same gate, same executor, same audit trail as a worker agent.

**Structural containment (T2) — revised during build, 2026-07-22.** The design proposed making `GateDecision` a **required argument** of the shared executor. Investigation found six existing call sites (`step_executor` ×4, `voice`, `resilience`), *all* already gated upstream by `gate_and_maybe_stop` inside the critic pipeline. Threading a parameter through the Solo Pack's revenue path would therefore be a large, risky change defending against a risk that does not exist.

The risk that *does* exist is a second call site appearing inside `ai/pragya/` that skips `acting.run_tool_calls`. T2 is therefore an **import-boundary test** over Pragya's package: exactly one module may reach the executor, none may reimplement `CATEGORY_RULES`, and `acting` must use the platform's gate rather than a local one. Same guarantee where it matters, zero blast radius outside Pragya. Verified to fail on an injected violation, not merely to pass.

### 5.2 The Meta-Agent — async delegation

The Architecture Board is seven sequential roles (RequirementChat → Curator → Architect → Critic → Validator → TestDriver → Promoter). That is minutes, not a conversational turn, so it can never run inline.

**Pattern: delegate, promise, report.**

1. Pragya recognises the need for a capability that does not exist.
2. She dispatches the board as a normal execution run (its implementation is untouched).
3. She tells the owner plainly: *"I'm having that built — a few minutes."*
4. Board completion emits a signal; she picks it up and reports back on the next turn or proactively.

This is the general form of VOICE's promise-don't-complete rule, and **the same pattern covers every long operation**: deep research (stage 1), bundle activation, board builds, bulk ingestion. One mechanism, not four.

## 6. Voice — two faces, two engines (decisions 3 + 4)

| | **KAR-01 gateway** (outward) | **Pragya** (inward) |
|---|---|---|
| Who calls | a customer calls the business | the owner calls their account manager |
| Counterparty | untrusted | authenticated owner |
| Engine | **realtime speech-to-speech** (decision 4) | **ASR → LLM → TTS** (decision 3) |
| Loop | collapsed 8-stage profile (B7) | Pragya turn loop (§4) |
| Session length | short, latency-critical | long, considered |
| Number | the tenant's business number | **Pragya's own number** (decision 5) |

### 6.1 Why ASR-LLM-TTS for Pragya

Session caps are the obvious reason — realtime sessions cap out well short of a months-long relationship, and a mid-conversation reconnect is a bad experience with an account manager.

The architectural reason is better: **a text-boundaried turn is what the platform can govern.** ASR-LLM-TTS produces a discrete text-in/text-out unit, so the tier classifier, the PolicyGate and the artifact extractor all work on a voice turn *unchanged*. Realtime speech-to-speech never surfaces a gateable turn boundary — the model owns the conversation. Voice therefore becomes a channel adapter over the same loop instead of a parallel universe.

### 6.2 The latency cost, stated honestly

| Segment | Realistic |
|---|---|
| Endpointing (silence detection) | 200–400 ms |
| ASR final transcript | 100–200 ms |
| LLM time-to-first-token | 300–600 ms |
| TTS time-to-first-byte | 100–250 ms |
| **Total to first audio** | **~0.8–1.4 s** |

Versus ~300 ms for realtime. This is a real regression on a real axis, accepted deliberately for the inward face and rejected for the outward one — which is exactly what decisions 3 and 4 encode.

**Mitigations are mandatory, not optional:** streaming ASR with good endpointing, streaming TTS (non-streaming will feel broken regardless of LLM speed), barge-in support, and acknowledgement tokens while the model thinks.

### 6.3 Pragya's own number (decision 5)

**The number is the routing discriminator.** An inbound call resolves by destination:

* → **Pragya's number** → inward pipeline, ASR-LLM-TTS, caller identified by `channel_bindings` (AUTH), T1 ceiling, voice can never self-elevate.
* → **the tenant's business number** → KAR-01, realtime, counterparty trust.

The two faces can never be confused at the entry point, which is worth more than the number costs. Implementation reuses the shipped `phone_numbers` pool (status `available → claimed → assigned`), assigned to the tenant's Pragya entity; `NumberRouter` gains the branch.

**Carrier plumbing is shared** (Twilio/Tata webhooks, media streams); the *handler* is not.

## 7. Code Mapping

| Piece | Where | Notes |
|---|---|---|
| Turn loop | `ai/pragya/runtime.py` — the §4 loop | replaces `conversation.handle_turn`'s internals, keeps its signature |
| Tool path | `ai/pragya/acting.py` — propose → gate → shared executor | calls, never wraps |
| Artifact extraction | `ai/pragya/artifacts.py` — per-stage schema from the scripts | |
| Advancement | `ai/pragya/advancement.py` — artifact gate + confirmation rule | pure |
| Stage reflection | `ai/pragya/reflection.py` — stage-completion, not call-completion | |
| Delegation | `ai/pragya/delegation.py` — dispatch + promise + report over SIG | board, research, activation |
| Voice adapter | `ai/pragya/channels/voice.py` — ASR/TTS pipeline over shared transport | |
| Console adapter | `ai/pragya/channels/console.py` — the existing SSE path | |
| Number routing | `src/voice/number_router.py` (extended) | the §6.3 branch |
| Gate containment | shared tool executor signature change | `GateDecision` becomes required |

## 8. Task Plan

| # | Task | Acceptance |
|---|---|---|
| T1 | The turn loop + the §3 seam, console channel only | a console turn runs end-to-end through the new loop; `usage_logs` written |
| T2 | **Gate containment** — import boundary over `ai/pragya/` (revised; see §5.1) | exactly one module reaches the executor; guard proven to fail on an injected violation |
| T3 | Artifact extraction + advancement (§4.2) | stages 1/3/4 auto-advance on artifacts; 2/5 require confirmation (goldens) |
| T4 | Delegation pattern + Meta-Agent dispatch (§5.2) | board runs async; Pragya promises and reports back |
| T5 | Voice adapter: ASR-LLM-TTS + Pragya's own number | a real call reaches the same turn loop as the console; barge-in works |
| T6 | Stage-completion reflection (§4.3) + drain-or-reap `voice_deferred_runs` | reflections written; no unbounded table |
| T7 | Behavioural script goldens over recorded turns | script guardrails asserted deterministically; no prose pinning |
| T8 | Integration + all gates green; build notes; maturity flips | parity/eval unchanged |

## 9. Testing the goldens without pinning prose (T7)

The trap: asserting on model wording gives either brittle string-matching or vacuous checks. RETR avoided it by grading *rankings* rather than text; the analogue is to grade **behavioural properties of a transcript**, drawn from each script's own `must_cover` and `guardrails`:

* Stage 1 asked **zero** questions answerable from public research.
* Stage 2's output carries numbered items **with confidence labels**.
* Stage 4 marked at least one verdict **"still open"** when evidence was thin.
* No stage collected an approval in chat.

Deterministic, cheap, CI-safe, and derived from assets already reviewed. An LLM-judge rubric stays an **offline** quality check, not a CI gate — it tests the judge as much as the script and costs money per run.

**The honest limit:** these test *adherence*, not whether the conversation was any good. Only a human reading real transcripts tells you that — so pair the gate with periodic manual review of sampled live transcripts, the same discipline C4 imposes on agents through deep-audit sampling.

## 10. Risks

| Risk | Containment |
|---|---|
| **Governance drift** — two loops, two places the gate must be called | T2's import boundary: one sanctioned actor module, no local authority matrix, gate imported from `governance.policy_gate` |
| **Metering gap** — her turns write no `usage_logs` | launch blocker, not a follow-up; parity suite is the canary |
| **Ongoing duplication** — two loops forever | bounded *only* if the §3 shared list holds; erosion happens one convenience fork at a time |
| **Latency regression** on voice | measure on real carrier audio early, not localhost |
| **Two voice engines to maintain** | accepted by decision 4; the §6 table is the boundary |

## 11. Decisions (Rahul, 2026-07-22)

1. **Take the split** — own turn loop, shared substrate.
2. **The §3 seam is locked before code.** 🔒 rows are charter, not preference.
3. **Pragya's voice is ASR-LLM-TTS.** Session caps and gateable turn boundaries.
4. **KAR-01 stays realtime.** Latency edge is worth it on the outward face; two engines coexist by design.
5. **Pragya gets her own phone number** — the number is the routing discriminator between the two faces.
