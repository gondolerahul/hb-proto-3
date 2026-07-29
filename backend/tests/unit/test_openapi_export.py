"""SUB T4 — the cross-repo contract gate (D1 §5).

The checked-in ``vihara/src/api/openapi.json`` must equal what the app
serves today. When this fails, the backend contract changed and Vihara has
not absorbed it — run:

    poetry run python scripts/export_openapi.py && cd ../vihara && npm run gen:api

and commit all three artifacts together (the atomic contract+consumer
commit this repo's Inc-4 discipline requires).
"""
from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EXPORTED = BACKEND_ROOT.parent / "vihara" / "src" / "api" / "openapi.json"


def test_the_exported_contract_matches_the_live_app():
    from scripts.export_openapi import canonical_openapi

    assert EXPORTED.exists(), (
        f"{EXPORTED} missing — run scripts/export_openapi.py")
    assert EXPORTED.read_text(encoding="utf-8") == canonical_openapi(), (
        "the backend contract changed and vihara has not absorbed it — "
        "run scripts/export_openapi.py, then `npm run gen:api` in vihara/, "
        "and commit contract + consumer together")
