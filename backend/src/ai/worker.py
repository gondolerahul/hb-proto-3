from arq import Worker
from arq.connections import RedisSettings
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from uuid import UUID, uuid4
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from src.common.database import AsyncSessionLocal
from src.ai.models import (
    ExecutionRun, HierarchicalEntity, LLMInteractionLog, EntityType, 
    RunStatus, Document, DocumentChunk, ToolInteractionLog, HumanApproval
)
from src.ai.schemas import (
    RunStatus as RunStatusEnum, EntityStatus, RelationshipType, 
    ReasoningMode, StepType, PlanStep, Planning, LogicGate, ContextPolicy
)
from src.config.service import ConfigService
from src.ai.usage_service import UsageService
from src.ai.tool_executor import ToolExecutor
import src.auth.models
import src.config.models
from google import genai
from google.genai import types
import asyncio
import json
import re
import copy

# --- Prompt Templates ---

DYNAMIC_PLANNER_PROMPT = """You are an AI planning agent. Given a user goal and available capabilities, generate a structured execution plan.

Output a JSON array of steps in this format:
[
  {
    "step_id": "step_1",
    "order": 1,
    "name": "Step Name",
    "description": "What this step accomplishes",
    "type": "ACTION",  // ACTION | TOOL_CALL | THOUGHT
    "target": {
      "prompt_template": "Template with {{variables}}",
      "tool_id": "tool_name_if_applicable"  
    },
    "required": true
  }
]

Rules:
1. If the goal is ambiguous, create a first step of type "THOUGHT" to ask the user for clarification
2. Break complex tasks into atomic, sequential steps
3. Use available tools when they can help accomplish the goal
4. Each step should have clear success criteria implied in its description
"""

DEFAULT_REVIEW_PROMPT = """You are a quality assurance critic. Review the output of an AI step execution.

Evaluate if the output meets the requirements described in the step description.

Respond with a JSON object:
{
  "passed": true/false,
  "reason": "Explanation of why it passed or failed",
  "suggestion": "If failed, specific suggestion for improvement"
}

Be strict but fair. Minor formatting issues are acceptable if the core task is accomplished.
"""

# --- Helper Functions ---

def parse_variables(text: str, variables: dict) -> str:
    """Replaces {{variable}} in text with values from variables dict."""
    if not text:
        return ""
    def replace(match):
        key = match.group(1).strip()
        val = variables
        for k in key.split('.'):
            if isinstance(val, dict):
                val = val.get(k, match.group(0))
            else:
                return match.group(0)
        return str(val)
    return re.sub(r'\{\{(.*?)\}\}', replace, text)


def build_sandwich_prompt(
    identity: str,
    tools: Optional[List[Dict]] = None,
    few_shot_examples: Optional[List[Dict[str, str]]] = None,
    context: Optional[str] = None,
    current_task: str = ""
) -> str:
    """
    Build structured prompt using the 'Sandwich Method'.
    
    Layers:
    1. Identity & Role (Who I am)
    2. Tools & Capabilities (What I can do)
    3. Few-Shot Examples (How I should behave)
    4. Context/History (What happened so far)
    5. Current Task (What I need to do now)
    """
    sections = []
    
    # Layer 1: Identity & Role
    sections.append(f"## Identity & Role\n{identity}")
    
    # Layer 2: Tools & Capabilities
    if tools:
        tool_descriptions = "\n".join([
            f"- **{t['name']}**: {t['description']}" for t in tools
        ])
        sections.append(f"## Available Tools\nYou can use the following tools:\n{tool_descriptions}")
    
    # Layer 3: Few-Shot Examples
    if few_shot_examples:
        example_text = "\n\n".join([
            f"**Scenario**: {ex.get('scenario', ex.get('input', ''))}\n**Response**: {ex.get('ideal_response', ex.get('output', ''))}"
            for ex in few_shot_examples
        ])
        sections.append(f"## Examples of Expected Behavior\n{example_text}")
    
    # Layer 4: Context/History
    if context:
        sections.append(f"## Previous Context\n{context}")
    
    # Layer 5: Current Task
    sections.append(f"## Current Task\n{current_task}")
    
    return "\n\n".join(sections)


def filter_context_for_step(
    step: PlanStep, 
    full_context: dict, 
    context_policy: Optional[Dict] = None
) -> dict:
    """
    Filter context based on step's explicit inputs and policy.
    
    Args:
        step: The plan step being executed
        full_context: Full execution context dictionary
        context_policy: Policy configuration from logic_gate
        
    Returns:
        Filtered context dictionary
    """
    if not context_policy:
        return full_context
    
    # Check for explicit input dependencies in step target
    if step.target and hasattr(step.target, 'input_dependencies'):
        deps = step.target.input_dependencies or []
        if deps:
            filtered = {"input": full_context.get("input")}
            for dep in deps:
                if dep in full_context:
                    filtered[dep] = full_context[dep]
            return filtered
    
    # Apply context policy
    policy_type = context_policy.get("type", "FULL")
    
    if policy_type == "LAST_N":
        n = context_policy.get("n", 3)
        keys = list(full_context.keys())
        # Always include 'input' and last N keys
        filtered = {"input": full_context.get("input")} if "input" in full_context else {}
        for k in keys[-n:]:
            filtered[k] = full_context[k]
        return filtered
    
    elif policy_type == "SLIDING_WINDOW":
        max_chars = context_policy.get("max_chars", 4000)
        filtered = {}
        total_chars = 0
        # Include from most recent first
        for k in reversed(list(full_context.keys())):
            v_str = str(full_context[k])
            if total_chars + len(v_str) <= max_chars:
                filtered[k] = full_context[k]
                total_chars += len(v_str)
            else:
                break
        return dict(reversed(list(filtered.items())))
    
    elif policy_type == "EXPLICIT":
        explicit_keys = context_policy.get("explicit_keys", [])
        return {k: full_context[k] for k in explicit_keys if k in full_context}
    
    # FULL - return everything
    return full_context


async def call_llm_unified(
    config: Dict[str, Any], 
    system_prompt: str, 
    user_prompt: str, 
    api_key: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    few_shot_examples: Optional[List[Dict[str, str]]] = None
) -> dict:
    """
    Unified LLM call using google-genai library with native function calling.
    
    Args:
        config: Model configuration (model_name, temperature, etc.)
        system_prompt: System/identity prompt
        user_prompt: User prompt/task
        api_key: Google API key
        tools: Optional list of tool schemas for function calling
        few_shot_examples: Optional few-shot examples for prompt injection
        
    Returns:
        Dict with 'output', 'function_calls', 'prompt_tokens', 'completion_tokens', 'latency_ms'
    """
    model = config.get("model_name", "gemini-2.0-flash")
    reasoning_mode = config.get("reasoning_mode", "REACT")
    temperature = config.get("temperature", 0.7)
    max_tokens = config.get("max_tokens")

    # Build dynamic prompt using Sandwich Method
    final_prompt = build_sandwich_prompt(
        identity=system_prompt,
        tools=tools,
        few_shot_examples=few_shot_examples,
        context=None,  # Context is already part of user_prompt if needed
        current_task=user_prompt
    )

    # Apply reasoning mode modifiers
    if reasoning_mode == "REACT":
        final_prompt += "\n\nThink step-by-step and act iteratively using the provided tools if available."
    elif reasoning_mode == "REFLECTION":
        final_prompt += "\n\nAfter providing your answer, critique it for accuracy and completeness."
    elif reasoning_mode == "CHAIN_OF_THOUGHT":
        final_prompt += "\n\nThink through this step by step before providing your final answer."

    start_time = datetime.utcnow()
    
    # Initialize Google GenAI client
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
    
    try:
        # Prepare contents
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=final_prompt)]
            )
        ]
        
        # Configure generation
        generate_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        
        # Build tool configuration if tools provided
        gemini_tools = None
        if tools:
            function_declarations = []
            for t in tools:
                try:
                    func_decl = types.FunctionDeclaration(
                        name=t["name"],
                        description=t.get("description", ""),
                        parameters=t.get("parameters")
                    )
                    function_declarations.append(func_decl)
                except Exception as e:
                    print(f"Warning: Could not create function declaration for {t.get('name')}: {e}")
            
            if function_declarations:
                gemini_tools = [types.Tool(function_declarations=function_declarations)]
        
        # Call Gemini via google-genai
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_config,
            tools=gemini_tools
        )
        
        latency = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Extract content, function calls, and usage info
        content = ""
        function_calls = []
        
        try:
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    # Check for function call
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        function_calls.append({
                            "name": fc.name,
                            "args": dict(fc.args) if fc.args else {}
                        })
                    # Check for text
                    elif hasattr(part, 'text') and part.text:
                        content += part.text
            
            # Fallback to .text property
            if not content and not function_calls:
                if response.text:
                    content = response.text
        except Exception as e:
            print(f"Warning: Error extracting response parts: {e}")
            if response.text:
                content = response.text

        # Inspect usage
        usage = response.usage_metadata
        prompt_tokens = usage.prompt_token_count if usage and usage.prompt_token_count is not None else 0
        completion_tokens = usage.candidates_token_count if usage and usage.candidates_token_count is not None else 0
        
        return {
            "output": content,
            "function_calls": function_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": int(latency)
        }
    except Exception as e:
        raise Exception(f"Gemini API Error (google-genai): {str(e)}")



# --- Execution Engine ---

class ExecutionEngine:
    def __init__(self, db: AsyncSessionLocal, redis_pool):
        self.db = db
        self.redis = redis_pool
        self.config_service = ConfigService(db)
        self.usage_service = UsageService(db)

    async def _execute_steps_dag(self, run, entity, steps: List[dict], context_state: dict) -> List[dict]:
        """Execute steps respecting dependencies, parallelizing independent ones."""
        
        # 1. Build Dependency Graph
        # Dependency is determined by explicit dependencies OR usage of {{variable}}
        step_deps = {s["step_id"]: set() for s in steps}
        step_map = {s["step_id"]: s for s in steps}
        
        for step in steps:
            s_id = step.get("step_id")
            # Explicit dependencies
            target = step.get("target", {})
            if target and "input_dependencies" in target:
                for dep in target.get("input_dependencies", []):
                     step_deps[s_id].add(dep)
            
            # Implicit dependencies (regex scan for {{step_name}})
            prompt = target.get("prompt_template", "")
            vars_needed = re.findall(r'\{\{(.*?)\}\}', prompt)
            for var in vars_needed:
                # var could be "step_1" or "step_1.output"
                base_var = var.split('.')[0]
                if base_var in step_map and base_var != s_id:
                    step_deps[s_id].add(base_var)

        # 2. Sequential Execution fallback if circular or not enough info? 
        # Actually standard topological sort execution
        
        completed = set()
        # Some steps might already be in context (from previous runs/restarts)
        for s in steps:
            if s["step_id"] in context_state and s["step_id"] != "input":
                completed.add(s["step_id"])
                
        results_map = {}
        ordered_results = []
        
        print(f"DAG Execution Plan for {len(steps)} steps. Dependencies: {step_deps}")

        while len(completed) < len(steps):
            # Find steps that are NOT completed AND all deps are satisfied
            ready = []
            for s in steps:
                s_id = s["step_id"]
                if s_id not in completed:
                    deps = step_deps[s_id]
                    if deps.issubset(completed) or not deps: # deps satisfied
                        ready.append(s)
            
            if not ready:
                remaining = [s["step_id"] for s in steps if s["step_id"] not in completed]
                print(f"Warning: Circular dependency or stall detected. Remaining: {remaining}. Switching to sequential for remainder.")
                # Execute remaining sequentially as fallback
                for s in steps:
                    if s["step_id"] not in completed:
                        step_obj = PlanStep(**s)
                        res = await self._execute_step_wrapper(run, entity, step_obj, context_state)
                        results_map[s["step_id"]] = res
                        completed.add(s["step_id"])
                break

            # Execute ready steps in parallel
            print(f"Executing batch: {[s['name'] for s in ready]}")
            
            tasks = []
            for s in ready:
                step_obj = PlanStep(**s)
                tasks.append(self._execute_step_wrapper(run, entity, step_obj, context_state))
                
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(batch_results):
                step_id = ready[i]["step_id"]
                
                if isinstance(result, Exception):
                    # Handle exception in parallel batch
                    print(f"Step {step_id} failed: {result}")
                    results_map[step_id] = {"error": str(result), "step": ready[i]["name"]}
                    # Fail the run?
                    raise result
                else:
                    results_map[step_id] = result
                    completed.add(step_id)
        
        # Return results in original order
        return [results_map.get(s["step_id"], {}) for s in steps]

    async def _execute_step_wrapper(self, run, entity, step_obj, context_state):
        """Wrapper to handle execution + review + context update for a single step."""
        # Execute Step
        step_result = await self._execute_step(run, entity, step_obj, context_state)
        
        # Review Mechanism
        if entity.logic_gate and entity.logic_gate.get("review_mechanism", {}).get("enabled"):
            step_result = await self._review_step_output(run, entity, step_obj, step_result)

        # Update Context immediately (thread-safety issue? AsyncSession is not thread-safe but we are in async loop)
        # context_state is a dict, modification is safe in single-threaded async loop
        if isinstance(step_result, dict) and "output" in step_result:
            context_state[step_obj.name] = step_result["output"]
            if step_obj.step_id:
                context_state[step_obj.step_id] = step_result["output"]
                
        return step_result

    # --- Updated execute_run using DAG ---

    async def execute_run(self, run_id: UUID) -> dict:
        # 1. Fetch Run and Entity
        result = await self.db.execute(
            select(ExecutionRun)
            .options(selectinload(ExecutionRun.entity))
            .where(ExecutionRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise Exception(f"Run {run_id} not found")

        entity = run.entity
        if not entity:
            raise Exception(f"Entity for run {run_id} not found")

        # 2. Update Status and Initialize Trace
        run.status = RunStatus.RUNNING
        run.started_at = datetime.utcnow()
        if not run.trace_id:
            run.trace_id = run.id
        await self.db.commit()
        
        # Publish Update
        channel = f"execution:{run.id}"
        await self.redis.publish(channel, json.dumps({"status": "RUNNING", "run_id": str(run.id)}))

        try:
            context_state = run.input_data or {}
            all_step_results = []
            
            # 3. Plan Generation/Reconciliation
            print(f"--- Starting Execution {run.id} for Entity {entity.name} ---")
            plan = await self._get_reconciled_plan(entity, run.input_data)
            steps = plan.get("steps", [])
            print(f"Plan reconciled. Steps to execute: {len(steps)}")
            run.dynamic_plan = plan # Store the actual plan used
            await self.db.commit()

            # 4. Execute Plan Steps (DAG)
            if self._has_parallel_steps(steps):
                all_step_results = await self._execute_steps_dag(run, entity, steps, context_state)
            else:
                 # Sequential fallback (optimized)
                for step in steps:
                    step_obj = PlanStep(**step)
                    step_result = await self._execute_step_wrapper(run, entity, step_obj, context_state)
                    all_step_results.append(step_result)
                    
                    if self._should_exit(step_obj, context_state):
                        break

            # 5. Finalize
            run.status = RunStatus.COMPLETED
            # Get output from last step
            last_step_name = steps[-1]["name"] if steps else None
            final_output = context_state.get(last_step_name) if last_step_name else "Success"
            
            run.result_data = {"output": final_output, "steps": all_step_results}
            run.context_state = context_state
            run.completed_at = datetime.utcnow()
            run.execution_time_ms = int((run.completed_at - run.started_at).total_seconds() * 1000)
            
            await self.db.commit()
            await self.redis.publish(channel, json.dumps({"status": "COMPLETED", "result": run.result_data}))
            return run.result_data

        except Exception as e:
            run.status = RunStatus.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            await self.db.commit()
            await self.redis.publish(channel, json.dumps({"status": "FAILED", "error": str(e)}))
            raise e
            
    def _has_parallel_steps(self, steps: List[dict]) -> bool:
        """Check if any steps can run in parallel (heuristic)."""
        # If any step relies on a step that is NOT the immediately preceding one, 
        # OR if multiple steps rely on the same parent.
        # For simplicity, if we have explicit dependencies, we assume DAG is intended.
        for s in steps:
            if s.get("target") and s["target"].get("input_dependencies"):
                return True
        return False

    async def _get_reconciled_plan(self, entity: HierarchicalEntity, input_data: dict) -> dict:
        """Merges static and dynamic plans based on strategy."""
        import copy
        planning = entity.planning or {}
        static_plan = copy.deepcopy(planning.get("static_plan", {})) or {}
        
        if "steps" not in static_plan:
            static_plan["steps"] = []
            
        # Fallback: If no steps and it is a leaf action/skill, add a default step
        if not static_plan["steps"] and entity.type in [EntityType.ACTION, EntityType.SKILL]:
            static_plan["steps"] = [{
                "step_id": "auto_generated",
                "order": 1,
                "name": "Execute",
                "description": f"Executing {entity.name}",
                "type": "ACTION",
                "target": {
                    "prompt_template": entity.description or "Process instruction: {{instruction}}"
                },
                "required": True
            }]

        dynamic_config = planning.get("dynamic_planning", {}) or {}
        
        if not dynamic_config.get("enabled"):
            return static_plan

        # Generate dynamic plan via LLM
        print(f"Generating dynamic plan for {entity.name} with input: {input_data}")
        
        # 1. Prepare planning prompt
        goal = input_data.get("input") or str(input_data)
        context = {
            "entity_name": entity.name,
            "entity_description": entity.description,
            "goal": goal,
            "tools": [t["name"] for t in entity.capabilities.get("tools", [])] if entity.capabilities else []
        }
        
        system_prompt = DYNAMIC_PLANNER_PROMPT
        user_prompt = f"Goal: {goal}\n\nAvailable Tools: {context['tools']}\n\nGenerate the execution plan."
        
        # 2. Call Planer LLM
        # Use a reasoning model if available for better planning
        api_key = await self.config_service.get_api_key_by_sku(entity.company_id, "gemini-2.0-flash") # Default
         
        try:
            plan_result = await call_llm_unified(
                config={"model_name": "gemini-2.0-flash", "temperature": 0.4},
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                api_key=api_key
            )
            
            # 3. Parse and Validate Plan
            output_text = plan_result["output"]
            
            # Extract JSON list
            json_str = output_text
            if "```json" in output_text:
                json_str = output_text.split("```json")[1].split("```")[0]
            elif "[" in output_text and "]" in output_text:
                json_str = output_text[output_text.find("["):output_text.rfind("]")+1]
                
            steps = json.loads(json_str)
            
            # Validate basic structure
            valid_steps = []
            for i, s in enumerate(steps):
                # Ensure GUID step_ids
                if not s.get("step_id"):
                    s["step_id"] = f"step_{i+1}_{str(uuid4())[:8]}"
                valid_steps.append(s)
                
            return {"steps": valid_steps}
            
        except Exception as e:
            print(f"Dynamic planning failed: {e}. Falling back to static plan.")
            # Add error step or fallback?
            return static_plan

    async def _execute_step(self, run: ExecutionRun, entity: HierarchicalEntity, step: PlanStep, context: dict) -> dict:
        """Routes execution to specific step handler."""
        if step.type == StepType.CHILD_ENTITY_INVOCATION:
            return await self._execute_child_invocation(run, step, context)
        elif step.type == StepType.TOOL_CALL:
            return await self._execute_tool_call(run, entity, step, context)
        elif step.type == StepType.THOUGHT or step.type == StepType.ACTION:
            return await self._execute_thought(run, entity, step, context)
        return {"error": "Unknown step type"}

    async def _execute_child_invocation(self, run: ExecutionRun, step: PlanStep, context: dict) -> dict:
        entity_id = step.target.entity_id if step.target else None
        if not entity_id:
            raise Exception(f"Child invocation missing entity_id for step {step.name}")
        
        # Create Child Run
        child_run = ExecutionRun(
            company_id=run.company_id,
            entity_id=step.target.entity_id,
            parent_run_id=run.id,
            trace_id=run.trace_id,
            input_data=context,
            status=RunStatus.PENDING
        )
        self.db.add(child_run)
        await self.db.commit()
        await self.db.refresh(child_run)
        
        # Recursive Execute
        child_result = await self.execute_run(child_run.id)
        
        # rollup metrics
        run.total_cost_usd += child_run.total_cost_usd or 0
        run.total_tokens += child_run.total_tokens or 0
        await self.db.commit()
        
        return {"step": step.name, "output": child_result.get("output"), "child_run_id": str(child_run.id)}

    async def _execute_tool_call(self, run: ExecutionRun, entity: HierarchicalEntity, step: PlanStep, context: dict) -> dict:
        tool_id = step.target.tool_id if step.target else None
        if not tool_id:
            raise Exception(f"Tool call missing tool_id for step {step.name}")
        
        start_time = datetime.utcnow()
        try:
            # Prepare inputs from context/variables
            raw_input = context.get("input") or str(context) # Fallback
            result = await ToolExecutor.execute_tools([{"tool": tool_id, "input": raw_input}])
            tool_result = result[0]
            
            latency = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Log Tool Call
            log = ToolInteractionLog(
                run_id=run.id,
                tool_id=tool_id,
                tool_name=tool_id,
                input_parameters={"input": raw_input},
                output_result=tool_result,
                success=tool_result.get("success", False),
                latency_ms=latency
            )
            self.db.add(log)
            await self.db.commit()
            
            return {"step": step.name, "output": tool_result.get("output")}
        except Exception as e:
            return {"step": step.name, "error": str(e), "success": False}

    async def _execute_thought(self, run: ExecutionRun, entity: HierarchicalEntity, step: PlanStep, context: dict) -> dict:
        # 1. Resolve Config
        print(f"Executing Thought/Action step: {step.name}")
        logic_gate = entity.logic_gate or {}
        config = logic_gate.get("reasoning_config", {})
        if not config:
            # Fallback to legacy llm_config
            config = entity.llm_config or {"model_provider": "google", "model_name": "gemini-2.0-flash"}
        
        # 2. Get API Key strategy (reused for other calls too)
        api_key = await self._get_api_key(run, config)
        
        # 3. Prepare Context & Prompts
        
        # Filter context based on policy
        filtered_context = filter_context_for_step(step, context, logic_gate.get("context_policy"))
        
        # Summarize if needed
        filtered_context = await self._maybe_summarize_context(run, entity, filtered_context, api_key)
        
        identity = entity.identity or {}
        system_prompt = identity.get("system_prompt", "You are a helpful assistant.")
        if "persona" in identity: # Handle nested persona structure
             system_prompt = identity.get("persona", {}).get("system_prompt", system_prompt)

        few_shot_examples = identity.get("few_shot_examples", [])
        if "persona" in identity:
             few_shot_examples = identity.get("persona", {}).get("few_shot_examples", few_shot_examples)

        # 4. Resolve Tools
        tools = None
        if entity.capabilities and entity.capabilities.get("tools"):
            # Get tool definitions for native function calling
            tool_ids = [t.get("tool_id") for t in entity.capabilities.get("tools", [])]
            tools = ToolExecutor.get_gemini_function_declarations(tool_ids)

        # 5. Prepare User Prompt
        input_vars = {**filtered_context}
        user_prompt = step.target.prompt_template if step.target and step.target.prompt_template else "{{input}}"
        user_prompt = parse_variables(user_prompt, input_vars)

        # 6. Call LLM
        print(f"Calling LLM {config.get('model_name')} via {config.get('model_provider')}...")
        
        llm_result = await call_llm_unified(
            config=config, 
            system_prompt=system_prompt, 
            user_prompt=user_prompt, 
            api_key=api_key,
            tools=tools,
            few_shot_examples=few_shot_examples
        )
        
        print(f"LLM Response: {llm_result['prompt_tokens']} prompt, {llm_result['completion_tokens']} completion")
        
        # 7. Handle Function Calls (if any)
        output = llm_result["output"]
        if llm_result.get("function_calls"):
            print(f"Executing {len(llm_result['function_calls'])} function calls...")
            tool_results = await ToolExecutor.execute_from_function_calls(llm_result["function_calls"])
            
            # Record tool logs
            for tr in tool_results:
                self.db.add(ToolInteractionLog(
                    run_id=run.id,
                    tool_id=tr["tool"],
                    tool_name=tr["tool"],
                    input_parameters=tr.get("args"),
                    output_result=tr.get("output"),
                    success=tr.get("success", False),
                    latency_ms=0 # Simplified
                ))
            
            # Format results and append to output
            output += ToolExecutor.format_tool_results(tool_results)
            
            # Optional: Feedback loop to LLM with tool results could be added here
        
        # 8. Log Interaction & Track Usage
        log = LLMInteractionLog(
            run_id=run.id,
            model_provider=config.get("model_provider"),
            model_name=config.get("model_name"),
            input_prompt=f"System: {system_prompt}\nUser: {user_prompt}",
            output_response=output,
            prompt_tokens=llm_result["prompt_tokens"],
            completion_tokens=llm_result["completion_tokens"],
            latency_ms=llm_result["latency_ms"],
            reasoning_mode=config.get("reasoning_mode")
        )
        self.db.add(log)
        
        # Track usage
        await self._log_usage(run, config, llm_result["prompt_tokens"], llm_result["completion_tokens"], log)

        await self.db.commit()
        return {"step": step.name, "output": output}

    async def _get_api_key(self, run, config):
        """Helper to resolve API Key using multiple strategies."""
        model_name = config.get("model_name", "gemini-2.0-flash")
        provider = config.get("model_provider", "google")
        
        # Strategy 1: Exact SKU match
        api_key = await self.config_service.get_api_key_by_sku(run.company_id, model_name)
        
        # Strategy 2: Try {model_name}-in SKU
        if not api_key:
            api_key = await self.config_service.get_api_key_by_sku(run.company_id, f"{model_name}-in")
            
        # Strategy 3: Pattern match
        if not api_key:
            api_key = await self.config_service.get_api_key_by_model(run.company_id, model_name)
            
        # Strategy 4: Provider generic key
        if not api_key:
            api_key = await self.config_service.get_api_key_by_sku(run.company_id, f"{provider}-api-key")
        
        # Strategy 5: Any key for this provider
        if not api_key:
            api_key = await self.config_service.get_api_key_by_provider(run.company_id, provider)
        
        if not api_key:
            raise Exception(f"API Key not found for {provider}/{model_name}")
            
        return api_key

    async def _log_usage(self, run, config, prompt_tokens, completion_tokens, log):
        """Helper to log usage stats."""
        input_sku = f"{config.get('model_name')}-in"
        output_sku = f"{config.get('model_name')}-out"
        
        input_usage = await self.usage_service.log_usage(
            company_id=run.company_id,
            service_sku=input_sku,
            raw_quantity=float(prompt_tokens),
            execution_id=run.id
        )
        
        output_usage = await self.usage_service.log_usage(
            company_id=run.company_id,
            service_sku=output_sku,
            raw_quantity=float(completion_tokens),
            execution_id=run.id
        )

        if input_usage:
            log.cost_usd += input_usage.calculated_cost
            run.total_cost_usd += input_usage.calculated_cost
        
        if output_usage:
            log.cost_usd += output_usage.calculated_cost
            run.total_cost_usd += output_usage.calculated_cost
            
        run.total_tokens += (prompt_tokens + completion_tokens)

    async def _maybe_summarize_context(self, run, entity, context_state: dict, api_key: str) -> dict:
        """Summarize context if it exceeds threshold."""
        context_str = json.dumps(context_state, default=str)
        threshold = entity.logic_gate.get("context_policy", {}).get("summarize_threshold", 8000)
        
        if len(context_str) <= threshold:
            return context_state
        
        print(f"Context size {len(context_str)} exceeds threshold {threshold}. Summarizing...")
        
        summary_result = await call_llm_unified(
            config={"model_name": "gemini-2.0-flash", "temperature": 0.3, "max_tokens": 500},
            system_prompt="Summarize the following execution context into a concise paragraph preserving key information.",
            user_prompt=context_str,
            api_key=api_key
        )
        
        return {"context_summary": summary_result["output"], "input": context_state.get("input")}

    async def _review_step_output(self, run, entity, step, result) -> dict:
        """Self-critique review mechanism with retry logic."""
        review_config = entity.logic_gate.get("review_mechanism", {})
        if not review_config.get("enabled"):
            return result
        
        # Don't review errors or tools for now
        if "error" in result:
            return result

        max_retries = entity.logic_gate.get("retry_policy", {}).get("max_retries", 3)
        review_prompt = review_config.get("review_prompt") or DEFAULT_REVIEW_PROMPT
        
        # Get independent API key for critic
        config = {"model_name": "gemini-2.0-flash", "temperature": 0.2} 
        api_key = await self._get_api_key(run, config)
        
        current_result = result
        
        for attempt in range(max_retries):
            print(f"Running Review/Critic Attempt {attempt+1}/{max_retries} for step {step.name}")
            
            # Call critic LLM
            critic_input = json.dumps({
                "step_description": step.description,
                "step_output": current_result.get("output"),
                "success_criteria": review_config.get("success_criteria", [])
            }, default=str)
            
            critic_result = await call_llm_unified(
                config=config,
                system_prompt=review_prompt,
                user_prompt=critic_input,
                api_key=api_key
            )
            
            # Parse critic response
            critique_text = critic_result["output"]
            passed = False
            reason = ""
            suggestion = ""
            
            try:
                # Try to parse JSON output from critic
                if "{" in critique_text and "}" in critique_text:
                    json_str = critique_text[critique_text.find("{"):critique_text.rfind("}")+1]
                    critique_json = json.loads(json_str)
                    passed = critique_json.get("passed", False)
                    reason = critique_json.get("reason", "")
                    suggestion = critique_json.get("suggestion", "")
                else:
                    # Fallback text parsing
                    passed = "passed" in critique_text.lower() and "true" in critique_text.lower()
                    reason = critique_text
            except Exception as e:
                print(f"Failed to parse critique: {e}")
                start_json = critique_text.find('{')
                end_json = critique_text.LastIndexOf('}')
                if start_json != -1 and end_json != -1:
                    try: 
                        critique_json = json.loads(critique_text[start_json: end_json+1])
                        passed = critique_json.get('passed', False)
                    except: pass

            if passed:
                return current_result
            
            # Retry with feedback if not passed
            if attempt < max_retries - 1:
                feedback = f"\n\nCRITIC FEEDBACK (Previous Attempt Failed): {reason}. Suggestion: {suggestion}\nPlease improve your response based on this."
                
                # Re-execute step context with feedback appended
                # This is a recursive call to _execute_thought but with modified context/prompt handling requires structural change
                # For MVP, we'll just append feedback to the next prompt or return the annotated result
                # Ideally we want to re-run the step.
                
                # Simplified Retry: Re-run the step with feedback in context
                # NOTE: This recursively calls _execute_step's logic
                retry_context = copy.deepcopy(run.context_state or {})
                retry_context["input"] = (retry_context.get("input", "") + feedback)
                
                # We need to know which type of step it was to retry correctly
                if step.type in [StepType.THOUGHT, StepType.ACTION]:
                    current_result = await self._execute_thought(run, entity, step, retry_context)
                elif step.type == StepType.TOOL_CALL:
                    # Tools usually static, maybe just retry?
                    current_result = await self._execute_tool_call(run, entity, step, retry_context)
                    
            else:
                # Handle failure per on_failure policy
                on_failure = review_config.get("on_failure", "RETRY")
                if on_failure == "ESCALATE":
                    current_result["requires_human_review"] = True
                    current_result["review_failure_reason"] = reason
                elif on_failure == "ABORT":
                    raise Exception(f"Step {step.name} failed verification after {max_retries} attempts: {reason}")
        
        return current_result

    def _should_exit(self, step: PlanStep, context: dict) -> bool:
        """Evaluates exit conditions for early termination."""
        for condition in step.exit_conditions:
            # Simplified evaluation
            if "error" in str(context.get(step.name, "")).lower():
                if condition.next_step == 'ESCALATE':
                    return True
        return False

# --- Arq Jobs ---

async def run_execution_recursive(ctx, run_id_str: str):
    run_id = UUID(run_id_str)
    import redis.asyncio as redis
    from src.common.config import settings
    
    redis_pool = redis.from_url(settings.REDIS_URL or "redis://localhost:6379")
    
    async with AsyncSessionLocal() as db:
        engine = ExecutionEngine(db, redis_pool)
        await engine.execute_run(run_id)
    
    await redis_pool.close()

async def process_document(ctx, document_id_str: str, file_content: bytes, file_type: str, filename: str):
    from src.ai.models import Document, DocumentChunk
    import io
    
    document_id = UUID(document_id_str)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == document_id))
        document = result.scalar_one_or_none()
        if not document:
            return
            
        try:
            if file_type == "txt":
                text = file_content.decode("utf-8")
            elif file_type == "pdf":
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            elif file_type == "docx":
                import docx
                doc = docx.Document(io.BytesIO(file_content))
                text = "\n".join([p.text for p in doc.paragraphs])
            else:
                text = file_content.decode("utf-8", errors="ignore")
                
            chunk_size = 500
            chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
            
            config_service = ConfigService(db)
            model_name = "gemini-embedding-004"
            
            # Strategy 1: Exact SKU match
            gemini_api_key = await config_service.get_api_key_by_sku(document.company_id, model_name)
            
            # Strategy 2: Pattern match (finds -in/-out SKUs)
            if not gemini_api_key:
                gemini_api_key = await config_service.get_api_key_by_model(document.company_id, model_name)
                
            # Strategy 3: Provider generic key
            if not gemini_api_key:
                gemini_api_key = await config_service.get_api_key_by_sku(document.company_id, "google-api-key") or \
                                 await config_service.get_api_key_by_sku(document.company_id, "gemini-api-key")
            
            # Strategy 4: Any key for google provider
            if not gemini_api_key:
                gemini_api_key = await config_service.get_api_key_by_provider(document.company_id, "google")
                             
            if not gemini_api_key:
                 raise Exception("Gemini API Key not found. Please ensure you have a 'google' integration configured.")

            async with httpx.AsyncClient() as client:
                for idx, chunk_text in enumerate(chunks):
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={gemini_api_key}"
                    response = await client.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        json={
                            "model": "models/text-embedding-004",
                            "content": {"parts": [{"text": chunk_text}]}
                        }
                    )
                    if response.status_code == 200:
                        embedding = response.json()["embedding"]["values"]
                        chunk = DocumentChunk(
                            document_id=document.id,
                            chunk_index=str(idx),
                            content=chunk_text,
                            embedding=embedding
                        )
                        db.add(chunk)
            
            document.upload_status = "completed"
            await db.commit()
            
        except Exception as e:
            document.upload_status = "failed"
            await db.commit()
            print(f"Doc processing failed: {e}")

class WorkerSettings:
    functions = [run_execution_recursive, process_document]
    
    # Parse Redis URL from environment config
    @staticmethod
    def _parse_redis_url():
        from src.common.config import settings
        from urllib.parse import urlparse
        parsed = urlparse(settings.REDIS_URL or "redis://localhost:6379")
        return parsed.hostname or "localhost", parsed.port or 6379
    
    _host, _port = _parse_redis_url.__func__()
    redis_settings = RedisSettings(host=_host, port=_port)

