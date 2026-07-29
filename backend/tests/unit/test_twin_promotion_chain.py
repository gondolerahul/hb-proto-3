"""GLASS X4 — the promotion chain, and the gates it deliberately reuses.

The properties that matter: no eleventh certified act (R5 stays green),
the checkpoint is the one that already fits, applying is a **sweep**, and
SEGA's refusal is recorded where the approver will read it rather than
swallowed.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.ai.twin import promotion_chain as pc


class FakeDB:
    def __init__(self, rows=None):
        self.added: list = []
        self.rows = rows or []
        self.commits = 0

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        for row in self.added:
            if getattr(row, "id", None) is None:
                row.id = uuid.uuid4()

    async def commit(self):
        self.commits += 1

    async def execute(self, *a, **kw):
        rows = self.rows

        class Result:
            def all(self_inner):
                return rows

        return Result()


def _evidence():
    return SimpleNamespace(
        run_id=uuid.uuid4(),
        grade="replay",
        as_card=lambda: {"source": "glasshouse", "grade": "replay"},
    )


def _approval(promotion: dict, status: str = "APPROVED"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        checkpoint_key=pc.PROMOTION_CHECKPOINT,
        status=status,
        responded_at=None,
        context_snapshot={"twin_promotion": promotion},
    )


# ── the card ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_promotion_raises_a_card_on_the_existing_checkpoint():
    db = FakeDB()
    entity_id = uuid.uuid4()
    approval = await pc.raise_promotion_approval(
        db, company_id=uuid.uuid4(), entity_id=entity_id,
        evidence=_evidence(), field="charter", addition="chase at 4 days")

    assert approval.checkpoint_key == "before_self_evolving_code_promotion"
    assert approval.status == "PENDING"
    promotion = approval.context_snapshot["twin_promotion"]
    assert promotion["entity_id"] == str(entity_id)
    assert promotion["addition"] == "chase at 4 days"
    assert promotion["applied_version_id"] is None
    # The evidence — and its caveat — travel onto the card.
    assert promotion["evidence"]["source"] == "glasshouse"


@pytest.mark.asyncio
async def test_the_anchor_run_is_the_entitys_own():
    """A promotion is *about* an entity, so its run row is that entity's —
    not one borrowed arbitrarily from the replay."""
    db = FakeDB()
    entity_id = uuid.uuid4()
    await pc.raise_promotion_approval(
        db, company_id=uuid.uuid4(), entity_id=entity_id,
        evidence=_evidence(), field="charter", addition="x")
    run = db.added[0]
    assert run.entity_id == entity_id
    assert run.input_data["channel"] == "twin_promotion"


# ── the sweep ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_approved_promotion_is_applied_through_sega(monkeypatch):
    entity_id = uuid.uuid4()
    company_id = uuid.uuid4()
    version_id = uuid.uuid4()
    seen: dict = {}

    async def fake_apply(db, *, company_id, entity_id, field, addition, now=None):
        seen.update(company_id=company_id, entity_id=entity_id,
                    field=field, addition=addition)
        return SimpleNamespace(id=version_id)

    import src.ai.evolution.proposals as proposals

    monkeypatch.setattr(proposals, "apply_proposal", fake_apply)

    approval = _approval({
        "entity_id": str(entity_id), "field": "charter",
        "addition": "chase at 4 days", "applied_version_id": None})
    out = await pc.apply_approved_promotions(FakeDB([(approval, company_id)]))

    assert out == {"applied": 1, "refused": 0}
    assert seen["entity_id"] == entity_id
    assert seen["addition"] == "chase at 4 days"
    stamped = approval.context_snapshot["twin_promotion"]
    assert stamped["applied_version_id"] == str(version_id)


@pytest.mark.asyncio
async def test_a_blast_radius_refusal_is_recorded_where_the_approver_reads_it(
        monkeypatch):
    from src.ai.evolution.blast_radius import BlastRadiusError

    async def refuse(db, **kwargs):
        raise BlastRadiusError("refusing a cross-tenant automated change")

    import src.ai.evolution.proposals as proposals

    monkeypatch.setattr(proposals, "apply_proposal", refuse)

    approval = _approval({
        "entity_id": str(uuid.uuid4()), "field": "charter",
        "addition": "x", "applied_version_id": None})
    out = await pc.apply_approved_promotions(FakeDB([(approval, uuid.uuid4())]))

    assert out == {"applied": 0, "refused": 1}
    assert "cross-tenant" in (
        approval.context_snapshot["twin_promotion"]["refused_because"])


@pytest.mark.asyncio
async def test_an_already_applied_promotion_is_not_applied_twice(monkeypatch):
    calls: list = []

    async def fake_apply(db, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4())

    import src.ai.evolution.proposals as proposals

    monkeypatch.setattr(proposals, "apply_proposal", fake_apply)

    approval = _approval({
        "entity_id": str(uuid.uuid4()), "field": "charter",
        "addition": "x", "applied_version_id": str(uuid.uuid4())})
    out = await pc.apply_approved_promotions(FakeDB([(approval, uuid.uuid4())]))
    assert out == {"applied": 0, "refused": 0}
    assert calls == []


@pytest.mark.asyncio
async def test_an_approval_of_some_other_governance_act_is_left_alone(
        monkeypatch):
    """The checkpoint is shared with self-evolving code promotion, so the
    sweep must claim only cards carrying a twin promotion."""
    calls: list = []

    async def fake_apply(db, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4())

    import src.ai.evolution.proposals as proposals

    monkeypatch.setattr(proposals, "apply_proposal", fake_apply)

    other = SimpleNamespace(
        id=uuid.uuid4(), checkpoint_key=pc.PROMOTION_CHECKPOINT,
        status="APPROVED", responded_at=None,
        context_snapshot={"category": "governance"})
    out = await pc.apply_approved_promotions(FakeDB([(other, uuid.uuid4())]))
    assert out == {"applied": 0, "refused": 0}
    assert calls == []


# ── R5: the certified set does not grow ──────────────────────────────────────

def test_glass_adds_no_eleventh_certified_gate():
    """GLASS routes promotion through the certified act that already
    exists (``respond_to_approval``). If this workstream ever adds an
    ``enforce_*`` call site, R5's correspondence test fails — this one
    fails first, and says why.

    Pinned by **AST, not by string match**: this test caught its own
    docstring on the first run, which is the same trap SEAM's two
    tripwire tests fell into. A call is a call node.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "ai" / "twin"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        } | {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not ({"enforce_tier", "enforce_kind"} & called), (
            f"{path.name} calls a tier gate — the Glasshouse promotes through "
            "the existing certified approval, and the certified set stays ten "
            "(R5, 14_glass.md §6)")
