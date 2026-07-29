"""Export the backend's OpenAPI document for Vihara's typed client (D1 §5).

Two clients against one backend drift; the mechanism that stops it:

1. This script writes the canonical ``openapi.json`` into
   ``vihara/src/api/openapi.json`` (checked in).
2. ``tests/unit/test_openapi_export.py`` regenerates the document in memory
   and fails when it differs from the checked-in copy — so a backend
   contract change Vihara has not absorbed is a red build in the same
   commit range, not a runtime 422 three weeks later.
3. ``cd vihara && npm run gen:api`` turns the export into
   ``src/api/schema.d.ts`` (also checked in).

Run after any route/schema change:
    poetry run python scripts/export_openapi.py && cd ../vihara && npm run gen:api
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
TARGET = BACKEND_ROOT.parent / "vihara" / "src" / "api" / "openapi.json"


def canonical_openapi() -> str:
    from src.main import app

    return json.dumps(app.openapi(), sort_keys=True, indent=1) + "\n"


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(canonical_openapi(), encoding="utf-8")
    print(f"exported OpenAPI -> {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
