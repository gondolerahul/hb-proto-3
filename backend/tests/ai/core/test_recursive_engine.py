"""Tests for the RecursiveReasoningEngine."""
import pytest
from decimal import Decimal
from src.ai.core.recursive_engine import RecursiveReasoningEngine
from src.ai.schemas import GoalNode


class TestRecursiveReasoningEngineConfig:
    """Tests for safety limits and configuration."""

    def test_default_safety_limits(self):
        assert RecursiveReasoningEngine.MAX_DEPTH == 5
        assert RecursiveReasoningEngine.MAX_TOTAL_EXPANSIONS == 20
        assert RecursiveReasoningEngine.DEFAULT_CONFIDENCE_THRESHOLD == 0.7

    def test_is_step_engine_subclass(self):
        # Reparented to StepEngine (the step surface) so it survives the C4
        # deletion of ExecutionEngine.execute_run; it drives leaves via
        # _step_executor._execute_step and never calls execute_run.
        from src.ai.core.step_engine import StepEngine
        assert issubclass(RecursiveReasoningEngine, StepEngine)


class TestGoalNodeIntegration:
    """Tests for GoalNode structure used by recursive engine."""

    def test_basic_goal_node(self):
        root = GoalNode(goal="Research AI", depth=0)
        assert root.goal == "Research AI"
        assert root.depth == 0
        assert root.children == []
        assert root.status == "pending"

    def test_goal_node_tree_structure(self):
        root = GoalNode(goal="Research AI", depth=0)
        child1 = GoalNode(goal="Find papers", depth=1, parent=root)
        child2 = GoalNode(goal="Analyze trends", depth=1, parent=root)
        root.children = [child1, child2]

        assert len(root.children) == 2
        assert not root.is_leaf()
        assert child1.is_leaf()

    def test_goal_node_to_dict(self):
        root = GoalNode(goal="Test goal", depth=0, confidence=0.8, status="completed")
        root.result = "Success"
        d = root.to_dict()
        assert d["goal"] == "Test goal"
        assert d["depth"] == 0
        assert d["confidence"] == 0.8
        assert d["status"] == "completed"
        assert d["result"] == "Success"

    def test_nested_to_dict(self):
        root = GoalNode(goal="Parent", depth=0)
        child = GoalNode(goal="Child", depth=1, parent=root)
        root.children = [child]
        d = root.to_dict()
        assert len(d["children"]) == 1
        assert d["children"][0]["goal"] == "Child"

    def test_cost_ceiling_as_decimal(self):
        """Verify cost ceiling works with Decimal arithmetic."""
        ceiling = Decimal("1.50")
        cost = Decimal("0.75")
        assert cost < ceiling
        cost += Decimal("0.80")
        assert cost >= ceiling
