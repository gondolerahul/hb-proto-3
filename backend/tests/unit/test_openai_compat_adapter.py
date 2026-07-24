"""Inc 5 / FLEET — the OpenAI-compatible adapter against a fake transport (unit).

No live GLM/Qwen/Kimi call is made anywhere in this increment; the transport is
injected, so this exercises request shaping, response parsing and the ReAct loop
deterministically. Live binding is activation-time ops (§7).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from src.ai.llm.openai_compat_adapter import PROVIDER_BASE_URLS, OpenAICompatAdapter

pytestmark = pytest.mark.asyncio


def _adapter(provider: str = "zhipu", model: str = "glm-4.6", transport=None,
             metadata: Dict[str, Any] | None = None) -> OpenAICompatAdapter:
    return OpenAICompatAdapter(api_key="k", model_name=model,
                               service_metadata=metadata or {}, provider=provider,
                               transport=transport)


def _body(content: str = "hello", tool_calls=None, prompt: int = 10, completion: int = 3) -> Dict[str, Any]:
    return {
        "model": "glm-4.6",
        "choices": [{"message": {"content": content, "tool_calls": tool_calls or []},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }


async def test_generate_shapes_the_request_and_parses_the_response() -> None:
    seen: List[Dict[str, Any]] = []

    async def transport(payload: Dict[str, Any]) -> Dict[str, Any]:
        seen.append(payload)
        return _body()

    adapter = _adapter(transport=transport)
    resp = await adapter.generate(
        "you are helpful", [{"role": "user", "parts": [{"text": "hi"}]}],
        temperature=0.3, max_tokens=256)

    # Request: unified 'parts' → OpenAI 'content', system prompt first.
    payload = seen[0]
    assert payload["model"] == "glm-4.6"
    assert payload["messages"][0] == {"role": "system", "content": "you are helpful"}
    assert payload["messages"][1] == {"role": "user", "content": "hi"}
    assert payload["temperature"] == 0.3 and payload["max_tokens"] == 256

    # Response: content + usage + provider stamped through.
    assert resp.output == "hello"
    assert (resp.prompt_tokens, resp.completion_tokens) == (10, 3)
    assert resp.provider == "zhipu"
    assert resp.finish_reason == "stop"


async def test_tool_calls_are_parsed_with_json_arguments() -> None:
    calls = [{"id": "c1", "function": {"name": "lookup", "arguments": json.dumps({"q": "acme"})}}]

    async def transport(payload: Dict[str, Any]) -> Dict[str, Any]:
        return _body(content="", tool_calls=calls)

    resp = await _adapter(transport=transport).generate("s", [])
    assert resp.function_calls == [{"name": "lookup", "args": {"q": "acme"}}]


async def test_malformed_tool_arguments_degrade_to_empty_args() -> None:
    calls = [{"id": "c1", "function": {"name": "lookup", "arguments": "{not json"}}]

    async def transport(payload: Dict[str, Any]) -> Dict[str, Any]:
        return _body(content="", tool_calls=calls)

    resp = await _adapter(transport=transport).generate("s", [])
    assert resp.function_calls == [{"name": "lookup", "args": {}}]   # never raises


async def test_react_loop_executes_tools_then_returns_final_answer() -> None:
    turns = {"n": 0}
    executed: List[Any] = []

    async def transport(payload: Dict[str, Any]) -> Dict[str, Any]:
        turns["n"] += 1
        if turns["n"] == 1:
            return _body(content="", tool_calls=[
                {"id": "c1", "function": {"name": "lookup", "arguments": "{}"}}])
        return _body(content="final answer")

    async def execute_tool_fn(fcs):
        executed.append(fcs)
        return [{"tool": "lookup", "output": "found", "success": True}]

    resp = await _adapter(transport=transport).generate_with_tools_react(
        "s", [{"role": "user", "parts": [{"text": "go"}]}],
        [{"name": "lookup", "description": "d", "parameters": {}}], execute_tool_fn)

    assert turns["n"] == 2                    # tool turn, then the answer
    assert executed and executed[0][0]["name"] == "lookup"
    assert resp.output == "final answer"
    assert resp.prompt_tokens == 20           # accumulated across both turns


async def test_base_url_resolves_per_provider_and_metadata_overrides() -> None:
    assert _adapter("zhipu").base_url == PROVIDER_BASE_URLS["zhipu"]
    assert _adapter("alibaba").base_url == PROVIDER_BASE_URLS["alibaba"]
    assert _adapter("moonshot").base_url == PROVIDER_BASE_URLS["moonshot"]
    # A company may pin a regional/gateway endpoint.
    custom = _adapter("zhipu", metadata={"base_url": "https://gw.internal/v1"})
    assert custom.base_url == "https://gw.internal/v1"


async def test_unknown_provider_without_base_url_raises_rather_than_calling_out() -> None:
    adapter = _adapter(provider="nobody")     # no transport, no base_url
    with pytest.raises(RuntimeError, match="no base_url"):
        await adapter.generate("s", [])


async def test_router_maps_fleet_providers_to_the_compat_adapter() -> None:
    """_get_adapter must route the fleet providers (and their aliases) here."""
    from src.ai.llm.router import _get_adapter

    for name, canonical in (("zhipu", "zhipu"), ("glm", "zhipu"), ("qwen", "alibaba"),
                            ("dashscope", "alibaba"), ("moonshot", "moonshot"), ("kimi", "moonshot")):
        adapter = _get_adapter(provider_name=name, api_key="k", model_name="m", service_metadata={})
        assert isinstance(adapter, OpenAICompatAdapter), name
        assert adapter.provider == canonical, name
