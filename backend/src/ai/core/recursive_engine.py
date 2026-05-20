"""
ai.core.recursive_engine — Production recursive goal decomposition engine.

Unlike the flat DAG executor, this engine:
1. Takes a high-level goal
2. Recursively decomposes it until sub-goals are atomic or confidence is high
3. Executes leaf goals via StepExecutorService
4. Synthesizes results bottom-up
5. Writes the entire goal tree to CORTEX

Phase 10D: Promoted from experimental stub to production-ready with safety
limits, cost tracking, and CORTEX integration.

Gated behind entity.reasoning_config.engine_type == "RECURSIVE".
"""
import json
import logging
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.ai.core.execution_engine import ExecutionEngine
from src.ai.models import ExecutionRun, HierarchicalEntity
from src.ai.schemas import GoalNode, PlanStep, StepType

logger = logging.getLogger(__name__)


class RecursiveReasoningEngine(ExecutionEngine):
    """
    Autonomous goal decomposition engine.

    Gated behind entity.reasoning_config.engine_type == "RECURSIVE".
    Falls back to standard ExecutionEngine for all other entity types.
    """

    # Safety limits
    MAX_DEPTH = 5
    MAX_TOTAL_EXPANSIONS = 20
    DEFAULT_CONFIDENCE_THRESHOLD = 0.7

    def __init__(self, db, redis_pool, company_id=None):
        super().__init__(db, redis_pool, company_id=company_id)
        self._expansion_count = 0
        self._total_cost = Decimal("0")

    async def execute_tree(
        self,
        run_id: UUID,
        root_goal: str,
        context: dict,
        tree_id: Optional[UUID] = None,
    ) -> dict:
        """
        Main entry point for recursive goal execution.

        Args:
            run_id: The ExecutionRun ID (for billing, logging)
            root_goal: High-level natural-language goal
            context: Initial context state
            tree_id: Optional CORTEX tree ID for writing goal nodes
        """
        run = await self._load_run(run_id)
        entity = await self._load_entity(run.entity_id)
        self._ensure_services(entity.company_id)

        # Get per-entity config
        reasoning_config = (entity.logic_gate or {}).get("reasoning_config", {})
        max_depth = reasoning_config.get("max_depth", self.MAX_DEPTH)
        confidence_threshold = reasoning_config.get(
            "confidence_threshold", self.DEFAULT_CONFIDENCE_THRESHOLD
        )
        cost_ceiling = Decimal(str(reasoning_config.get("cost_ceiling_usd", "1.00")))

        # Build root goal node
        root = GoalNode(goal=root_goal, depth=0)
        self._expansion_count = 0
        self._total_cost = Decimal("0")

        try:
            result = await self._execute_node(
                run, entity, root, context,
                max_depth=max_depth,
                confidence_threshold=confidence_threshold,
                cost_ceiling=cost_ceiling,
                tree_id=tree_id,
            )
            return {
                "output": result,
                "goal_tree": root.to_dict(),
                "total_expansions": self._expansion_count,
                "total_cost_usd": str(self._total_cost),
            }
        except Exception as e:
            logger.error(f"RecursiveReasoningEngine failed: {e}")
            return {
                "error": str(e),
                "goal_tree": root.to_dict(),
                "total_expansions": self._expansion_count,
            }

    async def _execute_node(
        self, run, entity, node: GoalNode, context: dict, *,
        max_depth: int, confidence_threshold: float,
        cost_ceiling: Decimal, tree_id: Optional[UUID],
    ) -> str:
        """Recursively execute a goal node."""
        node.status = "running"

        # Safety: check cost ceiling
        if self._total_cost >= cost_ceiling:
            node.status = "failed"
            node.result = f"Cost ceiling (${cost_ceiling}) exceeded"
            logger.warning(f"RecursiveEngine: Cost ceiling hit at depth {node.depth}")
            return node.result

        # Safety: check depth limit
        if node.depth >= max_depth:
            logger.info(f"RecursiveEngine: Max depth ({max_depth}) reached, executing as leaf")
            return await self._execute_leaf(run, entity, node, context, tree_id)

        # Safety: check expansion limit
        if self._expansion_count >= self.MAX_TOTAL_EXPANSIONS:
            logger.info(f"RecursiveEngine: Max expansions ({self.MAX_TOTAL_EXPANSIONS}) hit")
            return await self._execute_leaf(run, entity, node, context, tree_id)

        # Assess confidence — can we execute this goal directly?
        confidence = await self._assess_confidence(entity, node, context)
        node.confidence = confidence

        if confidence >= confidence_threshold:
            return await self._execute_leaf(run, entity, node, context, tree_id)

        # Decompose into sub-goals
        try:
            children = await self._expand_goal(entity, node, context)
        except Exception as e:
            logger.warning(f"Goal expansion failed, executing as leaf: {e}")
            return await self._execute_leaf(run, entity, node, context, tree_id)

        if not children:
            return await self._execute_leaf(run, entity, node, context, tree_id)

        # Execute children recursively
        results = []
        for child in children:
            child_result = await self._execute_node(
                run, entity, child, context,
                max_depth=max_depth,
                confidence_threshold=confidence_threshold,
                cost_ceiling=cost_ceiling,
                tree_id=tree_id,
            )
            results.append(child_result)

            # Inject child result into context for sibling steps
            context[f"__subgoal_{child.depth}_{len(results)}__"] = child_result

        # Synthesize results
        synthesis = await self._synthesize(entity, node, results, context)
        node.result = synthesis
        node.status = "completed"

        # Write to CORTEX
        if tree_id:
            await self._write_goal_to_cortex(tree_id, node, synthesis)

        return synthesis

    async def _assess_confidence(self, entity, node: GoalNode, context: dict) -> float:
        """Ask the LLM to self-assess confidence for this goal."""
        try:
            from src.ai.llm_router import LLMRouter
            llm = LLMRouter(db=self.db, company_id=entity.company_id)

            prompt = (
                f"On a scale of 0.0 to 1.0, how confident are you that you can "
                f"directly accomplish the following goal WITHOUT needing to break it "
                f"into sub-tasks?\n\n"
                f"Goal: {node.goal}\n"
                f"Depth: {node.depth}\n\n"
                f"Respond with ONLY a number between 0.0 and 1.0."
            )
            response = await llm.call_llm(
                task_type="text_generation",
                system_prompt="You are an AI planning assistant. Respond with only a confidence number.",
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=10,
            )
            # Track assessment cost
            cost = Decimal(str(response.cost_usd or 0))
            self._total_cost += cost

            return min(1.0, max(0.0, float(response.output.strip())))
        except Exception:
            return 0.5  # Default: uncertain

    async def _expand_goal(self, entity, node: GoalNode, context: dict) -> List[GoalNode]:
        """Decompose a goal into sub-goals via LLM."""
        self._expansion_count += 1

        from src.ai.llm_router import LLMRouter
        llm = LLMRouter(db=self.db, company_id=entity.company_id)

        prompt = (
            f"Break down the following goal into 2-5 concrete, actionable sub-goals.\n\n"
            f"Goal: {node.goal}\n"
            f"Current depth: {node.depth}\n\n"
            f"Respond with a JSON array of strings, each being a sub-goal:\n"
            f'["sub-goal 1", "sub-goal 2", ...]'
        )
        response = await llm.call_llm(
            task_type="text_generation",
            system_prompt="You are a goal decomposition expert. Respond with JSON only.",
            user_prompt=prompt,
            temperature=0.3,
            max_tokens=500,
        )

        from src.ai.shared.json_utils import parse_json_array
        sub_goals = parse_json_array(response.output)

        # Track cost
        cost = Decimal(str(response.cost_usd or 0))
        self._total_cost += cost

        children = []
        for sg in sub_goals:
            if isinstance(sg, str):
                child = GoalNode(
                    goal=sg,
                    depth=node.depth + 1,
                    parent=node,
                )
                children.append(child)
                node.children.append(child)
            elif isinstance(sg, dict) and "goal" in sg:
                child = GoalNode(
                    goal=sg["goal"],
                    depth=node.depth + 1,
                    parent=node,
                )
                children.append(child)
                node.children.append(child)

        return children

    async def _execute_leaf(self, run, entity, node: GoalNode, context: dict, tree_id=None) -> str:
        """Execute a leaf goal as a single THOUGHT step."""
        step = PlanStep(
            name=f"Goal: {node.goal[:60]}",
            type=StepType.THOUGHT,
            description=node.goal,
        )
        result = await self._step_executor._execute_step(run, entity, step, context)
        output = result.get("output", "") if isinstance(result, dict) else str(result)

        # Track cost
        if isinstance(result, dict):
            cost = Decimal(str(result.get("cost_usd", 0) or 0))
            self._total_cost += cost

        node.result = output
        node.status = "completed"

        # Write to CORTEX
        if tree_id:
            await self._write_goal_to_cortex(tree_id, node, output)

        return output

    async def _synthesize(self, entity, node: GoalNode, results: list, context: dict) -> str:
        """Synthesize child results into a unified answer for the parent goal."""
        from src.ai.llm_router import LLMRouter
        llm = LLMRouter(db=self.db, company_id=entity.company_id)

        results_text = "\n\n".join([f"Sub-result {i+1}: {r[:2000]}" for i, r in enumerate(results)])
        prompt = (
            f"You have completed the following sub-tasks for the goal: {node.goal}\n\n"
            f"{results_text}\n\n"
            f"Synthesize these results into a comprehensive answer for the original goal."
        )
        response = await llm.call_llm(
            task_type="text_generation",
            system_prompt="You are a synthesis expert. Combine sub-task results into a coherent answer.",
            user_prompt=prompt,
            temperature=0.5,
            max_tokens=2000,
        )

        cost = Decimal(str(response.cost_usd or 0))
        self._total_cost += cost

        return response.output

    async def _write_goal_to_cortex(self, tree_id: UUID, node: GoalNode, output: str):
        """Write a goal node and its result to the CORTEX tree."""
        try:
            from src.ai.memory.cortex_service import CortexRouter as CortexService
            cortex = CortexService(db=self.db, company_id=self.company_id)
            working_root = await cortex.get_working_root(tree_id)
            if working_root:
                await cortex.write(
                    parent_id=working_root.id,
                    node_type="finding",
                    title=f"🎯 Goal (d={node.depth}): {node.goal[:80]}",
                    summary=output[:300],
                    content=output[:50000],
                    status="complete" if node.status == "completed" else "failed",
                    source_ref={
                        "type": "recursive_goal",
                        "depth": node.depth,
                        "confidence": node.confidence,
                        "expansions": self._expansion_count,
                    },
                )
        except Exception as e:
            logger.debug(f"CORTEX goal write failed: {e}")

    # ── Helper methods for loading run/entity ──────────────────────────

    async def _load_run(self, run_id: UUID) -> ExecutionRun:
        """Load an ExecutionRun by ID."""
        result = await self.db.execute(
            select(ExecutionRun)
            .options(selectinload(ExecutionRun.entity))
            .where(ExecutionRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            from src.ai.core.exceptions import AgentError
            raise AgentError(f"Run {run_id} not found")
        return run

    async def _load_entity(self, entity_id: UUID) -> HierarchicalEntity:
        """Load a HierarchicalEntity by ID."""
        result = await self.db.execute(
            select(HierarchicalEntity)
            .where(HierarchicalEntity.id == entity_id)
        )
        entity = result.scalar_one_or_none()
        if not entity:
            from src.ai.core.exceptions import EntityNotFoundError
            raise EntityNotFoundError(str(entity_id), "not found")
        return entity
