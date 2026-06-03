"""
tests/parity/hermetic.py — deterministic, key-free runtime for parity.

The parity gate must run in CI with **no LLM API keys and no network**.
This module makes both the legacy ``ExecutionEngine`` and the new
``AgentLoop`` fully deterministic by:

  1. Patching ``LLMRouter._resolve_adapter`` to return a
     ``DeterministicAdapter`` — so every ``call_llm`` / ``call_llm_react``
     flows through canned, reproducible responses while the real tracing,
     usage-logging and cost code paths still run.
  2. Stubbing the network-bound ``web_search`` tool with a fixed result.

Because the LLM is held constant, any divergence the parity comparator
reports is attributable to the **engine** (orchestration / planning /
critics), which is exactly what gates the C4 legacy-deletion.

Shared by the recorder (``scripts/record_golden_runs.py``) and the
parity tests (``tests/parity/test_agent_loop_parity.py``) so goldens and
candidates are produced under identical conditions.
"""
from __future__ import annotations

import contextlib
import uuid
from typing import Any, Iterator, Optional

from src.ai.llm.base import BaseLLMAdapter
from src.ai.llm.types import LLMResponse

# Fixed token counts → deterministic usage rows / cost across runs.
_PROMPT_TOKENS = 100
_COMPLETION_TOKENS = 60

# A stable summary string used as the default generation output. It
# deliberately mentions the tokens the regression cases look for so the
# same fixtures double as smoke checks.
_DEFAULT_TEXT = (
    "Post-quantum cryptography advanced in 2025 as NIST finalized its "
    "lattice-based standards. This is a deterministic parity summary; the "
    "content is fixed so engine-vs-engine comparison is reproducible."
)


class DeterministicAdapter(BaseLLMAdapter):
    """A key-free, network-free LLM adapter with canned responses.

    The response is chosen from ``task_type`` so planner / critic / actor
    calls each get a shape their callers can parse, while everything else
    falls back to a stable text blob.
    """

    def __init__(self, task_type: str = "text_generation",
                 model_name: str = "mock-model"):
        self.task_type = task_type or "text_generation"
        self.model_name = model_name
        self.service_metadata = {}

    # -- response selection -------------------------------------------------
    def _canned_output(self) -> str:
        tt = self.task_type.lower()
        if "plan" in tt:
            # Minimal single-step dynamic plan; engines that don't use it
            # fall back to the entity's static plan, which is fine.
            return (
                '{"steps":[{"step_id":"s1","order":1,"name":"respond",'
                '"type":"ACTION","target":{"prompt_template":"{{input}}"},'
                '"required":true}]}'
            )
        if any(k in tt for k in ("critic", "verdict", "review", "align",
                                 "supervisor", "judge")):
            return '{"verdict":"PASS","concerns":[],"confidence":0.9}'
        return _DEFAULT_TEXT

    def _response(self) -> LLMResponse:
        return LLMResponse(
            output=self._canned_output(),
            function_calls=[],
            prompt_tokens=_PROMPT_TOKENS,
            completion_tokens=_COMPLETION_TOKENS,
            latency_ms=1,
            model_name=self.model_name,
            provider="mock",
            finish_reason="stop",
        )

    # -- BaseLLMAdapter contract -------------------------------------------
    async def generate(self, system_prompt, messages, tools=None,
                       temperature=0.7, max_tokens=None, top_p=1.0, **kwargs):
        return self._response()

    async def generate_with_tools_react(self, system_prompt, initial_messages,
                                        tool_schemas, execute_tool_fn,
                                        temperature=0.7, max_tokens=None,
                                        max_react_turns=10, **kwargs):
        # Return a final answer with no tool calls → deterministic, and the
        # tool layer is exercised separately by the static TOOL_CALL steps.
        return self._response()


async def _patched_resolve_adapter(self, task_type, model_override=None):
    return DeterministicAdapter(task_type=task_type)


async def _stub_web_search(self, input_data, *args, **kwargs):
    return ("NIST finalized lattice-based post-quantum cryptography standards "
            "in 2025 (deterministic stub result).")


@contextlib.contextmanager
def hermetic_llm_and_tools() -> Iterator[None]:
    """Context manager that applies the LLM + tool patches and restores them.

    Usable from non-pytest code (the recorder). Tests should prefer the
    ``parity_patches`` fixture which wraps this.
    """
    from src.ai.llm.router import LLMRouter
    from src.ai.tools.core.search import WebSearchTool

    orig_resolve = LLMRouter._resolve_adapter
    orig_run = WebSearchTool.run
    orig_run_ctx = getattr(WebSearchTool, "run_with_context", None)

    LLMRouter._resolve_adapter = _patched_resolve_adapter            # type: ignore[assignment]
    WebSearchTool.run = _stub_web_search                             # type: ignore[assignment]

    async def _run_with_context(self, input_data, context=None):
        return await _stub_web_search(self, input_data)
    if orig_run_ctx is not None:
        WebSearchTool.run_with_context = _run_with_context           # type: ignore[assignment]

    try:
        yield
    finally:
        LLMRouter._resolve_adapter = orig_resolve                    # type: ignore[assignment]
        WebSearchTool.run = orig_run                                 # type: ignore[assignment]
        if orig_run_ctx is not None:
            WebSearchTool.run_with_context = orig_run_ctx            # type: ignore[assignment]


async def seed_parity_run(
    db: Any,
    *,
    entity_fixture: str,
    input_data: dict,
    company_id: Optional[uuid.UUID] = None,
    commit: bool = True,
) -> str:
    """Insert a fresh company (if needed), entity, and PENDING run.

    Returns the new run id as a string. Used by both the recorder and the
    parity tests so goldens and candidates run the identical entity config.
    """
    from sqlalchemy import text
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.orm.execution import ExecutionRun
    from tests.harness import load_entity_fixture

    company_id = company_id or uuid.uuid4()
    dto = load_entity_fixture(entity_fixture)

    await db.execute(
        text(
            "INSERT INTO companies (id, name, type, status, created_at, updated_at) "
            "VALUES (:id, :n, 'TENANT', 'active', now(), now()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": str(company_id), "n": f"parity-{company_id.hex[:8]}"},
    )

    entity = HierarchicalEntity(
        id=uuid.uuid4(),
        company_id=company_id,
        # Unique name so repeated seeds don't collide on (company, name).
        name=f"{dto.name}_{uuid.uuid4().hex[:8]}",
        display_name=dto.display_name,
        description=dto.description,
        goal=dto.goal,
        type=dto.type.value,
        status=dto.status.value,
        version=dto.version,
        tags=dto.tags,
        identity=dto.identity,
        hierarchy=dto.hierarchy.model_dump() if dto.hierarchy else None,
        logic_gate=dto.logic_gate.model_dump() if dto.logic_gate else None,
        planning=dto.planning.model_dump() if dto.planning else None,
        capabilities=dto.capabilities.model_dump() if dto.capabilities else None,
        governance=dto.governance.model_dump() if dto.governance else None,
        io_contract=dto.io_contract.model_dump() if dto.io_contract else None,
        observability=dto.observability.model_dump() if dto.observability else None,
        metadata_extensions=dto.metadata_extensions,
    )
    db.add(entity)
    await db.flush()

    run = ExecutionRun(
        id=uuid.uuid4(),
        entity_id=entity.id,
        company_id=company_id,
        status="PENDING",
        input_data=input_data,
    )
    db.add(run)
    if commit:
        await db.commit()
    else:
        await db.flush()
    return str(run.id)
