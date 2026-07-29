"""ai/genui — the seams Vihara reads and writes (Increment 7, SEAM).

The package owns **no domain logic**. Every surface it serves is a projection
over shipped services — the estate read model composes ``loop/``,
``solo_pack/templates``, ``kpi/``, ``signals/``, ``governance/``,
``connectors/``; the tray composer reads the PolicyGate's own snapshot. A read
model that starts computing business truth of its own is a second source of it.

Contracts: docs/product-road-map/increment-7/06_backend_api_contracts.md (D5).
Decomposition: docs/product-road-map/increment-7/10_workstream_decomposition.md §2.

The init re-exports nothing — import submodules directly (the voice_loop
lesson: a package init that imports back toward its own consumers closes
cycles nobody sees until boot).
"""
