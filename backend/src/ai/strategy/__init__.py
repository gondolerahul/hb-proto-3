"""ai/strategy — the strategy pipeline (Inc 6 / STRAT, closes VG-11).

Notice → Strategize → Decide → Act → Close, as **records in the tenant data
plane** rather than control-plane tables (decision 1). That choice is what
makes the workstream small: the eight Planning objects inherit the record
service, governance, per-tenant schema evolution, SoR mastering, the memory
viewport, export, and Vihara's sheet renderer at no cost. A control-plane
`resolutions` table would have re-implemented most of that list, worse.

Import submodules directly. This init deliberately re-exports nothing — the
same rule VOICE learned when `voice_loop/__init__` re-exporting `identity`
closed an import cycle.
"""
