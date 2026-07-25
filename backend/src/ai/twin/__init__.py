"""ai/twin — the Glasshouse (Increment 6 / TWIN, VG-09).

> *"Beside the real, there is a glass room."* — Binding Law 3.

Where a consequential change is **tried before it is bet on**: take an idea — a
charter edit, a new agent, a policy change, a pricing move — run it against the
business's own history in an isolated plane, and get back a result that states
how much it should be believed.

The four hard parts, and where each lives:

* **the plane** — `tenant_schema/data_plane.Plane` (T1). A sibling schema, not
  a third backend, so both shipped backends host it unchanged.
* **honesty** — `twin.grading`. A grade is computed from what a run actually
  had; no API accepts one.
* **cost** — `twin.cost`. Charter decision 7 made twin spend *tenant*-initiated,
  so every what-if is visibly the tenant's money.
* **promotion** — `twin.promotion`, which calls **SEGA's** canary rather than
  inventing a second one.

One thing this is not: `POST /ai/signals/{id}/replay` (`signals/api.py`) already
exists and replays a signal into the **live** plane. That is an operational
retry, not a twin — nothing about it is isolated.

Import submodules directly; this init deliberately re-exports nothing (the
VOICE lesson, HANDOFF §5).
"""
