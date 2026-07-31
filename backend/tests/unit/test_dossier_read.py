"""Inc-7 D8 E3 — the colleague dossier's pure parts, and its door.

The rows are integration-tested (``test_dossier_read_db.py``). What must hold
without a database is everything that could quietly lie to an owner reading
their colleague's terms of engagement:

* a clause exists only where a field carries text, and names the column it
  came from;
* a competency the platform cannot resolve says so, and carries no note;
* the authority block is the **gate's** answer, not a second copy of the
  §9.3 matrix — and where the gate's amount-free answer is conditional, the
  dossier says which;
* nothing anywhere is called a target, because no target exists.

The router test is here too, for the reason the repo learned the hard way:
handlers are called directly, so a scoping rule that lives in a dependency is
a scoping rule nothing tests.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from src.ai.dossier import read as dr
from src.ai.governance.models import HITLCheckpointDef
from src.ai.orm.entity import HierarchicalEntity
from src.ai.tools.base import Tool, ToolRegistry

COMPANY = uuid.uuid4()


def _entity(**kwargs: Any) -> HierarchicalEntity:
    """An in-memory entity. Nothing is defaulted that the read model reads —
    an unset column arrives as ``None``, which is exactly the case the
    projection has to get right."""
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "company_id": COMPANY,
        "name": "agt-038-accounts-receivable",
        "display_name": "Accounts Receivable",
        "type": "AGENT",
        "status": "ACTIVE",
        "version": "1.0.0",
    }
    fields.update(kwargs)
    return HierarchicalEntity(**fields)


class _Registered(Tool):
    name = "email_send"
    description = "Send an email via SMTP."

    async def run(self, input_data: str) -> str:  # pragma: no cover - never called
        return ""


# ── clauses come from columns, and say which column ─────────────────────────

def test_a_clause_exists_only_where_a_field_carries_text():
    entity = _entity(
        goal="Nothing unreconciled for more than seven days.",
        description=None,
        identity={"role": "Accounts Receivable", "system_prompt": "  "},
    )
    clauses = {c["label"]: c for c in dr.charter_clauses(entity)}
    assert set(clauses) == {"Goal", "Role"}
    # A whitespace-only system prompt is an absent clause, not an empty one:
    # "Instructions: —" reads as a renderer bug rather than as an entity that
    # was authored without instructions.
    assert "Instructions" not in clauses
    assert clauses["Goal"]["source"] == "entity.goal"
    assert clauses["Role"]["source"] == "identity.role"


def test_tone_comes_from_the_personality_block_verbatim():
    entity = _entity(identity={"personality": {"tone": "professional"}})
    clauses = {c["label"]: c["value"] for c in dr.charter_clauses(entity)}
    assert clauses == {"Tone": "professional"}


def test_the_default_segregation_class_is_not_a_term_of_engagement():
    """Every entity that was never given a maker/checker role carries
    ``sod_class: "none"``. Printing it would turn a default into a clause the
    owner thinks somebody chose."""
    plain = _entity(governance={"sod_class": "none"})
    assert dr.charter_clauses(plain) == []

    maker = _entity(governance={"sod_class": "maker"})
    assert dr.charter_clauses(maker) == [{
        "label": "Segregation of duties", "value": "maker",
        "source": "governance.sod_class"}]


def test_no_clause_is_invented_for_an_entity_with_no_authored_text():
    assert dr.charter_clauses(_entity()) == []


# ── competencies: the tool list, and what the platform can actually resolve ──

def test_a_tool_the_platform_cannot_resolve_carries_no_note(monkeypatch):
    """The shipped Solo Pack templates name ``send_email``; the registered
    tool is ``email_send``. A dossier that rendered a note for it — or an
    empty one — would hide a live defect behind a tidy row."""
    ToolRegistry.register(_Registered())
    entity = _entity(capabilities={"tools": [
        {"tool_id": "send_email"}, {"tool_id": "email_send"}]})

    by_name = {c["name"]: c for c in dr.competencies(entity, COMPANY)}
    assert by_name["send_email"]["registered"] is False
    assert "note" not in by_name["send_email"]
    assert by_name["email_send"]["registered"] is True
    assert by_name["email_send"]["note"] == _Registered.description


def test_the_shipped_template_still_names_the_unresolvable_tool():
    """Pins the defect the flag reports, so fixing the template (or aliasing
    the tool) is what makes this test change — not a quiet re-render."""
    from src.ai.solo_pack.templates.finance import AGT_038

    named = {t["tool_id"] for t in AGT_038["capabilities"]["tools"]}
    assert "send_email" in named
    assert ToolRegistry.get_tool("send_email") is None


def test_connector_competencies_are_derived_from_the_qualified_name():
    """``mcp__<server>__<verb>`` is the CONN/SOR convention the authority map
    and the taint firewall both key off — so "is this a connector" is read,
    not assigned."""
    entity = _entity(capabilities={"tools": [
        {"tool_id": "mcp__zoho_books__create_invoice"},
        {"tool_id": "tenant_record_write"}]})
    by_name = {c["name"]: c for c in dr.competencies(entity, COMPANY)}
    assert by_name["mcp__zoho_books__create_invoice"]["kind"] == "connector"
    assert by_name["mcp__zoho_books__create_invoice"]["connector_id"] == "zoho_books"
    assert by_name["tenant_record_write"]["kind"] == "tool"
    assert "connector_id" not in by_name["tenant_record_write"]


def test_a_competency_carries_the_category_that_governs_it():
    entity = _entity(capabilities={"tools": [
        {"tool_id": "send_email"}, {"tool_id": "tenant_record_write"}]})
    by_name = {c["name"]: c for c in dr.competencies(entity, COMPANY)}
    assert by_name["send_email"]["category"] == "email_dispatch"
    assert by_name["send_email"]["checkpoint_key"] == (
        "before_high_value_email_dispatch")
    # An uncategorised tool is not an external business effect; the gate never
    # touches it, so the dossier must not imply a checkpoint that never fires.
    assert by_name["tenant_record_write"]["category"] is None
    assert by_name["tenant_record_write"]["checkpoint_key"] is None


def test_a_malformed_tool_list_yields_no_phantom_competencies():
    """Only ``{"tool_id": ...}`` counts — the shape ``step_executor`` resolves.
    A looser read would list a competency the colleague could never call."""
    entity = _entity(capabilities={"tools": [
        {"tool_id": "send_email"}, {"tool_id": "send_email"},
        {"no_tool_id": True}, None, "", "email_send", {"tool_id": "   "}]})
    assert [c["name"] for c in dr.competencies(entity, COMPANY)] == ["send_email"]


def test_an_entity_with_no_capabilities_block_has_no_competencies():
    assert dr.competencies(_entity(), COMPANY) == []


# ── authority: the gate's answer, never a second copy of the matrix ──────────

def _defs() -> dict[str, HITLCheckpointDef]:
    return {"before_refund_above_band": HITLCheckpointDef(
        key="before_refund_above_band", category="refund",
        description="A refund/credit note above the autonomous band.",
        default_threshold=200.0, threshold_unit="usd", platform_mandatory=False,
        sla_seconds=14400, on_timeout="auto_deny")}


def _authority(entity: HierarchicalEntity) -> dict[str, dict[str, Any]]:
    granted = dr.competencies(entity, COMPANY)
    return {a["category"]: a for a in dr.authority_view(entity, granted, _defs())}


def test_at_a1_every_governed_act_needs_a_human_in_the_gates_own_words():
    entity = _entity(
        governance={"autonomy_level": "A1"},
        capabilities={"tools": [{"tool_id": "issue_refund"}]})
    refund = _authority(entity)["refund"]
    assert refund["decision"] == "RAISE_HITL"
    assert refund["reason"] == (
        "A1 (propose) requires human approval of every external effect")
    # Nothing is conditional when the answer is "always a human".
    assert refund["conditional_on_amount"] is False
    assert refund["tools"] == ["issue_refund"]


def test_a_banded_category_at_a2_is_reported_as_conditional_on_the_amount():
    """The gate is asked without an amount, because a dossier describes terms
    and not an act. A flat "autonomous" for refunds would be true only until
    the first large one."""
    entity = _entity(
        governance={"autonomy_level": "A2", "authority": {"refund_usd": 50.0}},
        capabilities={"tools": [{"tool_id": "issue_refund"}]})
    refund = _authority(entity)["refund"]
    assert refund["decision"] == "PASS"
    assert refund["conditional_on_amount"] is True
    # The tenant's tuned band, not the platform default — and it comes back
    # from the gate rather than being read out of the block here.
    assert refund["band"] == 50.0
    assert refund["hard_block"] == 5000.0
    assert refund["unit"] == "usd"


def test_at_a0_the_gate_blocks_and_the_dossier_says_so():
    entity = _entity(
        governance={"autonomy_level": "A0"},
        capabilities={"tools": [{"tool_id": "issue_refund"}]})
    assert _authority(entity)["refund"]["decision"] == "BLOCK"


def test_a_checkpoint_the_registry_has_not_seeded_gets_no_invented_copy():
    """The description, SLA and mandatory flag are the registry row's or
    nothing. A dossier that filled them in would be describing a checkpoint
    the platform may not raise."""
    entity = _entity(
        governance={"autonomy_level": "A1"},
        capabilities={"tools": [
            {"tool_id": "issue_refund"}, {"tool_id": "send_email"}]})
    by_category = _authority(entity)
    assert by_category["refund"]["checkpoint_description"] == (
        "A refund/credit note above the autonomous band.")
    assert by_category["refund"]["sla_seconds"] == 14400
    for key in ("checkpoint_description", "sla_seconds", "on_timeout",
                "platform_mandatory"):
        assert key not in by_category["email_dispatch"]


def test_an_uncategorised_toolset_reaches_no_authority_category():
    entity = _entity(capabilities={"tools": [{"tool_id": "tenant_record_write"}]})
    assert _authority(entity) == {}


def test_a_malformed_governance_block_reads_as_the_cautious_band():
    """One unparseable row must not make the dossier unreadable, and A1 —
    a human approves everything — is the safe way to be wrong."""
    entity = _entity(
        governance={"autonomy_level": "banana"},
        capabilities={"tools": [{"tool_id": "issue_refund"}]})
    assert _authority(entity)["refund"]["decision"] == "RAISE_HITL"


# ── reliability: readings, and nothing called a target ──────────────────────

def test_reliability_names_the_demotion_bar_and_never_a_target():
    block = dr.reliability_block(
        _entity(governance={"timeout_ms": 60000}),
        runs_total=169, runs_failed=27, p95_latency_ms=8123.0)
    assert block["runs_total"] == 169
    assert block["failure_rate"] == pytest.approx(27 / 169)
    assert block["demotion_bar"]["latency_floor_ms"] == 60000.0
    assert "target" not in repr(block)


def test_no_runs_is_no_rate_rather_than_a_perfect_one():
    block = dr.reliability_block(_entity(), runs_total=0, runs_failed=0,
                                 p95_latency_ms=None)
    assert block["failure_rate"] is None
    assert block["p95_latency_ms"] is None
    assert block["demotion_bar"]["latency_floor_ms"] is None


def test_the_reliability_window_is_the_sweeps_own():
    """A dossier measured over a different window from the sweep that acts on
    it would make every demotion look arbitrary."""
    from src.ai.governance.demotion_sweep import WINDOW_DAYS

    block = dr.reliability_block(_entity(), runs_total=1, runs_failed=0,
                                 p95_latency_ms=None)
    assert block["window_days"] == WINDOW_DAYS


# ── the declared absences ───────────────────────────────────────────────────

def test_the_absences_the_platform_owes_the_surface_are_named():
    fields = {item["field"] for item in dr.ABSENT}
    assert {"slos", "probation", "standing"} <= fields
    # Every absence carries its reason — a list of field names would tell the
    # frontend to hide a region without telling anyone why.
    assert all(item["why"].strip() for item in dr.ABSENT)


def test_no_slo_target_exists_to_project():
    """The claim ``ABSENT`` makes about SLOs, pinned against the registry it
    is about: if a KPI ever grows a target, this fails and the absence has to
    be revisited rather than quietly outliving its reason."""
    from src.ai.kpi.definitions import KPI_DEFINITIONS

    assert KPI_DEFINITIONS
    assert not any(hasattr(d, "target") for d in KPI_DEFINITIONS)


def test_no_probationary_period_ships_to_project():
    """``demotion.py`` is the whole of the standing machinery: automatic
    demotion, evidence-gated promotion. Neither is a probation window."""
    from src.ai.governance import demotion

    assert not [name for name in dir(demotion) if "probation" in name.lower()]


# ── the door ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_endpoint_scopes_to_the_session_company(monkeypatch):
    from src.ai.dossier import router as dossier_router

    entity_id = uuid.uuid4()
    seen: dict[str, Any] = {}

    async def fake_view(db: Any, company_id: uuid.UUID,
                        eid: uuid.UUID) -> dict[str, Any]:
        seen["company_id"] = company_id
        seen["entity_id"] = eid
        return {"entity_id": str(eid)}

    monkeypatch.setattr(dossier_router, "dossier_view", fake_view)
    await dossier_router.get_dossier(
        entity_id=entity_id,
        current_user=SimpleNamespace(company_id=COMPANY),
        db=SimpleNamespace())
    assert seen == {"company_id": COMPANY, "entity_id": entity_id}


@pytest.mark.asyncio
async def test_another_tenants_colleague_is_a_404_and_not_a_403(monkeypatch):
    """Unknown and cross-tenant answer alike, so a probe cannot learn that an
    id exists in someone else's estate."""
    from fastapi import HTTPException

    from src.ai.dossier import router as dossier_router

    async def fake_view(db: Any, company_id: uuid.UUID,
                        eid: uuid.UUID) -> dict[str, Any] | None:
        return None

    monkeypatch.setattr(dossier_router, "dossier_view", fake_view)
    with pytest.raises(HTTPException) as raised:
        await dossier_router.get_dossier(
            entity_id=uuid.uuid4(),
            current_user=SimpleNamespace(company_id=COMPANY),
            db=SimpleNamespace())
    assert raised.value.status_code == 404


def test_the_endpoint_takes_no_company_parameter():
    """A cross-tenant read must not be expressible on this surface (D5 §2.2 —
    the VG-05 lesson). The absence is the control, so it is pinned."""
    import inspect

    from src.ai.dossier.router import get_dossier

    params = set(inspect.signature(get_dossier).parameters)
    assert params == {"entity_id", "current_user", "db"}
