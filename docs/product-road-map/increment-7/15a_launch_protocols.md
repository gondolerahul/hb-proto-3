# Increment 7 / POLISH P11 — The Launch Protocols (owner-side)

> **Status:** ✍️ written 2026-07-29 (POLISH P11). These are the **run sheets for the legs only a human with devices, users and production can walk**. Everything automatable is already in CI; every row here is owner-side by nature, not by omission. Results write back into [15_polish.md](./15_polish.md) §Build notes.

---

## 1. The zero-training test (spec §10.4 — a G6 exit criterion)

**Premise:** five naive users — non-tech-savvy, never seen the product — each complete six canonical tasks with **no assistance except Pragya**. Pass = all tasks completed, no external help. The estate must be **stage 9** (a finished estate; the test is of living in it, not of building it) with at least two trays waiting, one of them a payment.

**Setup (before any user sits down):**

- [ ] A pilot tenant with the Solo Pack active, real-looking records (not `test test`), and ≥ 2 pending approvals — one payment (T2) among them.
- [ ] A passkey enrolled for the test account (the Study), so the T2 ceremony is a fingerprint, not an enrolment flow mid-task.
- [ ] The observer's rule, said out loud to each user: *"I can't answer questions — but you can ask the assistant anything, by typing or speaking."*
- [ ] Screen + audio recording on; a stopwatch per task.

**The six tasks, verbatim, one card handed over at a time:**

| # | The card says | Completed when | Watch for |
|---|---|---|---|
| 1 | "Tell me how the business is doing this morning." | The user states the still line's content and whether anything needs them | Do they find depth 0's meaning unaided? Does silence read as *well* or as *broken*? |
| 2 | "Something is waiting for your decision. Deal with it." | A tray approved or declined through the ceremony | The beacon → tray path; whether the biometric moment causes fear |
| 3 | "Find the customer record for ⟨seeded name⟩ and correct their phone number." | The edit saved (or proposed, if not the owner) | The halls; whether search-by-walking works without a search bar |
| 4 | "How has ⟨seeded colleague⟩ been doing? Have a look at their work." | The dossier open and one decision inspected | District → colleague → dossier; the org-chart flip |
| 5 | "Ask for an analysis of last month's sales." | An analysis on screen (hall analytics or the steward's answer) | Whether they go to Pragya or hunt menus |
| 6 | "Try out what would happen if you gave your collections agent more freedom — without it being real." | A Glasshouse scenario run (or priced and consciously deferred) | Whether *"without it being real"* maps to the desaturated room |

**Scoring:** per task — completed unaided / completed via Pragya / failed. **Pass requires zero failures across all thirty task-runs.** A failure is a **finding against a surface, never against a user**: record where they were stuck, what they said, what they tried first. Two users failing the same task = one POLISH defect, filed before the parallel run starts.

## 2. The 30-day parallel-run checklist (pilot tenants)

**Doctrine:** Vihara runs **beside** the legacy console, same backend, same tenants; nothing is decommissioned. Cutover (the vhost flip) is a launch decision **outside** the increment, taken only after this run and the owner sign-off.

**Before day 1:**

- [ ] **The push** — `origin/master` is ~60 commits behind; push from a credentialed host (the standing action in HANDOFF §1).
- [ ] Deploy: `vihara.hirebuddha.com` vhost live (deploy/apache), `npm run build` artefacts served, `/api` proxied, cookie-mode auth verified against production (VP-01).
- [ ] Pilot tenants named (2–3), each with an owner who has: a passkey enrolled, the Line installed on their actual phone, push permission granted.
- [ ] The morning job live (02:25 UTC) and the first Morning Story confirmed on a real device; wallet gating observed (a text-degrade on an empty wallet is a **pass**, not a bug).
- [ ] The approval watcher and SSE stream healthy in production logs (`genui watcher` suite green on live PG is necessary, not sufficient).

**Weekly, during the run:**

- [ ] Every act done in Vihara this week is visible in the legacy console (same backend — this checks *belief*, not data), and one act done in legacy surfaces correctly in Vihara.
- [ ] Trays: count delivered vs approved-in-SLA; any tray that reached the WhatsApp last-resort gets a root-cause line.
- [ ] The p75 floors re-read from real-user timings if available; any sustained tier-B demotion offers investigated.
- [ ] Wallet: Vihara-attributed spend (manifests, morning audio, scenarios) within expectations; `tests/parity` stays 16 green on any backend change shipped mid-run.
- [ ] One naive-user task from §1 re-run ad hoc on whoever is available — drift shows up in fresh eyes first.

**Exit:** 30 days · no Sev-1 (a certified act misfiring is Sev-1 by definition) · pilot owners answer *"would you mind if we took the old console away?"* with indifference or relief · owner sign-off recorded in the HANDOFF.

## 3. The real-device matrix run sheet

One sitting, phones on the table. Each row records device, result, and a timing where the row names one.

**G1 (WORLD) — [08](./08_device_matrix.md) §9.3:**
- [ ] The matrix run: tier A desktop, tier B mid-range Android, tier C budget Android (world never loads, sheet first-class), tier D (reduced motion — static frame, full glow beacon).
- [ ] **The walkable look** — the owner walks the territory and judges it against the art bible; the atmosphere (P2/P3) is part of this judgement now: floor behind the still line, GL floor on A/B, 2D floor on C, one-GL-context rule visibly holding at depth 1.

**G3 (STEWARD) — [12](./12_steward.md) §8:**
- [ ] The phone call: dial the shared line, Pragya answers as the tenant's face; barge-in interrupts her mid-sentence.
- [ ] A live browser mic run: hold-to-talk in the dock, VAD closes the turn, the reply narrates to the session.

**G4 (LINE) — [13](./13_line.md) §7:**
- [ ] Android: install from the browser, push arrives **as a tray**, a fingerprint approves a payment end to end.
- [ ] iPhone: the install-first ceiling demonstrated (no push before install — the banner explains it *before* the user hunts).
- [ ] The WhatsApp last resort: kill the socket + revoke push on a test binding, confirm the mirror fires and the morning summary arrives.

**G5 (GLASS) — [14](./14_glass.md) §8:**
- [ ] A real scenario replayed against a real tenant's yesterday; the wallet hold drawn and settled; a promotion taken through the staged rollout with B11's limits visibly holding.

**P8's browser legs (WCAG):**
- [ ] axe browser extension over all 18 surfaces + the Line (contrast now enabled — the computed table covers tokens, not composed backgrounds).
- [ ] A full keyboard walk: every surface reachable, focus visible everywhere including world teleport; the skiplist reaches every district with the canvas ignored.
- [ ] A screen-reader sweep (VoiceOver or NVDA): the still line reads first; weather sentences and icons carry what motion carries.

**P9's device leg (VG-22 — the actual proof):**
- [ ] Chrome DevTools, 4× CPU throttle, Fast-3G, on the tier-B phone: p75 over ≥ 20 loads for — Still first-scaffold (**120ms**), Terrace-W (**300ms**), Terrace-S (**200ms**), district room (300ms), hall (300ms), Tray whole (**250ms**), Undercroft (300ms), Glasshouse (400ms). Record the eight numbers into [15_polish.md](./15_polish.md) §Build notes; a miss is named with its cause, not rounded down.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-29 | v1.0 — written as POLISH P11: the §10.4 test script (six cards, scoring that files failures against surfaces), the 30-day parallel-run checklist (pre-start · weekly · exit), and the one-sitting device run sheet consolidating every owner-side leg the increment left standing (G1 · G3 · G4 · G5 · P8 browser · P9 device). |
