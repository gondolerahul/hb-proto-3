"""Tests for tool executor module."""

import pytest
from src.ai.tool_executor import ToolExecutor
from src.ai.tools import ToolRegistry


@pytest.mark.asyncio
async def test_parse_tool_calls_simple_format():
    """Test parsing tool calls in simple TOOL:name:input format."""
    text = "Let me calculate that. TOOL:calculator:2+2 The result is 4."
    
    tool_calls = await ToolExecutor.parse_tool_calls(text)
    
    assert len(tool_calls) == 1
    assert tool_calls[0]["tool"] == "calculator"
    assert tool_calls[0]["input"] == "2+2 The result is 4."


@pytest.mark.asyncio
async def test_parse_multiple_tool_calls():
    """Test parsing multiple tool calls."""
    text = """
    First, TOOL:calculator:10*5
    Then, TOOL:web_search:Python programming
    """
    
    tool_calls = await ToolExecutor.parse_tool_calls(text)
    
    assert len(tool_calls) == 2
    assert tool_calls[0]["tool"] == "calculator"
    assert tool_calls[1]["tool"] == "web_search"


@pytest.mark.asyncio
async def test_parse_no_tool_calls():
    """Test parsing text with no tool calls."""
    text = "This is just regular text without any tool calls."
    
    tool_calls = await ToolExecutor.parse_tool_calls(text)
    
    assert len(tool_calls) == 0


@pytest.mark.asyncio
async def test_execute_calculator_tool():
    """Test executing calculator tool."""
    tool_calls = [
        {"tool": "calculator", "input": "2+2"}
    ]
    
    results = await ToolExecutor.execute_tools(tool_calls)
    
    assert len(results) == 1
    assert results[0]["tool"] == "calculator"
    assert results[0]["output"] == "4"
    assert results[0]["success"] is True


@pytest.mark.asyncio
async def test_execute_web_search_tool():
    """Test executing web search tool (mock)."""
    tool_calls = [
        {"tool": "web_search", "input": "Python programming"}
    ]
    
    results = await ToolExecutor.execute_tools(tool_calls)
    
    assert len(results) == 1
    assert results[0]["tool"] == "web_search"
    assert "Mock search results" in results[0]["output"]
    assert results[0]["success"] is True


@pytest.mark.asyncio
async def test_execute_invalid_tool():
    """Test executing a tool that doesn't exist."""
    tool_calls = [
        {"tool": "nonexistent_tool", "input": "test"}
    ]
    
    results = await ToolExecutor.execute_tools(tool_calls)
    
    assert len(results) == 1
    assert results[0]["success"] is False
    assert "not found" in results[0]["output"]


@pytest.mark.asyncio
async def test_execute_calculator_with_invalid_input():
    """Test calculator tool with invalid input."""
    tool_calls = [
        {"tool": "calculator", "input": "invalid expression"}
    ]
    
    results = await ToolExecutor.execute_tools(tool_calls)
    
    assert len(results) == 1
    # Calculator returns error message in output
    assert "Error" in results[0]["output"] or "Invalid" in results[0]["output"]


@pytest.mark.asyncio
async def test_format_tool_results():
    """Test formatting tool results."""
    results = [
        {
            "tool": "calculator",
            "input": "2+2",
            "output": "4",
            "success": True
        },
        {
            "tool": "web_search",
            "input": "Python",
            "output": "Mock results",
            "success": True
        }
    ]
    
    formatted = ToolExecutor.format_tool_results(results)
    
    assert "Tool Execution Results" in formatted
    assert "calculator" in formatted
    assert "web_search" in formatted
    assert "2+2" in formatted
    assert "4" in formatted


@pytest.mark.asyncio
async def test_format_empty_results():
    """Test formatting empty results."""
    formatted = ToolExecutor.format_tool_results([])
    
    assert formatted == ""
