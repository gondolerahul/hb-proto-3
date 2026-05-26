"""
Unit tests for src.ai.planner_service
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.ai.planning.planner_service import PlannerService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    return PlannerService(mock_db, company_id=uuid4())


class TestReconcile:

    @pytest.mark.asyncio
    async def test_reconcile_static_plan(self, service):
        """Should return static plan when dynamic is disabled."""
        entity = MagicMock()
        entity.planning = {
            "static_plan": {
                "steps": [
                    {"name": "step_1", "type": "THOUGHT", "description": "Think"},
                    {"name": "step_2", "type": "TOOL_CALL", "description": "Call tool"},
                ]
            },
            "dynamic_planning": {"enabled": False},
        }
        entity.type = "AGENT"
        entity.identity = {"system_prompt": "You are helpful."}
        run = MagicMock()
        run.id = uuid4()

        result = await service.reconcile(run, entity, {"input": "test"})
        assert "steps" in result
        assert len(result["steps"]) == 2

    @pytest.mark.asyncio
    async def test_reconcile_empty_plan_generates_default_for_action(self, service):
        """Should add a default step for ACTION entities with no steps."""
        entity = MagicMock()
        entity.planning = {
            "static_plan": {"steps": []},
            "dynamic_planning": {"enabled": False},
        }
        entity.type = "ACTION"
        entity.name = "TestAction"
        entity.description = "Do something"
        run = MagicMock()

        result = await service.reconcile(run, entity, {})
        assert len(result["steps"]) == 1
        assert result["steps"][0]["name"] == "Execute"


class TestHasParallelSteps:

    def test_independent_steps_returns_true(self, service):
        """Independent steps without dependencies can run in parallel."""
        steps = [
            {"step_id": "s1", "name": "a", "target": {}},
            {"step_id": "s2", "name": "b", "target": {}},
        ]
        # Both steps are immediately ready, so genuine parallelism exists
        assert service.has_parallel_steps(steps) is True

    def test_sequential_chain_returns_false(self, service):
        """A purely sequential chain cannot run steps in parallel initially."""
        steps = [
            {"step_id": "s1", "name": "a", "target": {}},
            {"step_id": "s2", "name": "b", "target": {"input_dependencies": ["s1"]}},
        ]
        # Only s1 is initially ready, so no initial parallelism
        assert service.has_parallel_steps(steps) is False

    def test_genuine_parallelism_with_deps_returns_true(self, service):
        """Should return True when multiple independent starting waves exist."""
        steps = [
            {"step_id": "s1", "name": "a", "target": {}},
            {"step_id": "s2", "name": "b", "target": {}},
            {"step_id": "s3", "name": "c", "target": {"input_dependencies": ["s1"]}},
        ]
        # s1 and s2 are both initially ready, so returns True
        assert service.has_parallel_steps(steps) is True



class TestValidateGoalProgress:

    @pytest.mark.asyncio
    async def test_validate_goal_success(self, service):
        """Should return parsed score from LLM."""
        mock_resp = MagicMock()
        mock_resp.output = '{"score": 90, "reasoning": "Goal achieved", "goal_achieved": true}'
        with patch.object(service.llm, 'call_llm', AsyncMock(return_value=mock_resp)):
            result = await service.validate_goal_progress(
                goal="Summarize the document",
                completed_steps=[{"name": "analyze", "output": "Summary complete."}],
                total_steps=2,
            )
            assert result["score"] == 90
            assert result["goal_achieved"] is True

    @pytest.mark.asyncio
    async def test_validate_goal_failure_returns_default(self, service):
        """Should return default score on LLM failure."""
        with patch.object(service.llm, 'call_llm',
                          AsyncMock(side_effect=RuntimeError("LLM down"))):
            result = await service.validate_goal_progress(
                goal="Research AI trends",
                completed_steps=[],
                total_steps=5,
            )
            assert result["score"] == 50
            assert result["goal_achieved"] is False


class TestAdaptPlan:

    @pytest.mark.asyncio
    async def test_adapt_plan_returns_revised_steps(self, service):
        """Should return revised steps from LLM."""
        revised_steps = [
            {"name": "retry_search", "type": "TOOL_CALL", "description": "Retry", "step_id": "s1"}
        ]
        mock_resp = MagicMock()
        mock_resp.output = '```json\n' + __import__('json').dumps(revised_steps) + '\n```'
        with patch.object(service.llm, 'call_llm', AsyncMock(return_value=mock_resp)):
            result = await service.adapt_plan(
                original_plan=[{"step_id": "s1", "name": "search"}],
                completed_steps=[],
                failed_step={"name": "search", "error": "timeout"},
                goal="Find information",
            )
            assert len(result) >= 1
            assert result[0]["name"] == "retry_search"
