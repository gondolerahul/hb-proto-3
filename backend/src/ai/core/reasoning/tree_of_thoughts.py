"""Tree-of-Thoughts reasoning — Track 2 adapter."""
from __future__ import annotations

from typing import Any, Optional

from src.ai.core.reasoning.base import register_reasoning
from src.ai.schemas.enums import ReasoningMode


class TreeOfThoughtsReasoning:
    name = ReasoningMode.TREE_OF_THOUGHTS

    async def run(
        self,
        *,
        llm_router: Any,
        system_prompt: str,
        user_prompt: str,
        task_type: str,
        config: dict,
        tool_schemas: list[dict],          # noqa: ARG002
        execute_tool_fn: Any,              # noqa: ARG002
        model_override: Optional[str] = None,
    ) -> tuple[str, Any]:
        fn = getattr(llm_router, "call_llm_tot", None) or getattr(
            llm_router, "call_llm_tree_of_thoughts", None
        )
        if fn is None:
            fn = getattr(llm_router, "call_llm", None)
        if fn is None:
            raise NotImplementedError("llm_router missing TOT and call_llm")
        resp = await fn(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_type=task_type,
            config=config,
            model_override=model_override,
        )
        text = getattr(resp, "output", None) or getattr(resp, "content", "") or str(resp)
        return text, resp


register_reasoning(TreeOfThoughtsReasoning())
