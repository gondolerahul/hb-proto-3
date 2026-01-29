"""
Base Tool classes and registry for HireBuddha AI Platform.

This module provides the abstract base class for tools and the global
registry for tool registration and lookup.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Tool(ABC):
    """Abstract base class for all AI tools.
    
    Subclasses must implement:
        - name: Human-readable tool name
        - description: Tool description for LLM context
        - run(): Async execution method
    """
    name: str
    description: str

    @abstractmethod
    async def run(self, input_data: str) -> str:
        """Execute the tool with the given input.
        
        Args:
            input_data: String input from the LLM
            
        Returns:
            String output to be returned to the LLM
        """
        pass
    
    def get_function_schema(self) -> Dict[str, Any]:
        """Return JSON schema for function calling.
        
        Override this method to provide custom parameter schemas.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "Input for the tool"
                    }
                },
                "required": ["input"]
            }
        }


class ToolRegistry:
    """Global registry for tool registration and lookup.
    
    Tools are registered at module import time and can be retrieved
    by name for execution by the AI engine.
    """
    _tools: Dict[str, Tool] = {}

    @classmethod
    def register(cls, tool: Tool) -> None:
        """Register a tool in the global registry.
        
        Args:
            tool: Tool instance to register
        """
        cls._tools[tool.name] = tool

    @classmethod
    def get_tool(cls, name: str) -> Optional[Tool]:
        """Get a tool by name.
        
        Args:
            name: Tool name to look up
            
        Returns:
            Tool instance or None if not found
        """
        return cls._tools.get(name)

    @classmethod
    def list_tools(cls) -> List[Dict[str, str]]:
        """List all registered tools with their descriptions.
        
        Returns:
            List of dicts with 'name' and 'description' keys
        """
        return [
            {"name": t.name, "description": t.description} 
            for t in cls._tools.values()
        ]
    
    @classmethod
    def get_all_schemas(cls) -> List[Dict[str, Any]]:
        """Get function schemas for all registered tools.
        
        Returns:
            List of function schemas for OpenAI function calling
        """
        return [t.get_function_schema() for t in cls._tools.values()]
