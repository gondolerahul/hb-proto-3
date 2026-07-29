"""Capture SEAM's exact manifest wire format for Vihara's tests (SUB T7).

Writes the NDJSON the /ai/genui/manifest route streams — produced by the
same ``compose_manifest`` + ``stream_manifest`` the route wraps, at a
pinned timestamp — into ``vihara/tests/fixtures/``. A vitest parses these
REAL captures through the client's parser and refusal ladder, which is the
cross-language half of the G0 round trip: if either end drifts, one side's
suite goes red.

``tests/unit/test_genui_fixture_export.py`` keeps the capture honest.
Regenerate after any composer change:
    poetry run python scripts/export_genui_fixtures.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TARGET_DIR = BACKEND_ROOT.parent / "vihara" / "tests" / "fixtures"
PINNED_NOW = datetime(2026, 7, 29, 12, 0, 0)

SURFACES: tuple[tuple[str, str, str], ...] = (
    ("still", "S", "still.ndjson"),
    ("terrace.sheet", "S", "terrace_sheet.ndjson"),
    ("terrace", "W", "terrace_world.ndjson"),
    ("district.P06", "S", "district_p06.ndjson"),
)


async def render_fixture(surface: str, renderer: str) -> str:
    from src.ai.genui.manifest import compose_manifest, stream_manifest

    manifest = compose_manifest(
        surface, renderer=renderer, now=PINNED_NOW)
    parts = [part async for part in stream_manifest(manifest)]
    return "".join(parts)


def main() -> int:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    for surface, renderer, filename in SURFACES:
        body = asyncio.run(render_fixture(surface, renderer))
        (TARGET_DIR / filename).write_text(body, encoding="utf-8")
        print(f"captured {surface} ({renderer}) -> {filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
