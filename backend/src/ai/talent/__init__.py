"""ai/talent — colleague lifecycle beyond hiring (DRIVER D7, VG-18).

Hiring already exists (entity creation + the Meta-Agent Board); what this
package owns is the other end: **termination as a workflow** — the exit
interview summary, the handover memo filed as an artifact, the refusal
over live runs, the Gallery stamp — over the shipped soft-delete.

Owner decision (11_driver.md §2.3): termination is a **plain governed
act**, not a certified one. Stopping an agent must never be harder than
hiring one — the same principle that leaves autonomy-lowering and
consent-revocation ungated. Nothing in this package may call
``enforce_tier``/``enforce_kind``; R5's correspondence test counts those
call sites and this package deliberately adds none.
"""
