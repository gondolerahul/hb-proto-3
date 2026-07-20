"""solo_pack/templates/_shared — reasoning defaults shared by curated templates.

Every Solo Pack workforce agent reasons in bounded REACT with a FULL context
policy. Keeping the block in one place means the curated templates differ only
where they *should* — identity, tools, and governance — not in boilerplate.
"""
from __future__ import annotations

from typing import Any

__all__ = ["REACT"]

# Shared reasoning defaults for the Solo Pack workforce agents.
REACT: dict[str, Any] = {
    "reasoning_config": {
        "task_type": "thinking", "reasoning_mode": "REACT",
        "temperature": 0.2, "execution_mode": "STANDARD", "max_react_turns": 8,
    },
    "context_policy": {"type": "FULL"},
}
