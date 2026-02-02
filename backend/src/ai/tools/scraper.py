"""Web Scraping tool for AI Entities."""

import json
import httpx
from typing import Any, Dict, List, Optional
from src.ai.tools.base import Tool

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

class ScraperTool(Tool):
    """Tool for scraping content from web pages.
    
    Actions:
    1. scrape_url: Get text content from a URL.
    """
    
    name = "scraper_tool"
    description = (
        "Extract text content from a web page URL. "
        "Input should be a JSON object with 'url'."
    )

    async def run(self, input_data: str) -> str:
        try:
            params = json.loads(input_data)
            url = params.get("url")
            
            if not url:
                return json.dumps({"error": "Missing 'url'"})

            return await self._scrape_url(url)

        except Exception as e:
            return json.dumps({"error": f"Scraper Tool Error: {str(e)}"})

    async def _scrape_url(self, url: str) -> str:
        if not BeautifulSoup:
            return json.dumps({"error": "beautifulsoup4 not installed"})
            
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                # Get text
                text = soup.get_text(separator='\n')
                
                # Clean up whitespace
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = '\n'.join(chunk for chunk in chunks if chunk)
                
                # Limit text length to avoid context overflow
                return json.dumps({
                    "status": "success",
                    "url": url,
                    "content": text[:10000], # First 10k chars
                    "length": len(text)
                })
        except Exception as e:
            return json.dumps({"error": f"Failed to scrape URL: {str(e)}"})

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the page to scrape"
                    }
                },
                "required": ["url"]
            }
        }
