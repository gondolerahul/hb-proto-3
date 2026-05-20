"""
ai.core.meta_review — Meta-Agent review hooks for execution monitoring.

Periodically invokes the Meta-Agent to assess execution quality and
recommend adjustments (continue, replan, abort).

Phase 10D: New module for autonomous execution supervision.
"""
import logging
from typing import Dict, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MetaReviewer:
    """
    Lightweight wrapper that invokes the Meta-Agent for execution review.

    Called by the execution loop every N steps to assess:
    - Is the execution on track toward the goal?
    - Should we replan?
    - Should we abort?
    """

    def __init__(self, db: AsyncSession, company_id: UUID):
        self.db = db
        self.company_id = company_id

    async def review_execution(
        self,
        entity_goal: str,
        completed_steps: List[Dict],
        remaining_steps: List[Dict],
        total_cost_usd: float = 0,
        context_summary: str = "",
    ) -> Dict:
        """
        Ask the Meta-Agent to review execution progress.

        Returns:
            {
                "recommendation": "CONTINUE" | "REPLAN" | "ABORT",
                "confidence": 0.0–1.0,
                "reasoning": "...",
                "adjustments": [...]
            }
        """
        try:
            from src.ai.llm_router import LLMRouter
            llm = LLMRouter(db=self.db, company_id=self.company_id)

            completed_summary = "\n".join([
                f"  {i+1}. {s.get('step_name', s.get('step', 'Unknown'))}: "
                f"{'✅' if not s.get('error') else '❌'} "
                f"{str(s.get('output', ''))[:100]}"
                for i, s in enumerate(completed_steps[-5:])
            ])

            remaining_summary = "\n".join([
                f"  {i+1}. {s.get('name', 'Unknown')} ({s.get('type', '?')})"
                for i, s in enumerate(remaining_steps[:5])
            ])

            prompt = (
                f"## Execution Review Request\n\n"
                f"**Goal:** {entity_goal}\n"
                f"**Completed steps ({len(completed_steps)}):**\n{completed_summary}\n\n"
                f"**Remaining steps ({len(remaining_steps)}):**\n{remaining_summary}\n\n"
                f"**Total cost so far:** ${total_cost_usd:.4f}\n\n"
                f"Assess whether this execution is on track. Respond with JSON:\n"
                f'{{"recommendation": "CONTINUE|REPLAN|ABORT", '
                f'"confidence": 0.0-1.0, "reasoning": "..."}}'
            )

            response = await llm.call_llm(
                task_type="text_generation",
                system_prompt=(
                    "You are a Meta-Agent supervisor reviewing an AI agent's execution. "
                    "Be concise. Respond with JSON only."
                ),
                user_prompt=prompt,
                temperature=0.2,
                max_tokens=300,
            )

            from src.ai.shared.json_utils import parse_json_object
            result = parse_json_object(response.output)
            if result:
                return {
                    "recommendation": result.get("recommendation", "CONTINUE").upper(),
                    "confidence": float(result.get("confidence", 0.5)),
                    "reasoning": result.get("reasoning", ""),
                    "adjustments": result.get("adjustments", []),
                }

        except Exception as e:
            logger.warning(f"Meta-review failed (non-fatal): {e}")

        return {"recommendation": "CONTINUE", "confidence": 0.5, "reasoning": "Review unavailable"}
