"""SEAM T2 — the manifest service.

The two properties everything else rests on:

* **Compositions are pure shapes.** No tenant state, no values, byte-stable
  across calls — which is what makes the intent-shape cache shareable across
  tenants by construction rather than by review (D4 §5).
* **The service refuses its own bad output.** Every D4 rule is exercised by
  mutation — one broken manifest per rule, each failing alone — because a
  validator never observed to fail is a function that returns [].
"""
from __future__ import annotations

import json
import re

import pytest

from src.ai.genui import manifest as m


def _compose(surface: str = "still", renderer: str = "S", **kw):
    return m.compose_manifest(surface, renderer=renderer, **kw)


# ── composition ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("surface,renderer", [
    ("still", "S"), ("still", "C"),
    ("terrace", "W"), ("terrace", "S"), ("terrace.sheet", "S"),
    ("district.P06", "S"), ("district.P03", "C"),
])
def test_every_v1_surface_composes_valid(surface, renderer):
    manifest = _compose(surface, renderer)
    assert m.validate_manifest(manifest) == []
    assert manifest["surface_id"] == surface
    assert manifest["components"]


def test_a_w_manifest_names_its_sheet():
    manifest = _compose("terrace", "W")
    assert manifest["sheet_equivalent"] == "terrace.sheet"


def test_composition_is_a_pure_shape():
    """Two calls, identical but for the timestamp — and no digits anywhere in
    a narrative template (R7), no binding values, no tenant anything."""
    first = _compose("terrace", "W")
    second = _compose("terrace", "W")
    first.pop("issued_at"), second.pop("issued_at")
    assert first == second

    for component in _compose("terrace.sheet", "S")["components"]:
        if component["type"].startswith("narrative."):
            assert not re.search(r"\d", component["props"]["template"])


def test_the_terrace_world_composes_kinds_not_sites():
    """One district component with an unparameterised binding — the renderer
    instantiates per datum. A per-site composition would have made the shape
    tenant-dependent and the cache a leak."""
    manifest = _compose("terrace", "W")
    district_components = [
        c for c in manifest["components"] if c["type"] == "world.district@1"]
    assert len(district_components) == 1
    assert district_components[0]["bindings"][0]["params"] == {}


def test_an_unknown_surface_is_a_named_refusal():
    with pytest.raises(m.UnknownSurface):
        _compose("boardroom", "S")
    with pytest.raises(m.UnknownSurface):
        _compose("district.P06.extra", "S")


# ── validation, one mutation per rule ────────────────────────────────────────

def _minimal(renderer: str = "S", **overrides):
    base = {
        "renderer": renderer, "plane": "live", "depth": 0,
        "layout": {"kind": "stack", "regions": ["r"]},
        "components": [],
    }
    base.update(overrides)
    return base


def test_r1_an_unresolvable_type_is_refused():
    bad = _minimal(components=[{"id": "x", "type": "primitive.imaginary@1"}])
    assert any("does not resolve" in p for p in m.validate_manifest(bad))


def test_r1_a_wrong_version_is_refused():
    bad = _minimal(components=[{"id": "x", "type": "primitive.pulse@9"}])
    assert any("does not resolve" in p for p in m.validate_manifest(bad))


def test_r3_a_world_component_outside_w_is_refused():
    bad = _minimal(components=[{"id": "x", "type": "world.district@1",
                                "props": {"process_code": "P03", "name": "x"}}])
    assert any("not renderable in S" in p for p in m.validate_manifest(bad))


def test_l5_certified_never_on_the_twin_plane():
    bad = _minimal(plane="twin", components=[{
        "id": "x", "type": "certified.approval@1",
        "props": {"approval_id": "a", "checkpoint_key": "k",
                  "summary": "s", "tier": "T2"},
        "honesty_grade": "unknown",
    }])
    assert any("twin plane (L5)" in p for p in m.validate_manifest(bad))


def test_l5_an_undeclared_certified_prop_is_refused():
    bad = _minimal(components=[{
        "id": "x", "type": "certified.approval@1",
        "props": {"approval_id": "a", "checkpoint_key": "k",
                  "summary": "s", "tier": "T2", "injected": "!"},
    }])
    assert any("undeclared props" in p for p in m.validate_manifest(bad))


def test_l5_a_missing_certified_prop_is_refused():
    bad = _minimal(components=[{
        "id": "x", "type": "certified.approval@1",
        "props": {"approval_id": "a"},
    }])
    assert any("missing required props" in p for p in m.validate_manifest(bad))


def test_l5_a_certified_component_carries_no_grade():
    bad = _minimal(components=[{
        "id": "x", "type": "certified.approval@1",
        "props": {"approval_id": "a", "checkpoint_key": "k",
                  "summary": "s", "tier": "T2"},
        "honesty_grade": "replay", "twin_run_id": "r1",
    }])
    assert any("carries no honesty_grade" in p for p in m.validate_manifest(bad))


def test_l6_twin_plane_requires_a_grade():
    bad = _minimal(plane="twin", components=[{
        "id": "x", "type": "primitive.pulse@1", "props": {},
    }])
    assert any("require honesty_grade" in p for p in m.validate_manifest(bad))


def test_l6_a_simulation_grade_requires_a_run_id():
    for grade in ("replay", "forecast", "unknown"):
        bad = _minimal(plane="twin", components=[{
            "id": "x", "type": "primitive.pulse@1", "props": {},
            "honesty_grade": grade,
        }])
        assert any("requires twin_run_id" in p
                   for p in m.validate_manifest(bad)), grade


def test_l6_untested_needs_no_run_id():
    """The fourth grade: *never tried* is the one honest claim that needs no
    run behind it (D4 §3.1)."""
    ok = _minimal(plane="twin", components=[{
        "id": "x", "type": "primitive.pulse@1", "props": {},
        "honesty_grade": "untested",
        "bindings": [{"source": "estate.pulse", "params": {}}],
    }])
    assert m.validate_manifest(ok) == []


def test_l9_a_w_manifest_without_a_sheet_is_refused():
    bad = _minimal(renderer="W")
    assert any("sheet_equivalent (L9)" in p for p in m.validate_manifest(bad))


def test_an_undeclared_binding_source_is_refused():
    bad = _minimal(components=[{
        "id": "x", "type": "primitive.pulse@1", "props": {},
        "bindings": [{"source": "billing.wallet", "params": {}}],
    }])
    assert any("not declared" in p for p in m.validate_manifest(bad))


# ── taint (VG-23) ─────────────────────────────────────────────────────────────

def _with_certified():
    return _minimal(components=[{
        "id": "x", "type": "certified.approval@1",
        "props": {"approval_id": "a", "checkpoint_key": "k",
                  "summary": "s", "tier": "T2"},
    }])


def test_below_internal_material_may_not_choose_a_certified_surface():
    for taint in ("counterparty", "external_verified"):
        with pytest.raises(m.ManifestRefused, match="VG-23"):
            m.enforce_taint(_with_certified(), taint)


def test_internal_material_may():
    m.enforce_taint(_with_certified(), "internal")
    m.enforce_taint(_with_certified(), "platform")


def test_tainted_material_without_certified_passes():
    m.enforce_taint(_minimal(), "counterparty")


# ── streaming (D4 §6) ─────────────────────────────────────────────────────────

def test_scaffold_fixes_identity_and_fill_only_fills():
    manifest = _compose("district.P06", "S")
    scaffold, fill = m.split_scaffold(manifest)
    scaffold_ids = [c["id"] for c in scaffold["components"]]
    assert scaffold_ids == [c["id"] for c in manifest["components"]]
    for skeleton in scaffold["components"]:
        assert set(skeleton) == {"id", "type", "region"}
    assert set(fill) == set(scaffold_ids)


def test_certified_components_ride_whole_in_the_scaffold():
    manifest = _with_certified()
    scaffold, fill = m.split_scaffold(manifest)
    assert scaffold["components"][0]["props"]["summary"] == "s"
    assert fill == {}


@pytest.mark.asyncio
async def test_the_stream_is_two_parseable_lines():
    manifest = _compose("still", "S")
    lines = [line async for line in m.stream_manifest(manifest)]
    assert len(lines) == 2
    scaffold, fill = (json.loads(line) for line in lines)
    assert scaffold["part"] == "scaffold" and fill["part"] == "fill"
    assert scaffold["surface_id"] == "still"


# ── the cache ─────────────────────────────────────────────────────────────────

class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


@pytest.mark.asyncio
async def test_the_second_ask_is_a_cache_hit(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(m, "_redis", lambda: fake)
    first, hit1 = await m.cached_compose("still", renderer="S")
    second, hit2 = await m.cached_compose("still", renderer="S")
    assert (hit1, hit2) == (False, True)
    first.pop("issued_at"), second.pop("issued_at")
    assert first == second


@pytest.mark.asyncio
async def test_density_and_renderer_shape_the_key(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(m, "_redis", lambda: fake)
    await m.cached_compose("still", renderer="S", density="novice")
    _, hit = await m.cached_compose("still", renderer="C", density="operator")
    assert hit is False
    assert len(fake.store) == 2


@pytest.mark.asyncio
async def test_taint_is_enforced_on_a_cache_hit_too(monkeypatch):
    """A cached certified composition must not be served to a tainted ask —
    the check runs on the hit path, not only at compose time."""
    fake = FakeRedis()
    monkeypatch.setattr(m, "_redis", lambda: fake)
    key = m.intent_shape_key(surface_id="s", density="novice", renderer="S")
    fake.store[key] = json.dumps(_with_certified())

    with pytest.raises(m.ManifestRefused, match="VG-23"):
        await m.cached_compose("s", renderer="S", taint="counterparty")


@pytest.mark.asyncio
async def test_no_redis_means_fresh_composition_not_failure(monkeypatch):
    monkeypatch.setattr(m, "_redis", lambda: None)
    manifest, hit = await m.cached_compose("still", renderer="S")
    assert hit is False and manifest["surface_id"] == "still"
