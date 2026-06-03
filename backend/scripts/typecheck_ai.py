#!/usr/bin/env python3
"""
typecheck_ai.py — Per-package ``mypy --strict`` gate for backend/src/ai.

Strict typing is adopted one package at a time (plan 01, item C12). Each
package that has been made strict-clean is added to ``CLEAN_PACKAGES`` below;
this gate then runs ``mypy --strict`` over exactly those packages and fails CI
if any of them regress. Packages not yet on the list are simply not checked
(whole-tree ``--strict`` is not green yet — ``core/`` alone has ~1190 errors).

``--follow-imports=silent`` is what makes the per-package boundary work: the
allowlisted packages are type-checked strictly, but errors in the modules they
import (the not-yet-clean rest of the tree) are followed for type information
and otherwise suppressed.

Adding a package: make ``mypy --strict --follow-imports=silent
src/ai/<pkg>`` report zero errors, then append ``"<pkg>"`` here.

Legacy-ORM convention (until the ORM is migrated to SQLAlchemy 2.0
``Mapped[]``): models in ``src/ai/orm`` still use the legacy ``Column(...)``
style, so mypy types every attribute as ``Column[T]``. Read access is wrapped
in ``cast(T, instance.attr)``; the handful of attribute *writes* that cannot be
cast carry a narrow ``# type: ignore[assignment]``. Migrating the ORM to
``Mapped[]`` would remove both and is tracked separately.

Run manually:
    python backend/scripts/typecheck_ai.py
Or hooked into CI (see scripts/run_ci_matrix.sh, fast lane).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Packages under src/ai that are strict-clean. Grows one PR at a time (C12).
CLEAN_PACKAGES: list[str] = [
    "governance",
]


def typecheck() -> int:
    if not CLEAN_PACKAGES:
        print("typecheck_ai: no strict packages configured — nothing to check")
        return 0

    targets = [f"src/ai/{pkg}" for pkg in CLEAN_PACKAGES]
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        "--strict",
        "--follow-imports=silent",
        *targets,
    ]
    print(f"typecheck_ai: mypy --strict over {', '.join(CLEAN_PACKAGES)}")
    result = subprocess.run(cmd, cwd=BACKEND_ROOT)
    return result.returncode


if __name__ == "__main__":
    sys.exit(typecheck())
