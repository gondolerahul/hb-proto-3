"""Tool execution module for parsing and executing tool calls from LLM responses."""

from typing import Dict, List, Optional
from src.ai.tools import ToolRegistry
import re
import json


class ToolExecutor:
    """Handles parsing and execution of tool calls from LLM responses."""
    
    @staticmethod
    async def parse_tool_calls(text: str) -> List[Dict[str, str]]:
        """
        Parse tool calls from LLM output.
        
        Supports multiple formats:
        1. TOOL:tool_name:input - Simple format
        2. JSON format: {"tool": "tool_name", "input": "input_data"}
        
        Args:
            text: LLM response text
            
        Returns:
            List of tool call dictionaries with 'tool' and 'input' keys
        """
        tool_calls = []
        
        # Pattern 1: TOOL:tool_name:input
        pattern1 = r'TOOL:(\w+):(.+?)(?=TOOL:|$)'
        matches = re.findall(pattern1, text, re.DOTALL)
        for tool, inp in matches:
            tool_calls.append({"tool": tool.strip(), "input": inp.strip()})
        
        # Pattern 2: JSON format
        pattern2 = r'\{[^}]*"tool"\s*:\s*"([^"]+)"[^}]*"input"\s*:\s*"([^"]+)"[^}]*\}'
        json_matches = re.findall(pattern2, text)
        for tool, inp in json_matches:
            tool_calls.append({"tool": tool.strip(), "input": inp.strip()})
        
        return tool_calls
    
    @staticmethod
    async def execute_tools(tool_calls: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Execute tool calls and return results.
        
        Args:
            tool_calls: List of tool call dictionaries
            
        Returns:
            List of result dictionaries with 'tool', 'input', and 'output' keys
        """
        results = []
        for call in tool_calls:
            tool = ToolRegistry.get_tool(call["tool"])
            if tool:
                try:
                    output = await tool.run(call["input"])
                    results.append({
                        "tool": call["tool"],
                        "input": call["input"],
                        "output": output,
                        "success": True
                    })
                except Exception as e:
                    results.append({
                        "tool": call["tool"],
                        "input": call["input"],
                        "output": f"Error: {str(e)}",
                        "success": False
                    })
            else:
                results.append({
                    "tool": call["tool"],
                    "input": call["input"],
                    "output": f"Error: Tool '{call['tool']}' not found",
                    "success": False
                })
        
        return results
    
    @staticmethod
    def format_tool_results(results: List[Dict[str, str]]) -> str:
        """
        Format tool execution results for inclusion in LLM context.
        
        Args:
            results: List of tool execution results
            
        Returns:
            Formatted string of tool results
        """
        if not results:
            return ""
        
        formatted = "\n\n=== Tool Execution Results ===\n"
        for i, result in enumerate(results, 1):
            formatted += f"\n{i}. Tool: {result['tool']}\n"
            formatted += f"   Input: {result['input']}\n"
            formatted += f"   Output: {result['output']}\n"
        formatted += "=== End Tool Results ===\n"
        
        return formatted
