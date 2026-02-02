import asyncio
import json
from uuid import UUID
from src.common.database import AsyncSessionLocal
from src.ai.service import AIService
from src.ai.schemas import (
    HierarchicalEntityCreate, EntityType, EntityStatus, 
    Planning, StaticPlan, LogicGate, ReasoningConfig, 
    Capabilities, ToolReference, IOContract, Persona, PersonaExample
)

COMPANY_ID = UUID("c8865856-8496-4054-80e3-3d9cdd79788e")

async def setup_entities():
    async with AsyncSessionLocal() as db:
        service = AIService(db)
        

        # 2. Action: Company Insight Research
        # ---------------------------------------------------------
        company_researcher = await service.create_entity(
            HierarchicalEntityCreate(
                name="company_researcher",
                display_name="Deep-Dive Company Analyst",
                description="Performs comprehensive research on a company's operations and products.",
                type=EntityType.ACTION,
                status=EntityStatus.ACTIVE,
                identity={
                    "persona": {
                        "system_prompt": (
                            "You are a Senior Business Analyst at a top-tier consulting firm. "
                            "Your task is to identify key operational details and product offerings of a company. "
                            "Focus on: Value Proposition, Target Audience, Revenue Streams, and Recent News. "
                            "Be precise, factual, and avoid fluff."
                        )
                    }
                },
                capabilities=Capabilities(tools=[
                    ToolReference(tool_id="search_tool"),
                    ToolReference(tool_id="scraper_tool")
                ]),
                planning=Planning(
                    static_plan=StaticPlan(
                        steps=[
                            {
                                "name": "FindWebsite",
                                "type": "TOOL_CALL",
                                "target": {"tool_id": "search_tool", "prompt_template": "{\"query\": \"{{company_name}} official website and product offerings\"}"}
                            },
                            {
                                "name": "ScrapeDetails",
                                "type": "TOOL_CALL",
                                "target": {"tool_id": "scraper_tool", "prompt_template": "{\"url\": \"{{FindWebsite.top_result_url}}\"}"}
                            },
                            {
                                "name": "SynthesizeInsight",
                                "type": "THOUGHT",
                                "target": {
                                    "prompt_template": (
                                        "Based on the scraped content: {{ScrapeDetails.output}}, "
                                        "Write a concise business profile for {{company_name}}. "
                                        "Include: 1. Core Mission 2. Key Products 3. Operations Overview."
                                    )
                                }
                            }
                        ]
                    )
                ),
                io_contract=IOContract(
                    input_schema={"type": "object", "properties": {"company_name": {"type": "string"}}},
                    output_schema={"type": "object", "properties": {"profile": {"type": "string"}}}
                )
            ),
            COMPANY_ID
        )
        print(f"Created Company Researcher: {company_researcher.id}")


        # 5. Process: Business Growth Orchestrator
        # ---------------------------------------------------------
        orchestrator = await service.create_entity(
            HierarchicalEntityCreate(
                name="growth_orchestrator",
                display_name="Ultimate Business Growth Orchestrator",
                description="The master process that orchestrates categorization, research, replies, and outreach.",
                type=EntityType.PROCESS,
                status=EntityStatus.ACTIVE,
                identity={
                    "persona": {
                        "system_prompt": (
                            "You are the Chief Growth Officer (CGO) of the company. "
                            "Your mission is to ensure every communication is optimized and every lead is pursued with intelligence. "
                            "You coordinate multiple AI agents to achieve maximum business growth."
                        )
                    }
                },
                planning=Planning(
                    static_plan=StaticPlan(
                        steps=[
                            {
                                "name": "AnalyzeAndRespond",
                                "type": "THOUGHT",
                                "target": {
                                    "prompt_template": (
                                        "Identify HIGH priority LEAD or CLIENT inquiries from the current inquiries. "
                                        "Trigger 'company_researcher' to get deep insights for them."
                                    )
                                }
                            }
                        ]
                    )
                )
            ),
            COMPANY_ID
        )
        print(f"Created Business Growth Orchestrator: {orchestrator.id}")

if __name__ == "__main__":
    asyncio.run(setup_entities())
