import asyncio
from src.common.database import AsyncSessionLocal
from src.ai.models import ExecutionRun
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
import src.config.models # Needed for relationships
import src.auth.models # Needed for relationships


async def check():
    async with AsyncSessionLocal() as session:
        # Get latest execution
        result = await session.execute(
            select(ExecutionRun)
            .options(selectinload(ExecutionRun.llm_logs), selectinload(ExecutionRun.child_runs))
            .order_by(desc(ExecutionRun.created_at))
            .limit(1)
        )
        run = result.scalar_one_or_none()
        
        if run:
            print(f"Run ID: {run.id}")
            print(f"Status: {run.status}")
            print(f"Result: {run.result_data}")
            print(f"Error: {run.error_message}")
            print(f"LLM Logs: {len(run.llm_logs)}")
            for log in run.llm_logs:
                print(f"  - Model: {log.model_name}, Prompt Tokens: {log.prompt_tokens}")
            print(f"Child Runs: {len(run.child_runs)}")
            for child in run.child_runs:
                print(f"  - Child ID: {child.id}, Status: {child.status}")
        else:
            print("No executions found.")

if __name__ == "__main__":
    asyncio.run(check())
