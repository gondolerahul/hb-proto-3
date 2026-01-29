from arq import Worker
from arq.connections import RedisSettings
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from uuid import UUID, uuid4
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from src.common.database import AsyncSessionLocal
from src.ai.models import (
    ExecutionRun, HierarchicalEntity, LLMInteractionLog, EntityType, 
    RunStatus, Document, DocumentChunk, ToolInteractionLog, HumanApproval
)
from src.ai.schemas import (
    RunStatus as RunStatusEnum, EntityStatus, RelationshipType, 
    ReasoningMode, StepType, PlanStep, Planning, LogicGate
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

async def call_llm_unified(config: Dict[str, Any], system_prompt: str, user_prompt: str, api_key: str) -> dict:
    """Unified LLM call using google-genai library."""
    model = config.get("model_name", "gemini-3-flash-preview")
    reasoning_mode = config.get("reasoning_mode", "REACT")
    temperature = config.get("temperature", 0.7)
    max_tokens = config.get("max_tokens")

    # Apply reasoning mode modifiers
    final_system = system_prompt
    if reasoning_mode == "REACT":
        final_system += "\nThink step-by-step and act iteratively using the provided tools."
    elif reasoning_mode == "REFLECTION":
        final_system += "\nAfter providing your answer, critique it for accuracy and completeness."

    start_time = datetime.utcnow()
    
    # Initialize Google GenAI client
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
    
    try:
        # Prepare contents
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"{final_system}\n\nUser: {user_prompt}")]
            )
        ]
        
        # Configure generation
        generate_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        
        # Call Gemini via google-genai
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_config
        )
        
        latency = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Extract content and usage info
        content = response.text
        usage = response.usage_metadata
        
        return {
            "output": content,
            "prompt_tokens": usage.prompt_token_count if usage else 0,
            "completion_tokens": usage.candidates_token_count if usage else 0,
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
            print(f"Plan reconciled. Steps to execute: {len(plan.get('steps', []))}")
            run.dynamic_plan = plan # Store the actual plan used
            await self.db.commit()

            # 4. Execute Plan Steps
            for step in plan.get("steps", []):
                step_obj = PlanStep(**step)
                
                # HITL Checkpoint (Simplified for MVP)
                # await self._check_hitl_checkpoint(run, step_obj)

                # Execute Step
                step_result = await self._execute_step(run, entity, step_obj, context_state)
                
                # Review Mechanism
                if entity.logic_gate and entity.logic_gate.get("review_mechanism", {}).get("enabled"):
                    step_result = await self._review_step_output(run, entity, step_obj, step_result)

                all_step_results.append(step_result)
                
                # Update Context
                if isinstance(step_result, dict) and "output" in step_result:
                    context_state[step_obj.name] = step_result["output"]
                
                # Check Exit Conditions
                if self._should_exit(step_obj, context_state):
                    break

            # 5. Finalize
            run.status = RunStatus.COMPLETED
            run.result_data = {"output": context_state.get(plan["steps"][-1]["name"]) if plan["steps"] else "Success", "steps": all_step_results}
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

        # Generate dynamic plan via LLM (Simplified for MVP)
        # TODO: Implement full LLM-based planning reconciliation
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
        if not step.target.entity_id:
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
        tool_id = step.target.tool_id
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
            config = entity.llm_config or {"model_provider": "google", "model_name": "gemini-3-flash-preview"}
        
        # 2. Get API Key - try multiple resolution strategies
        model_name = config.get("model_name", "gemini-3-flash-preview")
        provider = config.get("model_provider", "google")
        print(f"DEBUG: Resolving API Key for Company {run.company_id}, Model: {model_name}, Provider: {provider}")
        
        # Strategy 1: Exact SKU match
        api_key = await self.config_service.get_api_key_by_sku(run.company_id, model_name)
        
        # Strategy 2: Try {model_name}-in SKU (billing SKUs)
        if not api_key:
            api_key = await self.config_service.get_api_key_by_sku(run.company_id, f"{model_name}-in")
            
        # Strategy 3: Pattern match - any SKU starting with model name
        if not api_key:
            api_key = await self.config_service.get_api_key_by_model(run.company_id, model_name)
            
        # Strategy 4: Provider generic key e.g. google-api-key
        if not api_key:
            api_key = await self.config_service.get_api_key_by_sku(run.company_id, f"{provider}-api-key")
        
        # Strategy 5: Any key for this provider
        if not api_key:
            api_key = await self.config_service.get_api_key_by_provider(run.company_id, provider)
        
        if not api_key:
            raise Exception(f"API Key not found for {provider}. Checked: {model_name}, {model_name}-in, pattern:{model_name}*, {provider}-api-key, provider:{provider}")

        # 3. Prepare Prompts
        system_prompt = entity.identity.get("persona", {}).get("system_prompt", "You are a helpful assistant.") if entity.identity else "You are a helpful assistant."
        user_prompt = step.target.prompt_template or str(context)
        user_prompt = parse_variables(user_prompt, context)

        # 4. Call LLM
        print(f"Calling LLM {config.get('model_name')} via {config.get('model_provider')}...")
        llm_result = await call_llm_unified(config, system_prompt, user_prompt, api_key)
        print(f"LLM Response received ({llm_result['prompt_tokens']} prompt, {llm_result['completion_tokens']} completion)")
        
        # 5. Log Interaction & Track Usage
        log = LLMInteractionLog(
            run_id=run.id,
            model_provider=config.get("model_provider"),
            model_name=config.get("model_name"),
            input_prompt=f"System: {system_prompt}\nUser: {user_prompt}",
            output_response=llm_result["output"],
            prompt_tokens=llm_result["prompt_tokens"],
            completion_tokens=llm_result["completion_tokens"],
            latency_ms=llm_result["latency_ms"],
            reasoning_mode=config.get("reasoning_mode")
        )
        self.db.add(log)
        
        # Track usage/cost for input and output separately
        input_sku = f"{config.get('model_name')}-in"
        output_sku = f"{config.get('model_name')}-out"
        
        # Log input usage
        input_usage = await self.usage_service.log_usage(
            company_id=run.company_id,
            service_sku=input_sku,
            raw_quantity=float(llm_result["prompt_tokens"]),
            execution_id=run.id
        )
        
        # Log output usage
        output_usage = await self.usage_service.log_usage(
            company_id=run.company_id,
            service_sku=output_sku,
            raw_quantity=float(llm_result["completion_tokens"]),
            execution_id=run.id
        )

        if input_usage:
            log.cost_usd += input_usage.calculated_cost
            run.total_cost_usd += input_usage.calculated_cost
        
        if output_usage:
            log.cost_usd += output_usage.calculated_cost
            run.total_cost_usd += output_usage.calculated_cost
            
        run.total_tokens += (llm_result["prompt_tokens"] + llm_result["completion_tokens"])

        await self.db.commit()
        return {"step": step.name, "output": llm_result["output"]}

    async def _review_step_output(self, run, entity, step, result) -> dict:
        """Self-critique review mechanism."""
        # TODO: Implement full self-review logic with LLM feedback loop
        return result

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

