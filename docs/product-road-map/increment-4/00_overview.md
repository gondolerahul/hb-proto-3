# Increment 4 — The Connected Business + Pragya as a First-Class Runtime: Overview

> **Document Class:** Increment Design & Implementation Plan (index)
> **Author:** Buddha Cognitive Lab (drafted by Claude, decisions by Rahul)
> **Created:** 2026-07-22 · **Status:** Design — PRAGYA-RT seam locked; CONN/SOR carried from the charter
> **Parent:** [build_roadmap.md](../build_roadmap.md) §4 (Increment 4, L–XL, parallelizable)
> **Prerequisite:** Increment 3 complete on `master` (AUTH + PRAGYA + VOICE; D1, C4, C6, B7 closed).

---

## 1. Scope note — this increment gained a workstream

The charter scopes Increment 4 as **CONN** (the §6.6 connector catalog, MCP-first) and **SOR** (per-object mastering and write-back), explicitly "parallelizable per connector". Increment 3's build surfaced an architectural finding that belongs here rather than waiting:

**Pragya is running on an engine built for something else.** The shipped eight-stage loop (technical §12.1) is a *task* engine — perceive, strategize, act, observe, reflect over a bounded unit of work. Pragya's unit of work is a **months-long relationship**. Increment 3 made that work by wrapping the mismatch; [01_pragya_runtime.md](./01_pragya_runtime.md) removes it.

PRAGYA-RT touches an entirely different code area from the connectors, so it runs as a genuinely parallel third track and does not displace the charter's scope.

## 2. Decisions Taken (Rahul, 2026-07-22 — do not re-open during build)

1. **Take the split.** Pragya gets her own turn loop. The orchestration forks; the substrate does not.
2. **The seam is locked before code.** [01](./01_pragya_runtime.md) §3's shared/forked table is a decision, not a guideline. Every row marked 🔒 is non-negotiable.
3. **Pragya's voice uses an ASR-LLM-TTS pipeline**, not a realtime speech-to-speech model. Realtime session caps do not fit a months-long relationship, and a text-boundaried turn is what lets the tier classifier and the PolicyGate see a voice turn at all.
4. **KAR-01 keeps the realtime pipeline.** The outward face talks to customers in short, latency-sensitive calls where realtime's ~300 ms edge is worth having. Two engines coexist by design — see [01](./01_pragya_runtime.md) §6.
5. **Pragya gets her own phone number**, distinct from the tenant's business number. The number is what routes a call to the inward pipeline, so the two voice faces can never be confused at the entry point.
6. **Pragya's capability surface is her child entities, not a tool allowlist.** She calls children (Meta-Agent first; deep research, record access, scheduling later) that wrap tools — so her reach is governed where autonomy and SoD already live, and a new capability is a new entity rather than an edit to her loop. Full reasoning in [01](./01_pragya_runtime.md) §11.2.
7. **ASR/TTS resolve through the IntegrationRegistry** — Whisper on Vertex AI, Gemini TTS. Provider swaps are a registry row, not a code change.
8. **`inc4/pragya-rt` does not merge until the workstream is complete.**

## 3. Workstreams

| # | Doc | Workstream | Closes | Depends on |
|---|---|---|---|---|
| 1 | [01_pragya_runtime.md](./01_pragya_runtime.md) | **PRAGYA-RT** — Pragya's own turn loop, the governance seam, the ASR-LLM-TTS voice face, her own number | the four Inc-3 gaps (stage advancement, artifact extraction, deferred reflection, script goldens) | Inc-3 AUTH + PRAGYA |
| 2 | *(charter, doc TBD)* | **CONN** — the §6.6 connector catalog, MCP-first (accounting/bank feed → calendar, e-sign, enrichment, payouts) | **D2** (per-agent credential scoping) | Inc-1 SCH, GOV |
| 3 | *(charter, doc TBD)* | **SOR** — per-object mastering, mirrors, write-back, `sync.conflict` (§21) + HBS module depth (§10.3) | **C2** (human-task step type) | CONN |

## 4. Build Order

**PRAGYA-RT first**, and alone at the start. Its §3 seam decides how *anything* reaches a tool, and CONN's whole job is adding tools. Building connectors against a seam that is about to move would mean writing them twice.

After PRAGYA-RT's seam lands (its T1–T3), CONN and SOR proceed in parallel with the remainder.

## 5. Register Findings — where each closes

| Finding | Workstream | Note |
|---|---|---|
| **D2** per-agent credential scoping | CONN | SoD becomes real here or never — a shared credential defeats the maker/checker split |
| **C2** human-task step type | SOR | physical fulfillment appears with real operations |

PRAGYA-RT closes no register findings — it closes the four **build gaps** Increment 3 recorded honestly in its own build notes ([03 §7.3](../increment-3/02_pragya_v1.md), [04 §8.3](../increment-3/04_voice_realtime.md)).

## 6. Standing Rules (carried forward)

1. **One governance path.** Two orchestrators, one PolicyGate. A second route to a categorised tool is the D1 class of failure rebuilt.
2. **Metered or it doesn't ship.** A Pragya turn that writes no `usage_logs` is free compute the wallet cannot see. The parity suite is the canary.
3. **Anything longer than a turn is delegated, promised, and reported** — the general form of VOICE's promise-don't-complete rule.
4. **Docs move with code** — maturity tags + §N build-note delta logs per workstream on merge.
