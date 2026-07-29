"""Copy the authored component registry into the backend's served mirror.

The registry is authored in ``vihara/src/manifest/registry/*.json`` and served
from ``backend/src/ai/genui/registry_data/`` (D3 §7 — the manifest service must
validate its own output against the same registry the client validates
against). This script is the "regenerate" half; the "fail on diff" half is
``tests/unit/test_genui_registry.py::test_served_registry_is_byte_identical_to_the_authored_one``.

Run after editing any registry JSON:
    poetry run python scripts/sync_genui_registry.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
AUTHORED = BACKEND_ROOT.parent / "vihara" / "src" / "manifest" / "registry"
SERVED = BACKEND_ROOT / "src" / "ai" / "genui" / "registry_data"


def main() -> int:
    if not AUTHORED.is_dir():
        print(f"authored registry not found at {AUTHORED}", file=sys.stderr)
        return 1
    copied = 0
    for src in sorted(AUTHORED.glob("*.json")):
        shutil.copy2(src, SERVED / src.name)
        copied += 1
    print(f"synced {copied} registry file(s) -> {SERVED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
