"""genui/registry.py — the component registry, loaded, checked and served.

The registry is the frontend's contract with the manifest service: the service
may only emit component types that resolve here, and the client refuses a
manifest that names one it cannot resolve (D3 §1).

Two copies, one source (D3 §7): the registry is **authored** in
``vihara/src/manifest/registry/*.json`` and **mirrored** into this package's
``registry_data/``. ``scripts/sync_genui_registry.py`` copies; a unit test
fails when the two trees differ, which is the CI gate — a service that
validates manifests against a different registry than the client's discovers
its bugs in a renderer.

The invariants checked at load time are D3 §5's registry-level rules (R2's
certified purity, R3's renderer confinement, R6's golden naming). They raise
at import rather than serve junk: a malformed registry is a deploy error, not
a client-side surprise.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REGISTRY_DIR = Path(__file__).resolve().parent / "registry_data"

CLASSES = ("primitive", "certified", "world", "narrative")

#: R5's server half — the certified ↔ gate correspondence (D3 §3).
#: A component is certified iff it drives a backend endpoint calling
#: ``enforce_tier``/``enforce_kind``, with two named exception families:
#: the two *ceremony* components render the gate's refusal rather than drive
#: a gate, and ``consent`` gates only its raising direction (grant), whose
#: REST surface does not exist yet. The unit test diffs this table against
#: the actual ``enforce_*`` call sites in ``src/ai`` — a new certified
#: endpoint with no component, or a component with no gate, fails CI.
CERTIFIED_GATE_MAP: dict[str, str | None] = {
    "certified.approval": "src/ai/router.py::respond_to_approval",
    "certified.payment": "src/ai/router.py::respond_to_approval",
    "certified.autonomy-change": "src/ai/router.py::update_entity",
    "certified.connector-binding": "src/ai/connectors/router.py::bind",
    "certified.mastering-declaration": "src/ai/connectors/router.py::master_apply",
    "certified.provider-opt-in": "src/ai/intelligence/api.py::provider_opt_in",
    "certified.strategy-resolution": "src/ai/strategy/api.py::adopt",
    # Ceremony components — they *render* the tier gate's refusal.
    "certified.step-up": None,
    "certified.second-channel-wait": None,
    # Asymmetric: ceremony on grant only; no REST grant surface exists yet.
    "certified.consent": None,
}

#: R5's second exception family (DRIVER D3): gates whose certified surface
#: is the **generic step-up ceremony** rather than a component of their own.
#: D6 §7 draws the hall's bulk button opening ``certified.step-up`` — the
#: act carries no domain block to render, so an eleventh component would be
#: an invention the wireframes never asked for. Still derived, still
#: tested: the R5 unit test counts these call sites beside the
#: component-backed ones, so an unlisted ``enforce_*`` site still fails CI.
CEREMONY_ONLY_GATES: tuple[str, ...] = (
    "src/ai/tenant_schema/api.py::bulk_records",
)


def _check_entry(entry: dict[str, Any]) -> None:
    """Registry-level invariants, raised loudly at load (D3 §5)."""
    etype = entry.get("type")
    if not isinstance(etype, str) or "." not in etype:
        raise ValueError(f"registry entry without a class-prefixed type: {entry!r}")
    cls = entry.get("class")
    if cls not in CLASSES:
        raise ValueError(f"{etype}: unknown class {cls!r}")
    if not etype.startswith(f"{cls}."):
        raise ValueError(f"{etype}: type prefix does not match class {cls!r}")
    if not isinstance(entry.get("version"), int):
        raise ValueError(f"{etype}: version must be an integer")

    renderers = entry.get("renderers")
    if not isinstance(renderers, list) or not renderers:
        raise ValueError(f"{etype}: renderers missing")

    if cls == "world" and renderers != ["W"]:
        # R3: world components are confined to the World renderer.
        raise ValueError(f"{etype}: world components render in W only, got {renderers}")
    if cls != "world" and "W" in renderers:
        raise ValueError(f"{etype}: only world components may render in W")

    props = entry.get("props")
    if not isinstance(props, dict):
        raise ValueError(f"{etype}: props schema missing")

    if cls == "certified":
        # R2: certified purity — no undeclared prop is renderable, and no
        # declared prop may be generative.
        if props.get("additionalProperties") is not False:
            raise ValueError(f"{etype}: certified props must set additionalProperties: false")
        if "x-generative" in json.dumps(props):
            raise ValueError(f"{etype}: certified props may not carry x-generative")
        certified = entry.get("certified")
        if not isinstance(certified, dict):
            raise ValueError(f"{etype}: certified block missing")
        goldens = certified.get("goldens")
        # R6: a golden per renderer × density.
        expected = len(renderers) * len(entry.get("density_variants", []))
        if not isinstance(goldens, list) or len(goldens) != expected:
            raise ValueError(
                f"{etype}: expected {expected} goldens (renderer × density), "
                f"got {goldens!r}")
        if etype not in CERTIFIED_GATE_MAP:
            raise ValueError(
                f"{etype}: certified component absent from CERTIFIED_GATE_MAP — "
                "a certified component must name its gate or its exception")


@lru_cache(maxsize=1)
def load_registry() -> tuple[dict[str, Any], ...]:
    """Every entry from every class file, invariant-checked, load-once."""
    entries: list[dict[str, Any]] = []
    for cls in CLASSES:
        path = REGISTRY_DIR / f"{cls}.json"
        with path.open(encoding="utf-8") as fh:
            batch = json.load(fh)
        if not isinstance(batch, list):
            raise ValueError(f"{path.name}: expected a JSON array")
        for entry in batch:
            _check_entry(entry)
            entries.append(entry)

    types = [e["type"] for e in entries]
    if len(types) != len(set(types)):
        dupes = sorted({t for t in types if types.count(t) > 1})
        raise ValueError(f"duplicate registry types: {dupes}")

    mapped = set(CERTIFIED_GATE_MAP)
    present = {t for t in types if t.startswith("certified.")}
    if mapped != present:
        raise ValueError(
            f"CERTIFIED_GATE_MAP and the registry disagree: "
            f"only in map {sorted(mapped - present)}, "
            f"only in registry {sorted(present - mapped)}")
    return tuple(entries)


@lru_cache(maxsize=1)
def registry_version() -> str:
    """A content hash over the canonical registry — the ETag, and the
    ``registry.version`` term of the intent-shape cache key (D4 §5)."""
    canonical = json.dumps(load_registry(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def registry_payload() -> dict[str, Any]:
    """The GET /ai/genui/registry body."""
    return {
        "registry_version": registry_version(),
        "entries": list(load_registry()),
    }
