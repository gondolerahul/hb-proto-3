"""genui/manifest.py — the manifest service (VG-01's serving half, D4 made real).

**A manifest is a shape.** The build's load-bearing discovery: the first
draft composed from tenant state (which KPIs are measurable, which beacons
exist) — and that would have made the intent-shape cache tenant-dependent,
which D4 §5 forbids for a reason it states exactly ("two tenants asking the
same question get the same composition and different data"). So compositions
here are **pure functions of platform data** — the registry, the KPI
registry, the Wave-0 process table. A district with nothing to show renders
its components' empty states off empty bindings (D4 §7's rule); the shape
does not bend to the data. The corollary: composition needs **no database**,
and the cache can be consulted before any work is done.

Three parts:

* **Validation** (`validate_manifest`) — the service checks its own output
  against the same registry the client validates against, before anything is
  emitted (D3 §7). The rules are D4's: every type resolves (R1), certified
  props exact and non-generative (R2/L5), certified never on the twin plane,
  twin-plane components carry ``honesty_grade`` and a simulation-asserting
  grade carries ``twin_run_id`` (L6), every W manifest names its sheet (L9),
  every binding source is one its component's registry entry declares.
* **Composition** (`compose_manifest`) — heuristic-first over a closed
  surface table; no model for a known shape, which makes the cache the cost
  control (D5 §11). When an LLM composer lands for novel shapes its spend is
  ``CostAttribution.MANIFEST_GENERATION`` (tenant-initiated, registered now).
* **The cache** — Redis, TTL 15 min, D4 §5's key: no tenant, no user, no
  time, no binding values; ``registry.version`` and the entity-def version
  in. An unreachable Redis composes fresh — identical output, only slower.

**The taint rule (VG-23):** a manifest composed from material below
``internal`` on SEGA's ladder may not contain a ``certified.*`` component.
Certified surfaces render from platform-fixed compositions, never from one
that hostile content had a hand in choosing.

V1 surfaces: ``still`` · ``terrace`` (W with its L9 sheet) ·
``terrace.sheet`` · ``district.<code>``. The table grows as SUB/WORLD/DRIVER
consume it; the machine (validate → cache → stream, refusals specified) is
what SEAM ships.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator

from src.ai.evolution.taint_firewall import LADDER
from src.ai.genui.estate import QUARTER_FOR_PROCESS
from src.ai.genui.registry import load_registry, registry_version
from src.ai.kpi.definitions import KPI_DEFINITIONS
from src.common.config import settings

logger = logging.getLogger(__name__)

MANIFEST_TTL_SECONDS = 900
_TAINT_RANK = {level: index for index, level in enumerate(LADDER)}
_CERTIFIED_MIN_TAINT = _TAINT_RANK["internal"]


class ManifestRefused(Exception):
    """Raised when a composition must not be served, with the reason."""


class UnknownSurface(ManifestRefused):
    """No composition rule exists for this surface id — a 404, not a 500."""


# ── validation ────────────────────────────────────────────────────────────────

def _entries_by_type() -> dict[str, dict[str, Any]]:
    return {e["type"]: e for e in load_registry()}


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Every reason this manifest must not be emitted; [] when it may be."""
    problems: list[str] = []
    entries = _entries_by_type()
    plane = manifest.get("plane", "live")
    renderer = manifest.get("renderer")

    if renderer == "W" and not manifest.get("sheet_equivalent"):
        problems.append("a W manifest must name its sheet_equivalent (L9)")

    for component in manifest.get("components", []):
        ref = str(component.get("type", ""))
        bare, _, version = ref.partition("@")
        entry = entries.get(bare)
        if entry is None or (version and int(version) != entry["version"]):
            problems.append(f"{ref}: does not resolve in the registry (R1)")
            continue

        if renderer not in entry["renderers"]:
            problems.append(
                f"{ref}: not renderable in {renderer} "
                f"(renders in {entry['renderers']})")

        if entry["class"] == "certified":
            if plane == "twin":
                problems.append(
                    f"{ref}: certified components may not sit on the twin "
                    "plane (L5)")
            schema = entry["props"]
            declared = set(schema["properties"])
            required = set(schema.get("required", []))
            present = set(component.get("props", {}))
            if missing := required - present:
                problems.append(
                    f"{ref}: missing required props {sorted(missing)}")
            if extra := present - declared:
                problems.append(f"{ref}: undeclared props {sorted(extra)} (L5)")
            if "honesty_grade" in component:
                problems.append(
                    f"{ref}: a certified component carries no honesty_grade (L5)")

        if plane == "twin" and "honesty_grade" not in component:
            problems.append(
                f"{ref}: twin-plane components require honesty_grade (L6)")
        grade = component.get("honesty_grade")
        if grade in ("replay", "forecast", "unknown") and not component.get(
                "twin_run_id"):
            problems.append(
                f"{ref}: honesty_grade={grade} asserts a simulation and "
                "requires twin_run_id (L6)")

        allowed = _binding_sources(entry)
        for binding in component.get("bindings", []):
            source = binding.get("source")
            if allowed is not None and source not in allowed:
                problems.append(
                    f"{ref}: binding source {source!r} is not declared")

    return problems


def _binding_sources(entry: dict[str, Any]) -> set[str] | None:
    """The source enum an entry declares, or None when it declares none."""
    schema = entry.get("bindings")
    if not isinstance(schema, dict):
        return None
    items = schema.get("items")
    if not isinstance(items, dict):
        return None
    enum = items.get("properties", {}).get("source", {}).get("enum")
    return set(enum) if isinstance(enum, list) else None


def enforce_taint(manifest: dict[str, Any], taint: str) -> None:
    """VG-23: below-``internal`` material may not choose a certified surface."""
    if _TAINT_RANK.get(taint, 0) >= _CERTIFIED_MIN_TAINT:
        return
    for component in manifest.get("components", []):
        if str(component.get("type", "")).startswith("certified."):
            raise ManifestRefused(
                f"a manifest composed from {taint!r} material may not emit "
                f"{component['type']} (VG-23)")


# ── composition (pure — no DB, no tenant state) ──────────────────────────────

def compose_manifest(
    surface_id: str,
    *,
    renderer: str,
    density: str = "novice",
    taint: str = "internal",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compose, taint-check, validate — refuse rather than emit a bad one."""
    now = now or datetime.utcnow()

    if surface_id == "still":
        manifest = _still_manifest(renderer)
    elif surface_id == "terrace" and renderer == "W":
        manifest = _terrace_world_manifest()
    elif surface_id in ("terrace", "terrace.sheet"):
        manifest = _terrace_sheet_manifest(renderer)
    elif surface_id.startswith("district.") and surface_id.count(".") == 1:
        manifest = _district_sheet_manifest(surface_id.split(".", 1)[1], renderer)
    else:
        raise UnknownSurface(f"no composition rule for surface {surface_id!r}")

    manifest.update(
        manifest_version=1,
        surface_id=surface_id,
        density=density,
        issued_at=now.isoformat(),
        ttl_seconds=120,
    )
    manifest.setdefault("context_ref", {"kind": "estate", "id": None})
    enforce_taint(manifest, taint)
    problems = validate_manifest(manifest)
    if problems:
        # Refusing our own output is the point: the alternative is a renderer
        # discovering it (D3 §7).
        raise ManifestRefused("; ".join(problems))
    return manifest


def _still_manifest(renderer: str) -> dict[str, Any]:
    return {
        "renderer": "C" if renderer == "C" else "S",
        "plane": "live",
        "depth": 0,
        "layout": {"kind": "stack", "regions": ["line", "pulse"]},
        "components": [
            {
                "id": "c1",
                "type": "narrative.still-line@1",
                "region": "line",
                "props": {"template": "All is well. {raised} hands raised."},
                "bindings": [{"source": "estate.beacon", "params": {}}],
            },
            {
                "id": "c2",
                "type": "primitive.pulse@1",
                "region": "pulse",
                "props": {"label": "The pulse"},
                "bindings": [{"source": "estate.pulse", "params": {}}],
            },
        ],
    }


def _terrace_world_manifest() -> dict[str, Any]:
    """One component per *kind of site*, never per site: the World renderer
    instantiates one district/weather/beacon per bound datum. That is what
    keeps the composition a shape — a tenant with nineteen districts and a
    tenant with six get the same manifest and different territory."""
    return {
        "renderer": "W",
        "plane": "live",
        "depth": 1,
        "layout": {"kind": "world", "regions": ["territory"]},
        "components": [
            {
                "id": "districts",
                "type": "world.district@1",
                "region": "territory",
                "props": {"process_code": "*", "name": "Districts"},
                "bindings": [{"source": "estate.district", "params": {}}],
            },
            {
                "id": "weather",
                "type": "world.weather@1",
                "region": "territory",
                "props": {},
                "bindings": [{"source": "estate.weather", "params": {}}],
            },
            {
                "id": "beacons",
                "type": "world.beacon@1",
                "region": "territory",
                "props": {},
                "bindings": [{"source": "estate.beacon", "params": {}}],
            },
        ],
        "sheet_equivalent": "terrace.sheet",
    }


def _terrace_sheet_manifest(renderer: str) -> dict[str, Any]:
    """The L9 sheet: a dial per registered KPI, an envelope gauge per Wave-0
    process — platform data, so the shape is constant. Unmeasurable KPIs and
    absent envelopes arrive as empty bindings and render as empty states
    with the reason (D4 §7), which is the honest sheet for a young tenant."""
    components: list[dict[str, Any]] = [{
        "id": "c1",
        "type": "narrative.still-line@1",
        "region": "header",
        "props": {"template": "The estate, as a list."},
        "bindings": [{"source": "estate.beacon", "params": {}}],
    }]
    index = 1
    for definition in KPI_DEFINITIONS:
        index += 1
        components.append({
            "id": f"c{index}",
            "type": "primitive.kpi-dial@1",
            "region": "body",
            "props": {"title": definition.display_name,
                      "kpi_key": definition.key},
            "bindings": [{
                "source": "kpi.current",
                "params": {"kpi_key": definition.key},
            }],
        })
    for code in sorted(QUARTER_FOR_PROCESS):
        index += 1
        components.append({
            "id": f"c{index}",
            "type": "primitive.gauge@1",
            "region": "body",
            "props": {"title": f"{code} envelope"},
            "bindings": [{
                "source": "loop.envelope",
                "params": {"process_code": code},
            }],
        })
    return {
        "renderer": "C" if renderer == "C" else "S",
        "plane": "live",
        "depth": 1,
        "layout": {"kind": "stack", "regions": ["header", "body"]},
        "components": components,
    }


def _district_sheet_manifest(code: str, renderer: str) -> dict[str, Any]:
    """Parameterised by the process code alone — the KPI set comes from the
    platform KPI registry's ``owner_process``, so two tenants' district.P06
    manifests are identical and the cache may share them."""
    components: list[dict[str, Any]] = []
    index = 0
    for definition in KPI_DEFINITIONS:
        if definition.owner_process != code:
            continue
        index += 1
        components.append({
            "id": f"c{index}",
            "type": "primitive.kpi-dial@1",
            "region": "plinth",
            "props": {"title": definition.display_name,
                      "kpi_key": definition.key},
            "bindings": [{
                "source": "kpi.current",
                "params": {"kpi_key": definition.key},
            }],
        })
    index += 1
    components.append({
        "id": f"c{index}",
        "type": "primitive.gauge@1",
        "region": "treasury",
        "props": {"title": "Treasury"},
        "bindings": [{
            "source": "loop.envelope", "params": {"process_code": code}}],
    })
    index += 1
    components.append({
        "id": f"c{index}",
        "type": "primitive.timeline@1",
        "region": "activity",
        "props": {"title": "Recent activity"},
        "bindings": [{
            "source": "signals.history", "params": {"process_code": code}}],
    })
    return {
        "renderer": "C" if renderer == "C" else "S",
        "plane": "live",
        "depth": 2,
        "layout": {"kind": "stack",
                   "regions": ["plinth", "treasury", "activity"]},
        "components": components,
        "context_ref": {"kind": "process", "id": code},
    }


# ── the intent-shape cache ───────────────────────────────────────────────────

def intent_shape_key(
    *,
    surface_id: str,
    density: str,
    renderer: str,
    entity_defs_version: int = 0,
) -> str:
    """D4 §5's key for the surface-ask path. Deliberately absent: the tenant,
    the user, the time, every binding value. Deliberately present:
    ``registry.version`` and the entity-def version — the two invalidators
    most likely to be forgotten. The binding-sources term of D4's sketch
    belongs to the *intent* path (where Pragya knows her sources before
    composing); on the surface path the sources are an output, and the
    surface id is the shape."""
    payload = "‖".join([
        "surface", surface_id, density, renderer,
        str(entity_defs_version), registry_version(),
    ])
    return "genui:manifest:" + hashlib.sha256(payload.encode()).hexdigest()


async def cached_compose(
    surface_id: str,
    *,
    renderer: str,
    density: str = "novice",
    taint: str = "internal",
) -> tuple[dict[str, Any], bool]:
    """(manifest, was_cached). Cache first — composition is pure, so a hit
    skips all work; a miss composes, validates and stores. The cache holds
    shapes, never data, so sharing across tenants is safe by construction."""
    key = intent_shape_key(
        surface_id=surface_id, density=density, renderer=renderer)
    client = _redis()
    if client is not None:
        try:
            hit = await client.get(key)
            if hit is not None:
                cached: dict[str, Any] = json.loads(hit)
                cached["issued_at"] = datetime.utcnow().isoformat()
                enforce_taint(cached, taint)
                return cached, True
        except ManifestRefused:
            raise
        except Exception:  # noqa: BLE001 — cache trouble must not block a surface
            logger.warning("genui manifest cache read failed", exc_info=True)

    manifest = compose_manifest(
        surface_id, renderer=renderer, density=density, taint=taint)
    if client is not None:
        try:
            await client.set(key, json.dumps(manifest), ex=MANIFEST_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            logger.warning("genui manifest cache write failed", exc_info=True)
    return manifest, False


def _redis() -> Any | None:
    url = getattr(settings, "REDIS_URL", None)
    if not url:
        return None
    try:
        import redis.asyncio as aioredis

        client: Any = aioredis.from_url(url, decode_responses=True)  # type: ignore[no-untyped-call]
        return client
    except Exception:  # noqa: BLE001
        return None


# ── two-part streaming (D4 §6) ───────────────────────────────────────────────

def split_scaffold(
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Scaffold: identity + layout + component ids/types/regions. Fill: the
    props and bindings per component id. Certified components do not stream —
    they ride whole in the scaffold, or not at all (L5 has no partial mode).
    Component identity is fixed in the scaffold: a fill may only fill."""
    scaffold_components: list[dict[str, Any]] = []
    fill: dict[str, Any] = {}
    for component in manifest["components"]:
        if str(component["type"]).startswith("certified."):
            scaffold_components.append(dict(component))
            continue
        scaffold_components.append({
            "id": component["id"],
            "type": component["type"],
            "region": component.get("region"),
        })
        fill[component["id"]] = {
            "props": component.get("props", {}),
            "bindings": component.get("bindings", []),
        }

    scaffold = {
        key: value for key, value in manifest.items() if key != "components"}
    scaffold["components"] = scaffold_components
    return scaffold, fill


async def stream_manifest(manifest: dict[str, Any]) -> AsyncIterator[str]:
    """NDJSON: line one the scaffold (paintable), line two the fill."""
    scaffold, fill = split_scaffold(manifest)
    yield json.dumps({"part": "scaffold", **scaffold}) + "\n"
    yield json.dumps({"part": "fill", "components": fill}) + "\n"
