from arq import Worker
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import UUID
from datetime import datetime
from src.common.database import AsyncSessionLocal
from src.ai.models import ExecutionRun, HierarchicalEntity, LLMInteractionLog, EntityType, RunStatus, Document, DocumentChunk
from src.ai.schemas import RunStatus as RunStatusEnum
from src.config.service import ConfigService
from src.ai.usage_service import UsageService
import src.auth.models
import src.config.models
import httpx
import json
import re

# --- Helper Functions ---

def parse_variables(text: str, variables: dict) -> str:
    """Replaces {{variable}} in text with values from variables dict."""
    if not text:
        return ""
    def replace(match):
        key = match.group(1).strip()
        # Handle nested keys if needed, for now simple dict lookup
        val = variables
        for k in key.split('.'):
            if isinstance(val, dict):
                val = val.get(k, match.group(0))
            else:
                return match.group(0)
        return str(val)
    return re.sub(r'\{\{(.*?)\}\}', replace, text)

async def call_llm(provider: str, model: str, api_key: str, system_prompt: str, user_prompt: str) -> dict:
    async with httpx.AsyncClient(timeout=120.0) as client:
        start_time = datetime.utcnow()
        if provider == "openai":
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.7
                }
            )
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if response.status_code != 200:
                raise Exception(f"OpenAI API Error: {response.text}")
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return {
                "output": content,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "latency_ms": int(latency)
            }
            
        elif provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{
                        "parts": [{"text": f"{system_prompt}\n\nUser: {user_prompt}"}]
                    }]
                }
            )
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if response.status_code != 200:
                raise Exception(f"Gemini API Error: {response.text}")
                
            data = response.json()
            try:
                candidates = data.get("candidates", [])
                if not candidates:
                    content = "" # blocked block_reason?
                else:
                    content = candidates[0]["content"]["parts"][0]["text"]
                
                usage_metadata = data.get("usageMetadata", {})
                return {
                    "output": content,
                    "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
                    "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
                    "latency_ms": int(latency)
                }
            except (KeyError, IndexError) as e:
                raise Exception(f"Failed to parse Gemini response: {data}")
        
        else:
            raise Exception(f"Unsupported provider: {provider}")

# --- Execution Engine ---

class ExecutionEngine:
    def __init__(self, db: AsyncSessionLocal, redis_pool):
        self.db = db
        self.redis = redis_pool

    async def log_interaction(self, run_id: UUID, provider: str, model: str, input_prompt: str, response_data: dict):
        log = LLMInteractionLog(
            run_id=run_id,
            model_provider=provider,
            model_name=model,
            input_prompt=input_prompt,
            output_response=response_data["output"],
            prompt_tokens=response_data["prompt_tokens"],
            completion_tokens=response_data["completion_tokens"],
            latency_ms=response_data["latency_ms"]
        )
        self.db.add(log)
        await self.db.commit()

    async def execute_run(self, run_id: UUID) -> dict:
        # Fetch Run and Entity
        result = await self.db.execute(
            select(ExecutionRun)
            .options(selectinload(ExecutionRun.entity))
            .where(ExecutionRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise Exception(f"Run {run_id} not found")

        # Update Status
        run.status = RunStatus.RUNNING
        run.started_at = datetime.utcnow()
        await self.db.commit()
        
        # Publish Update
        channel = f"execution:{run.id}"
        await self.redis.publish(channel, json.dumps({"status": "RUNNING", "run_id": str(run.id)}))

        try:
            entity = run.entity
            output_data = {}
            
            if entity.type == EntityType.ACTION:
                output_data = await self._execute_action(run, entity)
            else:
                # Skill, Agent, Process share recursive logic
                output_data = await self._execute_composite(run, entity)

            # Success
            run.status = RunStatus.COMPLETED
            run.result_data = output_data
            run.completed_at = datetime.utcnow()
            await self.db.commit()
            await self.redis.publish(channel, json.dumps({"status": "COMPLETED", "result": output_data}))
            return output_data

        except Exception as e:
            # Failure
            run.status = RunStatus.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            await self.db.commit()
            await self.redis.publish(channel, json.dumps({"status": "FAILED", "error": str(e)}))
            raise e

    async def _execute_action(self, run: ExecutionRun, entity: HierarchicalEntity) -> dict:
        # 1. Prepare Prompt
        llm_config = entity.llm_config or {}
        provider = llm_config.get("provider", "openai")
        model = llm_config.get("model", "gpt-3.5-turbo")
        
        # Resolve API Key
        config_service = ConfigService(self.db)
        service_sku = f"{model}-in" if provider == "openai" else "gemini-api-key"
        api_key = await config_service.get_api_key_by_sku(run.company_id, service_sku) or \
                  await config_service.get_api_key_by_sku(run.company_id, f"{provider}-api-key")
        
        if not api_key:
            raise Exception(f"API Key not found for {provider}")

        # Static Plan as System Prompt
        static_plan = entity.static_plan or {}
        system_prompt = static_plan.get("prompt_template", "You are a helpful assistant.")
        # Variable substitution
        system_prompt = parse_variables(system_prompt, run.input_data or {})
        
        user_prompt = str(run.input_data)

        # 2. Call LLM
        llm_result = await call_llm(provider, model, api_key, system_prompt, user_prompt)
        
        # 3. Log Interaction
        await self.log_interaction(
            run.id, provider, model, 
            f"System: {system_prompt}\nUser: {user_prompt}", 
            llm_result
        )

        # 4. Handle Tool Calls (Simplified for now - just returning text)
        # TODO: Implement actual tool execution if LLM requests it
        
        return {"output": llm_result["output"]}

    async def _execute_composite(self, run: ExecutionRun, entity: HierarchicalEntity) -> dict:
        # Composite entities (Skill, Agent, Process) execute a PLAN.
        # 1. Reconcile Plan (Static vs Dynamic)
        # For Phase 2 MVP: usage static plan steps sequentially.
        
        static_plan = entity.static_plan or {}
        steps = static_plan.get("steps", [])
        
        context_state = run.input_data or {}
        run_results = {}

        for step in steps:
            step_id = step.get("id")
            step_entity_name = step.get("entity_name") # Referencing child entity by name? 
            # Or assume we have IDs in the plan. 
            # Ideally the plan has UUIDs or names that we resolve.
            # Let's assume for now steps describe what to do, and we might need to find an entity or use a prompt.
            
            # Simple implementation: Plan lists child Entity IDs or Names
            child_entity_id = step.get("entity_id")
            if not child_entity_id:
                # If no child entity, maybe it's just a reasoning step?
                continue
                
            # Create Child Run
            child_run = ExecutionRun(
                company_id=run.company_id,
                entity_id=UUID(child_entity_id),
                parent_run_id=run.id,
                input_data=context_state, # Pass current context
                status=RunStatus.PENDING
            )
            self.db.add(child_run)
            await self.db.commit()
            await self.db.refresh(child_run)
            
            # Recursive Execute
            # Note: We are recursing in the same worker process.
            child_result = await self.execute_run(child_run.id)
            
            # Update Context
            run_results[step_id] = child_result
            if isinstance(child_result, dict):
                context_state.update(child_result)

        return {"output": "Composite execution completed", "steps": run_results, "final_state": context_state}

# --- Arq Jobs ---

async def run_execution_recursive(ctx, run_id_str: str):
    run_id = UUID(run_id_str)
    import redis.asyncio as redis
    from src.common.config import settings
    
    redis_pool = redis.from_url(settings.REDIS_URL) # Use separate pool for pubsub interaction if needed
    
    async with AsyncSessionLocal() as db:
        engine = ExecutionEngine(db, redis_pool)
        await engine.execute_run(run_id)
    
    await redis_pool.close()

async def process_document(ctx, document_id_str: str, file_content: bytes, file_type: str, filename: str):
    # (Same implementation as before, just imports updated)
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
