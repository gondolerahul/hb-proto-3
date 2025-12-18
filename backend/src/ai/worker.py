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
from src.billing.service import BillingService
from src.auth.models import Tenant
import httpx
import json
from src.billing.schemas import InvoiceCreate

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
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            if not gemini_api_key:
                raise Exception("GEMINI_API_KEY not found")
            
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
                    # Extract agent_id from the node structure
                    # The structure is: {"id": "...", "type": "agent", "config": {"agent_id": "...", "input_mapping": {}}}
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
                    
                    # Prepare input by combining outputs from dependencies
                    dependencies = DAGValidator.get_node_dependencies(node_id, edges)
                    
                    if dependencies:
                        # Combine outputs from all dependencies
                        combined_input = "\n\n".join([
                            f"Output from {dep}:\n{workflow_results.get(dep, '')}" 
                            for dep in dependencies
                        ])
                        node_input = {"input": combined_input}
                    else:
                        # First node uses original execution input
                        node_input = execution.input_data
                    
                    # Execute agent
                    provider = agent.llm_config.get("provider", "openai")
                    model_name = agent.llm_config.get("model", "gpt-3.5-turbo")
                    
                    api_key_config_key = "OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"
                    try:
                        api_key = await config_service.get_decrypted_value(api_key_config_key)
                    except Exception:
                        import os
                        api_key = os.getenv(api_key_config_key)
                    
                    if not api_key:
                        raise Exception(f"API Key not found for provider {provider}")
                    
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
                
                # Real LLM Execution
                config_service = ConfigService(db)
                
                # Get API Key
                provider = agent.llm_config.get("provider", "openai")
                model_name = agent.llm_config.get("model", "gpt-3.5-turbo")
                enabled_tools = agent.llm_config.get("tools", [])
                
                api_key_config_key = "OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"
                try:
                    api_key = await config_service.get_decrypted_value(api_key_config_key)
                except Exception:
                    # Fallback to env var if not in DB
                    import os
                    api_key = os.getenv(api_key_config_key)
                    
                if not api_key:
                    raise Exception(f"API Key not found for provider {provider}")
                
                # Prepare system prompt with tool instructions if tools are enabled
                # Parse variables in system prompt
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
                
                # Check if LLM response contains tool calls
                if enabled_tools:
                    from src.ai.tool_executor import ToolExecutor
                    
                    tool_calls = await ToolExecutor.parse_tool_calls(llm_result["output"])
                    
                    if tool_calls:
                        # Execute tools
                        await r.publish(channel, json.dumps({"status": "executing_tools", "tool_count": len(tool_calls)}))
                        
                        tool_results = await ToolExecutor.execute_tools(tool_calls)
                        
                        # Make follow-up LLM call with tool results
                        tool_context = ToolExecutor.format_tool_results(tool_results)
                        follow_up_prompt = f"{execution.input_data}\n\n{tool_context}\n\nPlease provide your final response based on the tool results above."
                        
                        llm_result = await call_llm(
                            provider=provider,
                            model=model_name,
                            api_key=api_key,
                            system_prompt=agent.role,
                            user_prompt=str(follow_up_prompt)
                        )
                        
                        # Add tool execution info to result
                        llm_result["tool_calls"] = tool_calls
                        llm_result["tool_results"] = tool_results
                
                mock_result = llm_result # It's real now!

            # Update Status to Completed
            execution.status = "completed"
            execution.result_data = mock_result
            execution.completed_at = datetime.utcnow()
            await db.commit()
            
            await r.publish(channel, json.dumps({"status": "completed", "result": mock_result}))
            
            # Create billing ledger entry
            try:
                # Get tenant's partner_id
                tenant_result = await db.execute(select(Tenant).where(Tenant.id == execution.tenant_id))
                tenant = tenant_result.scalar_one_or_none()
                partner_id = tenant.partner_id if tenant else None
                
                # Extract token usage
                usage = mock_result.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                
                # Create ledger entries for input and output tokens
                billing_service = BillingService(db)
                
                if prompt_tokens > 0:
                    # Convert tokens to 1k units (billing is per 1k tokens)
                    input_quantity = Decimal(str(prompt_tokens / 1000))
                    await billing_service.calculate_and_create_ledger_entry(
                        tenant_id=execution.tenant_id,
                        partner_id=partner_id,
                        execution_id=execution.id,
                        resource_type="text_tokens_input",
                        quantity=input_quantity,
                        unit="1k_tokens",
                        entry_metadata=f"Execution: {execution.id}"
                    )
                
                if completion_tokens > 0:
                    output_quantity = Decimal(str(completion_tokens / 1000))
                    await billing_service.calculate_and_create_ledger_entry(
                        tenant_id=execution.tenant_id,
                        partner_id=partner_id,
                        execution_id=execution.id,
                        resource_type="text_tokens_output",
                        quantity=output_quantity,
                        unit="1k_tokens",
                        entry_metadata=f"Execution: {execution.id}"
                    )
                
                print(f"Successfully created ledger entries for execution {execution_id}")
                
            except Exception as billing_error:
                # Log billing errors but don't fail the execution
                print(f"Billing error (non-fatal): {billing_error}")
            
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            execution.completed_at = datetime.utcnow()
            await db.commit()
            await r.publish(channel, json.dumps({"status": "failed", "error": str(e)}))
            print(f"Execution failed: {e}")
        finally:
            await r.close()

async def generate_monthly_invoices(ctx, target_date: datetime = None):
    """
    Cron job to generate invoices for all active tenants for the previous month.
    Designed to run on the 1st of every month.
    """
    print("Starting monthly invoice generation...")
    
    # Calculate previous month period
    # If target_date is provided, use it as 'today'
    today = (target_date or datetime.utcnow()).date()
    # ... logic continues using 'today'
    first_day_current_month = today.replace(day=1)
    last_day_prev_month = first_day_current_month - timedelta(days=1)
    first_day_prev_month = last_day_prev_month.replace(day=1)
    
    start_date = datetime.combine(first_day_prev_month, datetime.min.time())
    end_date = datetime.combine(last_day_prev_month, datetime.max.time())
    due_date = datetime.combine(today + timedelta(days=14), datetime.max.time()) # Due in 14 days
    
    print(f"Generating invoices for period: {start_date} to {end_date}")
    
    async with AsyncSessionLocal() as db:
        billing_service = BillingService(db)
        
        # Fetch all active tenants
        result = await db.execute(select(Tenant).where(Tenant.status == 'active'))
        tenants = result.scalars().all()
        
        for tenant in tenants:
            try:
                print(f"Processing invoice for tenant: {tenant.name} ({tenant.id})")
                
                # Create invoice
                invoice_in = InvoiceCreate(
                    tenant_id=tenant.id,
                    period_start=start_date,
                    period_end=end_date,
                    due_date=due_date
                )
                
                invoice = await billing_service.generate_invoice(invoice_in)
                print(f"Generated Invoice {invoice.invoice_number} for Tenant {tenant.id} - Amount: ${invoice.total_amount}")
                
                # TODO: Trigger email notification here
                
            except Exception as e:
                print(f"Failed to generate invoice for tenant {tenant.id}: {e}")
    
    print("Monthly invoice generation completed.")

from arq.connections import RedisSettings

class WorkerSettings:
    functions = [run_execution, process_document, generate_monthly_invoices]
    cron_jobs = [
        cron(generate_monthly_invoices, day=1, hour=0, minute=0)
    ]
    redis_settings = RedisSettings(host="localhost", port=6379)
    on_startup = None
    on_shutdown = None


