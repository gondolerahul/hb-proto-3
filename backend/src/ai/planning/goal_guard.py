"""
ai.planning.goal_guard — Unified post-step goal validation middleware.

Combines:
1. GoalAlignmentVerifier (step output vs entity goal) — triggers retry
2. PlannerService.validate_goal_progress (overall progress) — triggers replan/early-exit

Replaces the two separate inline checks (~50 lines) in execute_run().

Phase 10D: New module for unified goal management.
"""
import logging
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class GoalGuard:
    """
    Post-step goal validation middleware.

    Usage:
        guard = GoalGuard(db, company_id, entity_goal, planner)
        action = await guard.check(step_result, step_name, step_idx, total_steps)
        # action["action"]: "CONTINUE" | "RETRY" | "REPLAN" | "EARLY_EXIT"
    """

    def __init__(
        self,
        db: AsyncSession,
        company_id: UUID,
        entity_goal: str,
        task_description: str = "",
        planner=None,
        confidence_threshold: float = 0.85,
    ):
        self.db = db
        self.company_id = company_id
        self.entity_goal = entity_goal
        self.task_description = task_description
        self.planner = planner
        self.confidence_threshold = confidence_threshold

    async def check(
        self,
        step_result: dict,
        step_name: str,
        step_idx: int,
        all_results: list,
        total_steps: int,
        is_autonomous: bool = False,
        goal_interval: int = 2,
    ) -> Dict:
        """
        Run post-step goal validation.

        Returns:
            {
                "action": "CONTINUE" | "RETRY" | "REPLAN" | "EARLY_EXIT",
                "reason": str,
                "correction_hint": str (if RETRY),
            }
        """
        result = {"action": "CONTINUE", "reason": ""}

        # Check 1: Step-level alignment (is this step's output on-topic?)
        if step_result and isinstance(step_result, dict):
            output = str(step_result.get("output", ""))[:2000]
            if output and not step_result.get("error"):
                try:
                    from src.ai.planning.goal_alignment import GoalAlignmentVerifier
                    verifier = GoalAlignmentVerifier(self.db, self.company_id)
                    alignment = await verifier.verify_step_alignment(
                        entity_goal=self.entity_goal,
                        task_desc=self.task_description,
                        step_output=output,
                        step_name=step_name,
                    )
                    if not alignment.get("aligned", True):
                        return {
                            "action": "RETRY",
                            "reason": f"Step '{step_name}' misaligned: {alignment.get('issues')}",
                            "correction_hint": alignment.get("correction_hint", ""),
                        }
                except Exception as e:
                    logger.debug(f"Goal alignment check failed: {e}")

        # Check 2: Overall goal progress (autonomous mode only)
        if is_autonomous and step_idx > 0 and step_idx % goal_interval == 0:
            if self.planner:
                try:
                    validation = await self.planner.validate_goal_progress(
                        goal=self.entity_goal,
                        completed_steps=all_results,
                        total_steps=total_steps,
                    )
                    score = validation.get("score", 0)
                    if score > self.confidence_threshold * 100:
                        return {
                            "action": "EARLY_EXIT",
                            "reason": f"Goal achieved (score={score})",
                        }
                    elif score < 30 and step_idx > total_steps // 2:
                        return {
                            "action": "REPLAN",
                            "reason": f"Low progress ({score}) past midpoint",
                        }
                except Exception as e:
                    logger.debug(f"Goal validation failed: {e}")

        return result
