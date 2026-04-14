#!/usr/bin/env python3
"""
Deep Research Cleanup & Recreate Script
=========================================
1. Deletes ALL existing deep-research entities (all 3 duplicate runs, 45 total)
2. Recreates the proper 15-entity hierarchy bottom-up
3. Links parent→child hierarchy relationships
4. Saves new entity_ids.json

Usage:
    python cleanup_and_recreate.py
"""

import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install with: pip install requests")
    sys.exit(1)

try:
    from jose import jwt
    from datetime import datetime, timedelta
except ImportError:
    print("Error: 'python-jose' library is required. Install with: pip install python-jose[cryptography]")
    sys.exit(1)


# ============================================================================
# Configuration
# ============================================================================

BASE_URL = "http://localhost:8000/api/v1"

# Generate a fresh JWT token
USER_EMAIL = "admin@hirebuddha.com"
COMPANY_ID = "699098ce-a31c-42ef-b13b-2780c7decb9d"
SECRET_KEY = "dev_secret_key_change_in_production"
ALGORITHM = "HS256"

def generate_token():
    data = {
        "sub": USER_EMAIL,
        "company_id": COMPANY_ID,
        "exp": datetime.utcnow() + timedelta(hours=24),
    }
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

TOKEN = generate_token()

# All 45 entity IDs to delete (3 runs × 15 entities each)
ALL_OLD_ENTITY_IDS = [
    # ---- Run 1 (11:15:55) ----
    "2715ad0f-ade8-47d4-be99-43cc80da54e3",
    "fb954229-d278-4f25-9029-2314ee7536ce",
    "f455da89-af5d-497f-8319-c92c0f6ae9e6",
    "6557d6ec-c2ea-40d9-ba13-f8959d456037",
    "fd0962b4-aa93-41d8-b581-00b11f9b2ceb",
    "e73a3327-68f7-4077-be25-aa08225e85fa",
    "65d31fe3-6ead-4dab-bf77-a4c67fac74b9",
    "92e25890-ed2d-4f26-ab13-85f069a4abae",
    "4f03ce8b-77a8-4fdb-b02c-df3177cd3f83",
    "05751383-2fc0-4e63-abd0-e848bcbcba99",
    "d4c1b02c-8837-4a13-94cf-90ff7a43a2eb",
    "647e58d9-0b0e-4908-ba11-ea71aeb03a8c",
    "e053fe51-6011-4792-81db-5c6653844455",
    "418361cf-3fc0-47c2-8bec-e75349b8465b",
    "7606fccc-034d-41df-bcae-9467740313e6",
    # ---- Run 2 (11:19:30) ----
    "53cddd83-49fe-450b-902a-7fbe6eca617f",
    "a35215c9-030b-442a-bc60-0693b9629fab",
    "6b9784c9-556e-45c2-be0b-89375d5ac18d",
    "354a78d1-ea68-4891-bcea-c0b8b05e7e79",
    "e714b455-de23-4ace-ad21-6e7bee2c249c",
    "37e33b5f-ee2a-4da8-97b9-04df6d9183b5",
    "bf03044f-03af-4b44-939c-ed35623f77c9",
    "cc6963b9-1369-4214-8bb1-088933169d23",
    "6e40c49f-5b7c-49c2-97f0-542737245202",
    "030b0b61-fafb-4f00-885d-139163d9c459",
    "ff9896d2-1d9b-4ee6-be07-57a558d9b9ac",
    "44d360a8-c576-4c7a-99f0-e523cd105bc8",
    "b863c432-c202-41cf-bfea-5a1fd4b314ba",
    "4b6f9ba5-aaa2-40c6-815e-0ce36d377a05",
    "830ff012-9db9-4ad9-8b8a-5864cdb391bc",
    # ---- Run 3 (11:20:08) — currently in entity_ids.json ----
    "30ad3a01-58cb-4fe1-a673-ccdaff9d9257",
    "17e96f3e-2f61-4d21-bdec-e381cbe4fc8e",
    "55ce31e2-3b13-46e6-9e05-98ee10ad9b0d",
    "d104ac3c-be2c-433f-9045-cf6cfbc7b938",
    "b5cb9eaa-e9a9-4839-a373-9c0780a2af6d",
    "f336943c-f95c-4b90-8c5f-9dc73a242590",
    "d7cc01fe-0949-48f3-9941-c5a78570293d",
    "0ce8468a-defe-4f45-9b94-b3343eff3c62",
    "4ce729a9-3c04-4295-98fc-3fa8aaf35e73",
    "497838f4-195a-42c2-9c50-f19412c7362b",
    "6c220fbf-ecfb-4f36-8ae2-75cd28b52b45",
    "4f6769c3-f8a0-4a74-8d98-2c228169ef45",
    "790933f1-e142-4b01-aceb-bc5c7d89b30a",
    "3ed7265e-f48f-47c6-bfb5-4629bdc5a636",
    "55e4083e-3760-4e4e-b7b5-661c4a23b03a",
]


# ============================================================================
# API Client
# ============================================================================

class APIClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        })

    def delete_entity(self, entity_id: str) -> bool:
        url = f"{self.base_url}/ai/entities/{entity_id}"
        resp = self.session.delete(url)
        if resp.status_code in (200, 204):
            print(f"  🗑️  Deleted: {entity_id}")
            return True
        elif resp.status_code == 404:
            print(f"  ⚠️  Not found (already deleted?): {entity_id}")
            return True
        else:
            print(f"  ❌ Delete failed ({resp.status_code}): {entity_id} — {resp.text[:200]}")
            return False

    def create_entity(self, payload: dict) -> dict:
        url = f"{self.base_url}/ai/entities"
        resp = self.session.post(url, json=payload)
        if resp.status_code not in (200, 201):
            print(f"  ❌ FAILED: {resp.status_code} — {resp.text[:500]}")
            resp.raise_for_status()
        data = resp.json()
        print(f"  ✅ Created: {data['name']} → {data['id']}")
        return data

    def update_entity(self, entity_id: str, payload: dict) -> dict:
        url = f"{self.base_url}/ai/entities/{entity_id}"
        resp = self.session.put(url, json=payload)
        if resp.status_code not in (200, 201):
            print(f"  ❌ UPDATE FAILED: {resp.status_code} — {resp.text[:500]}")
            resp.raise_for_status()
        data = resp.json()
        print(f"  ✅ Updated: {data['name']} — hierarchy linked")
        return data


# ============================================================================
# Entity Definitions (imported from create_entities.py structure)
# ============================================================================

# --- Layer 1: ACTIONs (7 entities) ---

ACTIONS = [
    {
        "key": "web_search_action",
        "payload": {
            "name": "deep-research-web-search",
            "display_name": "Deep Research Web Search",
            "description": "Executes a targeted web search query using SerpAPI/DuckDuckGo and returns structured results with titles, URLs, and snippets. Designed for precision recall on academic, technical, and current-affairs queries.",
            "goal": "Find the most relevant, authoritative web results for a given search query. Prioritize primary sources, academic publications, official documentation, and authoritative news sources over blog posts and opinion pieces.",
            "type": "ACTION",
            "version": "1.0.0",
            "status": "ACTIVE",
            "tags": ["deep-research", "search", "web", "information-retrieval"],
            "identity": {
                "system_prompt": "You are a precision web search specialist. Your job is to formulate the optimal search query and extract the most relevant results. Always prioritize: (1) Primary sources and official documentation, (2) Peer-reviewed or academic sources, (3) Authoritative journalism from established outlets, (4) Expert analysis from recognized domain specialists. Deprioritize: opinion blogs, social media posts, aggregator sites.",
                "behavioral_constraints": [
                    "Never fabricate search results or URLs",
                    "Always preserve exact URLs from search results",
                    "Flag when results seem outdated or potentially unreliable",
                    "Include publication dates when available"
                ]
            },
            "hierarchy": {"is_atomic": True, "composition_depth": 0, "children": []},
            "logic_gate": {
                "reasoning_config": {"task_type": "text_generation", "temperature": 0.2, "reasoning_mode": "REACT"},
                "retry_policy": {"max_retries": 2, "backoff_strategy": "EXPONENTIAL", "retry_on": ["TOOL_FAILURE", "TIMEOUT"]},
                "context_policy": {"type": "EXPLICIT", "explicit_keys": ["input", "query"], "summarize_threshold": 8000}
            },
            "planning": {
                "static_plan": {
                    "enabled": True,
                    "steps": [{
                        "step_id": "step_1", "order": 1,
                        "name": "Execute Web Search",
                        "description": "Run the web search query using the web_search tool",
                        "type": "TOOL_CALL",
                        "target": {"tool_id": "web_search", "prompt_template": "{{input}}", "input_dependencies": []},
                        "required": True
                    }]
                },
                "dynamic_planning": {"enabled": False}
            },
            "capabilities": {
                "tools": [{"tool_id": "web_search"}],
                "memory": {"enabled": True, "mode": "CORTEX"},
                "context_engineering": {"inject_cortex_viewport": True}
            },
            "governance": {"timeout_ms": 30000, "max_cost_usd": 0.10},
            "io_contract": {
                "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "The search query to execute"}}, "required": ["query"]},
                "output_schema": {"type": "object", "properties": {"results": {"type": "array", "description": "List of search result objects"}}}
            }
        }
    },
    {
        "key": "page_scrape_action",
        "payload": {
            "name": "deep-research-page-scrape",
            "display_name": "Deep Research Page Scraper",
            "description": "Scrapes a web page URL using Firecrawl and returns clean markdown content.",
            "goal": "Extract the complete, clean text content from a web page, preserving structure while removing navigation, ads, and boilerplate.",
            "type": "ACTION", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "scraping", "content-extraction"],
            "identity": {
                "system_prompt": "You are a web content extraction specialist. Extract the main content from web pages while preserving document structure. Focus on the article body, data tables, and key figures. Ignore navigation, ads, sidebars, and cookie banners.",
                "behavioral_constraints": ["Never modify the factual content of scraped text", "Preserve all data tables and structured information", "Note when content appears truncated or behind a paywall"]
            },
            "hierarchy": {"is_atomic": True, "composition_depth": 0, "children": []},
            "logic_gate": {
                "reasoning_config": {"task_type": "text_generation", "temperature": 0.1, "reasoning_mode": "REACT"},
                "retry_policy": {"max_retries": 3, "backoff_strategy": "EXPONENTIAL", "retry_on": ["TOOL_FAILURE", "TIMEOUT"]},
                "context_policy": {"type": "EXPLICIT", "explicit_keys": ["input", "url"]}
            },
            "planning": {"static_plan": {"enabled": True, "steps": [{"step_id": "step_1", "order": 1, "name": "Scrape URL Content", "description": "Scrape the target URL using the scraper tool", "type": "TOOL_CALL", "target": {"tool_id": "scraper_tool", "prompt_template": "{{input}}"}}]}},
            "capabilities": {"tools": [{"tool_id": "scraper_tool"}], "memory": {"enabled": True, "mode": "CORTEX"}},
            "governance": {"timeout_ms": 60000, "max_cost_usd": 0.05}
        }
    },
    {
        "key": "content_extract_action",
        "payload": {
            "name": "deep-research-content-extract",
            "display_name": "Deep Research Content Extractor",
            "description": "Analyzes scraped web content and extracts structured information: key claims, statistics, direct quotes, named entities, dates, and source credibility assessment.",
            "goal": "Transform raw web content into structured, citation-ready research notes with explicit source attribution for every extracted fact.",
            "type": "ACTION", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "extraction", "analysis", "NLP"],
            "identity": {
                "system_prompt": "You are a research analyst specializing in information extraction. From the given content, extract: (1) KEY CLAIMS, (2) STATISTICS, (3) QUOTES, (4) ENTITIES, (5) CREDIBILITY. Output as structured JSON.",
                "behavioral_constraints": ["Never infer statistics that aren't explicitly stated", "Always attribute claims to their original source", "Distinguish between facts, claims, and opinions", "Flag contradictions"]
            },
            "hierarchy": {"is_atomic": True, "composition_depth": 0, "children": []},
            "logic_gate": {
                "reasoning_config": {"task_type": "text_generation", "temperature": 0.2, "reasoning_mode": "CHAIN_OF_THOUGHT"},
                "context_policy": {"type": "FULL", "summarize_threshold": 15000}
            },
            "planning": {"static_plan": {"enabled": True, "steps": [{"step_id": "step_1", "order": 1, "name": "Extract Structured Information", "description": "Analyze the provided content and extract key claims, statistics, quotes, entities, and credibility assessment into structured JSON format", "type": "ACTION", "target": {"prompt_template": "Analyze this content and extract structured research information:\n\n{{input}}"}}]}},
            "capabilities": {"tools": [], "memory": {"enabled": True, "mode": "CORTEX"}},
            "governance": {"timeout_ms": 60000, "max_cost_usd": 0.15}
        }
    },
    {
        "key": "fact_check_action",
        "payload": {
            "name": "deep-research-fact-check",
            "display_name": "Deep Research Fact Checker",
            "description": "Takes a specific claim or statistic and verifies it against multiple independent sources via web search.",
            "goal": "Independently verify claims by cross-referencing against at least 2-3 independent authoritative sources. Produce a clear verdict: VERIFIED, PARTIALLY_VERIFIED, UNVERIFIED, or CONTRADICTED.",
            "type": "ACTION", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "fact-checking", "verification"],
            "identity": {
                "system_prompt": "You are a rigorous fact-checker. For each claim: (1) Search for independent corroboration, (2) Identify contradicting evidence, (3) Note recency and reliability, (4) Assign a verdict: VERIFIED/PARTIALLY_VERIFIED/UNVERIFIED/CONTRADICTED. Always show your verification chain.",
                "behavioral_constraints": ["Never mark a claim as VERIFIED without at least 2 independent sources", "Primary sources always outweigh secondary sources", "Note temporal limitations", "Flag unfalsifiable claims"]
            },
            "hierarchy": {"is_atomic": True, "composition_depth": 0, "children": []},
            "logic_gate": {
                "reasoning_config": {"task_type": "text_generation", "temperature": 0.1, "reasoning_mode": "REFLECTION"},
                "retry_policy": {"max_retries": 2, "backoff_strategy": "LINEAR"}
            },
            "planning": {"static_plan": {"enabled": True, "steps": [
                {"step_id": "step_1", "order": 1, "name": "Search for Verification", "description": "Search the web for independent sources that confirm or deny the claim", "type": "TOOL_CALL", "target": {"tool_id": "web_search", "prompt_template": "verify: {{input}}"}},
                {"step_id": "step_2", "order": 2, "name": "Assess Verification Evidence", "description": "Analyze search results and produce a verification verdict", "type": "ACTION", "target": {"prompt_template": "Based on the search results in {{step_1}}, verify the original claim:\n\nCLAIM: {{input}}\n\nProduce a verification verdict (VERIFIED/PARTIALLY_VERIFIED/UNVERIFIED/CONTRADICTED) with:\n1. Supporting sources (URL + key quote)\n2. Contradicting sources (if any)\n3. Confidence level (0-100%)\n4. Caveats or limitations", "input_dependencies": ["step_1"]}}
            ]}},
            "capabilities": {"tools": [{"tool_id": "web_search"}], "memory": {"enabled": True, "mode": "CORTEX"}},
            "governance": {"timeout_ms": 90000, "max_cost_usd": 0.20}
        }
    },
    {
        "key": "section_writer_action",
        "payload": {
            "name": "deep-research-section-writer",
            "display_name": "Deep Research Section Writer",
            "description": "Writes a single, publication-quality section of a research report from structured research findings.",
            "goal": "Transform research findings into a compelling, well-structured report section that reads like it was written by a senior research analyst.",
            "type": "ACTION", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "writing", "report-generation"],
            "identity": {
                "system_prompt": "You are a senior research writer producing publication-quality analysis. Every section you write must have: (1) A clear topic sentence, (2) Evidence paragraphs with analysis, (3) Proper inline citations [Source Name, Date], (4) A concluding insight.",
                "behavioral_constraints": ["Every factual claim must have an inline citation", "Never pad with generic filler text", "Use specific numbers over vague qualifiers", "Maintain consistent tone"]
            },
            "hierarchy": {"is_atomic": True, "composition_depth": 0, "children": []},
            "logic_gate": {"reasoning_config": {"task_type": "text_generation", "temperature": 0.5, "reasoning_mode": "CHAIN_OF_THOUGHT"}},
            "planning": {"static_plan": {"enabled": True, "steps": [{"step_id": "step_1", "order": 1, "name": "Write Report Section", "description": "Write a publication-quality section based on the provided research findings", "type": "ACTION", "target": {"prompt_template": "{{input}}"}}]}},
            "capabilities": {"tools": [], "memory": {"enabled": True, "mode": "CORTEX"}},
            "governance": {"timeout_ms": 120000, "max_cost_usd": 0.25}
        }
    },
    {
        "key": "outline_generator_action",
        "payload": {
            "name": "deep-research-outline-generator",
            "display_name": "Deep Research Outline Generator",
            "description": "Generates a detailed, hierarchical report outline based on the research topic and discovered information.",
            "goal": "Create a comprehensive report outline that ensures complete coverage of the topic.",
            "type": "ACTION", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "planning", "outline", "structure"],
            "identity": {
                "system_prompt": "You are a research report architect. Design outlines that: (1) Cover the topic comprehensively, (2) Flow logically, (3) Allocate depth proportional to importance, (4) Include specific content guidance. Output as a structured JSON array.",
                "behavioral_constraints": ["Every outline must include an Executive Summary section", "Every outline must include a Methodology/Sources section", "Subsections should be 3-7 per major section"]
            },
            "hierarchy": {"is_atomic": True, "composition_depth": 0, "children": []},
            "logic_gate": {"reasoning_config": {"task_type": "thinking", "temperature": 0.4, "reasoning_mode": "TREE_OF_THOUGHTS"}},
            "capabilities": {"tools": [], "memory": {"enabled": True, "mode": "CORTEX"}},
            "governance": {"timeout_ms": 90000, "max_cost_usd": 0.20}
        }
    },
    {
        "key": "pdf_export_action",
        "payload": {
            "name": "deep-research-pdf-export",
            "display_name": "Deep Research PDF Exporter",
            "description": "Takes the fully assembled research report content and generates a professionally formatted PDF document.",
            "goal": "Produce a publication-ready PDF.",
            "type": "ACTION", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "pdf", "export", "document-generation"],
            "identity": {
                "system_prompt": "You are a document formatting specialist. Format the report into a professional PDF with proper headers, page numbers, table of contents, citations, and consistent typography.",
                "behavioral_constraints": ["Preserve all citations and source references", "Maintain heading hierarchy", "Include page numbers and table of contents"]
            },
            "hierarchy": {"is_atomic": True, "composition_depth": 0, "children": []},
            "logic_gate": {"reasoning_config": {"task_type": "text_generation", "temperature": 0.1, "reasoning_mode": "REACT"}},
            "planning": {"static_plan": {"enabled": True, "steps": [{"step_id": "step_1", "order": 1, "name": "Generate PDF Report", "description": "Generate a professionally formatted PDF from the report content", "type": "TOOL_CALL", "target": {"tool_id": "pdf_generator", "prompt_template": "{{input}}"}}]}},
            "capabilities": {"tools": [{"tool_id": "pdf_generator"}], "memory": {"enabled": True, "mode": "CORTEX"}},
            "governance": {"timeout_ms": 120000, "max_cost_usd": 0.10}
        }
    },
]

# --- Layer 2: SKILLs (5 entities) ---

SKILLS = [
    {
        "key": "query_decomposer_skill",
        "payload": {
            "name": "deep-research-query-decomposer",
            "display_name": "Research Query Decomposer",
            "description": "Takes a broad research topic and systematically decomposes it into 5-15 targeted, non-overlapping search queries.",
            "goal": "Generate a set of search queries that provide comprehensive, multi-perspective coverage of the research topic.",
            "type": "SKILL", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "query-planning", "decomposition"],
            "identity": {
                "system_prompt": "You are a research query strategist. You use: (1) TAXONOMIC DECOMPOSITION, (2) PERSPECTIVE TRIANGULATION, (3) SPECIFICITY GRADIENT, (4) TEMPORAL SPANNING, (5) SOURCE TARGETING. Output JSON array of query objects.",
                "behavioral_constraints": ["Generate minimum 5, maximum 15 queries", "Queries must be non-overlapping", "At least 2 queries must target opposing viewpoints", "At least 1 query must target quantitative data"]
            },
            "hierarchy": {"is_atomic": False, "composition_depth": 1, "children": []},
            "logic_gate": {
                "reasoning_config": {"task_type": "thinking", "temperature": 0.5, "reasoning_mode": "TREE_OF_THOUGHTS"},
                "context_policy": {"type": "FULL", "summarize_threshold": 12000}
            },
            "planning": {
                "static_plan": {"enabled": True, "steps": [
                    {"step_id": "step_1", "order": 1, "name": "Analyze Research Topic", "description": "Analyze the research topic to identify key dimensions", "type": "ACTION", "target": {"prompt_template": "Analyze this research topic and identify all key dimensions:\n\nTOPIC: {{input}}"}},
                    {"step_id": "step_2", "order": 2, "name": "Generate Search Queries", "description": "Generate 5-15 targeted search queries", "type": "ACTION", "target": {"prompt_template": "Based on this topic analysis:\n\n{{step_1}}\n\nGenerate 5-15 optimal search queries as a JSON array.", "input_dependencies": ["step_1"]}}
                ]},
                "dynamic_planning": {"enabled": False}
            },
            "capabilities": {"tools": [], "memory": {"enabled": True, "mode": "CORTEX"}},
            "governance": {"timeout_ms": 120000, "max_cost_usd": 0.30}
        }
    },
    {
        "key": "source_discoverer_skill",
        "payload": {
            "name": "deep-research-source-discoverer",
            "display_name": "Research Source Discoverer",
            "description": "Executes a batch of search queries, deduplicates results, ranks sources by authority and relevance.",
            "goal": "Discover and rank the most authoritative, relevant sources for the research topic.",
            "type": "SKILL", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "source-discovery", "search-execution"],
            "identity": {
                "system_prompt": "You are a research librarian specializing in source discovery and evaluation. Evaluate and rank sources by authority, recency, depth, uniqueness, and bias.",
                "behavioral_constraints": ["Execute ALL provided search queries", "Deduplicate URLs", "Include at least 3 different source types", "Flag any sources with known bias"]
            },
            "hierarchy": {"is_atomic": False, "composition_depth": 1, "children": []},
            "logic_gate": {
                "reasoning_config": {"task_type": "text_generation", "temperature": 0.3, "reasoning_mode": "REACT"},
                "context_policy": {"type": "SLIDING_WINDOW", "max_chars": 20000},
                "retry_policy": {"max_retries": 2, "backoff_strategy": "EXPONENTIAL"}
            },
            "planning": {
                "static_plan": {"enabled": True, "steps": [
                    {"step_id": "step_1", "order": 1, "name": "Execute All Search Queries", "description": "Execute each search query and collect all results", "type": "TOOL_CALL", "target": {"tool_id": "web_search", "prompt_template": "{{input}}"}},
                    {"step_id": "step_2", "order": 2, "name": "Rank and Deduplicate Sources", "description": "Analyze results, deduplicate URLs, rank sources", "type": "ACTION", "target": {"prompt_template": "Given these search results:\n\n{{step_1}}\n\nProduce a ranked, deduplicated source list. Select the top 10-15 most valuable sources for scraping.", "input_dependencies": ["step_1"]}}
                ]},
                "dynamic_planning": {"enabled": True, "planning_prompt": "If initial search queries yield insufficient results on a dimension, generate additional targeted queries."}
            },
            "capabilities": {"tools": [{"tool_id": "web_search"}], "memory": {"enabled": True, "mode": "CORTEX"}},
            "governance": {"timeout_ms": 300000, "max_cost_usd": 1.00}
        }
    },
    {
        "key": "source_analyzer_skill",
        "payload": {
            "name": "deep-research-source-analyzer",
            "display_name": "Research Source Analyzer",
            "description": "For each high-priority source: scrapes content, extracts key claims/statistics/quotes, assesses credibility, writes findings to CORTEX.",
            "goal": "Transform raw web sources into structured, citation-ready research knowledge.",
            "type": "SKILL", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "source-analysis", "extraction"],
            "identity": {
                "system_prompt": "You are a deep research analyst. For each source URL: (1) Scrape full content, (2) Extract key claims/statistics/quotes, (3) Assess credibility, (4) Identify cross-source relationships, (5) Write findings to CORTEX tree.",
                "behavioral_constraints": ["Process sources one at a time", "Write findings to CORTEX after each source", "Track cross-source corroboration", "Stop after 10 sources or diminishing returns"]
            },
            "hierarchy": {"is_atomic": False, "composition_depth": 1, "children": []},
            "logic_gate": {
                "reasoning_config": {"task_type": "text_generation", "temperature": 0.2, "reasoning_mode": "CHAIN_OF_THOUGHT"},
                "context_policy": {"type": "SLIDING_WINDOW", "max_chars": 25000, "summarize_threshold": 20000}
            },
            "planning": {
                "static_plan": {"enabled": True, "steps": [
                    {"step_id": "step_1", "order": 1, "name": "Scrape Source Content", "description": "Scrape the full content from the next priority source URL", "type": "TOOL_CALL", "target": {"tool_id": "scraper_tool", "prompt_template": "{{input}}"}},
                    {"step_id": "step_2", "order": 2, "name": "Extract Structured Information", "description": "Analyze scraped content and extract key information", "type": "ACTION", "target": {"prompt_template": "Analyze this scraped content and extract structured research information:\n\n{{step_1}}\n\nExtract: KEY_CLAIMS, STATISTICS, QUOTES, ENTITIES, CREDIBILITY_SCORE (1-5), RELATIONSHIP_TO_PRIOR_FINDINGS", "input_dependencies": ["step_1"]}}
                ]},
                "dynamic_planning": {"enabled": True, "planning_prompt": "Iterate through all source URLs. For each URL: scrape, analyze, then continue. Skip failed scrapes."},
                "loop_control": {"max_iterations": 12, "iteration_context_mode": "SUMMARIZED", "summary_every_n_iterations": 3}
            },
            "capabilities": {
                "tools": [{"tool_id": "scraper_tool"}, {"tool_id": "headless_browser"}, {"tool_id": "web_search"}],
                "memory": {"enabled": True, "mode": "CORTEX", "cortex_config": {"auto_checkpoint": True, "context_budget_pct": 40}}
            },
            "governance": {"timeout_ms": 600000, "max_cost_usd": 3.00}
        }
    },
    {
        "key": "fact_verifier_skill",
        "payload": {
            "name": "deep-research-fact-verifier",
            "display_name": "Research Fact Verification Engine",
            "description": "Systematically verifies critical claims against independent sources. Produces a verification matrix.",
            "goal": "Ensure factual accuracy by independently verifying every critical claim.",
            "type": "SKILL", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "fact-checking", "verification", "quality"],
            "identity": {
                "system_prompt": "You are a senior fact-checker for a Tier-1 research firm. NO claim appears in the final report without independent verification. Process each claim through a 3-source verification protocol.",
                "behavioral_constraints": ["Verify the 10 most critical claims at minimum", "Each verification must cite at least 2 independent sources", "Flag single-source claims", "Produce a verification matrix"]
            },
            "hierarchy": {"is_atomic": False, "composition_depth": 1, "children": []},
            "logic_gate": {
                "reasoning_config": {"task_type": "text_generation", "temperature": 0.1, "reasoning_mode": "REFLECTION"},
                "context_policy": {"type": "SLIDING_WINDOW", "max_chars": 15000}
            },
            "planning": {
                "dynamic_planning": {"enabled": True, "planning_prompt": "For each critical claim: (1) formulate verification query, (2) search, (3) assess evidence, (4) record verdict. Use web_search."},
                "loop_control": {"max_iterations": 15, "iteration_context_mode": "SUMMARIZED", "summary_every_n_iterations": 5}
            },
            "capabilities": {
                "tools": [{"tool_id": "web_search"}],
                "memory": {"enabled": True, "mode": "CORTEX", "cortex_config": {"auto_checkpoint": True}}
            },
            "governance": {"timeout_ms": 600000, "max_cost_usd": 2.00}
        }
    },
    {
        "key": "knowledge_synthesizer_skill",
        "payload": {
            "name": "deep-research-knowledge-synthesizer",
            "display_name": "Research Knowledge Synthesizer",
            "description": "Reads the complete CORTEX knowledge tree and synthesizes into a coherent report with outline, sections, and PDF export.",
            "goal": "Transform accumulated CORTEX knowledge into a publication-quality research report.",
            "type": "SKILL", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "synthesis", "report-writing", "output"],
            "identity": {
                "system_prompt": "You are a senior research writer and knowledge synthesizer. (1) Navigate CORTEX, (2) Identify narrative threads, (3) Design report outline, (4) Write each section with citations, (5) ANALYZE, don't just summarize.",
                "behavioral_constraints": ["Read ALL CORTEX nodes before writing", "Executive Summary written LAST", "Every factual claim must be cited", "Include a Key Findings section"]
            },
            "hierarchy": {"is_atomic": False, "composition_depth": 1, "children": []},
            "logic_gate": {
                "reasoning_config": {"task_type": "text_generation", "temperature": 0.5, "reasoning_mode": "CHAIN_OF_THOUGHT"},
                "context_policy": {"type": "FULL", "summarize_threshold": 30000},
                "review_mechanism": {"enabled": True, "review_prompt": "Review the report section for factual accuracy, analytical depth, coherence, and completeness.", "on_failure": "RETRY"}
            },
            "planning": {
                "static_plan": {"enabled": True, "steps": [
                    {"step_id": "step_1", "order": 1, "name": "Synthesize Knowledge Tree", "description": "Read all findings from CORTEX and synthesize key themes", "type": "ACTION", "target": {"prompt_template": "Review all research findings and synthesize key themes:\n\n{{input}}"}},
                    {"step_id": "step_2", "order": 2, "name": "Generate Report Outline", "description": "Create a detailed, hierarchical report outline", "type": "ACTION", "target": {"prompt_template": "Based on these synthesized themes:\n\n{{step_1}}\n\nGenerate a comprehensive report outline as a JSON array.", "input_dependencies": ["step_1"]}},
                    {"step_id": "step_3", "order": 3, "name": "Write Full Report", "description": "Write each section of the report with proper citations", "type": "ACTION", "target": {"prompt_template": "Using this outline:\n\n{{step_2}}\n\nAnd these research findings:\n\n{{step_1}}\n\nWrite the complete research report. Write the Executive Summary LAST.", "input_dependencies": ["step_1", "step_2"]}},
                    {"step_id": "step_4", "order": 4, "name": "Generate PDF", "description": "Export the final report as a professionally formatted PDF", "type": "TOOL_CALL", "target": {"tool_id": "pdf_generator", "prompt_template": "{{step_3}}", "input_dependencies": ["step_3"]}}
                ]},
                "dynamic_planning": {"enabled": True, "planning_prompt": "If sections are too long, break into subsections."}
            },
            "capabilities": {
                "tools": [{"tool_id": "pdf_generator"}],
                "memory": {"enabled": True, "mode": "CORTEX", "cortex_config": {"auto_checkpoint": True, "context_budget_pct": 50}}
            },
            "governance": {"timeout_ms": 900000, "max_cost_usd": 5.00}
        }
    },
]

# --- Layer 3: AGENTs (2 entities) ---

AGENTS = [
    {
        "key": "research_director_agent",
        "payload": {
            "name": "deep-research-director",
            "display_name": "Research Director",
            "description": "Autonomous research agent that orchestrates the complete information gathering pipeline with multi-wave iterative research.",
            "goal": "Gather the most comprehensive, verified, multi-source body of research knowledge on the given topic.",
            "type": "AGENT", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "research-agent", "director", "orchestrator"],
            "identity": {
                "system_prompt": "You are the Research Director — a relentless research investigator.\n\n## Wave 1: Broad Discovery\n- Decompose the topic into 8-12 search queries\n- Execute searches and rank sources\n- Scrape and analyze the top 8-10 sources\n\n## Wave 2: Deep Dive\n- Identify gaps in Wave 1\n- Generate follow-up queries\n- Scrape 5-8 additional sources\n\n## Wave 3: Verification\n- Extract 10-15 critical claims\n- Independently verify each\n- Build verification matrix\n\nCHECKPOINT after each wave.",
                "behavioral_constraints": ["Always perform at least 2 research waves", "Never rely on a single source", "Always include opposing viewpoints", "Checkpoint after each wave", "Note scrape failures and find alternatives"]
            },
            "hierarchy": {"is_atomic": False, "composition_depth": 2, "children": []},
            "logic_gate": {
                "reasoning_config": {"task_type": "thinking", "temperature": 0.4, "reasoning_mode": "REFLECTION"},
                "retry_policy": {"max_retries": 3, "backoff_strategy": "EXPONENTIAL"},
                "context_policy": {"type": "SLIDING_WINDOW", "max_chars": 30000, "summarize_threshold": 25000, "preserve_keys": ["research_topic", "current_wave", "verification_matrix"]},
                "review_mechanism": {"enabled": True, "review_prompt": "Evaluate research completeness: (1) All topic dimensions covered? (2) At least 3 sources per major claim? (3) Opposing viewpoints explored? (4) Verification matrix complete?", "on_failure": "RETRY"}
            },
            "planning": {
                "dynamic_planning": {
                    "enabled": True,
                    "planning_prompt": "Plan a multi-wave research process:\n\nWave 1 — Broad Discovery: Decompose topic → execute searches → discover and rank sources → scrape top sources → extract findings\n\nWave 2 — Deep Dive: Identify gaps → follow-up queries → search → scrape additional sources → extract findings\n\nWave 3 — Verification: Extract critical claims → verify each independently → build verification matrix\n\nUse tools: web_search, scraper_tool, headless_browser. CHECKPOINT after each wave.",
                    "allowed_deviations": {"can_add_steps": True, "can_skip_optional_steps": True, "can_reorder_steps": True, "can_change_tools": True},
                    "reconciliation_strategy": "DYNAMIC_PRIORITY"
                },
                "loop_control": {"max_iterations": 3, "iteration_context_mode": "SUMMARIZED", "summary_every_n_iterations": 1}
            },
            "capabilities": {
                "tools": [{"tool_id": "web_search"}, {"tool_id": "scraper_tool"}, {"tool_id": "headless_browser"}],
                "memory": {"enabled": True, "mode": "CORTEX", "cortex_config": {"max_children": 12, "page_size_tokens": 8000, "context_budget_pct": 40, "auto_checkpoint": True, "resume_enabled": True}},
                "context_engineering": {"inject_cortex_viewport": True, "inject_episodic_memory": True, "inject_semantic_context": True, "no_truncation": True}
            },
            "governance": {"timeout_ms": 1200000, "max_cost_usd": 8.00, "max_recursion_depth": 4, "execution_limits": {"max_tool_calls": 50}},
            "observability": {"log_level": "INFO", "log_thoughts": True, "track_cost": True}
        }
    },
    {
        "key": "report_synthesizer_agent",
        "payload": {
            "name": "deep-research-synthesizer",
            "display_name": "Report Synthesizer",
            "description": "Autonomous report synthesis agent. Reads the CORTEX knowledge tree, identifies narrative threads, writes each section, reviews, and exports PDF.",
            "goal": "Produce a world-class research report with coherent analytical narrative, proper citations, and original analytical insights.",
            "type": "AGENT", "version": "1.0.0", "status": "ACTIVE",
            "tags": ["deep-research", "synthesis-agent", "report-writer"],
            "identity": {
                "system_prompt": "You are the Report Synthesizer — a world-class research writer.\n\n## Your Process:\n1. READ entire CORTEX knowledge tree\n2. IDENTIFY narrative threads\n3. DESIGN report outline\n4. WRITE each section, reviewing after each\n5. WRITE Executive Summary last\n6. EXPORT as PDF\n\n## Quality Standards:\n- Every paragraph: at least one data point or cited fact\n- Analysis > Description\n- Cross-reference findings\n- Include implications",
                "behavioral_constraints": ["Read ALL CORTEX nodes before writing", "Executive Summary written LAST", "Every section ends with an analytical insight", "Include Sources/References section", "Self-review each major section"]
            },
            "hierarchy": {"is_atomic": False, "composition_depth": 2, "children": []},
            "logic_gate": {
                "reasoning_config": {"task_type": "text_generation", "temperature": 0.5, "reasoning_mode": "REFLECTION"},
                "context_policy": {"type": "FULL", "summarize_threshold": 30000, "preserve_keys": ["report_outline", "completed_sections"]},
                "review_mechanism": {"enabled": True, "review_prompt": "Review critically: (1) All claims cited? (2) Analytical insight? (3) Logical flow? (4) Gaps? (5) Professional writing?", "success_criteria": [{"criterion": "All factual claims have inline citations", "validation_type": "LLM_JUDGE", "validator": "Check for [Source, Date] patterns in every factual claim"}, {"criterion": "Section contains analytical insight", "validation_type": "LLM_JUDGE", "validator": "Look for analytical language and insights beyond simple summarization"}], "on_failure": "RETRY"}
            },
            "planning": {
                "dynamic_planning": {"enabled": True, "planning_prompt": "Plan the report synthesis:\n1. Read all CORTEX findings\n2. Synthesize key themes\n3. Generate detailed outline\n4. Write each section, reviewing after each\n5. Write Executive Summary last\n6. Generate PDF\n\nUse pdf_generator tool for final export. Final report: 3000-8000 words."}
            },
            "capabilities": {
                "tools": [{"tool_id": "pdf_generator"}],
                "memory": {"enabled": True, "mode": "CORTEX", "cortex_config": {"auto_checkpoint": True, "context_budget_pct": 50, "resume_enabled": True}},
                "context_engineering": {"inject_cortex_viewport": True, "no_truncation": True}
            },
            "governance": {"timeout_ms": 900000, "max_cost_usd": 6.00, "max_recursion_depth": 3}
        }
    },
]


# ============================================================================
# Main Execution
# ============================================================================

def main():
    client = APIClient(BASE_URL, TOKEN)
    entity_ids = {}

    # ========================================
    # PHASE 0: Verify auth
    # ========================================
    print("=" * 60)
    print("Phase 0: Verifying authentication")
    print("=" * 60)
    resp = client.session.get(f"{BASE_URL}/ai/entities")
    if resp.status_code != 200:
        print(f"  ❌ Auth failed: {resp.status_code} — {resp.text[:200]}")
        sys.exit(1)
    print(f"  ✅ Authentication OK (found {len(resp.json())} existing entities)")

    # ========================================
    # PHASE 1: Delete all old deep-research entities
    # ========================================
    print("\n" + "=" * 60)
    print("Phase 1: Cleaning up ALL old deep-research entities (45 total)")
    print("=" * 60)

    deleted = 0
    failed = 0
    for eid in ALL_OLD_ENTITY_IDS:
        if client.delete_entity(eid):
            deleted += 1
        else:
            failed += 1
        time.sleep(0.1)

    print(f"\n  Summary: {deleted} deleted, {failed} failed")

    # ========================================
    # PHASE 2: Create ACTIONs (Layer 1)
    # ========================================
    print("\n" + "=" * 60)
    print("Phase 2: Creating ACTIONs (Layer 1 — 7 Atomic Operations)")
    print("=" * 60)
    for action_def in ACTIONS:
        key = action_def["key"]
        payload = action_def["payload"]
        try:
            result = client.create_entity(payload)
            entity_ids[key] = result["id"]
            time.sleep(0.3)
        except Exception as e:
            print(f"  ❌ Failed: {payload['name']}: {e}")
            sys.exit(1)

    # ========================================
    # PHASE 3: Create SKILLs (Layer 2)
    # ========================================
    print("\n" + "=" * 60)
    print("Phase 3: Creating SKILLs (Layer 2 — 5 Composed Capabilities)")
    print("=" * 60)
    for skill_def in SKILLS:
        key = skill_def["key"]
        payload = skill_def["payload"]
        try:
            result = client.create_entity(payload)
            entity_ids[key] = result["id"]
            time.sleep(0.3)
        except Exception as e:
            print(f"  ❌ Failed: {payload['name']}: {e}")
            sys.exit(1)

    # ========================================
    # PHASE 4: Create AGENTs (Layer 3)
    # ========================================
    print("\n" + "=" * 60)
    print("Phase 4: Creating AGENTs (Layer 3 — 2 Autonomous Specialists)")
    print("=" * 60)
    for agent_def in AGENTS:
        key = agent_def["key"]
        payload = agent_def["payload"]
        try:
            result = client.create_entity(payload)
            entity_ids[key] = result["id"]
            time.sleep(0.3)
        except Exception as e:
            print(f"  ❌ Failed: {payload['name']}: {e}")
            sys.exit(1)

    # ========================================
    # PHASE 5: Create PROCESS (Layer 4)
    # ========================================
    print("\n" + "=" * 60)
    print("Phase 5: Creating PROCESS (Layer 4 — Top-Level Orchestrator)")
    print("=" * 60)

    research_director_id = entity_ids["research_director_agent"]
    report_synthesizer_id = entity_ids["report_synthesizer_agent"]

    process_payload = {
        "name": "deep-research-process",
        "display_name": "🔬 Deep Research",
        "description": "World-class deep research process that takes any topic and produces a comprehensive, multi-source, fact-verified research report. Leverages CORTEX cognitive trees for unbounded context, multi-wave research with increasing depth, independent fact verification, and publication-quality synthesis.",
        "goal": "Conduct the most thorough, accurate, and analytically insightful research possible on the given topic. Produce a publication-quality report.",
        "type": "PROCESS", "version": "1.0.0", "status": "ACTIVE",
        "tags": ["deep-research", "process", "research", "analysis", "cortex-test"],
        "identity": {
            "system_prompt": "You are the Deep Research Orchestrator. You coordinate two specialized agents:\n\n1. **Research Director** — Conducts multi-wave information gathering with independent fact verification\n2. **Report Synthesizer** — Produces publication-quality analysis from accumulated knowledge\n\nYour process:\n1. Receive the research topic\n2. Invoke the Research Director\n3. Once research is complete, invoke the Report Synthesizer\n4. Return the completed report and PDF",
            "behavioral_constraints": ["Research Director must complete fully before Synthesizer begins", "If research is insufficient, send back for more", "Track total cost and halt if approaching limits", "Use CORTEX checkpointing"]
        },
        "hierarchy": {
            "is_atomic": False, "composition_depth": 3,
            "children": [
                {"child_id": research_director_id, "child_type": "AGENT", "relationship": "SEQUENTIAL"},
                {"child_id": report_synthesizer_id, "child_type": "AGENT", "relationship": "SEQUENTIAL"},
            ]
        },
        "logic_gate": {
            "reasoning_config": {"task_type": "thinking", "temperature": 0.3, "reasoning_mode": "REFLECTION"},
            "retry_policy": {"max_retries": 2, "backoff_strategy": "EXPONENTIAL"},
            "context_policy": {"type": "FULL", "summarize_threshold": 30000, "preserve_keys": ["research_topic", "research_status", "report_status"]}
        },
        "planning": {
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "step_1", "order": 1,
                        "name": "Research Phase",
                        "description": "Invoke the Research Director agent to conduct multi-wave research.",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": research_director_id, "prompt_template": "{{input}}", "input_dependencies": []},
                        "required": True
                    },
                    {
                        "step_id": "step_2", "order": 2,
                        "name": "Quality Gate",
                        "description": "Assess the completeness of the research phase.",
                        "type": "ACTION",
                        "target": {
                            "prompt_template": "Evaluate the research completeness:\n\n{{step_1}}\n\nAssess: (1) Sources analyzed ≥8, (2) Verification status, (3) Multi-perspective coverage, (4) Gaps. Output: PASS or NEEDS_MORE_RESEARCH.",
                            "input_dependencies": ["step_1"]
                        },
                        "required": True
                    },
                    {
                        "step_id": "step_3", "order": 3,
                        "name": "Synthesis Phase",
                        "description": "Invoke the Report Synthesizer agent to produce the final report.",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": report_synthesizer_id,
                            "prompt_template": "Synthesize the research into a comprehensive report. Research summary:\n\n{{step_1}}\n\nQuality assessment:\n\n{{step_2}}",
                            "input_dependencies": ["step_1", "step_2"]
                        },
                        "required": True
                    }
                ],
                "fallback_behavior": "ADAPTIVE"
            },
            "dynamic_planning": {"enabled": True, "planning_prompt": "If Quality Gate returns NEEDS_MORE_RESEARCH, re-invoke Research Director with specific gaps."}
        },
        "capabilities": {
            "tools": [],
            "memory": {"enabled": True, "mode": "CORTEX", "cortex_config": {"max_children": 12, "page_size_tokens": 8000, "context_budget_pct": 40, "auto_checkpoint": True, "resume_enabled": True}},
            "context_engineering": {"inject_cortex_viewport": True, "inject_episodic_memory": True, "no_truncation": True}
        },
        "governance": {"timeout_ms": 1800000, "max_cost_usd": 20.00, "max_recursion_depth": 5, "execution_limits": {"max_tool_calls": 100}},
        "observability": {"log_level": "INFO", "log_thoughts": True, "track_cost": True}
    }

    try:
        result = client.create_entity(process_payload)
        entity_ids["deep_research_process"] = result["id"]
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        sys.exit(1)

    # ========================================
    # PHASE 6: Link Entity Hierarchy
    # ========================================
    print("\n" + "=" * 60)
    print("Phase 6: Linking Entity Hierarchy (SKILLs → ACTIONs, AGENTs → SKILLs)")
    print("=" * 60)

    # SKILLs → ACTIONs
    skill_action_map = {
        "source_discoverer_skill": ["web_search_action"],
        "source_analyzer_skill": ["page_scrape_action", "content_extract_action"],
        "fact_verifier_skill": ["fact_check_action"],
        "knowledge_synthesizer_skill": ["outline_generator_action", "section_writer_action", "pdf_export_action"],
    }

    for skill_key, action_keys in skill_action_map.items():
        skill_id = entity_ids[skill_key]
        children = [
            {"child_id": entity_ids[ak], "child_type": "ACTION", "relationship": "SEQUENTIAL"}
            for ak in action_keys
        ]
        client.update_entity(skill_id, {
            "hierarchy": {"is_atomic": False, "composition_depth": 1, "children": children}
        })
        time.sleep(0.2)

    # AGENTs → SKILLs
    agent_skill_map = {
        "research_director_agent": [
            "query_decomposer_skill",
            "source_discoverer_skill",
            "source_analyzer_skill",
            "fact_verifier_skill",
        ],
        "report_synthesizer_agent": [
            "knowledge_synthesizer_skill",
        ],
    }

    for agent_key, skill_keys in agent_skill_map.items():
        agent_id = entity_ids[agent_key]
        children = [
            {"child_id": entity_ids[sk], "child_type": "SKILL", "relationship": "SEQUENTIAL"}
            for sk in skill_keys
        ]
        client.update_entity(agent_id, {
            "hierarchy": {"is_atomic": False, "composition_depth": 2, "children": children}
        })
        time.sleep(0.2)

    # ========================================
    # Summary
    # ========================================
    print("\n" + "=" * 60)
    print("✅ Deep Research Setup Complete!")
    print("=" * 60)
    print(f"\nTotal entities created: {len(entity_ids)}")

    # Print hierarchy tree
    print("\n📊 Entity Hierarchy:")
    print(f"  PROCESS: 🔬 Deep Research → {entity_ids['deep_research_process']}")
    print(f"  ├── AGENT: Research Director → {entity_ids['research_director_agent']}")
    print(f"  │   ├── SKILL: Query Decomposer → {entity_ids['query_decomposer_skill']}")
    print(f"  │   ├── SKILL: Source Discoverer → {entity_ids['source_discoverer_skill']}")
    print(f"  │   │   └── ACTION: Web Search → {entity_ids['web_search_action']}")
    print(f"  │   ├── SKILL: Source Analyzer → {entity_ids['source_analyzer_skill']}")
    print(f"  │   │   ├── ACTION: Page Scraper → {entity_ids['page_scrape_action']}")
    print(f"  │   │   └── ACTION: Content Extractor → {entity_ids['content_extract_action']}")
    print(f"  │   └── SKILL: Fact Verifier → {entity_ids['fact_verifier_skill']}")
    print(f"  │       └── ACTION: Fact Checker → {entity_ids['fact_check_action']}")
    print(f"  └── AGENT: Report Synthesizer → {entity_ids['report_synthesizer_agent']}")
    print(f"      └── SKILL: Knowledge Synthesizer → {entity_ids['knowledge_synthesizer_skill']}")
    print(f"          ├── ACTION: Outline Generator → {entity_ids['outline_generator_action']}")
    print(f"          ├── ACTION: Section Writer → {entity_ids['section_writer_action']}")
    print(f"          └── ACTION: PDF Exporter → {entity_ids['pdf_export_action']}")

    # Save entity IDs
    output_path = os.path.join(os.path.dirname(__file__), "entity_ids.json")
    with open(output_path, "w") as f:
        json.dump(entity_ids, f, indent=2)
    print(f"\nEntity IDs saved to: {output_path}")


if __name__ == "__main__":
    main()
