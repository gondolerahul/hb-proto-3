"""SUB T7 — the wire-fixture gate: the NDJSON captures Vihara's tests parse
must equal what the composer streams today. When this fails, regenerate:

    poetry run python scripts/export_genui_fixtures.py

and commit fixtures + composer change together.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from scripts.export_genui_fixtures import (
    PINNED_NOW,
    SURFACES,
    TARGET_DIR,
    render_fixture,
)

assert PINNED_NOW  # imported for the side of documentation


@pytest.mark.parametrize("surface,renderer,filename", SURFACES)
def test_the_captured_wire_matches_the_composer(surface, renderer, filename):
    captured = Path(TARGET_DIR / filename)
    assert captured.exists(), (
        f"{filename} missing — run scripts/export_genui_fixtures.py")
    assert captured.read_text(encoding="utf-8") == asyncio.run(
        render_fixture(surface, renderer)), (
        f"{filename} drifted from the composer — regenerate and commit both")
