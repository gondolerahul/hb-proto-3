"""The gate-containment boundary (Inc-4 PRAGYA-RT T2).

The Inc-4 seam makes two orchestrators share one PolicyGate. That is only safe
while "did we gate this?" has a single answer per orchestrator, so Pragya's
package must have exactly **one** module that can reach a tool.

**Why this is an import test and not a type signature.** The design doc
proposed making ``GateDecision`` a required argument of the shared executor.
Six call sites already exist (``step_executor`` ×4, ``voice``, ``resilience``)
and all of them are gated upstream by ``gate_and_maybe_stop`` inside the
critic pipeline — so threading a parameter through the Solo Pack's revenue
path would be a large change protecting against a risk that is not there.

The risk that *is* there: someone adds a second call site inside
``ai/pragya/`` that skips ``acting.run_tool_calls``. This test makes that a
build failure, with no blast radius outside Pragya's own package.
"""
from __future__ import annotations

import ast
from pathlib import Path

PRAGYA_ROOT = Path(__file__).resolve().parents[2] / "src" / "ai" / "pragya"

#: The one module permitted to reach the shared tool executor.
SANCTIONED_ACTOR = "acting.py"

#: Names that mean "I can run a tool".
EXECUTOR_NAMES = {"ToolExecutor", "execute_from_function_calls", "execute_tools"}


def _modules() -> list[Path]:
    return sorted(p for p in PRAGYA_ROOT.rglob("*.py")
                  if "__pycache__" not in p.parts)


def _imported_names(path: Path) -> set[str]:
    """Every name a module imports, however it imports it."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.rsplit(".", 1)[-1])
    return names


def test_pragya_has_modules_to_check() -> None:
    """Guards the test itself: a moved package must not silently pass."""
    assert PRAGYA_ROOT.is_dir()
    assert len(_modules()) >= 5


def test_only_acting_can_reach_the_tool_executor() -> None:
    """One path from Pragya to a tool, so there is one place to audit."""
    offenders = {
        path.name: sorted(_imported_names(path) & EXECUTOR_NAMES)
        for path in _modules()
        if path.name != SANCTIONED_ACTOR
        and _imported_names(path) & EXECUTOR_NAMES
    }
    assert not offenders, (
        f"these modules can reach a tool without going through "
        f"{SANCTIONED_ACTOR}: {offenders}. Route the call through "
        f"acting.run_tool_calls, which gates it first."
    )


def test_acting_actually_imports_the_shared_executor() -> None:
    """The inverse: if acting stopped using the shared executor, Pragya would
    have grown her own — which the seam forbids."""
    names = _imported_names(PRAGYA_ROOT / SANCTIONED_ACTOR)
    assert "ToolExecutor" in names


def test_acting_gates_through_the_shared_policy_gate() -> None:
    """It must be the platform's gate, not a Pragya-local reimplementation."""
    source = (PRAGYA_ROOT / SANCTIONED_ACTOR).read_text(encoding="utf-8")
    assert "from src.ai.governance.policy_gate import" in source
    assert "evaluate_policy" in source


def test_no_pragya_module_reimplements_the_authority_matrix() -> None:
    """One taxonomy. A local CATEGORY_RULES would be the D1 failure rebuilt."""
    for path in _modules():
        source = path.read_text(encoding="utf-8")
        assert "CATEGORY_RULES: dict" not in source, path.name
        assert "CATEGORY_RULES = {" not in source, path.name
