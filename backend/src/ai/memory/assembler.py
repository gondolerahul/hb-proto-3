"""
ai.memory.assembler — Unified memory assembly interface.

Routes memory retrieval through either v1 (MemoryRouter) or v2
(MemoryAssemblyService) based on entity configuration.

Phase 10C: Replaces 35+ lines of branching in execute_run() with
a single function call.
"""
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def assemble_memory(
    db: AsyncSession,
    company_id: UUID,
    entity_id: UUID,
    user_id: Optional[UUID] = None,
    tree_id: Optional[UUID] = None,
    task_description: str = "",
    memory_pipeline: str = "v2",                            # Track 6 default flip
    memory_scope: str = "FULL",
    runtime_tree: Any = None,
    long_running: bool = False,
) -> Dict[str, Any]:
    """Unified entry point for memory retrieval.

    Phase 11 Track 6: ``memory_pipeline`` default is now ``"v2"``. The
    v1 path (``MemoryRouter``) is retained as an explicit opt-in for
    rollback safety only and will be removed in Track 9. On the v2 path,
    if the entity has no Episodic Tree data yet, the
    :class:`LegacyEpisodicReader` tops up the result with rows from the
    flat ``episodic_memories`` table so a freshly-migrated entity does
    not look amnesiac on its first run.

    Args:
        memory_pipeline: "v2" (MemoryAssemblyService, default) or "v1"
            (legacy MemoryRouter — explicit opt-in only).
        memory_scope: "FULL", "RUN_SCOPED", "INTELLIGENCE_ONLY",
            "KNOWLEDGE_ONLY", "NONE".

    Returns:
        Dict with memory context ready for injection into context_state.
    """
    if memory_scope == "NONE":
        return {}

    if memory_pipeline == "v1":
        # Explicit opt-in for the legacy pipeline (rollback safety).
        return await _assemble_v1(
            db, entity_id, user_id, tree_id,
            memory_scope, long_running,
        )

    result = await _assemble_v2(
        db, company_id, entity_id, user_id,
        task_description, memory_scope, runtime_tree,
    )

    # First-run top-up: if the v2 pipeline returned no episodic context
    # AND the requested scope cares about episodes, fall back to the
    # legacy flat-table reader so freshly-migrated entities don't
    # appear amnesiac. Pure read; no write-backs.
    if memory_scope in ("FULL", "RUN_SCOPED") and not result.get("__episodic_memory__"):
        try:
            from src.ai.memory.legacy_episodic_reader import LegacyEpisodicReader
            legacy = await LegacyEpisodicReader(db).read(
                entity_id=entity_id, user_id=user_id, limit=5,
            )
            if legacy:
                result["__episodic_memory__"] = legacy
        except Exception as exc:                                            # noqa: BLE001
            logger.debug(f"Legacy episodic top-up skipped: {exc}")

    return result


async def _assemble_v1(
    db: Any, entity_id: UUID, user_id: Optional[UUID], tree_id: Optional[UUID],
    memory_scope: str, long_running: bool,
) -> Dict[str, Any]:
    """Legacy MemoryRouter path."""
    from src.ai.memory.memory_service import MemoryRouter
    memory_router = MemoryRouter(db)

    memory_ctx = await memory_router.retrieve(
        entity_id=entity_id,
        user_id=user_id,
        tree_id=tree_id,
        long_running=long_running,
    )

    result: Dict[str, Any] = {}
    if memory_scope in ("FULL", "RUN_SCOPED"):
        memory_text = memory_router.format_for_prompt(memory_ctx)
        if memory_text:
            result["__memory__"] = memory_text
    elif memory_scope == "INTELLIGENCE_ONLY":
        logger.info(f"Memory scope=INTELLIGENCE_ONLY: skipping episodic injection")
        try:
            from src.ai.failure_pattern_service import FailurePatternService
            fps = FailurePatternService(db)
            patterns = await fps.get_failure_patterns(entity_id, limit=5)
            if patterns:
                pattern_text = "## Known Failure Patterns\n"
                for p in patterns:
                    pattern_text += f"⚠️ {p['description']}\n   Mitigation: {p['suggestion']}\n"
                result["__memory__"] = pattern_text
        except (ImportError, Exception) as _fp_err:
            logger.debug(f"Failure pattern injection skipped: {_fp_err}")
    elif memory_scope == "KNOWLEDGE_ONLY":
        # Knowledge + Intelligence, no episodic
        memory_text = memory_router.format_for_prompt(memory_ctx)
        if memory_text:
            result["__memory__"] = memory_text
        # Also attempt failure patterns
        try:
            from src.ai.failure_pattern_service import FailurePatternService
            fps = FailurePatternService(db)
            patterns = await fps.get_failure_patterns(entity_id, limit=5)
            if patterns:
                rules = [f"⚠️ {p['description']}: {p['suggestion']}" for p in patterns]
                result["__intelligence_rules__"] = rules
        except (ImportError, Exception):
            pass

    return result


async def _assemble_v2(
    db: Any, company_id: UUID, entity_id: UUID, user_id: Optional[UUID],
    task_description: str, memory_scope: str, runtime_tree: Any,
) -> Dict[str, Any]:
    """New MemoryAssemblyService path — 4-domain retrieval."""
    from src.ai.memory.memory_assembly_service import MemoryAssemblyService

    # Map memory_scope to include_domains
    domain_map = {
        "FULL": ["knowledge", "experience", "intelligence", "episodic"],
        "RUN_SCOPED": ["knowledge", "experience", "intelligence", "episodic"],
        "INTELLIGENCE_ONLY": ["intelligence"],
        "KNOWLEDGE_ONLY": ["knowledge", "intelligence"],
    }
    domains = domain_map.get(memory_scope, ["knowledge", "experience", "intelligence", "episodic"])

    assembler = MemoryAssemblyService(db, company_id)
    result = await assembler.assemble_runtime_memory(
        entity_id=entity_id,
        user_id=user_id,
        task_description=task_description,
        runtime_tree=runtime_tree,
        include_domains=domains,
    )

    # Format into the same structure execute_run expects
    memory_context: Dict[str, Any] = {}
    if result.formatted_prompt:
        memory_context["__memory__"] = result.formatted_prompt
    if result.intelligence_rules:
        memory_context["__intelligence_rules__"] = result.intelligence_rules
    if result.episodic_context:
        memory_context["__episodic_memory__"] = result.episodic_context

    logger.info(
        f"MemoryAssembly v2: {len(result.knowledge_refs)} knowledge refs, "
        f"{len(result.experience_suggestions)} experience suggestions, "
        f"{len(result.intelligence_rules)} rules, "
        f"{len(result.episodic_context)} episodes"
    )
    return memory_context
