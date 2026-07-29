# Increment 7 / Phase A — D6: Surface Wireframes

> **Deliverable D6** of [01_phase_a_overview.md](./01_phase_a_overview.md). Spec §5's inventory, drawn.
> **Status:** ✅ **R2 PASSED 2026-07-29.** All seventeen surfaces pass as drawn — the tray, the Terrace's Three-Questions-as-beacons, the dossier-as-one-on-one and the presentation-only density split all accepted (§21). These layouts are now the build reference for G0–G2.
> **Depends on:** [03_art_bible.md](./03_art_bible.md) · [04_component_registry.md](./04_component_registry.md). **Writes back into:** D3 §8 — see §20 here.
> **Visual proof:** [wireframes/spine.html](./wireframes/spine.html) — the spine loop (still surface → terrace → district → tray → approve) at both densities — plus **five high-fidelity visual boards built 2026-07-28, linked into the walkable depth ladder** (each links to the next; ⌘↑/⌘↓ move between levels): [still-visual](./wireframes/still-visual.html) (depth 0) → [estate-visual](./wireframes/estate-visual.html) (depth 1) → [district-visual](./wireframes/district-visual.html) (depth 2) → [glasshouse-visual](./wireframes/glasshouse-visual.html) (depth 2) → [undercroft-visual](./wireframes/undercroft-visual.html) (depth 3). The boards are the **end-state visual reference** — construction language per art bible §13, owner-approved on the first two. The remaining twelve surfaces stay as layouts below; drawing all seventeen in HTML would be building the app, not designing it.

---

## 0. How to read this

Each surface gives: its **depth and renderer**, an **ASCII layout** at operator density, what **novice density changes**, its **composition** (region → component → bindings), its **L9 sheet equivalent** where the renderer is W, and the **echoes** it emits (L10).

Layouts are proportional, not pixel-accurate. Every component named resolves in D3's registry, or appears in §20's delta.

## 1. The shell (every surface at depth ≥ 1 shares it)

Drawn once because it is the same everywhere, and because deciding it once is what stops seventeen surfaces inventing seventeen chromes.

```
┌──────────────────────────────────────────────────────────────────────┐
│  ◦ Northwind Co.            all is well · 2 waiting          ⌘K   ◐  │ ← still line, always
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                        « the surface body »                          │
│                                                                      │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  filtered Invoices to overdue > ₹50k                          undo   │ ← echo ribbon (4s)
└──────────────────────────────────────────────────────────────────────┘
   ▲ depth dial (left rim, hidden until hover/⌘↑↓)      ▲ Pragya presence mark ◐
```

**The shell is app-owned, not manifest-composed.** A manifest composes the *body*; the still line, depth dial, ⌘K palette, echo ribbon and presence mark are the application. This matters more than it looks: it means a malformed or hostile manifest cannot remove the user's way out of a surface, and it keeps the chrome off the manifest schema entirely.

| Element | Behaviour |
|---|---|
| **Still line** | The depth-0 sentence, condensed. Always present, always Pragya's voice, always the same words as depth 0 |
| **Depth dial** | ⌘↑ rises, ⌘↓ descends. Hidden until reached for — the ladder is one axis and should feel like one gesture (art bible §9: 320ms crossfade + 12px rise) |
| **⌘K** | Same parser as Pragya (§6.4). Anything typed here is also an utterance; anything said to her is also a command |
| **Echo ribbon** | L10. 120ms in, 4s dwell, 400ms out. `undo` is the surface's own inverse, itself echoed |
| **Presence mark ◐** | listening / speaking / working / away. Never a face, never a floating avatar — in the territory she is the beam instead |

---

## 2. The Still Surface · depth 0 · S

> **Visual board: [wireframes/still-visual.html](./wireframes/still-visual.html)** — including the zero-gold-at-rest demo toggle.

The default of every session on every device (L1). The only surface with no chrome, because it *is* the chrome.

```
                                                                          
                                                                          
                                                                          
                All is well.                                              
                ₹2.4L collected this week.                                
                Two colleagues are waiting for you.        ← gold, the only gold
                                                                          
                                                          ◦               
                                                     (the pulse, breathing)
                                                                          
```

| | |
|---|---|
| **Composition** | `narrative.still-line` × 1–3 · `primitive.pulse` |
| **Bindings** | `estate.pulse` · `kpi.business` (one figure, chosen by LEARN's morning set) · `trays.count` |
| **Novice** | Three lines, always including the hands-raised line even at zero ("Nothing needs you.") |
| **Operator** | One line; hands-raised becomes a count in the corner |
| **Echoes** | none — reading is not an act |

**The lines are R7 templates.** `"₹{collected} collected this week."` — the figure is a binding, the sentence is a frame. This is the surface where a stale number would do the most damage, because it is the one the owner reads without questioning.

**At zero hands raised, no gold on the screen but the brand mark.** That is the entire design (art bible §2.1 — "almost no gold"; the mark and wordmark are sanctioned, and the board's demo toggle proves the rest goes dark).

---

## 3. The Terrace · depth 1 · W (+S)

> **Visual board: [wireframes/estate-visual.html](./wireframes/estate-visual.html)** — owner-approved 2026-07-28; orbit, zoom, hover, day–night live.

The whole-estate horizon. The Three Questions are beacons *on the map*, not a menu beside it.

```
┌──────────────────────────────────────────────────────────────────────┐
│  ◦ Northwind Co.            all is well · 2 waiting          ⌘K   ◐  │
├──────────────────────────────────────────────────────────────────────┤
│  ╭─ 06:00 ──────────────── now ──────────────── +7d ─╮  ← time scrubber (rim)
│                                                                      │
│         ▲ ghost-lights (what's ahead, beyond the Now)                │
│                                                                      │
│        ◈ beacon                              ◈ beacon                │
│     ╱▔▔▔▔▔╲          ╱▔▔▔▔▔╲          ╱▔▔▔▔▔╲          ╱▔▔▔▔▔╲       │
│    │ Growth│ ═══════ │ Money │ ~~fog~ │ Care  │ ═══════ │ Trust │      │
│     ╲_____╱  traffic  ╲_____╱          ╲_____╱          ╲_____╱       │
│        │                  │                                          │
│      ⌂ gate            ⌂ gate                    ⌂⌂⌂ gatehouses      │
│                                                                      │
│   ⌸ Gallery              ⬡ Glasshouse            ⌷ Library            │
├──────────────────────────────────────────────────────────────────────┤
```

| | |
|---|---|
| **Composition** | `world.district` × n · `world.road` · `world.gatehouse` · `world.beacon` · `world.weather` · `world.time-scrubber` · `world.ghost` |
| **Bindings** | `estate` (one read) · `stream` (beacons, traffic, weather, pulse) |
| **Novice** | Districts labelled with department names, not process codes. Amber trail-lights (*what happened*) are on by default; the scrubber is collapsed to "today" |
| **Operator** | Process codes shown, trail-lights off unless asked, scrubber expanded, keyboard teleport (`⌘K` → district name) |
| **Echoes** | `panned to Money quarter` · `scrubbed to +3d` · `opened Care district` |

**L9 sheet equivalent — `terrace.sheet`:** the same `estate` payload as a list. Quarters as sections, districts as rows carrying name, KPI headline, treasury bar, weather sentence, hands-raised count. Beacons sort to the top. **This is not a fallback view; it is the surface a keyboard user or a low-end device gets, and it must be pleasant to live in** (art bible §11, spec §12.1).

**The three questions in one frame.** *What happened* is the amber trail-lights along today's completed routes; *what needs me* is gold beacons; *what's ahead* is ghost-lights past the Now on the scrubber. Nothing is a tab.

---

## 4. The Tray · any depth · C · **certified**

The only interruption that exists (L2, L8). Anatomy fixed by spec §6.1 and by D5 §4's contract.

```
╭──────────────────────────────────────────────────────────╮
│  PREPARED BY MEERA · COLLECTIONS            ⏱ 3h 26m left │ ← sla-countdown, quiet
├──────────────────────────────────────────────────────────┤
│  Kulkarni Traders crossed 60 days overdue on KT-2291.    │ ← what happened + object link
│                                                          │
│  I'd send the firm reminder we agreed after their last   │ ← recommendation
│  call, and hold the legal language back a cycle.         │
│  ▸ why                                                   │   (expands: the reasoning)
│                                                          │
│  ┌ FORECAST ─────────────────────────────────────────┐   │ ← honesty grade, if twin-informed
│  │ Recovers ₹1.4L/month on 11 weeks of history.      │   │
│  └───────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────┤
│  ◦ CERTIFIED · PAYMENT · T2                              │ ← the certified block starts here
│  Pay ₹84,200 to Kulkarni Traders against KT-2291.        │
│  [ Approve with passkey ]  [ Adjust ]  [ Decline ]       │
├──────────────────────────────────────────────────────────┤
│  Talk to me about it                                     │
╰──────────────────────────────────────────────────────────╯
```

| | |
|---|---|
| **Composition** | `narrative.story-card` (what happened + recommendation) · `primitive.sla-countdown` · **`certified.payment@1`** (or `approval` / `consent` / …) · `primitive.prose` (the talk-to-me affordance) |
| **Bindings** | `trays/{id}` (D5 §4) |
| **Novice** | One recommended path presented, others behind "other options"; `why` expanded by default |
| **Operator** | All paths inline with their costs; `why` collapsed |
| **Echoes** | `approved KT-2291 payout` · `declined …` · `asked about …` — every path echoes, including asking |

Four rules this surface must not break:

1. **The certified block is byte-identical here, on the Line and in a sheet** (L5, D3 R6). Everything above the rule may differ by density; nothing below it may.
2. **The countdown is quiet, never an alarm.** `sla_seconds` surfaces as a number that ticks; it never turns red, never pulses, never sounds. An SLA that shouts converts a considered decision into a rushed one.
3. **A path with no cost shows no cost line** (D5 §4.1). No placeholder, no "—", no estimate.
4. **Certified components do not stream** (D4 §6). The tray's prose may arrive first; the block arrives whole.

---

## 5. District room · depth 2 · W+S

> **Visual board: [wireframes/district-visual.html](./wireframes/district-visual.html)** — owner-approved 2026-07-28.

One Process, entered from its district on the Terrace.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Collections · P08                                    ⌘K   ◐         │
├───────────────────────────────┬──────────────────────────────────────┤
│  ▮▮▮▮▮▯▯  DSO 38d  ↓4         │  Meera        A2   ◈ hand raised     │
│  plinth (KPI)                 │  Ravi         A1     running         │
│                               │  Anjali       A1     idle            │
│  ▰▰▰▰▰▰▱▱ ₹18k / ₹30k         │                                      │
│  treasury · reserve ▮ gold    │  ── live runs ──────────────────     │
│                               │  ▸ chase KT-2291        00:04        │
│  ~~ fog ~~                    │  ▸ reconcile 14 invoices 00:31       │
│  "Below target for 9 days."   │                                      │
├───────────────────────────────┴──────────────────────────────────────┤
│  in ▸ 42 signals/h        out ▸ 37 signals/h        parked ▸ 3       │
└──────────────────────────────────────────────────────────────────────┘
```

| | |
|---|---|
| **Composition** | `world.plinth` · `world.treasury-gauge` · `world.weather` · `world.workplace` × n · `primitive.register` (live runs) · `primitive.figure` × 3 (traffic) |
| **Bindings** | `estate/district/{code}` · `stream` (run state, beacons, envelope burn) |
| **Novice** | Prose header — "Collections is behind. Meera needs you." — then the panels. Traffic hidden |
| **Operator** | Grid as drawn; process code shown; traffic and parked counts inline and clickable into the Undercroft |
| **Echoes** | `opened Meera's dossier` · `paused Ravi` · `opened run 4f2a` |

**L9 sheet equivalent — `district.sheet`:** identical data, vertical stack, no camera. The plinth becomes a KPI row, the treasury a bar, the weather its sentence, colleagues a table with autonomy and state columns.

**The protected reserve is the one gold thing on the treasury gauge** — the seam that never drains (spec §4, art bible §2.1). Everything else on the bar is warm-white.

---

## 6. Colleague dossier / one-on-one · depth 2 · S

```
┌──────────────────────────────────────────────────────────────────────┐
│   ◍  Meera                                  Collections · A2  ◈      │
│      "I chase overdue invoices and escalate when they age past 60."  │
├──────────────────────────────────────────────────────────────────────┤
│  CHARTER            COMPETENCIES        SLO                          │
│  ▸ goal, tone,      ▸ 6 tools           on-time  ▮▮▮▮▮▯ 84%          │
│    escalation       ▸ 2 connectors      accuracy ▮▮▮▮▮▮ 96%          │
├──────────────────────────────────────────────────────────────────────┤
│  RECENT DECISIONS — told, not logged                                 │
│  · Held the Kulkarni reminder back a cycle after their call. ▸ trace  │
│  · Escalated three invoices past 90 days to you on Tuesday.  ▸ trace  │
├──────────────────────────────────────────────────────────────────────┤
│  Tell Meera something                                    [ speak ]   │
└──────────────────────────────────────────────────────────────────────┘
```

| | |
|---|---|
| **Composition** | portrait (art bible §7) · `primitive.prose` · `primitive.record-sheet` (charter) · `primitive.kpi-dial` × 2 · `narrative.story-card` × n · `primitive.trace-viewer` (one flip away) |
| **Bindings** | `entities/{id}` · `executions` · `kpi` · `learning.outcomes` |
| **Novice** | Decisions as stories only; the trace link present but not prominent |
| **Operator** | A `▸ trace` on every line; charter shown as its governance JSON one flip away |
| **Echoes** | `told Meera to hold legal language for a cycle` — **feedback is an echo and an input**: it reaches her charter as a proposal, never as a direct write (SEGA's proposal path) |

**Recent decisions are *told*, not listed.** A dossier that shows a log teaches nothing; a dossier that says what she decided and why is a one-on-one. The trace is one flip away for anyone who wants it — which is the same relationship every narrative surface here has to its data.

---

## 7. Registry Halls · depth 2 · S

Full generated CRUD over `tenant_entity_defs`. One hall per HBS module; the spine is **35 objects** across CRM, Accounting, HRMS, ERP, Legal, Marketing and Planning.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Accounting                         Invoices ▾   saved: Overdue >50k │
├──────────────────────────────────────────────────────────────────────┤
│  ☐  KT-2291   Kulkarni      ₹84,200   62d   ⊛ Zoho    ◧ proposed     │
│  ☐  ST-1180   Sharma        ₹12,400   14d   ⊛ Zoho                   │
│  ☐  NW-0042   Northwind     ₹ 6,900    3d                            │
│         ▲ master's seal ⊛              ▲ tracked change ◧            │
├──────────────────────────────────────────────────────────────────────┤
│  3 selected            [ Bulk… T2 ]        ⇄ flip: analytics / query │
└──────────────────────────────────────────────────────────────────────┘
```

| | |
|---|---|
| **Composition** | `primitive.register` · `primitive.record-sheet` · `primitive.tracked-change` · `primitive.chart-set` (analytics room, one flip) |
| **Bindings** | `tenant-schema/defs` + `/records` (both shipped — the strongest surface that already exists) |
| **Novice** | Fewer columns, prose empty-states, bulk hidden |
| **Operator** | Full grid, column chooser, saved views, keyboard traversal, JSON one flip away |
| **Echoes** | `filtered Invoices to overdue > ₹50k` · `edited KT-2291 due date` · `accepted Meera's proposed change to ST-1180` |

Three properties the record service already guarantees and this surface must **render** rather than re-implement:

* **Owner-writes / others-propose** shows as *editability*: a field another process owns is not disabled, it accepts an edit and files it as a proposal (`◧`). Disabling it would hide the collaboration model.
* **The master's seal `⊛`** marks a per-object SoR-mastered record (Inc-4). Editing it writes back through the bridge and passes the 19th checkpoint.
* **Bulk is T2** — `bulk_data_operation` — so the button opens `certified.step-up`, not a confirm dialog.

**Schema evolution needs no deploy**: a field SEGA proposed and a human approved appears here on the next ask, because `entity_def_version` is in the manifest cache key (D4 §8).

---

## 8. The Boardroom · depth 2 · S (+W setting)

Where STRAT's pipeline becomes a place. **Nothing produces Planning records today** — the objects seed, the rules hold, the API works, and no agent or wizard step creates a Minutes or a Proposition. This surface is that missing producer.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Board · Q3 review                       ◐ Pragya is listening       │
├──────────────────────────────────────────────┬───────────────────────┤
│  She arrives prepared:                       │  MINUTES (live)       │
│  · DSO up 9 days since June                  │  · margin question    │
│  · Care CSAT flat at 4.6                     │  · pricing raised     │
│  · P19 flagged: two lapsed accounts          │                       │
│                                              │                       │
│  ┌ PROPOSITION ──────────────────────────┐   │  ▸ take to Glasshouse │
│  │ Raise chase cadence to every 4 days   │   │                       │
│  │ ◦ UNTESTED — never tried              │   │                       │
│  └───────────────────────────────────────┘   │                       │
├──────────────────────────────────────────────┴───────────────────────┤
│  [ Adopt as Resolution · T2 ]                        ⇄ Planning Hall │
└──────────────────────────────────────────────────────────────────────┘
```

| | |
|---|---|
| **Composition** | `narrative.story-card` (agenda) · `primitive.prose` (live minutes) · `narrative.mandate` · **`certified.strategy-resolution@1`** · `primitive.chart-set` (materialised on request) |
| **Bindings** | `kpi.business` · `kpi.history` · `strategy/*` (shipped) · `twin` (grades, read-only) |
| **Novice** | Conversation-first; propositions appear as she names them |
| **Operator** | Minutes editable inline; the Planning Hall one flip away |
| **Echoes** | `raised a proposition on chase cadence` · `adopted resolution R-14` |

**`UNTESTED` is rendered as its own thing**, never as `unknown` (D4 §3.1). A proposition nobody has simulated must not look like one the Glasshouse could not grade — that distinction is why STRAT added a fourth value, and this is the surface where losing it would matter.

**The honest limit shown as a limit:** taking a proposition to the Glasshouse is drawn, and TWIN's scenario runner is not wired end-to-end. The button exists in the design; whether it is live at G2 or G5 is a build-order question, not a design one.

---

## 9. The Talent Office · depth 2 · S

Brief → shortlist → interview → probation → confirmation.

| | |
|---|---|
| **Layout** | Left: the brief as a conversation. Centre: three to five candidate cards (portrait, charter summary, proposed tools, cost/month). Right: the interview — a scoped Glasshouse session running real past cases against the candidate |
| **Composition** | `narrative.story-card` × n (candidates) · `primitive.diff` (candidate vs existing colleague) · `primitive.trace-viewer` (interview runs) · `certified.autonomy-change@1` (hire lands at A1) |
| **Bindings** | Meta-Agent Board (shipped, 7 roles incl. TestDriver) · `twin` (the interview *is* a twin session) |
| **Novice** | One recommended candidate, others behind "see others" |
| **Operator** | Side-by-side compare, editable charter before hire |
| **Echoes** | `briefed for a collections colleague` · `interviewed candidate 2 against March cases` · `hired Meera at A1` |

**Termination is drawn but not contracted** — VG-18 (no termination workflow; soft-delete only) is explicitly outside D5. The exit-interview and handover-memo flow is designed here and blocked on that gap, which is recorded rather than assumed.

---

## 10. The Standup · depth 1–2 · C sequence

Ninety seconds, one card per colleague, each drillable. On the Line this *is* the Morning Story.

| | |
|---|---|
| **Composition** | `narrative.standup-line` × n, swipe/arrow sequenced |
| **Bindings** | `executions` (yesterday) · `trays` · `kpi.history` (deltas) |
| **Novice** | Auto-advancing with Pragya's voice over each card |
| **Operator** | All lines on one sheet; voice off by default |
| **Echoes** | `opened Ravi's standup line` |

**Relayed by Pragya, never spoken by the colleague** (L2). The card says "prepared by Ravi"; the voice is always hers. One voice is not a stylistic preference — it is what keeps notification discipline enforceable.

---

## 11. The Gallery · depth 2 · S+W

The growth journey: Seasons timeline, monuments, mandates, colleagues past, and the predicted-vs-realized ghost of every promoted experiment.

| | |
|---|---|
| **Composition** | `primitive.timeline` (Seasons) · `world.monument` × n · `narrative.season-marker` · `primitive.diff` (version ledger) · `primitive.chart-set` (predicted vs realized) |
| **Bindings** | `strategy` (resolutions, reviews) · `evolution` version ledger (SEGA) · `kpi.history` · `twin` runs |
| **Novice** | The story: seasons, what changed, what happened after |
| **Operator** | Every version of every entity, diffable |
| **Echoes** | `walked back from mandate M-9 to its resolution` |

**Portraits in the Gallery are desaturated** by the same rule as the twin (art bible §7.2) — the past and the not-yet-real share a material, because neither is currently true.

**The KPI series starts 2026-07-25 with no backfill, by construction.** For roughly a quarter this surface will be honest about having little to show, and it must say so rather than render an empty chart.

---

## 12. The Glasshouse · depth 2 · W+S, desaturated

> **Visual board: [wireframes/glasshouse-visual.html](./wireframes/glasshouse-visual.html)** — real/twin panes, the gold ribbon, all four honesty grades, the promotion strip.

```
┌───────────────────────────────┬──────────────────────────────────────┐
│  REAL                         │  TWIN                     (drained)  │
│   ╱▔▔▔╲   ╱▔▔▔╲               │   ╱▔▔▔╲   ╱▔▔▔╲                      │
│  │Money│ │ Care│              │  │Money│ │ Care│                     │
│   ╲___╱   ╲___╱               │   ╲___╱   ╲___╱                      │
│  DSO 38d                      │  DSO 31d   ◆◆◆ divergence (gold)     │
├───────────────────────────────┴──────────────────────────────────────┤
│  LEVERS   chase cadence ●───────  4d      collectors  ●──  2         │
├──────────────────────────────────────────────────────────────────────┤
│  SHELF  · cadence 4d  FORECAST  · +2 collectors REPLAY  · price +5% UNKNOWN
├──────────────────────────────────────────────────────────────────────┤
│  PROMOTE →  diff → certified approval → Board build → canary → GA     │
└──────────────────────────────────────────────────────────────────────┘
```

| | |
|---|---|
| **Composition** | `world.glasshouse-pane` × 2 · `world.divergence-ribbon` · `primitive.scenario-lever` × n · `narrative.story-card` (shelf) · `primitive.diff` · `certified.autonomy-change` / `certified.strategy-resolution` (promotion) |
| **Bindings** | `twin` (scenarios, runs, grades, forecast) · `evolution` (canary) |
| **Novice** | One lever at a time, the grade in words ("this is a forecast, not a replay") |
| **Operator** | All levers, tournament compare, raw run traces |
| **Echoes** | `tried chase cadence at 4 days` · `promoted scenario S-3 to canary` |

**Everything in this surface is desaturated except the divergence ribbon and the certified seals** (art bible §5). The one thing your eye finds in a simulation is the thing that differs from reality, which is the only reason to be in there.

**Cost is visible and cheap by design** — twin spend is tenant-initiated (charter decision 6), so a running scenario shows its cost, and keeping a what-if cheap (bounded windows, cached baselines, no re-embedding) is a design requirement rather than an optimisation.

---

## 13. The Library · depth 2 · S

```
┌──────────────────────────────────────────────────────────────────────┐
│  Library          uploads · drives · generated · from conversations  │
├───────────────────────────┬──────────────────────────────────────────┤
│  Pricing 2026.pdf         │  PROVENANCE                              │
│  ▸ viewer                 │  uploaded by Rahul · 12 Mar · effective  │
│                           │  from 1 Apr 2026                         │
│                           │  INFLUENCE  ▮▮▮▮▮▯                       │
│                           │  answered 40 questions this month        │
│                           │  cited by Meera, Ravi, Pragya            │
│                           │  ⚠ SUPERSEDED by Pricing 2026-Q3.pdf     │
│                           │  READ BY  Collections, Sales             │
└───────────────────────────┴──────────────────────────────────────────┘
```

| | |
|---|---|
| **Composition** | `primitive.document` · `primitive.provenance` · `primitive.gauge` (influence) · `primitive.citation` · `primitive.register` (collections) |
| **Bindings** | `documents` + LIB's provenance/influence/staleness columns (`lib001`/`lib002`) · retrieval projections (`document_id`, `staleness_state`, `heading_path`, `filename`) |
| **Novice** | Collections and the viewer; influence as a sentence |
| **Operator** | Chunks, embeddings and retrieval traces one flip away (Undercroft) |
| **Echoes** | `opened Pricing 2026.pdf at page 4` · `marked Pricing 2026 superseded` |

**"Answered 40 questions" is `distinct_queries`, not `retrievals`** — LIB shipped a third counter precisely because a row count overstates influence in proportion to how finely the chunker split the document. This surface must bind the counter that matches the sentence it prints.

**Citations open the source at the passage** — the reason retrieval now projects `heading_path` and `chunk_index`.

**Honest limit rendered honestly:** nothing calls `raise_contradiction` yet, so the contradiction flag exists and is always absent. The surface shows staleness (which is live) and does not show a contradiction section until something produces one.

---

## 14. The Bridges & Gates board · depth 2 · S (+W at the estate edge)

| | |
|---|---|
| **Layout** | Two columns. **Bridges** — connected systems of record, each with sync health, master declarations per object, credential expiry, open conflicts. **Gates** — channels and broadcast platforms, each with consent posture, DNC state, volume |
| **Composition** | `primitive.register` × 2 · `certified.connector-binding@1` · `certified.mastering-declaration@1` · `certified.consent@1` · `primitive.diff` (conflict: both versions) |
| **Bindings** | `connectors/{catalog,bindings,status}` (shipped) · consent registry · `social_connections` |
| **Novice** | "What's connected" and "what needs attention" only |
| **Operator** | Full scope and credential audit, per-object mastering table |
| **Echoes** | `connected Zoho Books` · `declared Zoho master of Invoices` · `revoked LinkedIn consent for promotions` |

Two states have designed idioms because they are the ones that actually happen: a **`sync.conflict` is a dispute at the bridge** — a tray with both versions and master-wins as the default — and an **expired credential is a bridge under repair**. `credentials_expire_at` ships and *is never populated*, so the sweep is correct and today always empty; this surface must therefore not imply that a bridge without an expiry date has been checked.

---

## 15. The Undercroft · depth 3 · S, dense

> **Visual board: [wireframes/undercroft-visual.html](./wireframes/undercroft-visual.html)** — including the manifest inspector and the live signal bus.

Everything the platform already exposes, in one place, in mono, at operator density regardless of the learned value (art bible §6).

| | |
|---|---|
| **Contents** | Signals inspector · trigger registry · envelope ledgers · run traces · schema browser · routing attribution · consent/DNC registry · **manifest inspector** · feature flags |
| **Composition** | `primitive.register` × n · `primitive.trace-viewer` · `primitive.diff` · `primitive.chart-set` |
| **Bindings** | `signals/*`, `loop/envelope`, `intelligence/*`, `tenant-schema/defs`, `genui/manifest` — all shipped except the last |
| **Echoes** | every filter and every drill |

**The manifest inspector is a Vihara-specific addition** and it is the one that makes the rest of the product debuggable: it shows the manifest currently rendered, its `intent_shape`, its cache age, and the registry versions it resolved against. Without it, "why did she show me that" has no answer anywhere.

---

## 16–18. The Private Line · C · installable PWA

Three surfaces, one thread (L3).

| Surface | Layout | Composition |
|---|---|---|
| **Thread** | Pragya's thread only — voice notes, cards, certified trays with biometric step-up. No per-agent threads | `narrative.story-card` · `certified.*` · `certified.step-up` |
| **Morning Story** | The Standup, swipeable, her voice over each card | `narrative.standup-line` sequence |
| **Pocket Desk** | Pinned live cards, vitals always on top | `primitive.figure` · `primitive.kpi-dial` · `narrative.still-line` |

| | |
|---|---|
| **Bindings** | `pragya/channel` (WS) · `trays` · `estate` (vitals only) |
| **Push** | Web Push/VAPID; a push is a tray or it does not exist (L8, D5 §7) |
| **Echoes** | Same bus; the Line's echoes carry `renderer: "C"` so density learning does not confuse a phone tap for an operator click |
| **Not on the Line** | Depth 3. The Undercroft is desktop-only, by design |

**WhatsApp read-mirror is read + notify only** (spec §14.3, India-first). Approvals never happen on WhatsApp — certified surfaces exist only in the Line app, because a certified surface needs a channel where step-up is possible.

---

## 19. Onboarding — retired as a surface, staged in the world

Spec §5 marks the wizard *retired* and §15.1 replaces it with the nine-stage engagement staged in the estate itself: empty plot → ghost estate → the Library and Registry Halls filling as documents land → the ghost correcting itself → the first Boardroom session → candidates in the Talent Office → the Bridges flow → construction and rehearsal → **the still surface appearing for the first time**.

No new surfaces: it is the Terrace, the Halls, the Boardroom, the Talent Office and the Bridges board, with `world.ghost` doing the work. The Inc-2 wizard step APIs are already authored as Pragya's stage contract and are driven conversationally.

**The interface earns its silence only after the estate exists.** Depth 0 is the reward at stage 9, not the start screen at stage 1 — which is the one sequencing detail in the whole product that cannot be got wrong without losing the idea.

---

## 20. § Delta — written back into D3 §8

Drawing the surfaces needed **ten components** the registry did not have. Each is listed with the surface that demanded it, so the registry's growth is traceable to a drawn surface rather than to a hunch. Registry: **35 → 45**.

| Component | Class | Demanded by | Why not an existing component |
|---|---|---|---|
| `still-line` | narrative | §2 Still Surface | An R7 template with a strict one-to-three-line contract and the product's only guaranteed-present prose |
| `pulse` | primitive | §2, §3 | Sheel's heartbeat, breathing; not a `figure` (it has no value) and not a `gauge` (it has no scale) |
| `sla-countdown` | primitive | §4 Tray | Its whole specification is what it must *not* do — never red, never pulse, never alarm |
| `tracked-change` | primitive | §7 Halls | Renders others-propose. A `diff` compares two documents; this marks a pending proposal inside a live row |
| `citation` | primitive | §13 Library, Pragya answers | Opens a source *at a passage*; needs `document_id` + `heading_path` + `chunk_index` together |
| `provenance` | primitive | §13 Library | A fixed ten-field shape from `lib001`, not a schema-derived `record-sheet` |
| `scenario-lever` | primitive | §12 Glasshouse | A bounded input that costs money to move; needs its cost estimate inline |
| `time-scrubber` | world | §3 Terrace | Named in spec §3 and absent from §9.2's list |
| `ghost` | world | §3, §19 | Ghost-lights ahead of Now and the onboarding ghost estate are the same component: *hypothesis, visibly not fact* |
| `divergence-ribbon` | world | §12 Glasshouse | Named in spec §11 and absent from §9.2's list |

Two of these — `time-scrubber` and `divergence-ribbon` — are named in the spec's own prose and simply missing from its component list. The other eight are genuine discoveries, and `ghost` is the most consequential: **the onboarding theatre and the "what's ahead" beacons are the same idea**, and building them as two components would have produced two visual languages for *not yet real* in a product whose central honesty law is exactly that distinction.

## 21. What R2 needs from the owner — ✅ PASSED 2026-07-29 (all four judged as drawn)

1. **The tray (§4)** — the most-used surface in the product and the one the zero-training test turns on.
2. **The Terrace (§3)** — whether the Three Questions read as beacons on a map rather than as a menu.
3. **The dossier (§6)** — whether "recent decisions told as stories" reads as a one-on-one or as a log with prose on it.
4. **Density (throughout)** — whether the novice/operator split is presentation-only, as §6.3 requires. If any row above gates *capability*, it is wrong.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-29 | v1.2 — **R2 PASSED.** The owner accepted all four §21 judgments: the tray as drawn, the Terrace's Three Questions reading as beacons, the dossier reading as a one-on-one, and the density split confirmed presentation-only. The same session resolved **VP-03 to The Study** (see D8 §4) — a depth-2 shell-reachable surface to be added to this inventory as the eighteenth surface when the decomposition's owning workstream drafts it. |
| 2026-07-28 | v1.1 — **five visual boards linked in** (see the header and the per-surface pointers): the Still Surface, Terrace, District room, Glasshouse and Undercroft now have end-state interactive boards forming the walkable depth ladder, built to the owner's five inspiration references in the brand palette. The owner approved the territory language on the terrace and district boards 2026-07-28; the other three are built to it and reviewed by the same three-lens adversarial pass. The boards are R2's primary review material alongside the layouts below. |
| 2026-07-28 | v1.0 — all seventeen §5 surfaces drawn at both densities with their L9 equivalents, plus the shell drawn once (and made **app-owned rather than manifest-composed**, so a hostile manifest cannot remove the user's way out). The delta pass added **ten components**, of which two were named in the spec's own prose and missing from its list. The most consequential discovery is `ghost`: the onboarding theatre and the "what's ahead" beacons are the same idea, and building them separately would have produced two visual languages for *not yet real* in a product whose central honesty law is that exact distinction. Three shipped limits are drawn as limits rather than hidden — the unwired scenario runner, the never-populated `credentials_expire_at`, and the KPI series with no backfill. |
