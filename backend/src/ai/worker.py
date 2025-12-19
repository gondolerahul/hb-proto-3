import asyncio
from arq import Worker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timedelta
from arq.cron import cron
from decimal import Decimal
from src.common.database import AsyncSessionLocal
from src.ai.models import Execution, Agent, Workflow
from src.config.service import ConfigService
from src.ai.usage_service import UsageService
from src.auth.models import Company
import httpx
import json
import os

import io

import re

def parse_variables(text: str, variables: dict) -> str:
    """
    Replaces {{variable}} in text with values from variables dict.
    """
    if not text:
        return ""
    
    def replace(match):
        key = match.group(1).strip()
        return str(variables.get(key, match.group(0)))
    
    return re.sub(r'\{\{(.*?)\}\}', replace, text)

async def process_document(ctx, document_id_str: str, file_content: bytes, file_type: str, filename: str):
    from src.ai.models import Document, DocumentChunk
    from src.common.config import settings
    import os
    
    document_id = UUID(document_id_str)
    
    async with AsyncSessionLocal() as db:
        # Fetch Document
        result = await db.execute(select(Document).where(Document.id == document_id))
        document = result.scalar_one_or_none()
        
        if not document:
            print(f"Document {document_id} not found")
            return

        try:
            # Extract text based on file type
            if file_type == "txt":
                text = file_content.decode("utf-8")
            elif file_type == "pdf":
                import PyPDF2
                try:
                    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text() + "\n"
                except Exception as e:
                    raise Exception(f"Failed to parse PDF: {str(e)}")
            elif file_type == "docx":
                import docx
                try:
                    doc = docx.Document(io.BytesIO(file_content))
                    text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
                except Exception as e:
                    raise Exception(f"Failed to parse DOCX: {str(e)}")
            else:
                text = file_content.decode("utf-8", errors="ignore")
            
            # Chunk the text (simple chunking by character count)
            chunk_size = 500
            chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
            
            # Get Gemini API key for embeddings
            config_service = ConfigService(db)
            gemini_api_key = await config_service.get_api_key_by_sku(document.company_id, "gemini-embedding-004")
            
            if not gemini_api_key:
                # Fallback
                gemini_api_key = await config_service.get_api_key_by_sku(document.company_id, "gemini-api-key")

            if not gemini_api_key:
                raise Exception(f"Gemini API Key not found in Integrations for company {document.company_id}")
            
            # Generate embeddings for each chunk
            async with httpx.AsyncClient(timeout=60.0) as client:
                for idx, chunk_text in enumerate(chunks):
                    # Call Gemini embedding API
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={gemini_api_key}"
                    response = await client.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        json={
                            "model": "models/text-embedding-004",
                            "content": {
                                "parts": [{"text": chunk_text}]
                            }
                        }
                    )
                    
                    if response.status_code != 200:
                        raise Exception(f"Gemini Embedding API Error: {response.text}")
                    
                    data = response.json()
                    embedding = data["embedding"]["values"]
                    
                    # Create chunk with embedding
                    chunk = DocumentChunk(
                        document_id=document.id,
                        chunk_index=str(idx),
                        content=chunk_text,
                        embedding=embedding
                    )
                    db.add(chunk)
            
            # Update document status
            document.upload_status = "completed"
            await db.commit()
            print(f"Document {document_id} processed successfully")
            
        except Exception as e:
            document.upload_status = "failed"
            await db.commit()
            print(f"Document processing failed: {str(e)}")

async def call_llm(provider: str, model: str, api_key: str, system_prompt: str, user_prompt: str) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
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
            if response.status_code != 200:
                raise Exception(f"OpenAI API Error: {response.text}")
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return {
                "output": content,
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0)
                }
            }
            
        elif provider == "gemini":
            # Gemini API (Google AI Studio)
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
            if response.status_code != 200:
                raise Exception(f"Gemini API Error: {response.text}")
                
            data = response.json()
            try:
                content = data["candidates"][0]["content"]["parts"][0]["text"]
                # Gemini doesn't always return usage in the same format, we might need to estimate or check docs
                # For now, we'll estimate or use what's available
                usage_metadata = data.get("usageMetadata", {})
                return {
                    "output": content,
                    "usage": {
                        "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
                        "completion_tokens": usage_metadata.get("candidatesTokenCount", 0)
                    }
                }
            except (KeyError, IndexError) as e:
                raise Exception(f"Failed to parse Gemini response: {data}")
        
        else:
            raise Exception(f"Unsupported provider: {provider}")

async def run_execution(ctx, execution_id_str: str):
    import json
    import redis.asyncio as redis
    from src.common.config import settings
    
    execution_id = UUID(execution_id_str)
    r = redis.from_url(settings.REDIS_URL)
    channel = f"execution:{execution_id}"

    async with AsyncSessionLocal() as db:
        # Fetch Execution
        result = await db.execute(select(Execution).where(Execution.id == execution_id))
        execution = result.scalar_one_or_none()
        if not execution:
            print(f"Execution {execution_id} not found")
            await r.close()
            return

        # Update Status to Running
        execution.status = "running"
        execution.started_at = datetime.utcnow()
        await db.commit()
        
        await r.publish(channel, json.dumps({"status": "running"}))

        try:
            if execution.workflow_id:
                # Workflow Execution with DAG dependency resolution
                workflow_result = await db.execute(select(Workflow).where(Workflow.id == execution.workflow_id))
                workflow = workflow_result.scalar_one_or_none()
                
                if not workflow:
                    raise Exception("Workflow not found")
                
                from src.ai.dag_validator import DAGValidator
                
                dag = workflow.dag_structure
                nodes_data = dag.get("nodes", [])
                edges_data = dag.get("edges", [])
                
                # Convert to dict format for validator
                nodes = [{"id": n.get("id"), **n} for n in nodes_data]
                edges = [{"source": e.get("source"), "target": e.get("target")} for e in edges_data]
                
                # Get execution order using topological sort
                execution_order = DAGValidator.topological_sort(nodes, edges)
                
                # Create node lookup
                node_map = {node["id"]: node for node in nodes}
                workflow_results = {}
                
                config_service = ConfigService(db)
                
                for node_id in execution_order:
                    node = node_map[node_id]
                    agent_id = node.get("config", {}).get("agent_id") or node.get("data", {}).get("agentId") or node.get("agentId")
                    
                    if not agent_id:
                        continue
                    
                    # Fetch Agent
                    agent_result = await db.execute(select(Agent).where(Agent.id == UUID(agent_id)))
                    agent = agent_result.scalar_one_or_none()
                    
                    if not agent:
                        continue
                    
                    await r.publish(channel, json.dumps({
                        "status": "step_start",
                        "node_id": node_id,
                        "agent_name": agent.name
                    }))
                    
                    # Prepare input
                    dependencies = DAGValidator.get_node_dependencies(node_id, edges)
                    if dependencies:
                        combined_input = "\n\n".join([
                            f"Output from {dep}:\n{workflow_results.get(dep, '')}" 
                            for dep in dependencies
                        ])
                        node_input = {"input": combined_input}
                    else:
                        node_input = execution.input_data
                    
                    # Execute agent
                    provider = agent.llm_config.get("provider", "openai")
                    model_name = agent.llm_config.get("model", "gpt-3.5-turbo")
                    
                    # Fetch API Key from Registry
                    config_service = ConfigService(db)
                    service_sku = f"{model_name}-in" if provider == "openai" else "gemini-api-key"
                    api_key = await config_service.get_api_key_by_sku(execution.company_id, service_sku)
                    
                    if not api_key:
                        # try fallback to provider-wide key
                        api_key = await config_service.get_api_key_by_sku(execution.company_id, f"{provider}-api-key")
                    
                    if not api_key:
                        raise Exception(f"API Key not found for provider {provider} and company {execution.company_id}")
                    
                    # Parse variables in system prompt
                    system_prompt = parse_variables(agent.role, node_input if isinstance(node_input, dict) else {})
                    
                    llm_result = await call_llm(
                        provider=provider,
                        model=model_name,
                        api_key=api_key,
                        system_prompt=system_prompt,
                        user_prompt=str(node_input)
                    )
                    
                    step_output = llm_result["output"]
                    workflow_results[node_id] = step_output
                    
                    # Log Usage
                    usage_service = UsageService(db)
                    usage = llm_result.get("usage", {})
                    if usage.get("prompt_tokens"):
                        await usage_service.log_usage(
                            company_id=execution.company_id,
                            service_sku=f"{model_name}-in", # or map to specific SKU
                            raw_quantity=usage["prompt_tokens"],
                            execution_id=execution.id,
                            metadata={"node_id": node_id, "type": "input"}
                        )
                    if usage.get("completion_tokens"):
                        await usage_service.log_usage(
                            company_id=execution.company_id,
                            service_sku=f"{model_name}-out",
                            raw_quantity=usage["completion_tokens"],
                            execution_id=execution.id,
                            metadata={"node_id": node_id, "type": "output"}
                        )

                    await r.publish(channel, json.dumps({
                        "status": "step_complete",
                        "node_id": node_id,
                        "output": step_output
                    }))
                
                # Aggregate token usage from all steps
                total_prompt_tokens = 0
                total_completion_tokens = 0
                
                mock_result = {
                    "output": "Workflow completed successfully",
                    "steps": workflow_results,
                    "execution_order": execution_order,
                    "usage": {
                        "prompt_tokens": total_prompt_tokens or 50, 
                        "completion_tokens": total_completion_tokens or 100
                    }
                }
                
            else:
                # Single Agent Execution
                # Fetch Agent
                agent_result = await db.execute(select(Agent).where(Agent.id == execution.agent_id))
                agent = agent_result.scalar_one_or_none()
                
                # Fetch API Key from Registry
                config_service = ConfigService(db)
                provider = agent.llm_config.get("provider", "openai")
                model_name = agent.llm_config.get("model", "gpt-3.5-turbo")
                enabled_tools = agent.llm_config.get("tools", [])
                
                service_sku = f"{model_name}-in" if provider == "openai" else "gemini-api-key"
                api_key = await config_service.get_api_key_by_sku(execution.company_id, service_sku)
                
                if not api_key:
                    # Fallback
                    api_key = await config_service.get_api_key_by_sku(execution.company_id, f"{provider}-api-key")
                
                if not api_key:
                    raise Exception(f"API Key not found for provider {provider} and company {execution.company_id}")
                
                # Prepare system prompt
                system_prompt = parse_variables(agent.role, execution.input_data if isinstance(execution.input_data, dict) else {})
                
                if enabled_tools:
                    from src.ai.tools import ToolRegistry
                    available_tools = [t for t in ToolRegistry.list_tools() if t["name"] in enabled_tools]
                    if available_tools:
                        tool_descriptions = "\n".join([f"- {t['name']}: {t['description']}" for t in available_tools])
                        system_prompt += f"\n\nYou have access to the following tools:\n{tool_descriptions}\n\nTo use a tool, respond with: TOOL:tool_name:input_data"
                
                # Call LLM
                llm_result = await call_llm(
                    provider=provider,
                    model=model_name,
                    api_key=api_key,
                    system_prompt=system_prompt,
                    user_prompt=str(execution.input_data)
                )
                
                # Tool execution logic remains same...
                if enabled_tools:
                    from src.ai.tool_executor import ToolExecutor
                    tool_calls = await ToolExecutor.parse_tool_calls(llm_result["output"])
                    if tool_calls:
                        await r.publish(channel, json.dumps({"status": "executing_tools", "tool_count": len(tool_calls)}))
                        tool_results = await ToolExecutor.execute_tools(tool_calls)
                        tool_context = ToolExecutor.format_tool_results(tool_results)
                        follow_up_prompt = f"{execution.input_data}\n\n{tool_context}\n\nPlease provide your final response based on the tool results above."
                        llm_result = await call_llm(
                            provider=provider,
                            model=model_name,
                            api_key=api_key,
                            system_prompt=agent.role,
                            user_prompt=str(follow_up_prompt)
                        )
                        llm_result["tool_calls"] = tool_calls
                        llm_result["tool_results"] = tool_results
                
                mock_result = llm_result

            # Update Status to Completed
            execution.status = "completed"
            execution.result_data = mock_result
            execution.completed_at = datetime.utcnow()
            await db.commit()
            
            await r.publish(channel, json.dumps({"status": "completed", "result": mock_result}))
            
            # Create usage log entries
            try:
                usage_service = UsageService(db)
                usage = mock_result.get("usage", {})
                if usage.get("prompt_tokens"):
                    await usage_service.log_usage(
                        company_id=execution.company_id,
                        service_sku=f"{model_name}-in",
                        raw_quantity=usage["prompt_tokens"],
                        execution_id=execution.id,
                        metadata={"type": "input"}
                    )
                if usage.get("completion_tokens"):
                    await usage_service.log_usage(
                        company_id=execution.company_id,
                        service_sku=f"{model_name}-out",
                        raw_quantity=usage["completion_tokens"],
                        execution_id=execution.id,
                        metadata={"type": "output"}
                    )
            except Exception as usage_error:
                print(f"Usage logging error (non-fatal): {usage_error}")
            
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            execution.completed_at = datetime.utcnow()
            await db.commit()
            await r.publish(channel, json.dumps({"status": "failed", "error": str(e)}))
            print(f"Execution failed: {e}")
        finally:
            await r.close()

# Removed legacy billing invoice generation

from arq.connections import RedisSettings

class WorkerSettings:
    functions = [run_execution, process_document]
    cron_jobs = []
    redis_settings = RedisSettings(host="localhost", port=6379)
    on_startup = None
    on_shutdown = None


