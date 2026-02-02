# Tools package initialization
"""
HireBuddha AI Tools Package

This package contains production-ready tool implementations for:
- Calculator: Safe mathematical expression evaluation
- Search: Real web search using DuckDuckGo
- Email: Email sending capabilities via SMTP
"""

from src.ai.tools.base import Tool, ToolRegistry
from src.ai.tools.calculator import CalculatorTool
from src.ai.tools.search import WebSearchTool
from src.ai.tools.excel import ExcelTool
from src.ai.tools.scraper import ScraperTool

# Register all default tools
ToolRegistry.register(CalculatorTool())
ToolRegistry.register(WebSearchTool())
ToolRegistry.register(ExcelTool())
ToolRegistry.register(ScraperTool())

__all__ = [
    "Tool",
    "ToolRegistry",
    "CalculatorTool", 
    "WebSearchTool",
    "ExcelTool",
    "ScraperTool"
]
