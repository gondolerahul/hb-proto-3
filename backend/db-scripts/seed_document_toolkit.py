"""
seed_document_toolkit.py — Seed the Document Generation Toolkit entities.

Creates the Document Director (PROCESS) and its 5 child entities for a
given company. Follows the same pattern as seed_admin_user.py.

Usage:
    python backend/db-scripts/seed_document_toolkit.py \\
        --company-id <uuid> --user-id <uuid> [--dry-run]
"""
import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from document_toolkit_prompts import (
    CONTENT_ARCHITECT_PROMPT,
    DOCUMENT_DIRECTOR_PROMPT,
    DOCUMENT_RENDERER_PROMPT,
    QUALITY_INSPECTOR_PROMPT,
    REVISION_AGENT_PROMPT,
    VISUAL_ASSET_CREATOR_PROMPT,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ─── Entity Templates ──────────────────────────────────────────────────────

def _content_architect() -> dict:
    return {
        "name": "content-architect",
        "display_name": "Content Architect",
        "description": "Analyzes document requests and produces structured Document Blueprint JSON for downstream agents.",
        "goal": "Transform a natural language document request into a comprehensive, structured Blueprint that fully specifies content, layout, visuals, and theme.",
        "type": "AGENT",
        "version": "1.0.0",
        "status": "ACTIVE",
        "tags": ["document-generation", "content-planning"],
        "identity": {
            "role": "Senior Information Designer",
            "system_prompt": CONTENT_ARCHITECT_PROMPT,
            "personality": {"tone": "analytical", "verbosity": "moderate", "formality": "semi-formal"},
        },
        "logic_gate": {
            "reasoning_config": {
                "reasoning_mode": "REACT",
                "temperature": 0.4,
                "task_type": "text_generation",
            },
            "context_policy": {"type": "FULL"},
        },
        "planning": {
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "step_1", "order": 1,
                    "name": "Produce Document Blueprint",
                    "description": "Analyze the document request and output a structured Blueprint JSON",
                    "type": "ACTION",
                    "target": {"prompt_template": "{{input}}"},
                    "required": True,
                }],
            },
            "dynamic_planning": {"enabled": False},
        },
        "capabilities": {
            "tools": [],
            "meta_cognition": {"platform_awareness": False, "registry_search": False, "self_modification": False},
        },
        "governance": {"max_cost_usd": 0.50, "timeout_ms": 60000, "max_recursion_depth": 1},
        "io_contract": {
            "input_schema": {"type": "object", "properties": {"input": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"blueprint": {"type": "object"}}},
        },
    }


def _visual_asset_creator() -> dict:
    return {
        "name": "visual-asset-creator",
        "display_name": "Visual Asset Creator",
        "description": "Generates charts, diagrams, and AI images specified in a Document Blueprint.",
        "goal": "Produce every visual asset specified in the Blueprint as high-quality PNG files using matplotlib, and AI image generation.",
        "type": "AGENT",
        "version": "1.0.0",
        "status": "ACTIVE",
        "tags": ["document-generation", "data-visualization"],
        "identity": {
            "role": "Data Visualization Specialist",
            "system_prompt": VISUAL_ASSET_CREATOR_PROMPT,
            "personality": {"tone": "creative", "verbosity": "concise", "formality": "casual"},
        },
        "logic_gate": {
            "reasoning_config": {
                "reasoning_mode": "REACT",
                "temperature": 0.3,
                "task_type": "text_generation",
            },
            "context_policy": {"type": "FULL"},
        },
        "planning": {
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "step_1", "order": 1,
                    "name": "Generate Visual Assets",
                    "description": "Read visual_assets_needed from Blueprint, generate each asset, output Asset Manifest JSON",
                    "type": "ACTION",
                    "target": {"prompt_template": "{{input}}"},
                    "required": True,
                }],
            },
            "dynamic_planning": {"enabled": False},
        },
        "capabilities": {
            "tools": [
                {"tool_id": "sandbox_code", "max_execution_seconds": 120},
                {"tool_id": "image_generation"},
                {"tool_id": "terminal"},
            ],
            "meta_cognition": {"platform_awareness": False, "registry_search": False, "self_modification": False},
        },
        "governance": {"max_cost_usd": 1.50, "timeout_ms": 300000, "max_recursion_depth": 1},
    }


def _document_renderer() -> dict:
    return {
        "name": "document-renderer",
        "display_name": "Document Renderer",
        "description": "Writes and executes Python code to create the final document file from a Blueprint and Asset Manifest.",
        "goal": "Produce a pixel-perfect document file by writing Python code that uses the correct library (python-pptx, python-docx, openpyxl, or WeasyPrint).",
        "type": "AGENT",
        "version": "1.0.0",
        "status": "ACTIVE",
        "tags": ["document-generation", "code-generation"],
        "identity": {
            "role": "Expert Python Document Engineer",
            "system_prompt": DOCUMENT_RENDERER_PROMPT,
            "personality": {"tone": "technical", "verbosity": "moderate", "formality": "semi-formal"},
        },
        "logic_gate": {
            "reasoning_config": {
                "reasoning_mode": "REACT",
                "temperature": 0.2,
                "task_type": "text_generation",
                "max_tokens": 65536,
                "model_name": "gemini-2.5-flash",
            },
            "context_policy": {"type": "FULL"},
        },
        "planning": {
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "step_1", "order": 1,
                    "name": "Render Document",
                    "description": "Write Python code to create the document from Blueprint + Asset Manifest, execute it, then call document_save",
                    "type": "ACTION",
                    "target": {"prompt_template": "{{input}}"},
                    "required": True,
                }],
            },
            "dynamic_planning": {"enabled": False},
        },
        "capabilities": {
            "tools": [
                {"tool_id": "sandbox_code", "max_execution_seconds": 600},
                {"tool_id": "terminal"},
                {"tool_id": "document_save"},
            ],
            "context_engineering": {
                "context_sources": [],  # Populated by seeder with library reference doc IDs
            },
            "meta_cognition": {"platform_awareness": False, "registry_search": False, "self_modification": False},
        },
        "governance": {"max_cost_usd": 1.50, "timeout_ms": 600000, "max_recursion_depth": 1},
    }


def _quality_inspector() -> dict:
    return {
        "name": "quality-inspector",
        "display_name": "Quality Inspector",
        "description": "Validates generated documents for visual and structural defects using rasterization and heuristic analysis.",
        "goal": "Catch visual defects (overflow, empty slides, missing images, unstyled tables) before the document is delivered.",
        "type": "AGENT",
        "version": "1.0.0",
        "status": "ACTIVE",
        "tags": ["document-generation", "quality-assurance"],
        "identity": {
            "role": "Visual QA Specialist",
            "system_prompt": QUALITY_INSPECTOR_PROMPT,
            "personality": {"tone": "critical", "verbosity": "concise", "formality": "formal"},
        },
        "logic_gate": {
            "reasoning_config": {
                "reasoning_mode": "REACT",
                "temperature": 0.2,
                "task_type": "text_generation",
            },
            "context_policy": {"type": "FULL"},
        },
        "planning": {
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "step_1", "order": 1,
                    "name": "Inspect Document Quality",
                    "description": "Validate structure, attempt visual rasterization, check for defects, output QA Report JSON",
                    "type": "ACTION",
                    "target": {"prompt_template": "{{input}}"},
                    "required": True,
                }],
            },
            "dynamic_planning": {"enabled": False},
        },
        "capabilities": {
            "tools": [
                {"tool_id": "terminal"},
                {"tool_id": "sandbox_code", "max_execution_seconds": 60},
            ],
            "meta_cognition": {"platform_awareness": False, "registry_search": False, "self_modification": False},
        },
        "governance": {"max_cost_usd": 0.50, "timeout_ms": 120000, "max_recursion_depth": 1},
    }


def _revision_agent() -> dict:
    return {
        "name": "revision-agent",
        "display_name": "Revision Agent",
        "description": "Applies targeted fixes to documents based on QA defect reports. One fix cycle only.",
        "goal": "Fix all defects identified by the Quality Inspector in a single pass without rewriting the entire document.",
        "type": "SKILL",
        "version": "1.0.0",
        "status": "ACTIVE",
        "tags": ["document-generation", "document-repair"],
        "identity": {
            "role": "Document Repair Specialist",
            "system_prompt": REVISION_AGENT_PROMPT,
            "personality": {"tone": "precise", "verbosity": "concise", "formality": "formal"},
        },
        "logic_gate": {
            "reasoning_config": {
                "reasoning_mode": "CHAIN_OF_THOUGHT",
                "temperature": 0.2,
                "task_type": "text_generation",
            },
            "context_policy": {"type": "FULL"},
        },
        "planning": {
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "step_1", "order": 1,
                    "name": "Apply Fixes",
                    "description": "Parse QA defect report, open document, apply fixes, save via document_save",
                    "type": "ACTION",
                    "target": {"prompt_template": "{{input}}"},
                    "required": True,
                }],
            },
            "dynamic_planning": {"enabled": False},
        },
        "capabilities": {
            "tools": [
                {"tool_id": "sandbox_code", "max_execution_seconds": 300},
                {"tool_id": "terminal"},
                {"tool_id": "document_save"},
            ],
            "meta_cognition": {"platform_awareness": False, "registry_search": False, "self_modification": False},
        },
        "governance": {"max_cost_usd": 0.50, "timeout_ms": 300000, "max_recursion_depth": 1},
    }


def _document_director(child_ids: dict) -> dict:
    """Build the Document Director PROCESS entity with child entity references."""
    return {
        "name": "document-director",
        "display_name": "Document Director",
        "description": (
            "Orchestrates world-class document generation across PPTX, DOCX, XLSX, and PDF "
            "by coordinating 5 specialized child agents through a production pipeline: "
            "Content Architecture → Visual Assets → Rendering → QA Inspection → Revision."
        ),
        "goal": (
            "Produce visually stunning, publication-quality documents by orchestrating "
            "Content Architect, Visual Asset Creator, Document Renderer, Quality Inspector, "
            "and Revision Agent in a sequential pipeline."
        ),
        "type": "PROCESS",
        "version": "1.0.0",
        "status": "ACTIVE",
        "tags": ["document-generation", "system", "premium"],
        "identity": {
            "role": "Creative Director & Production Manager",
            "system_prompt": DOCUMENT_DIRECTOR_PROMPT,
            "personality": {"tone": "professional", "verbosity": "concise", "formality": "semi-formal"},
        },
        "hierarchy": {
            "children": [
                {"child_id": child_ids["content_architect"], "relationship": "SEQUENTIAL"},
                {"child_id": child_ids["visual_asset_creator"], "relationship": "SEQUENTIAL"},
                {"child_id": child_ids["document_renderer"], "relationship": "SEQUENTIAL"},
                {"child_id": child_ids["quality_inspector"], "relationship": "SEQUENTIAL"},
                {"child_id": child_ids["revision_agent"], "relationship": "CONDITIONAL",
                 "condition": {"enabled": True, "expression": "quality_inspector.defects_found == true",
                               "description": "Only runs if QA Inspector finds defects"}},
            ],
            "is_atomic": False,
            "composition_depth": 1,
        },
        "logic_gate": {
            "reasoning_config": {
                "reasoning_mode": "REACT",
                "temperature": 0.3,
                "task_type": "text_generation",
            },
            "context_policy": {"type": "FULL"},
        },
        "planning": {
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "step_1", "order": 1,
                        "name": "Content Architecture",
                        "description": "Analyze the document request and produce a structured Document Blueprint JSON",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": child_ids["content_architect"],
                                   "prompt_template": "{{input}}"},
                        "required": True,
                    },
                    {
                        "step_id": "step_2", "order": 2,
                        "name": "Visual Asset Creation",
                        "description": "Generate all charts, diagrams, and images specified in the Blueprint",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": child_ids["visual_asset_creator"],
                                   "prompt_template": "Document Blueprint from Content Architect:\n\n{{step_1}}",
                                   "input_dependencies": ["step_1"]},
                        "required": True,
                    },
                    {
                        "step_id": "step_3", "order": 3,
                        "name": "Document Rendering",
                        "description": "Write and execute Python code to create the final document file",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": child_ids["document_renderer"],
                                   "prompt_template": "Document Blueprint:\n\n{{step_1}}\n\nAsset Manifest:\n\n{{step_2}}",
                                   "input_dependencies": ["step_1", "step_2"]},
                        "required": True,
                    },
                    {
                        "step_id": "step_4", "order": 4,
                        "name": "Quality Inspection",
                        "description": "Validate the generated document for visual and structural defects",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": child_ids["quality_inspector"],
                                   "prompt_template": "Inspect this document:\n\n{{step_3}}",
                                   "input_dependencies": ["step_3"]},
                        "required": True,
                    },
                    {
                        "step_id": "step_5", "order": 5,
                        "name": "Revision",
                        "description": "Apply targeted fixes for defects found by Quality Inspector (only if defects exist)",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": child_ids["revision_agent"],
                                   "prompt_template": "Document path and QA report:\n\nDocument: {{step_3}}\n\nQA Report: {{step_4}}",
                                   "input_dependencies": ["step_3", "step_4"]},
                        "required": False,
                    },
                ],
            },
            "dynamic_planning": {"enabled": False},
        },
        "capabilities": {
            "tools": [
                {"tool_id": "sandbox_code", "max_execution_seconds": 600},
                {"tool_id": "terminal"},
                {"tool_id": "image_generation"},
                {"tool_id": "document_save"},
            ],
            "meta_cognition": {"platform_awareness": False, "registry_search": False, "self_modification": False},
        },
        "governance": {"max_cost_usd": 5.00, "timeout_ms": 900000, "max_recursion_depth": 3},
        "io_contract": {
            "input_schema": {
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "Natural language document request"},
                },
                "required": ["input"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "document_path": {"type": "string"},
                    "format": {"type": "string"},
                    "qa_status": {"type": "string"},
                },
            },
        },
        "metadata_extensions": {
            "toolkit_version": "1.0.0",
            "supported_formats": ["pptx", "docx", "xlsx", "pdf"],
        },
        "is_template": True,
    }


# ─── Database Operations ───────────────────────────────────────────────────

async def seed_entities(company_id: str, user_id: str, dry_run: bool = False):
    """Create all Document Toolkit entities for the given company."""
    from uuid import UUID
    company_uuid = UUID(company_id)
    user_uuid = UUID(user_id)

    # Generate entity payloads
    children_templates = {
        "content_architect": _content_architect(),
        "visual_asset_creator": _visual_asset_creator(),
        "document_renderer": _document_renderer(),
        "quality_inspector": _quality_inspector(),
        "revision_agent": _revision_agent(),
    }

    if dry_run:
        logger.info("=== DRY RUN — Validating entity payloads ===")
        child_ids = {k: str(uuid.uuid4()) for k in children_templates}
        director = _document_director(child_ids)
        all_entities = {**children_templates, "document_director": director}
        for name, entity in all_entities.items():
            logger.info(f"  ✓ {name}: type={entity['type']}, tools={len(entity.get('capabilities', {}).get('tools', []))}")
        logger.info(f"Total entities: {len(all_entities)}")
        logger.info("Payload validation passed. Run without --dry-run to create in DB.")
        # Print director JSON for inspection
        print(json.dumps(director, indent=2, default=str))
        return

    # Real DB operations
    from src.common.database import AsyncSessionLocal
    from src.ai.models import HierarchicalEntity
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Check for existing entities
        existing = await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.company_id == company_uuid,
                HierarchicalEntity.name == "document-director",
            )
        )
        if existing.scalar_one_or_none():
            logger.warning("Document Director already exists for this company. Skipping.")
            return

        # Create child entities first
        child_ids = {}
        for key, template in children_templates.items():
            entity = HierarchicalEntity(
                company_id=company_uuid,
                created_by=user_uuid,
                name=template["name"],
                display_name=template["display_name"],
                description=template["description"],
                goal=template["goal"],
                type=template["type"],
                version=template["version"],
                status=template["status"],
                tags=template["tags"],
                identity=template["identity"],
                hierarchy=template.get("hierarchy"),
                logic_gate=template["logic_gate"],
                planning=template["planning"],
                capabilities=template["capabilities"],
                governance=template["governance"],
                io_contract=template.get("io_contract"),
                is_template=True,
            )
            db.add(entity)
            await db.flush()
            child_ids[key] = str(entity.id)
            logger.info(f"  Created {template['display_name']} ({template['type']}): {entity.id}")

        # Create Document Director with child references
        director_template = _document_director(child_ids)
        director = HierarchicalEntity(
            company_id=company_uuid,
            created_by=user_uuid,
            name=director_template["name"],
            display_name=director_template["display_name"],
            description=director_template["description"],
            goal=director_template["goal"],
            type=director_template["type"],
            version=director_template["version"],
            status=director_template["status"],
            tags=director_template["tags"],
            identity=director_template["identity"],
            hierarchy=director_template["hierarchy"],
            logic_gate=director_template["logic_gate"],
            planning=director_template["planning"],
            capabilities=director_template["capabilities"],
            governance=director_template["governance"],
            io_contract=director_template.get("io_contract"),
            metadata_extensions=director_template.get("metadata_extensions"),
            is_template=True,
        )
        db.add(director)
        await db.commit()
        logger.info(f"  Created Document Director (PROCESS): {director.id}")

        # Update children with parent_id
        for key, child_id_str in child_ids.items():
            child_entity = await db.get(HierarchicalEntity, UUID(child_id_str))
            if child_entity:
                child_entity.parent_id = director.id
        await db.commit()

        logger.info(f"\n{'='*60}")
        logger.info(f"Document Generation Toolkit seeded successfully!")
        logger.info(f"  Company: {company_id}")
        logger.info(f"  Director ID: {director.id}")
        for key, cid in child_ids.items():
            logger.info(f"  {key}: {cid}")
        logger.info(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Seed Document Generation Toolkit entities")
    parser.add_argument("--company-id", required=True, help="Company UUID")
    parser.add_argument("--user-id", required=True, help="User UUID (creator)")
    parser.add_argument("--dry-run", action="store_true", help="Validate payloads without DB writes")
    args = parser.parse_args()

    asyncio.run(seed_entities(args.company_id, args.user_id, args.dry_run))


if __name__ == "__main__":
    main()
