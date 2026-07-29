"""SEAM T1 — the component registry: loading, invariants, and R5.

Three families of test, in the order they earn their keep:

* **R5, the certified ↔ gate correspondence** (D3 §3.1): the set of
  ``certified.*`` registry entries must equal the set of ``enforce_tier`` /
  ``enforce_kind`` call sites in ``src/ai`` (plus the named ceremony/asymmetry
  exceptions). This is the one rule that spans the repo boundary — it is why
  the "five certified endpoints" line cannot drift again.
* **The two-copies gate** (D3 §7): the served registry must be byte-identical
  to the authored one in ``vihara/``.
* **Mutation tests of the load-time checker** — each invariant violated one
  at a time, because a checker never observed to fail is a function that
  returns ``True`` (the repo's standing rule for controls).
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ai.genui.registry import (
    CERTIFIED_GATE_MAP,
    REGISTRY_DIR,
    _check_entry,
    load_registry,
    registry_payload,
    registry_version,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
AUTHORED_DIR = BACKEND_ROOT.parent / "vihara" / "src" / "manifest" / "registry"


# ── shape ─────────────────────────────────────────────────────────────────────

def test_registry_loads_the_phase_a_inventory():
    """48 entries: 19 primitive · 10 certified · 13 world · 6 narrative —
    the sum of D3 §6's *named lists*, which is authoritative over its "35 → 45"
    headline (that headline miscounts its own lists by three; correction
    recorded in D3 §9). Every type unique and class-prefixed."""
    entries = load_registry()
    by_class: dict[str, int] = {}
    for e in entries:
        by_class[e["class"]] = by_class.get(e["class"], 0) + 1
    assert by_class == {"primitive": 19, "certified": 10, "world": 13, "narrative": 6}
    types = [e["type"] for e in entries]
    assert len(types) == len(set(types)) == 19 + 10 + 13 + 6

    for e in entries:
        assert e["type"].startswith(e["class"] + ".")


def test_served_registry_is_byte_identical_to_the_authored_one():
    """The CI half of D3 §7: the backend serves a mirror of the registry
    authored in vihara/. A drifted mirror means the manifest service validates
    against a different contract than the client — run
    ``python scripts/sync_genui_registry.py`` and commit both."""
    assert AUTHORED_DIR.is_dir(), f"authored registry missing at {AUTHORED_DIR}"
    authored = sorted(p.name for p in AUTHORED_DIR.glob("*.json"))
    served = sorted(p.name for p in REGISTRY_DIR.glob("*.json"))
    assert authored == served and authored, "registry file sets differ"
    for name in authored:
        assert (AUTHORED_DIR / name).read_bytes() == (REGISTRY_DIR / name).read_bytes(), (
            f"{name} differs between vihara/ and the served mirror — "
            "run scripts/sync_genui_registry.py")


# ── R5: the certified set is derived, not chosen ─────────────────────────────

ENFORCE_CALL = re.compile(r"await enforce_(?:tier|kind)\(")


def _actual_enforce_sites() -> dict[str, int]:
    """Count enforce_* *call* sites per file under src/ai (definitions and the
    guard module itself excluded)."""
    sites: dict[str, int] = {}
    ai_root = BACKEND_ROOT / "src" / "ai"
    for path in ai_root.rglob("*.py"):
        rel = str(path.relative_to(BACKEND_ROOT))
        if rel.endswith("inward_auth/guard.py"):
            continue
        hits = len(ENFORCE_CALL.findall(path.read_text(encoding="utf-8")))
        if hits:
            sites[rel] = hits
    return sites


def test_certified_set_corresponds_to_the_enforce_call_sites():
    """R5. A new ``enforce_tier``/``enforce_kind`` call site with no certified
    component — or a certified component whose gate no longer exists — fails
    here, not in a design review three documents later (D3 §3.3)."""
    declared: dict[str, int] = {}
    for gate in CERTIFIED_GATE_MAP.values():
        if gate is None:
            continue  # ceremony components and the consent asymmetry (D3 §3.2/§3.4)
        file_part = gate.split("::")[0]
        declared[file_part] = declared.get(file_part, 0) + 1
    # approval and payment share one call site (respond_to_approval): collapse.
    declared["src/ai/router.py"] -= 1
    actual = _actual_enforce_sites()
    assert actual == declared, (
        "enforce_* call sites and CERTIFIED_GATE_MAP disagree.\n"
        f"  in code:     {actual}\n"
        f"  in registry: {declared}\n"
        "A new certified endpoint needs a certified component (and its "
        "goldens); a removed one needs its registry entry retired.")


def test_every_certified_entry_is_in_the_gate_map_and_vice_versa():
    present = {e["type"] for e in load_registry() if e["class"] == "certified"}
    assert present == set(CERTIFIED_GATE_MAP)


# ── certified purity and confinement (R2 / R3 / R6), on the real data ────────

def test_certified_props_are_closed_and_non_generative():
    for e in load_registry():
        if e["class"] != "certified":
            continue
        assert e["props"]["additionalProperties"] is False, e["type"]
        assert "x-generative" not in str(e["props"]), e["type"]
        goldens = e["certified"]["goldens"]
        assert len(goldens) == len(e["renderers"]) * len(e["density_variants"]), e["type"]
        assert len(goldens) == len(set(goldens)), e["type"]


def test_world_components_are_confined_to_the_world_renderer():
    for e in load_registry():
        if e["class"] == "world":
            assert e["renderers"] == ["W"], e["type"]
        else:
            assert "W" not in e["renderers"], e["type"]


def test_narrative_templates_carry_no_digits():
    """R7's registry-level half: a narrative entry's props must offer a
    ``template`` slot, and no default/example prose in the schema may contain
    a digit — figures arrive through bindings or they do not arrive."""
    for e in load_registry():
        if e["class"] != "narrative":
            continue
        assert "template" in e["props"]["properties"], e["type"]
        assert not re.search(r"\d", str(e["props"].get("default", ""))), e["type"]


# ── mutation tests: each invariant fails alone ────────────────────────────────

def _minimal_certified() -> dict:
    return {
        "type": "certified.approval",
        "class": "certified",
        "version": 1,
        "renderers": ["S", "C"],
        "density_variants": ["novice", "operator"],
        "props": {"type": "object", "properties": {}, "additionalProperties": False},
        "bindings": {"type": "array"},
        "certified": {"intent_kind": "categorised_action", "gate": "x",
                      "goldens": ["a", "b", "c", "d"]},
    }


def test_checker_refuses_an_open_certified_props_schema():
    entry = _minimal_certified()
    entry["props"]["additionalProperties"] = True
    with pytest.raises(ValueError, match="additionalProperties"):
        _check_entry(entry)


def test_checker_refuses_a_generative_certified_prop():
    entry = _minimal_certified()
    entry["props"]["properties"]["note"] = {"type": "string", "x-generative": True}
    with pytest.raises(ValueError, match="x-generative"):
        _check_entry(entry)


def test_checker_refuses_a_world_component_outside_w():
    entry = _minimal_certified()
    entry.update(type="world.district", **{"class": "world"})
    entry.pop("certified")
    entry["renderers"] = ["S"]
    with pytest.raises(ValueError, match="W only"):
        _check_entry(entry)


def test_checker_refuses_w_on_a_non_world_component():
    entry = _minimal_certified()
    entry["renderers"] = ["S", "W"]
    with pytest.raises(ValueError, match="only world components"):
        _check_entry(entry)


def test_checker_refuses_a_wrong_golden_count():
    entry = _minimal_certified()
    entry["certified"]["goldens"] = ["a", "b"]  # needs renderers × densities = 4
    with pytest.raises(ValueError, match="goldens"):
        _check_entry(entry)


def test_checker_refuses_a_certified_component_with_no_gate_mapping():
    entry = _minimal_certified()
    entry["type"] = "certified.brand-new-thing"
    with pytest.raises(ValueError, match="CERTIFIED_GATE_MAP"):
        _check_entry(entry)


def test_checker_refuses_a_mismatched_class_prefix():
    entry = _minimal_certified()
    entry["type"] = "primitive.approval"
    with pytest.raises(ValueError, match="prefix"):
        _check_entry(entry)


# ── serving ───────────────────────────────────────────────────────────────────

def test_registry_version_is_stable_and_in_the_payload():
    assert registry_version() == registry_version()
    payload = registry_payload()
    assert payload["registry_version"] == registry_version()
    assert len(payload["entries"]) == 48


@pytest.mark.asyncio
async def test_get_registry_pays_a_304_to_a_current_client():
    from src.ai.genui.router import get_registry

    user = SimpleNamespace(id="u", company_id="c")
    full = await get_registry(if_none_match=None, current_user=user)
    assert full.status_code == 200
    etag = full.headers["ETag"]
    cached = await get_registry(if_none_match=etag, current_user=user)
    assert cached.status_code == 304
    assert cached.headers["ETag"] == etag
