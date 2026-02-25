"""
Web Search Tool for HireBuddha AI Platform.

Provides real web search functionality using multiple backends:
1. Google Custom Search API — preferred (GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID env vars)
2. SerpAPI — second choice (SERP_API_KEY or SERPAPI_KEY env var)
3. duckduckgo-search library — free robust fallback (no API key needed)
4. DuckDuckGo Instant Answers API — final minimal fallback

Configure via Integration Registry or env vars.
"""

import httpx
import json
import os
import re
import logging
from typing import Dict, Any, List, Optional
from src.ai.tools.base import Tool

logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
    """Web search tool with multiple backend support.

    Priority order:
        1. Google Custom Search API (GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID)
        2. SerpAPI / Google Search (SERP_API_KEY or SERPAPI_KEY)
        3. duckduckgo-search Python library (free, no key)
        4. DuckDuckGo Instant Answers API (very limited, no key)
    """

    name = "web_search"
    description = (
        "Search the web for current information on any topic. "
        "Returns a list of relevant results including titles, URLs, and snippets. "
        "Input should be a plain-text search query or a JSON object with a 'query' key."
    )

    _TIMEOUT = 15.0
    _DDG_API_URL = "https://api.duckduckgo.com/"
    _GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"
    _SERP_API_URL = "https://serpapi.com/search"

    # ---------------------------------------------------------------------------
    # Input parsing
    # ---------------------------------------------------------------------------

    def _parse_query(self, input_data: str) -> str:
        """Extract search query from raw input string or JSON dict."""
        raw = (input_data or "").strip()
        if not raw:
            return ""

        # Try JSON parsing first
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    for key in ("query", "q", "search", "input", "text"):
                        if key in parsed and isinstance(parsed[key], str):
                            return parsed[key].strip()
                    # Fallback: first string value
                    for v in parsed.values():
                        if isinstance(v, str) and v.strip():
                            return v.strip()
            except json.JSONDecodeError:
                pass  # Not JSON

        return raw

    # ---------------------------------------------------------------------------
    # API key resolution
    # ---------------------------------------------------------------------------

    async def _resolve_keys(self, context: Optional[Dict] = None) -> Dict[str, Optional[str]]:
        """Look up available search API keys from env + integration registry."""
        keys = {
            "google_cse_api_key": os.getenv("GOOGLE_CSE_API_KEY"),
            "google_cse_id": os.getenv("GOOGLE_CSE_ID"),
            "serp_api_key": os.getenv("SERP_API_KEY") or os.getenv("SERPAPI_KEY"),
        }

        # Nothing to look up if all already found from env
        if all([keys["google_cse_api_key"], keys["google_cse_id"]]) or keys["serp_api_key"]:
            return keys

        # Integration registry lookup
        if context and context.get("company_id"):
            try:
                from uuid import UUID as _UUID
                from src.common.database import AsyncSessionLocal
                from sqlalchemy import select
                from src.config.models import IntegrationRegistry
                from src.common.security import decrypt_api_key

                async with AsyncSessionLocal() as db:
                    company_uuid = _UUID(str(context["company_id"]))
                    result = await db.execute(
                        select(IntegrationRegistry).where(
                            IntegrationRegistry.company_id == company_uuid,
                            IntegrationRegistry.status == "active",
                            IntegrationRegistry.encrypted_api_key.isnot(None),
                        )
                    )
                    entries = result.scalars().all()
                    for entry in entries:
                        name_lower = (entry.provider_name or "").lower()
                        model_lower = (entry.model_name or "").lower()
                        key_str = decrypt_api_key(entry.encrypted_api_key)

                        if "serp" in name_lower or "serp" in model_lower:
                            keys["serp_api_key"] = keys["serp_api_key"] or key_str
                        elif "google" in name_lower and "cse" in model_lower:
                            keys["google_cse_api_key"] = keys["google_cse_api_key"] or key_str
            except Exception as e:
                logger.debug(f"[WebSearch] Registry lookup failed: {e}")

        return keys

    # ---------------------------------------------------------------------------
    # Backend 1: Google Custom Search API
    # ---------------------------------------------------------------------------

    async def _search_google_cse(self, query: str, api_key: str, cse_id: str) -> Optional[List[Dict]]:
        """Search using Google Custom Search JSON API."""
        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                response = await client.get(
                    self._GOOGLE_CSE_URL,
                    params={
                        "key": api_key,
                        "cx": cse_id,
                        "q": query,
                        "num": 10,
                    }
                )
                response.raise_for_status()
                data = response.json()

            results = []
            for item in data.get("items", [])[:8]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })

            logger.info(f"[WebSearch] Google CSE returned {len(results)} results for: {query[:60]}")
            return results if results else None

        except Exception as e:
            logger.warning(f"[WebSearch] Google CSE failed: {e}")
            return None

    # ---------------------------------------------------------------------------
    # Backend 2: SerpAPI
    # ---------------------------------------------------------------------------

    async def _search_serpapi(self, query: str, api_key: str) -> Optional[List[Dict]]:
        """Search using SerpAPI (Google results)."""
        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                response = await client.get(
                    self._SERP_API_URL,
                    params={
                        "q": query,
                        "api_key": api_key,
                        "engine": "google",
                        "num": 10,
                        "hl": "en",
                    }
                )
                response.raise_for_status()
                data = response.json()

            results = []

            # Answer box
            answer_box = data.get("answer_box", {})
            if answer_box.get("answer") or answer_box.get("snippet"):
                results.append({
                    "title": "Direct Answer",
                    "url": answer_box.get("link", ""),
                    "snippet": answer_box.get("answer") or answer_box.get("snippet", ""),
                })

            for item in data.get("organic_results", [])[:8]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })

            logger.info(f"[WebSearch] SerpAPI returned {len(results)} results for: {query[:60]}")
            return results if results else None

        except Exception as e:
            logger.warning(f"[WebSearch] SerpAPI failed: {e}")
            return None

    # ---------------------------------------------------------------------------
    # Backend 3: duckduckgo-search library (handles bot detection)
    # ---------------------------------------------------------------------------

    async def _search_ddg_library(self, query: str) -> Optional[List[Dict]]:
        """Search using the ddgs Python library (handles bot detection)."""
        try:
            # Try new ddgs package first, fall back to duckduckgo_search
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            import asyncio

            def _sync_search():
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=8))

            # Run in threadpool since ddgs is sync
            loop = asyncio.get_event_loop()
            items = await loop.run_in_executor(None, _sync_search)

            results = []
            for item in items:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("href", item.get("url", "")),
                    "snippet": item.get("body", item.get("description", "")),
                })

            logger.info(f"[WebSearch] DDG library returned {len(results)} results for: {query[:60]}")
            return results if results else None

        except ImportError:
            logger.debug("[WebSearch] ddgs / duckduckgo-search not installed")
            return None
        except Exception as e:
            logger.warning(f"[WebSearch] DDG library failed: {e}")
            return None

    # ---------------------------------------------------------------------------
    # Backend 4: DuckDuckGo Instant Answers API (minimal fallback)
    # ---------------------------------------------------------------------------

    async def _search_ddg_api(self, query: str) -> List[Dict]:
        """Search using the DuckDuckGo Instant Answers API."""
        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                response = await client.get(
                    self._DDG_API_URL,
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": "1",
                        "skip_disambig": "1",
                    },
                )
                response.raise_for_status()
                data = response.json()

            results = []
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", "Summary"),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data["Abstract"],
                })
            if data.get("Answer"):
                results.append({
                    "title": "Instant Answer",
                    "url": "",
                    "snippet": data["Answer"],
                })
            for topic in data.get("RelatedTopics", [])[:5]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("Name", "Related"),
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic["Text"][:400],
                    })

            logger.info(f"[WebSearch] DDG API returned {len(results)} results for: {query[:60]}")
            return results

        except Exception as e:
            logger.warning(f"[WebSearch] DDG API failed: {e}")
            return []

    # ---------------------------------------------------------------------------
    # Main entry points
    # ---------------------------------------------------------------------------

    async def run(self, input_data: str) -> str:
        """Execute a web search without extra context."""
        return await self.run_with_context(input_data, context=None)

    async def run_with_context(self, input_data: str, context: Optional[Dict] = None) -> str:
        """Execute a web search with optional execution context.

        Args:
            input_data: Search query string or JSON with 'query' key.
            context: Optional execution context (for API key lookup).

        Returns:
            Formatted string of search results.
        """
        query = self._parse_query(input_data)
        if not query:
            return "Error: Empty search query. Please provide a search term."

        logger.info(f"[WebSearch] Searching for: {query[:100]}")

        # Resolve available API keys
        keys = await self._resolve_keys(context)

        results: Optional[List[Dict]] = None

        # Backend 1: Google Custom Search
        if keys.get("google_cse_api_key") and keys.get("google_cse_id"):
            results = await self._search_google_cse(
                query, keys["google_cse_api_key"], keys["google_cse_id"]
            )

        # Backend 2: SerpAPI
        if not results and keys.get("serp_api_key"):
            results = await self._search_serpapi(query, keys["serp_api_key"])

        # Backend 3: duckduckgo-search library
        if not results:
            results = await self._search_ddg_library(query)

        # Backend 4: DDG Instant Answers API
        if not results:
            results = await self._search_ddg_api(query)

        if not results:
            return (
                f"No results found for: '{query}'. "
                "For better results, configure GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID "
                "or SERP_API_KEY environment variables."
            )

        return self._format_results(query, results)

    # ---------------------------------------------------------------------------
    # Output formatting
    # ---------------------------------------------------------------------------

    def _format_results(self, query: str, results: List[Dict]) -> str:
        """Format a list of result dicts into a readable string."""
        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            title = (r.get("title") or "").strip()
            url = (r.get("url") or "").strip()
            snippet = (r.get("snippet") or "").strip()
            if len(snippet) > 400:
                snippet = snippet[:400] + "..."
            lines.append(f"{i}. {title}")
            if url:
                lines.append(f"   URL: {url}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")
        return "\n".join(lines)

    def get_function_schema(self) -> Dict[str, Any]:
        """Return JSON schema for Gemini function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up on the web"
                    }
                },
                "required": ["query"]
            }
        }
