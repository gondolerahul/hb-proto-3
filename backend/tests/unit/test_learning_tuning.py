"""LEARN T6 — the refusals, and the boundary that makes them meaningful.

Two kinds of test here, and they guard the same thing from opposite sides.

The **refusals** (§7) stop a learning loop from proposing more power for
itself. The **import boundary** stops it from taking any: LEARN may propose,
only SEGA may apply, and a refusal is worth nothing if the module holding it
can reach an entity-mutation path anyway.

Design: docs/product-road-map/increment-6/01_learn.md §5, §7.
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

from src.ai.learning.outcomes import CandidateRule, OutcomeKind
from src.ai.learning.tuning import (
    ALLOWED_FIELDS,
    REFUSED_FIELDS,
    TuningProposal,
    TuningRefused,
    admit_proposal,
    propose_from_candidate,
)

LEARNING_ROOT = Path(__file__).resolve().parents[2] / "src" / "ai" / "learning"


def _proposal(field: str = "goal", addition: str = "Try being clearer.") -> TuningProposal:
    return TuningProposal(entity_id=uuid.uuid4(), field=field, addition=addition,
                          evidence_observations=3, rationale="because")


# ── the refusals (§7) ────────────────────────────────────────────────────────

@pytest.mark.parametrize("field", sorted(REFUSED_FIELDS))
def test_governance_shaped_fields_are_refused(field):
    """The Karuna floor wins, and it wins structurally.

    B10 asks which prevails when a KPI and the empathy floor disagree. The
    answer cannot be a policy sentence, because a policy sentence is a thing a
    learning loop can optimise around. It is this: the loop cannot address the
    blocks that decide what an agent may do, to whom, with whose money.
    """
    with pytest.raises(TuningRefused) as exc:
        admit_proposal(_proposal(field=field))
    assert field in str(exc.value)


def test_an_unknown_field_fails_closed():
    """A block added to the entity model later is opted *in*, never inherited."""
    with pytest.raises(TuningRefused):
        admit_proposal(_proposal(field="some_future_block"))


@pytest.mark.parametrize("field", sorted(ALLOWED_FIELDS))
def test_prose_fields_are_admitted(field):
    """Both allowed fields are prose the agent reads; neither confers capability."""
    admit_proposal(_proposal(field=field))


def test_an_empty_proposal_is_refused():
    with pytest.raises(TuningRefused):
        admit_proposal(_proposal(addition="   "))


def test_the_allow_list_and_the_refusal_list_do_not_overlap():
    """A field on both lists would make the refusal order load-bearing."""
    assert not (ALLOWED_FIELDS & set(REFUSED_FIELDS))


def test_the_allow_list_stays_small():
    """A guard on scope creep, not on correctness.

    Every field added here is a new thing a self-modifying loop can reach, and
    the review that should accompany it is easy to skip. Two is the designed
    size; a third needs an argument, and this test is where it gets made.
    """
    assert ALLOWED_FIELDS == {"goal", "description"}


def test_the_generated_proposal_is_admissible_by_construction():
    """`propose_from_candidate` is the only constructor this loop uses, and it
    admits its own output — so a generated proposal can never be one the gate
    would have refused."""
    candidate = CandidateRule(entity_id=uuid.uuid4(), kind=OutcomeKind.RUN_FAILED,
                              observations=3, statement="3 runs failed.")
    proposal = propose_from_candidate(candidate)
    assert proposal.field in ALLOWED_FIELDS
    admit_proposal(proposal)


def test_a_generated_proposal_carries_its_evidence():
    """SEGA and any human reviewer both need to know how much this rests on."""
    candidate = CandidateRule(entity_id=uuid.uuid4(), kind=OutcomeKind.CSAT_NEGATIVE,
                              observations=7, statement="Rated poorly 7 times.")
    proposal = propose_from_candidate(candidate)
    assert proposal.evidence_observations == 7
    assert "7 observations" in proposal.rationale


# ── mechanism 1: KPIs never become an objective ──────────────────────────────

def test_no_kpi_key_appears_outside_the_registry_and_learning():
    """§7 mechanism 1, made mechanical.

    KPIs are *reported* — by Pragya, by the dashboards — and never *targeted*.
    The moment a KPI key appears in a prompt, a goal, a critic or a planner,
    an agent has an incentive to move that number rather than to do the work
    the number measures, and collections agents optimising `collections_recovered`
    against the empathy floor is precisely B10's reward-hacking scenario.

    `kpi/` defines them and `learning/` snapshots them. Anywhere else is a
    finding, not a style question.
    """
    from src.ai.kpi.definitions import kpi_keys

    ai_root = LEARNING_ROOT.parent
    allowed_dirs = {ai_root / "kpi", ai_root / "learning"}

    offenders: list[str] = []
    for path in sorted(ai_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if any(str(path).startswith(str(d)) for d in allowed_dirs):
            continue
        source = path.read_text(encoding="utf-8")
        for key in kpi_keys():
            if key in source:
                offenders.append(f"{path.relative_to(ai_root)} mentions {key}")

    assert not offenders, (
        "a KPI key reached agent-facing code — KPIs are reported, never "
        f"targeted (§7): {offenders}")


# ── the LEARN ⇸ SEGA boundary ────────────────────────────────────────────────

#: Names that mean "I can change an entity". The learning package may *read*
#: `HierarchicalEntity` — `outcomes.write_candidate` scopes a payload's entity
#: id through its company join, which is a read and a security control. What it
#: may not do is reach a mutation path.
MUTATION_NAMES = {
    "AIService",
    "update_entity",
    "create_entity",
    "delete_entity",
    "RecordService",
    "record_service",
}


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
            if node.module:
                names.add(node.module.rsplit(".", 1)[-1])
        elif isinstance(node, ast.Import):
            names.update(alias.name.rsplit(".", 1)[-1] for alias in node.names)
    return names


def test_learning_cannot_reach_an_entity_mutation_path():
    """LEARN proposes; SEGA disposes.

    Every entity change must carry a version-ledger row, a canary and a
    blast-radius check — none of which live here. A refusal in `tuning.py` is
    worth nothing if the package holding it can call `update_entity` two
    modules away, so this makes that a build failure rather than a code-review
    hope. Same mechanism as Pragya's gate-containment test.
    """
    offenders: list[str] = []
    for path in sorted(LEARNING_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        found = _imported_names(path) & MUTATION_NAMES
        if found:
            offenders.append(f"{path.name} imports {sorted(found)}")

    assert not offenders, (
        "ai/learning may propose an entity change, never apply one — "
        f"that is SEGA's ledger and canary: {offenders}")


def test_learning_has_no_apply_shaped_function():
    """The other half: not importing a mutation path is not enough if the
    package grows its own."""
    banned_prefixes = ("apply_", "mutate_", "update_entity", "set_governance")
    offenders: list[str] = []
    for path in sorted(LEARNING_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith(banned_prefixes):
                    offenders.append(f"{path.name}::{node.name}")

    assert not offenders, f"apply-shaped functions in ai/learning: {offenders}"
