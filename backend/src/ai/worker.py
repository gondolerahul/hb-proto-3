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
import httpx
import json
import re
import asyncio

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
    """Unified LLM call with support for reasoning modes and provider routing."""
    provider = config.get("model_provider", "openai")
    model = config.get("model_name", "gpt-4o")
    reasoning_mode = config.get("reasoning_mode", "REACT")
    temperature = config.get("temperature", 0.7)
    max_tokens = config.get("max_tokens")

    # Apply reasoning mode modifiers
    final_system = system_prompt
    if reasoning_mode == "REACT":
        final_system += "\nThink step-by-step and act iteratively using the provided tools."
    elif reasoning_mode == "REFLECTION":
        final_system += "\nAfter providing your answer, critique it for accuracy and completeness."

    async with httpx.AsyncClient(timeout=120.0) as client:
        start_time = datetime.utcnow()
        
        if provider == "openai":
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": final_system},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            )
        elif provider == "google":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{
                        "parts": [{"text": f"{final_system}\n\nUser: {user_prompt}"}]
                    }],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens
                    }
                }
            )
        else:
            raise Exception(f"Unsupported provider: {provider}")

        latency = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        if response.status_code != 200:
            raise Exception(f"{provider.capitalize()} API Error: {response.text}")
        
        data = response.json()
        if provider == "openai":
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return {
                "output": content,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "latency_ms": int(latency)
            }
        else: # google
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            usage = data.get("usageMetadata", {})
            return {
                "output": content,
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "latency_ms": int(latency)
            }

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
            plan = await self._get_reconciled_plan(entity, run.input_data)
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
        static_plan = entity.planning.get("static_plan", {}) if entity.planning else {}
        dynamic_config = entity.planning.get("dynamic_planning", {}) if entity.planning else {}
        
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
        logic_gate = entity.logic_gate or {}
        config = logic_gate.get("reasoning_config", {})
        if not config:
            # Fallback to legacy llm_config
            config = entity.llm_config or {"model_provider": "openai", "model_name": "gpt-4o"}
        
        # 2. Get API Key
        service_sku = config.get("model_name", "gpt-4o")
        api_key = await self.config_service.get_api_key_by_sku(run.company_id, service_sku) or \
                  await self.config_service.get_api_key_by_sku(run.company_id, f"{config.get('model_provider')}-api-key")
        
        if not api_key:
            raise Exception(f"API Key not found for {config.get('model_provider')}")

        # 3. Prepare Prompts
        system_prompt = entity.identity.get("persona", {}).get("system_prompt", "You are a helpful assistant.") if entity.identity else "You are a helpful assistant."
        user_prompt = step.target.prompt_template or str(context)
        user_prompt = parse_variables(user_prompt, context)

        # 4. Call LLM
        llm_result = await call_llm_unified(config, system_prompt, user_prompt, api_key)
        
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
        
        # Track usage/cost
        total_tokens = llm_result["prompt_tokens"] + llm_result["completion_tokens"]
        usage_log = await self.usage_service.log_usage(
            company_id=run.company_id,
            service_sku=config.get("model_name"),
            raw_quantity=float(total_tokens),
            execution_id=run.id
        )
        if usage_log:
            log.cost_usd = usage_log.calculated_cost
            run.total_cost_usd += usage_log.calculated_cost
            run.total_tokens += total_tokens

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
            gemini_api_key = await config_service.get_api_key_by_sku(document.company_id, "gemini-embedding-004") or \
                             await config_service.get_api_key_by_sku(document.company_id, "gemini-api-key")
                             
            if not gemini_api_key:
                 raise Exception("Gemini API Key not found")

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
    redis_settings = RedisSettings(host="localhost", port=6379)
