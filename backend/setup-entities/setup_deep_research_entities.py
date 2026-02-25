"""
Setup script for Deep Research Process hierarchical entities.
Creates all 18 entities (1 PROCESS, 3 AGENTS, 6 SKILLS, 8 ACTIONS) in the database.
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.ext.asyncio import AsyncSession
from src.common.database import AsyncSessionLocal
from src.common.config import settings
from src.ai.models import HierarchicalEntity
from src.auth.models import Company
from sqlalchemy import select
from uuid import uuid4

# Entity definitions will be split across multiple functions to avoid token limits

async def create_action_entities(session: AsyncSession, company_id):
    """Create all ACTION level entities (Level 4)"""
    print("Creating ACTION entities...")
    
    actions = {}
    
    # Topic Query Planner
    actions['topic_query_planner'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="topic_query_planner",
        display_name="Topic Query Planner",
        description="Generates optimized search queries from a research topic.",
        tags=["planning", "queries"],
        identity={
            "system_prompt": "Generate 5-10 search queries for the given research topic. Include:\n- 2-3 broad queries for general understanding\n- 2-3 specific queries for detailed aspects\n- 1-2 queries for recent news/developments\n- 1-2 academic-style queries\n\nOutput as a JSON array of query strings."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "plan",
                    "order": 1,
                    "name": "Generate Queries",
                    "type": "THOUGHT",
                    "target": {
                        "prompt_template": "Research Topic: {{input}}\n\nGenerate optimized search queries for comprehensive research on this topic. Output a JSON array of 5-10 query strings."
                    },
                    "required": True
                }]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.4,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 30000}
    )
    
    # Web Search Action
    actions['web_search_action'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="web_search_action",
        display_name="Web Search Action",
        description="Executes web searches using the web_search tool and aggregates results.",
        tags=["search", "web"],
        identity={
            "system_prompt": "You are a web search executor. For each provided query:\n1. Execute the web search\n2. Extract relevant URLs and summaries\n3. Aggregate all results\n\nUse the web_search tool for each query. Compile a comprehensive list of sources found."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "search",
                    "order": 1,
                    "name": "Execute Searches",
                    "type": "ACTION",
                    "target": {
                        "prompt_template": "Execute web searches for the following queries and compile results:\n\n{{input}}\n\nUse the web_search tool for each query. Return a compiled list of all sources found with URLs and summaries."
                    },
                    "required": True
                }]
            }
        },
        capabilities={"tools": [{"tool_id": "web_search"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.2,
                "reasoning_mode": "REACT"
            }
        },
        governance={"timeout_ms": 60000}
    )
    
    # Source Scraper Action
    actions['source_scraper_action'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="source_scraper_action",
        display_name="Source Scraper Action",
        description="Extracts detailed content from web URLs using the scraper tool.",
        tags=["scraping", "extraction"],
        identity={
            "system_prompt": "You are a content extraction specialist. For each URL provided:\n1. Use the scraper_tool to extract content\n2. Summarize the key information\n3. Note the source URL for citation\n\nFocus on extracting factual information relevant to the research topic."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "scrape",
                    "order": 1,
                    "name": "Scrape Sources",
                    "type": "ACTION",
                    "target": {
                        "prompt_template": "Extract content from the following sources:\n\n{{input}}\n\nUse the scraper_tool for each URL. Compile extracted content with source attribution."
                    },
                    "required": True
                }]
            }
        },
        capabilities={"tools": [{"tool_id": "scraper_tool"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.1,
                "reasoning_mode": "REACT"
            }
        },
        governance={"timeout_ms": 90000}
    )
    
    # Credibility Validator
    actions['credibility_validator'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="credibility_validator",
        display_name="Credibility Validator",
        description="Evaluates and scores the credibility of research sources.",
        tags=["validation", "credibility"],
        identity={
            "system_prompt": "Evaluate each source for credibility using CRAAP criteria:\n- Currency: Is the information recent?\n- Relevance: Does it relate to the topic?\n- Authority: Is the source reputable?\n- Accuracy: Is the information verifiable?\n- Purpose: Is there bias?\n\nScore each source 1-10 and provide brief justification. Output as JSON array."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "validate",
                    "order": 1,
                    "name": "Validate Sources",
                    "type": "THOUGHT",
                    "target": {
                        "prompt_template": "Evaluate the credibility of these sources:\n\n{{input}}\n\nScore each 1-10 using CRAAP criteria. Output as JSON array with source, score, and justification."
                    },
                    "required": True
                }]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.2,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 60000}
    )
    
    # Information Synthesizer
    actions['information_synthesizer'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="information_synthesizer",
        display_name="Information Synthesizer",
        description="Synthesizes gathered information into organized themes and insights.",
        tags=["synthesis", "analysis"],
        identity={
            "system_prompt": "Synthesize the gathered research information:\n1. Identify major themes and categories\n2. Extract key facts and statistics\n3. Note areas of consensus and conflict\n4. Highlight the most significant findings\n5. Save a detailed raw research dump to a markdown file named 'research_notes.md' using the file_writer tool. This is CRITICAL for audit.\n6. Map information to potential report sections\n\nOutput a structured synthesis with clear organization."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "synthesize_data",
                    "order": 1,
                    "name": "Synthesize Information",
                    "type": "THOUGHT",
                    "target": {
                        "prompt_template": "Synthesize the following research information into organized themes and insights:\n\n{{input}}\n\nIdentify patterns, extract key findings, and organize by topic area. Output your synthesis."
                    },
                    "required": True
                },
                {
                    "step_id": "save_notes",
                    "order": 2,
                    "name": "Save Research Notes",
                    "type": "TOOL_CALL",
                    "target": {
                        "tool_id": "file_writer",
                        "prompt_template": "{\"filename\": \"research_notes.md\", \"content\": \"{{synthesize_data}}\"}"
                    },
                    "required": True
                },
                {
                    "step_id": "create_outline",
                    "order": 3,
                    "name": "Create Report Outline",
                    "type": "THOUGHT",
                    "target": {
                        "prompt_template": "Based on the synthesized research:\n\n{{synthesize_data}}\n\nCreate a detailed report outline. Include section headers, key points for each section, and source references."
                    },
                    "required": True
                }]
            }
        },
        capabilities={"tools": [{"tool_id": "file_writer"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.3,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 90000}
    )
    
    # Outline Creator
    actions['outline_creator'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="outline_creator",
        display_name="Outline Creator",
        description="Creates a detailed report outline with section structure and content mapping.",
        tags=["outline", "structure"],
        identity={
            "system_prompt": "Create a comprehensive report outline:\n\n## Standard Structure:\n1. Title Page\n2. Table of Contents\n3. Executive Summary\n4. Introduction\n   - Background & Context\n   - Research Objectives\n   - Scope & Methodology\n5. Findings (multiple sub-sections based on themes)\n6. Analysis & Discussion\n7. Conclusions & Recommendations\n8. References\n9. Appendices (if needed)\n\nFor each section, list:\n- Key points to cover\n- Relevant sources to cite\n- Approximate length guidance"
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "create_outline",
                    "order": 1,
                    "name": "Create Outline",
                    "type": "THOUGHT",
                    "target": {
                        "prompt_template": "Based on the synthesized research:\n\n{{input}}\n\nCreate a detailed report outline. Include section headers, key points for each section, and source references. Add additional sections as needed based on the research findings."
                    },
                    "required": True
                }]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.3,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 60000}
    )
    
    # Section Drafter
    actions['section_drafter'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="section_drafter",
        display_name="Section Drafter",
        description="Drafts comprehensive report content for all sections.",
        tags=["writing", "drafting"],
        identity={
            "system_prompt": "Draft the complete research report in markdown format. Write each section with:\n- Clear, professional prose\n- Logical flow and transitions\n- Proper citations [Source Name]\n- Supporting evidence and data\n- Appropriate depth and detail\n\nOutput the complete report content ready for PDF generation."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "draft",
                    "order": 1,
                    "name": "Draft Report",
                    "type": "THOUGHT",
                    "target": {
                        "prompt_template": "Using the following outline and synthesized research:\n\n{{input}}\n\nDraft the complete research report in markdown format. Include all sections with professional content. Ensure proper citations and logical flow. The report should be comprehensive and publication-ready."
                    },
                    "required": True
                }]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.5,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 180000}
    )
    
    # PDF Generator Action
    actions['pdf_generator_action'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="pdf_generator_action",
        display_name="PDF Generator Action",
        description="Generates the final PDF document from markdown content using the pdf_generator tool.",
        tags=["pdf", "generation", "output"],
        identity={
            "system_prompt": "You are a PDF generation specialist. Your job is to:\n1. Take the drafted report content (markdown)\n2. Prepare proper parameters for the PDF generator\n3. Call the pdf_generator tool with content, title, and filename\n4. Return the generated PDF path\n\nEnsure the content is properly formatted markdown for optimal PDF output."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "generate",
                    "order": 1,
                    "name": "Generate PDF",
                    "type": "ACTION",
                    "target": {
                        "prompt_template": "Generate a PDF from the following report content:\n\n{{input}}\n\nUse the pdf_generator tool with appropriate title and filename. Return the path to the generated PDF."
                    },
                    "required": True
                }]
            }
        },
        capabilities={"tools": [{"tool_id": "pdf_generator"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.1,
                "reasoning_mode": "REACT"
            }
        },
        governance={"timeout_ms": 120000}
    )
    
    # Add all actions to session
    for action in actions.values():
        session.add(action)
    
    await session.commit()
    print(f"✓ Created {len(actions)} ACTION entities")
    return actions


async def create_skill_entities(session: AsyncSession, company_id, actions):
    """Create all SKILL level entities (Level 3)"""
    print("Creating SKILL entities...")
    
    skills = {}
    
    # Query Planning Skill
    skills['query_planning_skill'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="SKILL",
        name="query_planning_skill",
        display_name="Query Planning Skill",
        description="Decomposes research topics into structured search queries, identifying key aspects, related concepts, and optimal search strategies.",
        tags=["planning", "search", "decomposition"],
        identity={
            "system_prompt": "You are a search query optimization specialist. Given a research topic, break it down into:\n1. Primary search queries for core concepts\n2. Secondary queries for related aspects\n3. Specific queries for recent developments\n4. Academic/scholarly search terms\n\nOutput a structured list of 5-10 search queries optimized for web search, ranging from broad to specific."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "generate_queries",
                    "order": 1,
                    "name": "Generate Search Queries",
                    "type": "CHILD_ENTITY_INVOCATION",
                    "target": {"entity_id": str(actions['topic_query_planner'].id)},
                    "required": True
                }]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.4,
                "reasoning_mode": "REACT"
            }
        },
        governance={"timeout_ms": 60000}
    )
    
    # Information Gathering Skill
    skills['information_gathering_skill'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="SKILL",
        name="information_gathering_skill",
        display_name="Information Gathering Skill",
        description="Executes search queries and extracts content from multiple web sources, aggregating information for synthesis.",
        tags=["search", "scraping", "collection"],
        identity={
            "system_prompt": "You are an information gathering specialist. Your job is to:\n1. Execute web searches using provided queries\n2. Identify the most relevant URLs from search results\n3. Extract detailed content from those sources\n4. Compile all gathered information with source attribution\n\nBe thorough and systematic. Gather information from diverse source types when available."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "web_search",
                        "order": 1,
                        "name": "Execute Web Searches",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": str(actions['web_search_action'].id)},
                        "required": True
                    },
                    {
                        "step_id": "scrape_sources",
                        "order": 2,
                        "name": "Scrape Source Content",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(actions['source_scraper_action'].id),
                            "input_dependencies": ["web_search"]
                        },
                        "required": True
                    }
                ]
            },
            "dynamic_planning": {
                "enabled": True,
                "planning_prompt": "Based on initial search results, determine if additional targeted searches are needed. If results are sparse, plan alternative query formulations."
            },
            "loop_control": {"max_iterations": 3}
        },
        capabilities={"tools": [{"tool_id": "web_search"}, {"tool_id": "scraper_tool"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.3,
                "reasoning_mode": "REACT"
            }
        },
        governance={"timeout_ms": 120000}
    )
    
    # Source Evaluation Skill
    skills['source_evaluation_skill'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="SKILL",
        name="source_evaluation_skill",
        display_name="Source Evaluation Skill",
        description="Evaluates the credibility and reliability of gathered sources, scoring them and filtering out unreliable information.",
        tags=["evaluation", "credibility", "validation"],
        identity={
            "system_prompt": "You are a source credibility analyst. Evaluate each source based on:\n1. Authority - Is the author/organization credible?\n2. Accuracy - Can claims be verified?\n3. Currency - Is the information recent?\n4. Coverage - Is the information comprehensive?\n5. Purpose - Is there bias or commercial interest?\n\nScore each source 1-10 and provide justification. Flag any sources below 5 as potentially unreliable."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "validate",
                    "order": 1,
                    "name": "Validate Source Credibility",
                    "type": "CHILD_ENTITY_INVOCATION",
                    "target": {"entity_id": str(actions['credibility_validator'].id)},
                    "required": True
                }]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.2,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 90000}
    )
    
    # Data Synthesis Skill
    skills['data_synthesis_skill'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="SKILL",
        name="data_synthesis_skill",
        display_name="Data Synthesis Skill",
        description="Synthesizes gathered information into organized themes, resolves conflicts, and creates a structured report outline.",
        tags=["synthesis", "organization", "outline"],
        identity={
            "system_prompt": "You are a research synthesis expert. Your job is to:\n1. Categorize information into logical themes\n2. Identify key patterns and insights\n3. Resolve conflicting information\n4. Create a comprehensive report outline\n5. Map sources to each section\n\nOutput a detailed outline with section headers, key points, and source references for each section."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "synthesize",
                        "order": 1,
                        "name": "Synthesize Information",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": str(actions['information_synthesizer'].id)},
                        "required": True
                    },
                    {
                        "step_id": "outline",
                        "order": 2,
                        "name": "Create Report Outline",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(actions['outline_creator'].id),
                            "input_dependencies": ["synthesize"]
                        },
                        "required": True
                    }
                ]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.3,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 120000}
    )
    
    # Report Drafting Skill
    skills['report_drafting_skill'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="SKILL",
        name="report_drafting_skill",
        display_name="Report Drafting Skill",
        description="Drafts comprehensive report sections including executive summary, introduction, methodology, findings, analysis, and conclusion.",
        tags=["writing", "drafting", "content"],
        identity={
            "system_prompt": "You are an expert report writer. Draft each section of the research report:\n\n1. **Executive Summary** - Concise overview of key findings (200-300 words)\n2. **Introduction** - Context, objectives, and scope\n3. **Methodology** - Research approach and sources used\n4. **Findings** - Detailed presentation of research results\n5. **Analysis** - Interpretation and implications\n6. **Conclusion** - Summary and recommendations\n7. **References** - Properly formatted citations\n\nWrite in professional academic tone. Support all claims with citations. Use markdown formatting."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "draft_sections",
                    "order": 1,
                    "name": "Draft All Sections",
                    "type": "CHILD_ENTITY_INVOCATION",
                    "target": {"entity_id": str(actions['section_drafter'].id)},
                    "required": True
                }]
            },
            "dynamic_planning": {
                "enabled": True,
                "planning_prompt": "Based on the outline complexity, determine if sections should be drafted sequentially or if additional sub-sections are needed."
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.5,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 180000}
    )
    
    # Report Formatting Skill
    skills['report_formatting_skill'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="SKILL",
        name="report_formatting_skill",
        display_name="Report Formatting Skill",
        description="Formats the drafted report content and generates a professional PDF document.",
        tags=["formatting", "pdf", "output"],
        identity={
            "system_prompt": "You are a document formatting specialist. Your job is to:\n1. Ensure consistent markdown formatting throughout the document\n2. Properly format citations and references\n3. Add table of contents structure\n4. Format tables and lists consistently\n5. Call the PDF generator tool to create the final document\n\nEnsure the document is professionally formatted and ready for distribution."
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "generate_pdf",
                    "order": 1,
                    "name": "Generate PDF Document",
                    "type": "CHILD_ENTITY_INVOCATION",
                    "target": {"entity_id": str(actions['pdf_generator_action'].id)},
                    "required": True
                }]
            }
        },
        capabilities={"tools": [{"tool_id": "pdf_generator"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.2,
                "reasoning_mode": "REACT"
            }
        },
        governance={"timeout_ms": 120000}
    )
    
    # Add all skills to session
    for skill in skills.values():
        session.add(skill)
    
    await session.commit()
    print(f"✓ Created {len(skills)} SKILL entities")
    return skills


async def create_agent_entities(session: AsyncSession, company_id, skills):
    """Create all AGENT level entities (Level 2)"""
    print("Creating AGENT entities...")
    
    agents = {}
    
    # Research Orchestrator Agent
    agents['research_orchestrator_agent'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="AGENT",
        name="research_orchestrator_agent",
        display_name="Research Orchestrator Agent",
        description="An intelligent agent that plans research strategies, generates search queries, gathers information from multiple sources, and validates source credibility. Uses iterative refinement to ensure comprehensive coverage.",
        tags=["research", "planning", "gathering"],
        identity={
            "system_prompt": "You are an expert research strategist. Your role is to:\n1. Analyze research topics and break them into key research questions\n2. Plan multi-source information gathering strategies\n3. Coordinate web searches and content extraction\n4. Validate source credibility and cross-reference information\n5. Identify gaps and iterate on research until comprehensive\n\nAlways prioritize accuracy over speed. Use diverse sources including academic, news, and official data when available.",
            "few_shot_examples": [{
                "scenario": "Research topic: Impact of AI on healthcare",
                "ideal_response": "I will structure this research into: 1) Current AI applications in diagnostics, 2) AI in drug discovery, 3) Patient care automation, 4) Ethical considerations, 5) Future trends. For each area, I will search for peer-reviewed studies, industry reports, and news from the past 2 years."
            }],
            "behavioral_constraints": [
                "Always use at least 3 different search queries per major topic",
                "Cross-reference key claims across multiple sources",
                "Flag any conflicting information for synthesis phase"
            ]
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "plan_queries",
                        "order": 1,
                        "name": "Plan Research Queries",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": str(skills['query_planning_skill'].id)},
                        "required": True
                    },
                    {
                        "step_id": "gather_info",
                        "order": 2,
                        "name": "Gather Information",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(skills['information_gathering_skill'].id),
                            "input_dependencies": ["plan_queries"]
                        },
                        "required": True
                    },
                    {
                        "step_id": "evaluate_sources",
                        "order": 3,
                        "name": "Evaluate Sources",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(skills['source_evaluation_skill'].id),
                            "input_dependencies": ["gather_info"]
                        },
                        "required": True
                    }
                ],
                "fallback_behavior": "ADAPTIVE"
            },
            "dynamic_planning": {
                "enabled": True,
                "planning_prompt": "Assess the completeness of gathered information. If critical gaps exist, plan additional targeted searches. Consider: Are all key aspects covered? Are sources diverse enough? Is there conflicting information that needs resolution?",
                "allowed_deviations": {
                    "can_add_steps": True,
                    "can_skip_optional_steps": True
                }
            },
            "loop_control": {
                "max_iterations": 5,
                "iteration_context_mode": "SUMMARIZED"
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.4,
                "reasoning_mode": "REACT"
            },
            "context_policy": {"type": "FULL"},
            "review_mechanism": {
                "enabled": True,
                "review_prompt": "Evaluate if the research phase has gathered sufficient information. Check: 1) Are there at least 5 credible sources? 2) Are all key aspects of the topic covered? 3) Is the information recent and relevant?",
                "on_failure": "RETRY"
            }
        },
        governance={
            "timeout_ms": 300000,
            "max_recursion_depth": 8
        },
        observability={
            "log_thoughts": True,
            "track_cost": True
        }
    )
    
    # Synthesis Agent
    agents['synthesis_agent'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="AGENT",
        name="synthesis_agent",
        display_name="Synthesis Agent",
        description="Synthesizes gathered research information, identifies patterns and themes, resolves conflicting data, and creates a structured outline for the final report.",
        tags=["synthesis", "organization", "analysis"],
        identity={
            "system_prompt": "You are an expert research synthesizer and analyst. Your role is to:\n1. Analyze and categorize gathered information\n2. Identify key themes, patterns, and insights\n3. Resolve conflicting information through critical analysis\n4. Create a comprehensive, logical outline for the report\n5. Highlight key findings and their implications\n\nYour output should provide a clear roadmap for the report writing phase, with all information properly organized and attributed to sources.",
            "behavioral_constraints": [
                "Always attribute information to its source",
                "Clearly flag any conflicting data and provide resolution",
                "Organize information in a logical, hierarchical structure",
                "Identify and highlight the most important findings"
            ]
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "synthesize_data",
                    "order": 1,
                    "name": "Synthesize Information",
                    "type": "CHILD_ENTITY_INVOCATION",
                    "target": {"entity_id": str(skills['data_synthesis_skill'].id)},
                    "required": True
                }]
            },
            "dynamic_planning": {
                "enabled": True,
                "planning_prompt": "Based on the volume and complexity of gathered information, determine if multiple synthesis passes are needed. For complex topics with many sources, plan for initial categorization, then deep analysis, then outline creation.",
                "allowed_deviations": {"can_add_steps": True}
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.3,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            },
            "context_policy": {"type": "FULL"}
        },
        governance={
            "timeout_ms": 180000,
            "max_recursion_depth": 5
        }
    )
    
    # Report Writer Agent
    agents['report_writer_agent'] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="AGENT",
        name="report_writer_agent",
        display_name="Report Writer Agent",
        description="Drafts comprehensive report sections from synthesized research and generates a professionally formatted PDF document with title page, table of contents, executive summary, methodology, findings, analysis, conclusions, and references.",
        tags=["writing", "report", "pdf", "formatting"],
        identity={
            "system_prompt": "You are an expert technical and research writer. Your role is to:\n1. Transform synthesized research into clear, professional prose\n2. Write compelling executive summaries\n3. Structure reports with proper sections (Introduction, Methodology, Findings, Analysis, Conclusion)\n4. Ensure proper citation and reference formatting\n5. Maintain consistent tone and style throughout\n\nYour writing should be:\n- Clear and accessible to a general audience\n- Professionally structured with logical flow\n- Well-supported with evidence and citations\n- Comprehensive yet concise",
            "few_shot_examples": [{
                "scenario": "Write an executive summary for AI healthcare research",
                "ideal_response": "## Executive Summary\n\nThis report examines the transformative impact of artificial intelligence on modern healthcare systems. Our research reveals three key findings: (1) AI-powered diagnostic tools have achieved accuracy rates exceeding 94% in early disease detection, (2) Drug discovery timelines have been reduced by 40% through machine learning applications, and (3) Automated patient care systems show promise in addressing healthcare workforce shortages. The analysis indicates a projected $150 billion market opportunity by 2030, with significant implications for healthcare policy and practice."
            }]
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "draft_report",
                        "order": 1,
                        "name": "Draft Report Sections",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": str(skills['report_drafting_skill'].id)},
                        "required": True
                    },
                    {
                        "step_id": "format_pdf",
                        "order": 2,
                        "name": "Format and Generate PDF",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(skills['report_formatting_skill'].id),
                            "input_dependencies": ["draft_report"]
                        },
                        "required": True
                    }
                ]
            },
            "dynamic_planning": {
                "enabled": True,
                "planning_prompt": "Based on the synthesized content, determine if additional sections are needed beyond the standard structure. Consider adding appendices for detailed data, methodology details for complex research, or additional analysis sections for multi-faceted topics."
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.5,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            },
            "context_policy": {"type": "FULL"},
            "review_mechanism": {
                "enabled": True,
                "review_prompt": "Review the drafted report for: 1) Completeness - all required sections present, 2) Coherence - logical flow between sections, 3) Quality - professional tone and proper citations, 4) Accuracy - claims supported by sources",
                "on_failure": "RETRY"
            }
        },
        governance={
            "timeout_ms": 180000,
            "max_recursion_depth": 5
        }
    )
    
    # Add all agents to session
    for agent in agents.values():
        session.add(agent)
    
    await session.commit()
    print(f"✓ Created {len(agents)} AGENT entities")
    return agents


async def create_process_entity(session: AsyncSession, company_id, agents):
    """Create the top-level PROCESS entity (Level 1)"""
    print("Creating PROCESS entity...")
    
    process = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="PROCESS",
        name="deep_research_process",
        display_name="Deep Research Process",
        description="Conducts comprehensive, multi-source research on any given topic and produces a detailed, well-formatted PDF report. Operates iteratively—refining its approach based on intermediate findings.",
        tags=["research", "report", "pdf", "comprehensive"],
        identity={
            "system_prompt": "You are a master research orchestrator. Your role is to coordinate a comprehensive research workflow that produces high-quality, well-researched reports. You manage three specialized agents: Research Orchestrator (for information gathering), Synthesis Agent (for organizing findings), and Report Writer (for producing the final document). Always ensure thoroughness, accuracy, and professional output quality.",
            "behavioral_constraints": [
                "Never produce reports without verifying information from multiple sources",
                "Always iterate on research if initial findings are insufficient",
                "Ensure all claims are supported by credible sources",
                "Maintain professional academic tone throughout"
            ]
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "step_1_research",
                        "order": 1,
                        "name": "Research Phase",
                        "description": "Execute comprehensive research using the Research Orchestrator Agent",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": str(agents['research_orchestrator_agent'].id)},
                        "required": True
                    },
                    {
                        "step_id": "step_2_synthesis",
                        "order": 2,
                        "name": "Synthesis Phase",
                        "description": "Synthesize and organize all gathered information",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(agents['synthesis_agent'].id),
                            "input_dependencies": ["step_1_research"]
                        },
                        "required": True
                    },
                    {
                        "step_id": "step_3_report",
                        "order": 3,
                        "name": "Report Generation Phase",
                        "description": "Draft and format the final PDF report",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(agents['report_writer_agent'].id),
                            "input_dependencies": ["step_2_synthesis"]
                        },
                        "required": True
                    }
                ],
                "fallback_behavior": "ADAPTIVE"
            },
            "dynamic_planning": {
                "enabled": True,
                "planning_prompt": "Based on the research topic, determine if additional research phases are needed. If the topic is broad, plan for multiple research iterations focusing on different aspects.",
                "constraints": [
                    "Always include at least one research phase",
                    "Always include synthesis and report phases",
                    "Add iteration phases if findings are insufficient"
                ],
                "reconciliation_strategy": "HYBRID",
                "allowed_deviations": {
                    "can_add_steps": True,
                    "can_skip_optional_steps": True,
                    "can_reorder_steps": False
                }
            },
            "loop_control": {
                "max_iterations": 3,
                "iteration_context_mode": "SUMMARIZED"
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.3,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            },
            "context_policy": {"type": "FULL"}
        },
        capabilities={
            "context_engineering": {
                "context_priority": ["SYSTEM_PROMPT", "USER_INPUT", "STATIC_PLAN"]
            }
        },
        governance={
            "timeout_ms": 600000,
            "max_recursion_depth": 10
        },
        io_contract={
            "input_schema": {
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "The research topic to investigate"},
                    "depth": {"type": "string", "enum": ["basic", "comprehensive", "exhaustive"], "description": "Research depth level"},
                    "output_filename": {"type": "string", "description": "Name for the output PDF file"}
                },
                "required": ["input"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "pdf_path": {"type": "string"},
                    "summary": {"type": "string"},
                    "sources_count": {"type": "integer"}
                }
            }
        },
        observability={
            "log_level": "INFO",
            "log_thoughts": True,
            "track_cost": True
        }
    )
    
    session.add(process)
    await session.commit()
    print(f"✓ Created PROCESS entity")
    return process


async def main():
    """Main setup function"""
    print("\n" + "="*60)
    print("Deep Research Process - Entity Setup")
    print("="*60 + "\n")
    
    async with AsyncSessionLocal() as session:
        # Get first company (or create one if needed)
        result = await session.execute(select(Company).limit(1))
        company = result.scalar_one_or_none()
        
        if not company:
            print("❌ No company found in database. Please create a company first.")
            return
        
        print(f"Using company: {company.name} (ID: {company.id})\n")
        
        # Create entities in bottom-up order
        actions = await create_action_entities(session, company.id)
        skills = await create_skill_entities(session, company.id, actions)
        agents = await create_agent_entities(session, company.id, skills)
        process = await create_process_entity(session, company.id, agents)
        
        print("\n" + "="*60)
        print("✅ Successfully created all 18 entities!")
        print("="*60)
        print(f"\nProcess Entity ID: {process.id}")
        print(f"Process Name: {process.display_name}")
        print("\nYou can now execute this process from the frontend.")
        print("Navigate to Entity Library and find 'Deep Research Process'")
        print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
