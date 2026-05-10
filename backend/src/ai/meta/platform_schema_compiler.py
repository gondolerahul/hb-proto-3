"""
platform_schema_compiler.py — Compiles the platform capability surface into
a structured JSON schema that serves as the Meta-Agent's "firmware".

Two modes of operation:
  1. compile()       — Build-time / deploy-time full compilation
  2. refresh()       — Runtime incremental refresh (tenant-scoped tools, models)

The compiled schema is injected into the Meta-Agent's system prompt context
via the platform_introspect meta-tool.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PlatformSchemaCompiler:
    """Compiles the HireBuddha platform surface into a queryable schema."""

    def __init__(self, db: AsyncSession = None, company_id: UUID = None):
        self.db = db
        self.company_id = company_id
        self._cached_schema: Optional[Dict[str, Any]] = None
        self._cached_hash: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def compile(self, include_tenant_tools: bool = True) -> Dict[str, Any]:
        """Full compilation of platform schema.

        Returns a dict containing:
          - entity_types: available entity types and their semantics
          - step_types: available execution step types
          - reasoning_modes: available LLM reasoning strategies
          - execution_modes: STANDARD vs AUTONOMOUS
          - tools: all available tools with function schemas
          - model_endpoints: configured LLM providers/models (tenant-scoped)
          - constraints: execution limits and governance parameters
          - composition_rules: how entities compose into hierarchies
          - schema_version: hash for drift detection
        """
        schema = {
            "compiled_at": datetime.now(timezone.utc).isoformat(),
            "entity_types": self._compile_entity_types(),
            "step_types": self._compile_step_types(),
            "reasoning_modes": self._compile_reasoning_modes(),
            "execution_modes": self._compile_execution_modes(),
            "tools": self._compile_tools(include_tenant=include_tenant_tools),
            "model_endpoints": await self._compile_model_endpoints(),
            "constraints": self._compile_constraints(),
            "composition_rules": self._compile_composition_rules(),
            "memory_modes": self._compile_memory_modes(),
            "hitl_triggers": self._compile_hitl_triggers(),
            "io_contract_spec": self._compile_io_contract_spec(),
            "behavioral_annotations": self._compile_behavioral_annotations(),
        }

        # Compute schema hash for drift detection
        schema_str = json.dumps(schema, sort_keys=True, default=str)
        schema["schema_version"] = hashlib.sha256(schema_str.encode()).hexdigest()[:16]

        self._cached_schema = schema
        self._cached_hash = schema["schema_version"]

        logger.info(
            f"Platform schema compiled: {len(schema['tools'])} tools, "
            f"version={schema['schema_version']}"
        )
        return schema

    async def refresh(self) -> Dict[str, Any]:
        """Runtime refresh — recompiles tenant-scoped sections only.

        Cheaper than full compile(): skips static enum extraction and
        only refreshes tools (tenant additions) and model endpoints
        (integration changes).
        """
        if not self._cached_schema:
            return await self.compile()

        # Refresh mutable sections
        self._cached_schema["tools"] = self._compile_tools(include_tenant=True)
        self._cached_schema["model_endpoints"] = await self._compile_model_endpoints()
        self._cached_schema["compiled_at"] = datetime.now(timezone.utc).isoformat()

        # Recompute hash
        schema_str = json.dumps(self._cached_schema, sort_keys=True, default=str)
        new_hash = hashlib.sha256(schema_str.encode()).hexdigest()[:16]

        if new_hash != self._cached_hash:
            logger.info(f"Platform schema drift detected: {self._cached_hash} → {new_hash}")
            self._cached_hash = new_hash
            self._cached_schema["schema_version"] = new_hash

        return self._cached_schema

    def get_cached(self) -> Optional[Dict[str, Any]]:
        """Return cached schema without recompilation."""
        return self._cached_schema

    # ------------------------------------------------------------------
    # Entity Types
    # ------------------------------------------------------------------

    def _compile_entity_types(self) -> List[Dict[str, str]]:
        """Extract entity types from schemas.py enums with semantic descriptions."""
        return [
            {
                "type": "ACTION",
                "description": "Atomic unit of work. Single LLM reasoning step or tool call. "
                               "Cannot have children. Always has exactly one step in its plan.",
                "can_have_children": False,
                "typical_step_count": "1",
            },
            {
                "type": "SKILL",
                "description": "Reusable multi-step capability. Can chain multiple "
                               "TOOL_CALL and ACTION steps. No child entities.",
                "can_have_children": False,
                "typical_step_count": "2-5",
            },
            {
                "type": "AGENT",
                "description": "Autonomous reasoning entity with tools, memory, and "
                               "optional CORTEX cognitive tree. Supports AUTONOMOUS execution "
                               "mode with self-reflection and goal validation.",
                "can_have_children": False,
                "typical_step_count": "3-10",
            },
            {
                "type": "PROCESS",
                "description": "Orchestration entity that coordinates child entities "
                               "(AGENTs, SKILLs) via CHILD_ENTITY_INVOCATION steps. "
                               "Supports DAG execution with parallel branches.",
                "can_have_children": True,
                "typical_step_count": "2-20",
            },
        ]

    # ------------------------------------------------------------------
    # Step Types
    # ------------------------------------------------------------------

    def _compile_step_types(self) -> List[Dict[str, str]]:
        return [
            {
                "type": "THOUGHT",
                "description": "Pure LLM reasoning step. No tool call. Uses prompt_template "
                               "to structure the reasoning task. Output stored in context.",
            },
            {
                "type": "ACTION",
                "description": "LLM-driven action step. The LLM receives context from prior "
                               "steps and generates output. Core workhorse for data transformation.",
            },
            {
                "type": "TOOL_CALL",
                "description": "Direct tool invocation. Requires target.tool_id. The LLM "
                               "generates tool arguments, then the tool is executed. Uses "
                               "REACT loop for multi-turn tool interactions.",
            },
            {
                "type": "CHILD_ENTITY_INVOCATION",
                "description": "Delegates execution to a child HierarchicalEntity. Requires "
                               "target.entity_id pointing to an existing entity within the "
                               "same company. Creates a child ExecutionRun.",
            },
            {
                "type": "NAVIGATE",
                "description": "CORTEX-native. Moves the cursor to a specific node in the "
                               "cognitive tree. Updates __cortex_viewport__.",
            },
            {
                "type": "READ",
                "description": "CORTEX-native. Reads paginated content from a tree node.",
            },
            {
                "type": "WRITE",
                "description": "CORTEX-native. Creates a new finding/output node in the tree.",
            },
            {
                "type": "RECURSE",
                "description": "CORTEX-native. Spawns a sub-task as a child execution run "
                               "rooted at a tree node.",
            },
            {
                "type": "AWAIT_CHILDREN",
                "description": "CORTEX-native. Waits for all child RECURSE executions to "
                               "complete and collects their results.",
            },
        ]

    # ------------------------------------------------------------------
    # Reasoning & Execution Modes
    # ------------------------------------------------------------------

    def _compile_reasoning_modes(self) -> List[Dict[str, str]]:
        return [
            {"mode": "REACT", "description": "Reason-Act cycle. LLM reasons, calls tools, observes, repeats."},
            {"mode": "CHAIN_OF_THOUGHT", "description": "Step-by-step reasoning before acting."},
            {"mode": "REFLECTION", "description": "Post-action self-critique and correction."},
            {"mode": "TREE_OF_THOUGHTS", "description": "Explores multiple reasoning branches."},
        ]

    def _compile_execution_modes(self) -> List[Dict[str, str]]:
        return [
            {
                "mode": "STANDARD",
                "description": "Static plan-execute. Steps run in order. No self-reflection.",
            },
            {
                "mode": "AUTONOMOUS",
                "description": "Goal-centric with self-reflection. Agent validates progress "
                               "every N steps, can re-plan on failure, and early-exits when "
                               "goal is achieved. Requires: goal field set on entity.",
                "config_keys": [
                    "goal_validation_interval",
                    "confidence_threshold",
                    "max_replanning_attempts",
                    "self_reflection_enabled",
                ],
            },
        ]

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _compile_tools(self, include_tenant: bool = True) -> List[Dict[str, Any]]:
        """Extract all registered tools with their function schemas."""
        from src.ai.tools.base import ToolRegistry

        if include_tenant and self.company_id:
            tools = ToolRegistry.get_tools_for_company(self.company_id)
        else:
            tools = ToolRegistry._tools

        compiled = []
        for name, tool in tools.items():
            # Skip meta-tools from the compilation (avoid self-reference)
            if name.startswith("meta_"):
                continue

            schema = tool.get_function_schema()
            compiled.append({
                "tool_id": name,
                "description": tool.description,
                "function_schema": schema,
                "supports_context": tool.supports_context(),
                "category": self._categorize_tool(name),
            })
        return compiled

    def _categorize_tool(self, tool_name: str) -> str:
        """Heuristic tool categorization for the Meta-Agent's understanding."""
        categories = {
            "search": ["web_search", "scraper_tool"],
            "document": ["pdf_generator", "file_writer", "docx_tool", "pptx_tool", "excel"],
            "communication": ["email_ingest", "email_classify", "email_draft", "email_send",
                              "whatsapp_send_tenant"],
            "media": ["image_generation", "video_generation"],
            "code": ["sandbox_code", "terminal_tool"],
            "browser": ["headless_browser"],
            "social": ["linkedin", "twitter", "facebook", "instagram", "youtube",
                       "tiktok", "reddit", "quora", "pinterest"],
            "ads": ["google_ads", "meta_ads", "linkedin_ads", "youtube_ads",
                    "x_ads", "snapchat_ads"],
            "crm": ["crm_update_lead", "google_calendar", "get_current_datetime"],
            "utility": ["calculator"],
        }
        name_lower = tool_name.lower()
        for category, keywords in categories.items():
            if any(kw in name_lower for kw in keywords):
                return category
        return "utility"

    # ------------------------------------------------------------------
    # Model Endpoints (tenant-scoped)
    # ------------------------------------------------------------------

    async def _compile_model_endpoints(self) -> List[Dict[str, Any]]:
        """Query IntegrationRegistry for available LLM endpoints."""
        if not self.db or not self.company_id:
            return []

        try:
            from src.config.models import IntegrationRegistry

            result = await self.db.execute(
                select(IntegrationRegistry).where(
                    IntegrationRegistry.company_id == self.company_id,
                    IntegrationRegistry.is_enabled == True,
                    IntegrationRegistry.category == "ai_model",
                )
            )
            integrations = result.scalars().all()

            endpoints = []
            for integ in integrations:
                endpoints.append({
                    "provider": integ.provider,
                    "model_name": integ.service_name,
                    "category": integ.category,
                    "is_default": bool(integ.is_default),
                })
            return endpoints
        except Exception as e:
            logger.debug(f"Model endpoint compilation failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Constraints & Rules
    # ------------------------------------------------------------------

    def _compile_constraints(self) -> Dict[str, Any]:
        from src.ai.constants import (
            MAX_REACT_TURNS,
            MAX_CONTENT_CHARS,
            MAX_CONTEXT_TRUNCATION_CHARS,
            CONTEXT_SUMMARIZE_THRESHOLD,
        )
        return {
            "max_react_turns": MAX_REACT_TURNS,
            "max_content_chars": MAX_CONTENT_CHARS,
            "context_summarize_threshold": CONTEXT_SUMMARIZE_THRESHOLD,
            "max_context_truncation_chars": MAX_CONTEXT_TRUNCATION_CHARS,
            "max_recursion_depth_default": 5,
            "max_tool_rate_default": None,
            "cortex_max_children_per_node": 12,
            "cortex_page_size_tokens": 8000,
        }

    def _compile_composition_rules(self) -> List[str]:
        return [
            "PROCESS entities contain child AGENTs/SKILLs via hierarchy.children[].child_id",
            "CHILD_ENTITY_INVOCATION steps MUST have target.entity_id pointing to a valid "
            "HierarchicalEntity within the same company_id scope",
            "Children share the parent's CORTEX tree via __cortex_tree_id__ context propagation",
            "DAG execution: steps with input_dependencies run in parallel when independent",
            "Step outputs are referenced via {{step_id}} template variables in prompt_template",
            "Context flows from parent to child via input_data; child result flows back "
            "via context_state[step_name]",
            "Max composition depth enforced by governance.max_recursion_depth (default 5)",
        ]

    def _compile_memory_modes(self) -> List[Dict[str, str]]:
        return [
            {
                "mode": "STANDARD",
                "description": "Episodic (last N interactions) + Semantic (pgvector document search). "
                               "Suitable for short-lived, stateless agent executions.",
            },
            {
                "mode": "CORTEX",
                "description": "Cognitive tree for unbounded context. Enables long-running tasks "
                               "with persistent state, knowledge ingestion, and sub-task delegation. "
                               "Required for AUTONOMOUS execution mode with self-reflection.",
            },
        ]

    def _compile_hitl_triggers(self) -> List[Dict[str, str]]:
        return [
            {"trigger": "BEFORE_STEP", "description": "Pause before a named step executes"},
            {"trigger": "AFTER_STEP", "description": "Pause after a named step completes"},
            {"trigger": "COST_THRESHOLD", "description": "Pause when accumulated cost exceeds USD threshold"},
            {"trigger": "TOOL_CALL", "description": "Pause before a specific tool is called"},
            {"trigger": "CUSTOM", "description": "Custom expression: step_count > N, cost > N, has_key('X')"},
        ]

    def _compile_io_contract_spec(self) -> Dict[str, Any]:
        return {
            "description": "Every entity can define input_schema and output_schema as JSON Schema objects. "
                           "The execution engine validates input_data against input_schema before execution.",
            "input_schema_default": {"type": "object", "properties": {}},
            "output_schema_default": {"type": "object", "properties": {}},
            "variable_resolution": {
                "pattern": "{{variable_name}}",
                "sources": [
                    "input_data fields",
                    "prior step outputs (by step_id or step name)",
                    "context_state keys",
                    "__cortex_viewport__ (CORTEX mode)",
                    "__memory_context__ (episodic/semantic memory)",
                ],
            },
        }

    # ------------------------------------------------------------------
    # Behavioral Annotations (V2 — execution semantics)
    # ------------------------------------------------------------------

    def _compile_behavioral_annotations(self) -> List[Dict[str, Any]]:
        """Encode critical execution semantics that cannot be extracted from enums.

        These rules describe non-obvious runtime behaviors of the execution
        engine, context propagation, and CORTEX system.  They are injected
        into the Meta-Agent's context alongside the structural schema so it
        can generate agents that respect platform invariants.
        """
        return [
            {
                "rule": "CORTEX_TREE_PROPAGATION",
                "description": (
                    "When a PROCESS invokes a child via CHILD_ENTITY_INVOCATION, "
                    "the __cortex_tree_id__ from parent context is automatically "
                    "propagated to the child's input_data. All entities in a "
                    "hierarchy share one CORTEX tree."
                ),
                "affects": ["CHILD_ENTITY_INVOCATION", "CORTEX"],
            },
            {
                "rule": "CHILD_CONTEXT_STRIPPING",
                "description": (
                    "Before a child entity receives context from its parent, "
                    "all generic step_id keys (step_1, step_2, ...) are stripped "
                    "to prevent step-skip collision. Named step outputs and "
                    "internal keys are preserved."
                ),
                "affects": ["CHILD_ENTITY_INVOCATION", "context_state"],
            },
            {
                "rule": "PARENT_MEMORY_ISOLATION",
                "description": (
                    "Parent-scoped memory keys (__memory__, __episodic_memory__, "
                    "__semantic_context__) are stripped from child context to "
                    "prevent child entities from being confused by parent's "
                    "past execution history."
                ),
                "affects": ["CHILD_ENTITY_INVOCATION", "memory"],
            },
            {
                "rule": "AUTONOMOUS_REQUIRES_GOAL",
                "description": (
                    "execution_mode=AUTONOMOUS requires: entity.goal is set, "
                    "logic_gate.reasoning_config.self_reflection_enabled=true, "
                    "goal_validation_interval > 0. Without these, the engine "
                    "falls back to STANDARD mode silently."
                ),
                "affects": ["AUTONOMOUS", "goal_validation"],
            },
            {
                "rule": "SCRAPER_AUTO_INGEST",
                "description": (
                    "When scraper_tool or headless_browser executes during a "
                    "CORTEX-enabled run, the output is automatically written as "
                    "a knowledge node under the tree's Knowledge Root."
                ),
                "affects": ["scraper_tool", "headless_browser", "CORTEX"],
            },
            {
                "rule": "REACT_TOOL_INJECTION",
                "description": (
                    "Only tools with usage='AUTONOMOUS' or 'BOTH' are injected "
                    "into the LLM prompt for REACT reasoning. Tools with "
                    "usage='PLANNED' are executed deterministically by the "
                    "static plan executor and never shown to the LLM."
                ),
                "affects": ["REACT", "tools"],
            },
            {
                "rule": "VARIABLE_RESOLUTION_ORDER",
                "description": (
                    "{{variable}} in prompt_template resolves in order: "
                    "1) input_data fields, 2) prior step outputs (by step_id), "
                    "3) prior step outputs (by step name), 4) context_state keys. "
                    "Double-brace {{var}} takes priority over single-brace {var}."
                ),
                "affects": ["prompt_template", "context_state"],
            },
            {
                "rule": "TOOL_CALL_SELF_HEALING",
                "description": (
                    "When a TOOL_CALL step fails with a formatting error, the "
                    "engine automatically asks the LLM to reformat the input and "
                    "retries once. Infrastructure errors (auth, timeout) are not retried."
                ),
                "affects": ["TOOL_CALL"],
            },
            {
                "rule": "CHILD_RESULT_ACCUMULATION",
                "description": (
                    "When a CHILD_ENTITY_INVOCATION completes, ALL child step "
                    "outputs are accumulated and joined (not just the last step). "
                    "This ensures multi-step child agents pass their full work "
                    "to the parent."
                ),
                "affects": ["CHILD_ENTITY_INVOCATION"],
            },
            {
                "rule": "CREDIT_CIRCUIT_BREAKER",
                "description": (
                    "After each step, the engine checks the company's credit "
                    "balance. If exhausted, execution stops with PARTIAL_COMPLETE "
                    "status and partial results are saved. A child entity also "
                    "gets a credit gate check before being spawned."
                ),
                "affects": ["governance", "billing"],
            },
            {
                "rule": "DAG_PARALLEL_ISOLATION",
                "description": (
                    "When multiple steps run in parallel (DAG execution), each "
                    "step gets its own AsyncSession and a deep-copied context. "
                    "This prevents PendingRollbackError and cross-contamination."
                ),
                "affects": ["DAG", "parallel"],
            },
            {
                "rule": "PROCESS_REQUIRES_HIERARCHY",
                "description": (
                    "PROCESS entities must define hierarchy.children[] with "
                    "child_id entries and corresponding CHILD_ENTITY_INVOCATION "
                    "steps in the static plan. Each child_id must point to an "
                    "existing entity within the same company_id scope."
                ),
                "affects": ["PROCESS", "hierarchy"],
            },
            {
                "rule": "UNCERTAINTY_SIGNAL",
                "description": (
                    "During THOUGHT/ACTION steps, if the LLM includes "
                    '{"needs_clarification": true, "question": "..."} in its '
                    "response, the engine raises an UncertaintySignal instead "
                    "of treating it as normal output. This can trigger HITL."
                ),
                "affects": ["THOUGHT", "ACTION", "HITL"],
            },
            {
                "rule": "CONTEXT_SUMMARIZATION",
                "description": (
                    "When context exceeds the summarize_threshold (default 8000 "
                    "chars), older step outputs are summarized by the LLM to "
                    "fit within the context window. Domain-specific keys listed "
                    "in context_policy.preserve_keys are kept verbatim."
                ),
                "affects": ["context_policy", "SLIDING_WINDOW"],
            },
            {
                "rule": "META_TOOL_ISOLATION",
                "description": (
                    "All meta-tools (meta_platform_introspect, meta_registry_search, "
                    "meta_schema_validator, meta_entity_creator, meta_entity_executor) "
                    "use isolated AsyncSession instances to prevent DB transaction "
                    "poisoning during validation or execution steps."
                ),
                "affects": ["meta_tools", "database"],
            },
            {
                "rule": "HITL_TIMEOUT_BEHAVIOR",
                "description": (
                    "HITL checkpoints block execution until approved, rejected, "
                    "or timed out. If auto_approve_on_timeout=True, the checkpoint "
                    "auto-approves when timeout expires. Otherwise, the execution "
                    "fails with a timeout error."
                ),
                "affects": ["HITL", "governance"],
            },
        ]


# ---------------------------------------------------------------------------
# Convenience: module-level compile function
# ---------------------------------------------------------------------------

async def compile_platform_schema(
    db: AsyncSession = None,
    company_id: UUID = None,
) -> Dict[str, Any]:
    """One-shot schema compilation."""
    compiler = PlatformSchemaCompiler(db=db, company_id=company_id)
    return await compiler.compile()

