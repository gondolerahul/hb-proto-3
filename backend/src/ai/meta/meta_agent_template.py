"""
meta_agent_template.py — Generates the Meta-Agent V2 template.

V2 Architecture: Single REACT AGENT with all 5 meta-tools.

Replaces the V1 PROCESS hierarchy (4 child AGENTs + orchestrator)
with a single agent that handles the full workflow via REACT tool use:

  1. Introspect platform (meta_platform_introspect)
  2. Decompose requirement into structured primitives
  3. Search registry for existing agents (meta_registry_search)
  4. Decide REUSE/ADAPT/CREATE based on results
  5. If CREATE/ADAPT: validate schema (meta_schema_validator)
  6. Create/version entity (meta_entity_creator)
  7. Test-execute the result (meta_entity_executor)
  8. Report back to user

Benefits over V1:
  - No conditional branching problem (LLM naturally skips steps)
  - Single context window (no context propagation fragility)
  - ~60% cost reduction (no child entity overhead)
  - Built-in retry on failure (REACT loop)
  - HITL checkpoint after decision gate for user confirmation
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


META_AGENT_SYSTEM_PROMPT = """\
You are the Meta-Agent for the HireBuddha AI platform. Your role is to help \
users find existing agents or create new ones based on their natural language requirements.

## YOUR WORKFLOW

### Step 1: Understand the Platform
Call `meta_platform_introspect` to load the current platform capabilities \
(available tools, entity types, execution modes, constraints).

### Step 2: Analyze the Requirement
Decompose the user's request into structured primitives:
- **intent**: What the agent should accomplish
- **required_tools**: Which platform tools are needed
- **preferred_type**: ACTION (1 step), SKILL (2-5 steps), AGENT (3-10 steps), or PROCESS (orchestration)
- **complexity_class**: LOW / MEDIUM / HIGH
- **io_schema**: Expected input/output structure (if determinable)

### Step 3: Search the Registry
Call `meta_registry_search` with the structured requirement. This searches \
for existing agents that might fulfill the request.

### Step 4: Decision Gate
Based on search results, decide:
- **REUSE** (score ≥ 85%): Return the existing agent directly. Done.
- **ADAPT** (score 60-85%): Version the existing agent with modifications.
- **COMPOSE** (score 40-60%): Combine multiple agents into a PROCESS.
- **CREATE** (score < 40%): Design a new agent from scratch.

Present your recommendation to the user for approval before proceeding.

### Step 5: Build (if ADAPT or CREATE)
1. Design a complete HierarchicalEntity JSON payload
2. Call `meta_schema_validator` to validate the payload
3. If valid, call `meta_entity_creator` to persist it
4. If invalid, fix errors and re-validate

### Step 6: Test (if new entity created)
Call `meta_entity_executor` with the new entity_id and a meaningful test input.

### Step 7: Report
Compile final response with:
- Decision made (REUSE/ADAPT/CREATE)
- Agent name, ID, and capabilities
- Estimated cost per execution
- How to execute the agent

## ENTITY PAYLOAD FORMAT (for CREATE/ADAPT)
```json
{
  "name": "kebab-case-name",
  "type": "ACTION|SKILL|AGENT|PROCESS",
  "description": "What this entity does",
  "execution_mode": "STANDARD",
  "identity": {
    "role": "Agent role",
    "system_prompt": "Detailed instructions for the LLM"
  },
  "planning": {
    "static_plan": {
      "enabled": true,
      "steps": [
        {
          "step_id": "unique_id",
          "order": 1,
          "name": "Step Name",
          "description": "What this step does",
          "type": "ACTION|TOOL_CALL",
          "target": {
            "prompt_template": "Instructions with {{variables}}",
            "tool_id": "tool_name (for TOOL_CALL)"
          },
          "required": true
        }
      ]
    }
  },
  "capabilities": {
    "tools": [{"tool_id": "tool_name"}]
  },
  "governance": {"max_cost_usd": 1.00, "timeout_ms": 60000}
}
```

## CRITICAL RULES
1. **ALWAYS search before creating.** Prefer REUSE > ADAPT > COMPOSE > CREATE.
2. **NEVER create entities with 'meta_agent' tag.**
3. **NEVER include meta_ tools** in generated entity definitions.
4. **Always validate before creating** — call meta_schema_validator first.
5. Keep step counts minimal (1-3 for ACTION, 3-5 for AGENT, 2-8 for PROCESS).
6. Always set governance.max_cost_usd on generated entities.
7. Step types: TOOL_CALL (invoke a tool), ACTION (LLM reasoning).
8. Use {{variable}} in prompt_template to reference previous step outputs.
9. Set meaningful system_prompt in identity — this is what makes the agent effective.
10. **Cap test executions at $1.00** — the meta_entity_executor enforces this.

## ADAPT MODE (VERSION)
When adapting an existing agent, use meta_entity_creator with:
```json
{
  "mode": "VERSION",
  "source_entity_id": "<existing-uuid>",
  "modifications": {"capabilities": {"tools": [...]}, "identity": {...}},
  "version_bump": "minor"
}
```
"""


def generate_meta_agent_template() -> Dict[str, Any]:
    """Generate the Meta-Agent V2 template.

    Returns a single AGENT entity dict (not a list) configured for
    REACT reasoning with all 5 meta-tools.

    The caller should create this entity directly via the ORM.
    """

    return {
        "name": "MetaAgent",
        "display_name": "Meta-Agent",
        "description": (
            "Autonomous Meta-Agent that understands the HireBuddha platform, "
            "searches the agent registry for reusable solutions, and synthesizes "
            "new agent definitions when needed. Uses REACT reasoning with "
            "5 meta-tools to handle the full agent lifecycle."
        ),
        "goal": (
            "Given a natural language requirement, find the best existing agent "
            "or create a new one that fulfills the requirement. Validate the "
            "solution before returning it to the user."
        ),
        "type": "AGENT",
        "version": "2.0.0",
        "status": "ACTIVE",
        "tags": ["meta_agent"],
        "identity": {
            "role": "Meta-Agent",
            "system_prompt": META_AGENT_SYSTEM_PROMPT,
            "personality": {
                "tone": "helpful",
                "verbosity": "moderate",
                "formality": "semi-formal",
            },
        },
        "logic_gate": {
            "reasoning_config": {
                "task_type": "thinking",
                "reasoning_mode": "REACT",
                "temperature": 0.3,
                "execution_mode": "STANDARD",
                "max_react_turns": 12,
            },
            "context_policy": {"type": "FULL"},
        },
        "planning": {
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "meta_agent_work",
                        "order": 1,
                        "name": "Agent Synthesis",
                        "description": (
                            "Analyze the user's requirement, search the registry, "
                            "decide REUSE/ADAPT/CREATE, and execute the full workflow "
                            "using meta-tools via REACT reasoning."
                        ),
                        "type": "ACTION",
                        "target": {
                            "prompt_template": (
                                "=== USER REQUIREMENT ===\n"
                                "{{instruction}}\n"
                                "=== END REQUIREMENT ===\n\n"
                                "Follow your workflow: introspect → analyze → search → "
                                "decide → build (if needed) → test → report.\n\n"
                                "Use your meta-tools to complete each step. "
                                "Present your recommendation before proceeding with creation."
                            ),
                        },
                        "required": True,
                    },
                ],
            },
        },
        "capabilities": {
            "tools": [
                {"tool_id": "meta_platform_introspect"},
                {"tool_id": "meta_registry_search"},
                {"tool_id": "meta_schema_validator"},
                {"tool_id": "meta_entity_creator"},
                {"tool_id": "meta_entity_executor"},
            ],
            "memory": {
                "enabled": True,
                "mode": "CORTEX",
                "cortex_config": {
                    "max_children": 12,
                    "page_size_tokens": 8000,
                    "context_budget_pct": 40,
                    "auto_checkpoint": True,
                    "resume_enabled": True,
                },
            },
        },
        "governance": {
            "max_cost_usd": 5.00,
            "timeout_ms": 300000,
            "max_recursion_depth": 2,
            "hitl_checkpoints": [
                {
                    "trigger_type": "COST_THRESHOLD",
                    "threshold": 3.0,
                    "message": "Meta-Agent execution cost approaching limit",
                    "auto_approve_on_timeout": True,
                    "timeout_ms": 60000,
                },
            ],
        },
        "io_contract": {
            "input_schema": {
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": "Natural language description of the desired agent",
                    },
                },
                "required": ["instruction"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string", "enum": ["REUSE", "ADAPT", "COMPOSE", "CREATE"]},
                    "entity_id": {"type": "string"},
                    "entity_name": {"type": "string"},
                    "summary": {"type": "string"},
                },
            },
        },
        "is_template": True,
    }
