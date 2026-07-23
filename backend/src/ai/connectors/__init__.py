"""ai.connectors — the §6.6 connector catalog and per-company binding layer.

Increment 4 / CONN. A *connector* is an external system (accounting, bank feed,
calendar, ...) reached through the shipped MCP seam (``ai.tools.mcp``). This
package adds three things the seam did not have on its own:

* a **catalog** (:mod:`.catalog`) — the hand-authored manifest of §6.6
  connectors, the same code-resident-data pattern as ``solo_pack.bundles``;
* **persistence + credentials** for a per-company binding (Increment 4 / CONN
  T2), so a bound server survives a restart and its secret lives in the vault;
* the **SOR** mastering discipline (Increment 4 / SOR) behind the writes those
  connector tools perform — mirror rows, write-back-first, master-wins.

Design + task plan: ``docs/product-road-map/increment-4/02_conn_sor.md``.
The catalog is import-safe and free of I/O; nothing here binds a live server on
import — binding is an explicit, credentialed activation step (T2).
"""
from __future__ import annotations

from src.ai.connectors.catalog import (
    CONNECTOR_CATALOG,
    AuthKind,
    ConnectorBackend,
    ConnectorDef,
    connector_by_id,
    connectors_for_domain,
    connectors_mastering,
)

__all__ = [
    "CONNECTOR_CATALOG",
    "AuthKind",
    "ConnectorBackend",
    "ConnectorDef",
    "connector_by_id",
    "connectors_for_domain",
    "connectors_mastering",
]
