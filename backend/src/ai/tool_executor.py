"""Tool execution module for parsing and executing tool calls from LLM responses."""

from typing import Dict, List, Optional, Any
from src.ai.tools import ToolRegistry
import re
import json


class ToolExecutor:
    """Handles parsing and execution of tool calls from LLM responses."""
    
    @staticmethod
    async def parse_tool_calls(text: str) -> List[Dict[str, str]]:
        """
        Parse tool calls from LLM output (legacy regex-based parsing).
        
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
    async def execute_from_function_calls(function_calls: List[Dict[str, Any]], extra_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute tools from native function call format (Gemini function calling).
        
        Args:
            function_calls: List of {"name": "tool_name", "args": {"input": "...", ...}}
            
        Returns:
            List of result dictionaries with execution results
        """
        results = []
        for call in function_calls:
            tool_name = call.get("name")
            tool_args = call.get("args", {})
            tool = ToolRegistry.get_tool(tool_name)
            
            if tool:
                try:
                    # Build the raw input string the tool expects
                    if isinstance(tool_args, dict) and "input" in tool_args:
                        raw_input = tool_args["input"]
                    elif isinstance(tool_args, str):
                        raw_input = tool_args
                    else:
                        # Serialize all args (possibly including model_name, prompt, etc.)
                        # Strip injected context keys so the tool's JSON schema isn't polluted
                        clean_args = {k: v for k, v in tool_args.items()
                                      if k not in ("company_id", "user_id")}
                        raw_input = json.dumps(clean_args)

                    # Always pass extra_context through run_with_context so tools that
                    # need DB-based API keys (e.g. image_generation) can use company_id.
                    output = await tool.run_with_context(raw_input, context=extra_context)

                    results.append({
                        "tool": tool_name,
                        "args": tool_args,
                        "output": output,
                        "success": True
                    })
                except Exception as e:
                    results.append({
                        "tool": tool_name,
                        "args": tool_args,
                        "output": f"Error: {str(e)}",
                        "success": False
                    })
            else:
                results.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "output": f"Error: Tool '{tool_name}' not found. Available tools: {[t['name'] for t in ToolRegistry.list_tools()]}",
                    "success": False
                })
        
        return results
    
    @staticmethod
    async def execute_tools(tool_calls: List[Dict[str, str]], extra_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
        """
        Execute tool calls and return results (legacy method).
        
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
                    # Inject extra context into input if it's JSON
                    tool_input = call["input"]
                    if extra_context:
                        try:
                            # Try to parse and inject
                            input_dict = json.loads(tool_input) if isinstance(tool_input, str) else tool_input
                            if isinstance(input_dict, dict):
                                input_dict.update(extra_context)
                                tool_input = json.dumps(input_dict)
                        except:
                            pass # Keep as is if not JSON
                            
                    output = await tool.run(tool_input)
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
    def get_gemini_function_declarations(tool_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Get Gemini-compatible function declarations for specified tools.
        
        Args:
            tool_ids: List of tool IDs to include, or None for all tools
            
        Returns:
            List of function declaration dictionaries for Gemini API
        """
        all_schemas = ToolRegistry.get_all_schemas()
        
        if tool_ids is None:
            return all_schemas
        
        # Filter to only requested tools
        return [s for s in all_schemas if s["name"] in tool_ids]
    
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
            if 'input' in result:
                formatted += f"   Input: {result['input']}\n"
            elif 'args' in result:
                formatted += f"   Args: {json.dumps(result['args'])}\n"
            formatted += f"   Output: {result['output']}\n"
            formatted += f"   Success: {result.get('success', 'N/A')}\n"
        formatted += "=== End Tool Results ===\n"
        
        return formatted
    
    @staticmethod
    def format_function_call_response(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format tool results for Gemini function response format.
        
        Args:
            results: List of tool execution results
            
        Returns:
            List of function response parts for Gemini API
        """
        responses = []
        for result in results:
            responses.append({
                "function_response": {
                    "name": result["tool"],
                    "response": {
                        "output": result["output"],
                        "success": result.get("success", True)
                    }
                }
            })
        return responses

