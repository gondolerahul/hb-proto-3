# Increment 7 / Phase B — GLASS: The Glasshouse Opens (G5)

> **Status:** ✍️ workstream opened 2026-07-29, branch `inc7/glass`.
> **Read first:** [10_workstream_decomposition.md](./10_workstream_decomposition.md) §8 (the scope) · [increment-6/03_twin.md](../increment-6/03_twin.md) §14.7 (the assembly TWIN declared unbuilt — this workstream's first task) · [07_surface_wireframes.md](./07_surface_wireframes.md) §12 (the room) · [04_component_registry.md](./04_component_registry.md) (R5's certified-set rule, which constrains promotion).

---

## 1. What GLASS is, and what the assessment found

The Glasshouse is the plane where a business can rehearse. TWIN (Increment 6) built every piece of it — the sibling schema, materialisation, signal selection, deny-by-default tool substitution, computed-only honesty grading, forecasting, cost estimation, promotion evidence — and then said, in the plainest sentence in the whole road map: *"No scenario runner is wired end-to-end… the pieces are each tested, the assembly is not, and calling it done would be the dishonest version of this row."*

GLASS is that assembly, and then the room over it. Two findings from walking it against the code:

**Finding 1 — the substituted registry has no consumer, and could not have one.** `twin/substitution.py` builds a tool mapping in which every externally-effectful tool is replaced. Nothing accepts that mapping. The shipped executor resolves tools from a **class-level global** (`ToolRegistry.get_tool`, two call sites in `ai/tool_executor.py`), and the record-writing tool opens its tenant session with `tenant_data_plane.session(cid)` — defaulting to `Plane.LIVE`. So a twin run built today would execute *real* tools against the *live* plane while a beautifully tested substitution object sat unused beside it. Two seams are missing, and `agent_loop.py` is pinned at its 1500-line cap, so neither can be a parameter threaded through the loop.

**Finding 2 — the room is assembly, not invention.** SUB and WORLD already authored all five Glasshouse components (`world.glasshouse-pane`, `world.divergence-ribbon`, `primitive.scenario-lever`, `primitive.diff`, `world.ghost`), the manifest schema already carries `plane: "live" | "twin"`, and `--twin-desaturate` / `.vh-desaturated` already exist as **surface-applied** tokens — which is what makes the plane boundary unforgeable, since a component cannot desaturate itself.

**And one constraint that decides the promotion design before it is written:** R5's correspondence rule says a component is certified **iff** a backend endpoint calls `enforce_tier`/`enforce_kind`. The certified set is **ten** and the wireframe's own composition row names `certified.autonomy-change` and `certified.strategy-resolution` for the promotion strip. So promotion must **route into two existing certified acts**, never add an eleventh. See §6.

## 2. § Decisions (locked with Rahul 2026-07-29 — do not re-litigate)

1. **The twin binding is context-scoped.** A contextvar the runner sets for the duration of a run, consulted at the two tool-executor call sites and at the plane resolver. No agent-loop change; the override cannot outlive the run. The cost is accepted knowingly — invisible plumbing on a live hot path — and paid for with mutation tests in both directions (§4).
2. **A scenario runs as an arq job.** A rehearsal should run the way the real thing runs: same queue, same worker, same loop. Heavy work stays off the request path. Stated consequence: the arq worker is a known single point of failure, so a dead worker leaves scenarios queued — visible, not silent.
3. **The promotion chain goes all the way to SEGA's canary** — consume the proposal signal, take it through an existing certified act, hand off to `admit_change` + the entity canary with B11's blast-radius limits visibly holding. This is what VR-01 said G5 consumes and what the exit demo shows.
4. **A wallet hold is drawn before the run** and settled to actuals, released on refusal — closing TWIN's fifth honest limit. An unaffordable scenario refuses *before* spending rather than half-way through.

## 3. The task plan

| X | Task | Where |
|---|---|---|
| X0 | This doc · branch `inc7/glass` | docs |
| X1 | The **binding seam**: `twin/binding.py` + the two executor sites + the plane resolver · mutation-tested both directions | `ai/twin/`, `ai/tool_executor.py`, `ai/tenant_schema/data_plane.py` |
| X2 | The **scenario runner** — the assembly TWIN declared unbuilt: a real `TwinRun` from a real replay | `twin/runner.py` |
| X3 | The **arq job** + the **wallet hold** + `POST /ai/twin/scenarios/{id}/run` | `twin/crons.py`, `twin/api.py` |
| X4 | The **promotion chain** — the proposal consumer → an existing certified act → SEGA's canary | `twin/promotion.py`, `evolution/` |
| X5 | The **Glasshouse surface** — panes, ribbon, levers, shelf, promotion strip | `vihara/src/app/GlasshouseSurface.tsx` |
| X6 | Gates · §Build notes · HANDOFF · merge | docs |

## 4. Design — the binding seam (X1)

**One object, set for the duration of one run, read in three places.**

```python
@dataclass(frozen=True)
class TwinBinding:
    company_id: uuid.UUID
    tools: dict[str, Any]      # the substituted registry
    recorder: CallRecorder
```

`twin_bound(binding)` is an async context manager over a `ContextVar`; `active_binding()` is the reader. Three consumers:

1. **`tool_executor.py`, both `ToolRegistry.get_tool(...)` sites** — through one helper, `binding.resolve_tool(name)`, which returns the substituted tool when a binding is active and the real one otherwise. One helper rather than two inline checks, because two would be two things to keep in step.
2. **The tenant plane resolver** — when a binding is active, the plane is **forced to `TWIN` regardless of the argument passed**. That is the stronger property and the deliberate one: a tool inside a rehearsal cannot opt back into reality by asking for `Plane.LIVE`. It is the plane-level counterpart of substitution's deny-by-default.
3. **The runner itself**, which sets it.

**Why a contextvar and not a parameter.** Because the alternative is threading a flag through `AgentLoop.run` → the executors → the tools, and `agent_loop.py` is at its line cap while the tools are third-party-shaped. A contextvar follows the async task naturally, is reset on exit even when the body raises, and — the property that matters — **cannot be forgotten by a call site that does not know it exists**, which is exactly the failure mode a flag would have.

**Why it must be mutation-tested in both directions.** This is invisible plumbing on a path every live run takes. The tests, each verified to fail on the injected change:

* **No binding → nothing changes.** A live run resolves the real tool and the live plane. (Removing the "no binding" early return must fail this.)
* **Binding → nothing escapes.** Inside a binding, an externally-effectful tool resolves to a `SubstitutedTool` and the session is the twin schema — including when the caller explicitly asks for `Plane.LIVE`.
* **The binding does not leak.** After the context exits — and after it exits *by raising* — resolution is real again.
* **Materialisation still reads reality.** The one legitimate live-plane read inside the twin package runs *outside* any binding; a test pins that ordering, because a materialiser that read the twin plane would copy an empty schema over itself and the failure would look like "the scenario found nothing".

**Concurrency, stated:** contextvars are per-task, so two scenarios and a live run in the same worker process do not see each other's bindings. That is the property being bought.

## 5. Design — the scenario runner (X2/X3)

`twin/runner.py`, one function with a very deliberate order:

1. **Admit** — `cost.admit` (the daily Glasshouse cap, B13-classified tenant spend).
2. **Estimate and hold** — `cost.estimate` → `wallet_holds.place_hold`. Decision 4. A refused hold is a **refused run row**, not an exception thrown at the caller: TWIN's precedent is that refusals are modelled as results, so the shelf shows *why* a rehearsal did not happen.
3. **Materialise** — `materialise(company_id, scope)`, outside any binding (§4).
4. **Build the substituted registry** from the company's real tools + a fresh `CallRecorder`.
5. **Replay** — `replay(db, company_id, scope, handler=...)`, where the handler is the piece that did not exist: for each selected signal it spawns a **twin-marked `ExecutionRun`** (a control-plane row, so the rehearsal is auditable like any run) and executes the *shipped* `AgentLoop` inside `twin_bound(...)`.
6. **Grade** — `grading.grade(GradeInputs(...))` from what the engine observed. Nothing here accepts a grade; TWIN asserts that by reflection and GLASS must not be the module that breaks it.
7. **Write the `TwinRun`** with metrics, cost, grade, and the recorder's counts.
8. **Settle** the hold to actuals.

**The handler is the whole assembly**, and the reason it belongs here rather than in `replay.py` is TWIN's own: *"TWIN selects and counts"* — the dispatcher is shipped, and a second module that knows how to turn a signal into work would be the second place to fix when dispatch changes.

**External effects must be zero, and that is an assertion, not a hope.** The recorder counts them; a run finishing with `external_effects > 0` is a **failed run with a refusal reason**, because it means substitution did not hold and the honest response is to say so loudly rather than to publish a tidy result.

## 6. Design — promotion (X4), and why it adds no certified act

The chain the spec draws is *diff → certified approval → Board build → canary → GA*. Read against R5, that middle step is **not a new gate**:

* A scenario that argues for **more autonomy** promotes through `certified.autonomy-change` → the existing `router.py::update_entity` gate.
* A scenario that argues for a **strategic change** promotes through `certified.strategy-resolution` → the existing `strategy/api.py::adopt` gate.

So GLASS ships **no new `enforce_*` call site**, the certified set stays **ten**, and R5's cross-repo correspondence test exits this workstream byte-identical — the same discipline DRIVER kept when bulk became a ceremony-only gate rather than an eleventh component.

What GLASS *does* add is the **consumer** for `twin.promotion_proposed`, which today is emitted and read by nobody: it turns the proposal into a tray (STEWARD's watcher already delivers trays, so the pocket and the desk both get it for free), carries the evidence card as the approval's context, and on approval hands the change to **SEGA's `admit_change` + entity canary** — where B11's five limits already bite, and where a promotion that violates one is refused by machinery this workstream does not touch.

**The refusal that matters most** is already built: `propose_promotion` refuses an `unknown`-graded run, because *"putting an illustration in front of an owner as though it were evidence trains them to click through the ceremony, which is how a gate stops working."* GLASS's job is to not weaken it.

## 7. Design — the room (X5)

Two panes over one estate read: **REAL** at full saturation, **TWIN** desaturated by the surface (never by the components — the unforgeable property, art bible §5). The **divergence ribbon** and the certified seals are the only saturated things in the twin pane, because the one thing your eye should find in a simulation is what differs from reality.

Four honesty grades render distinctly and `untested` must not read like `unknown` (D4 §3.1): *never tried* and *tried, ungradable* are different facts about a bet. Levers carry their cost inline — twin spend is tenant-initiated (Inc-6 charter decision 6), so a what-if that costs money says so before it is pulled. The Scenario Shelf lists past runs with their grades; the promotion strip renders the diff and opens whichever existing certified ceremony the change belongs to.

## 8. What G5's exit needs that this branch cannot supply

A real tenant with real history, a real scenario replayed against yesterday, and a promotion watched through a staged rollout — the pilot-walkthrough shape of G1's device matrix and G2's business day. Everything else exits at the test level here.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-29 | v1.0 — workstream opened. Four owner decisions locked (§2): context-scoped twin binding · the runner is an arq job · the promotion chain goes all the way to SEGA's canary · a wallet hold is drawn before the run. Two assessment findings recorded before any code: **the substituted registry had no consumer and could not have had one** (the executor reads a class-level global; the record tool defaults to the live plane; the agent loop is line-capped), and **the room is assembly, not invention** (all five components authored, the plane flag and the desaturation token already shipped). One constraint decided the promotion design in advance: R5 keeps the certified set at ten, so promotion **routes into two existing certified acts** rather than adding an eleventh. |
