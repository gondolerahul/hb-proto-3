from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import math

class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    async def run(self, input_data: str) -> str:
        pass

class CalculatorTool(Tool):
    name = "calculator"
    description = "Useful for performing mathematical calculations. Input should be a mathematical expression."

    async def run(self, input_data: str) -> str:
        try:
            # WARNING: eval is dangerous. In production, use a safe math parser.
            # For this prototype, we'll restrict characters.
            allowed_chars = "0123456789+-*/(). "
            if not all(c in allowed_chars for c in input_data):
                return "Error: Invalid characters in expression."
            
            result = eval(input_data, {"__builtins__": None}, {})
            return str(result)
        except Exception as e:
            return f"Error calculating: {str(e)}"

class WebSearchTool(Tool):
    name = "web_search"
    description = "Useful for searching the internet for information."

    async def run(self, input_data: str) -> str:
        # Mock implementation
        return f"Mock search results for: {input_data}\n1. Result A\n2. Result B"

class ToolRegistry:
    _tools: Dict[str, Tool] = {}

    @classmethod
    def register(cls, tool: Tool):
        cls._tools[tool.name] = tool

    @classmethod
    def get_tool(cls, name: str) -> Optional[Tool]:
        return cls._tools.get(name)

    @classmethod
    def list_tools(cls) -> List[Dict[str, str]]:
        return [{"name": t.name, "description": t.description} for t in cls._tools.values()]

# Register default tools
ToolRegistry.register(CalculatorTool())
ToolRegistry.register(WebSearchTool())
