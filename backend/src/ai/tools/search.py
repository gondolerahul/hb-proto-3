"""
Web Search Tool for HireBuddha AI Platform.

Provides real web search functionality using DuckDuckGo's instant answer API.
No API key required - uses the free DuckDuckGo instant answers endpoint.
"""

import httpx
from typing import Dict, Any, List
from src.ai.tools.base import Tool


class WebSearchTool(Tool):
    """Web search tool using DuckDuckGo instant answers.
    
    This tool provides real web search results using DuckDuckGo's
    free instant answer API. Results include:
        - Abstract/summary from Wikipedia or other sources
        - Related topics
        - Instant answer when available
    
    Note: For more comprehensive results, consider integrating
    with a paid search API (Google, Bing, SerpAPI).
    """
    
    name = "web_search"
    description = (
        "Search the web for information using DuckDuckGo. "
        "Returns summaries and related topics. "
        "Input should be a search query string."
    )
    
    _API_URL = "https://api.duckduckgo.com/"
    _TIMEOUT = 10.0

    async def run(self, input_data: str) -> str:
        """Execute a web search and return formatted results.
        
        Args:
            input_data: Search query string
            
        Returns:
            Formatted search results string
        """
        query = input_data.strip()
        if not query:
            return "Error: Empty search query"
        
        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                response = await client.get(
                    self._API_URL,
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": "1",
                        "skip_disambig": "1"
                    }
                )
                response.raise_for_status()
                data = response.json()
            
            return self._format_results(query, data)
            
        except httpx.TimeoutException:
            return f"Error: Search request timed out for query: {query}"
        except httpx.HTTPStatusError as e:
            return f"Error: Search failed with status {e.response.status_code}"
        except Exception as e:
            return f"Error performing search: {str(e)}"

    def _format_results(self, query: str, data: Dict[str, Any]) -> str:
        """Format DuckDuckGo API response into readable results.
        
        Args:
            query: Original search query
            data: API response data
            
        Returns:
            Formatted results string
        """
        results = []
        results.append(f"Search results for: {query}\n")
        
        # Abstract (main summary)
        if data.get("Abstract"):
            results.append(f"Summary: {data['Abstract']}")
            if data.get("AbstractSource"):
                results.append(f"Source: {data['AbstractSource']}")
            if data.get("AbstractURL"):
                results.append(f"URL: {data['AbstractURL']}")
            results.append("")
        
        # Instant answer
        if data.get("Answer"):
            results.append(f"Answer: {data['Answer']}")
            results.append("")
        
        # Related topics
        related_topics = data.get("RelatedTopics", [])
        if related_topics:
            results.append("Related Topics:")
            for i, topic in enumerate(related_topics[:5], 1):  # Limit to 5 topics
                if isinstance(topic, dict) and topic.get("Text"):
                    text = topic["Text"]
                    # Truncate long texts
                    if len(text) > 200:
                        text = text[:200] + "..."
                    results.append(f"  {i}. {text}")
            results.append("")
        
        # If no results found
        if len(results) <= 2:
            results.append("No detailed results found.")
            results.append("Try a more specific query or rephrase your search.")
        
        return "\n".join(results)

    def get_function_schema(self) -> Dict[str, Any]:
        """Return JSON schema for function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query to look up on the web"
                    }
                },
                "required": ["query"]
            }
        }
