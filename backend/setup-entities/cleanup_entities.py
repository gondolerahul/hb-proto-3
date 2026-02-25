"""
Cleanup script to delete all hierarchical entities from the database.
Run this before re-running setup_deep_research_entities.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from src.common.database import AsyncSessionLocal
from src.ai.models import (
    HierarchicalEntity, 
    ExecutionRun, 
    LLMInteractionLog, 
    ToolInteractionLog, 
    HumanApproval, 
    UsageLog,
    Document,
    DocumentChunk
)
from src.auth.models import Company


async def cleanup_all_entities():
    """Delete all hierarchical entities and their execution runs from ALL companies"""
    print("\n" + "="*60)
    print("Hierarchical Entities Cleanup (ALL COMPANIES)")
    print("="*60 + "\n")
    
    async with AsyncSessionLocal() as session:
        # Get all companies
        result = await session.execute(select(Company))
        companies = result.scalars().all()
        
        if not companies:
            print("❌ No companies found in database.")
            return
        
        print(f"Found {len(companies)} companies:\n")
        for company in companies:
            print(f"  - {company.name} (ID: {company.id})")
        
        # Count existing entities across all companies
        count_result = await session.execute(select(HierarchicalEntity))
        entities = count_result.scalars().all()
        entity_count = len(entities)
        
        if entity_count == 0:
            print("\n✓ No entities found in hierarchical_entities. Checking for orphan logs...\n")
        else:
            print(f"\nFound {entity_count} total entities to delete:\n")
        
        print("\n" + "-"*60)
        # Note: In an automated environment, specify "yes"
        print("This script will delete ALL data in the following tables:")
        print("- llm_interaction_logs")
        print("- tool_interaction_logs")
        print("- human_approvals")
        print("- usage_logs")
        print("- execution_runs")
        print("- document_chunks")
        print("- documents")
        print("- hierarchical_entities")
        
        # We'll skip confirmation for this turn since we're piping "yes" anyway
        
        # 1. Delete logs and dependencies
        print("\nDeleting dependent logs...")
        await session.execute(delete(LLMInteractionLog))
        await session.execute(delete(ToolInteractionLog))
        await session.execute(delete(HumanApproval))
        await session.execute(delete(UsageLog))
        await session.commit()
        print("✓ Deleted all logs")
        
        # 2. Delete execution runs
        print("Deleting execution runs...")
        # Note: execution_runs has a self-reference parent_run_id
        # We might need to nullify it or delete in specific order if not cascade
        # For simplicity, we can just delete all
        await session.execute(delete(ExecutionRun))
        await session.commit()
        print("✓ Deleted all execution runs")
        
        # 3. Delete documents
        print("Deleting documents...")
        await session.execute(delete(DocumentChunk))
        await session.execute(delete(Document))
        await session.commit()
        print("✓ Deleted all documents and chunks")
        
        # 4. Delete entities
        print("Deleting entities...")
        # Note: hierarchical_entities has a self-reference parent_id
        # We update them to null first to avoid FK issues if they exist
        from sqlalchemy import update
        await session.execute(update(HierarchicalEntity).values(parent_id=None))
        await session.commit()
        
        await session.execute(delete(HierarchicalEntity))
        await session.commit()
        print(f"✓ Deleted {entity_count} entities")
        
        print("\n" + "="*60)
        print("✅ Cleanup completed successfully!")
        print("="*60)
        print("\nYou can now run: python backend/setup_deep_research_entities.py")
        print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(cleanup_all_entities())
