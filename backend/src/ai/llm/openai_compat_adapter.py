"""
ai.llm.openai_compat_adapter — one adapter for the OpenAI-compatible fleet.

GLM (Zhipu), Qwen (Alibaba DashScope) and Kimi (Moonshot AI) all expose
OpenAI-shaped ``/chat/completions`` endpoints, so a single adapter serves all
three — the ``base_url`` selects the provider.

**Tested seam, not a live integration (Inc 5 / FLEET §7).** The HTTP call goes
through an *injectable* ``transport`` (the Zoho ``MCPClient`` pattern), so tests
drive it against fakes and **no live GLM/Qwen/Kimi call is made in this
increment**. The live path builds an ``AsyncOpenAI`` client against ``base_url``
and is activation-time ops.

A transport is ``async (payload: dict) -> dict`` returning the raw
OpenAI-shaped response body.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.ai.llm.base import BaseLLMAdapter
from src.ai.llm.types import LLMResponse

logger = logging.getLogger(__name__)

Transport = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]

# The OpenAI-compatible endpoint per provider. Overridable per company through
# ``service_metadata["base_url"]`` (a regional or gateway endpoint).
PROVIDER_BASE_URLS: Dict[str, str] = {
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",              # GLM
    "alibaba": "https://dashscope.aliyuncs.com/compatible-mode/v1",  # Qwen (DashScope)
    "moonshot": "https://api.moonshot.ai/v1",                     # Kimi
}


class OpenAICompatAdapter(BaseLLMAdapter):
    """Adapter for any OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        service_metadata: Dict[str, Any],
        provider: str = "",
        transport: Optional[Transport] = None,
    ):
        super().__init__(api_key, model_name, service_metadata)
        self.provider = provider or self.service_metadata.get("provider", "")
        self.base_url = (
            self.service_metadata.get("base_url")
            or PROVIDER_BASE_URLS.get(self.provider, "")
        )
        self._transport = transport

    # -- transport ---------------------------------------------------------

    async def _call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """One chat-completions round trip. Injected transport wins; otherwise
        the live SDK path (activation-time ops — not exercised in this increment)."""
        if self._transport is not None:
            return await self._transport(payload)
        if not self.base_url:
            raise RuntimeError(
                f"OpenAICompatAdapter: no base_url for provider '{self.provider}' — "
                f"set service_metadata['base_url'] or register the provider.")
        from openai import AsyncOpenAI  # live path

        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = await client.chat.completions.create(**payload)
        return resp.model_dump()  # type: ignore[no-any-return]

    # -- format helpers ----------------------------------------------------

    def _build_messages(self, system_prompt: str, messages: List[Dict]) -> List[Dict]:
        """Convert the platform's unified (Gemini-shaped ``parts``) format to
        OpenAI messages — same mapping the Azure adapter uses."""
        result: List[Dict[str, Any]] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                continue
            if role == "model":
                role = "assistant"
            parts = msg.get("parts", [])
            content = ""
            if isinstance(parts, list):
                for p in parts:
                    if isinstance(p, dict) and "text" in p:
                        content += p["text"]
                    elif isinstance(p, str):
                        content += p
            elif isinstance(parts, str):
                content = parts
            if content:
                result.append({"role": role, "content": content})
        return result

    def get_tool_declarations(self, tool_schemas: List[Dict]) -> List[Dict]:
        """JSON Schema tool defs → OpenAI tool format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": s["name"],
                    "description": s.get("description", ""),
                    "parameters": s.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for s in tool_schemas
        ]

    def _payload(
        self, system_prompt: str, messages: List[Dict], tools: Optional[List[Dict]],
        temperature: float, max_tokens: Optional[int], top_p: float,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": self._build_messages(system_prompt, messages),
            "temperature": temperature,
            "top_p": top_p,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = self.get_tool_declarations(tools)
        return payload

    def _to_response(self, raw: Dict[str, Any], latency_ms: int = 0) -> LLMResponse:
        """Parse an OpenAI-shaped body into the platform's unified response."""
        choices = raw.get("choices") or [{}]
        first = choices[0] or {}
        message = first.get("message") or {}
        function_calls: List[Dict[str, Any]] = []
        for tc in (message.get("tool_calls") or []):
            fn = (tc or {}).get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (ValueError, TypeError):
                    args = {}
            function_calls.append({"name": fn.get("name", ""), "args": args or {}})
        usage = raw.get("usage") or {}
        return LLMResponse(
            output=message.get("content") or "",
            function_calls=function_calls,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
            model_name=raw.get("model") or self.model_name,
            provider=self.provider,
            finish_reason=first.get("finish_reason") or "stop",
        )

    # -- the BaseLLMAdapter contract ---------------------------------------

    async def generate(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        **kwargs,
    ) -> LLMResponse:
        started = time.monotonic()
        raw = await self._call(
            self._payload(system_prompt, messages, tools, temperature, max_tokens, top_p))
        return self._to_response(raw, int((time.monotonic() - started) * 1000))

    async def generate_with_tools_react(
        self,
        system_prompt: str,
        initial_messages: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        execute_tool_fn,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_react_turns: int = 10,
        **kwargs,
    ) -> LLMResponse:
        started = time.monotonic()
        oai_messages = self._build_messages(system_prompt, initial_messages)
        tools = self.get_tool_declarations(tool_schemas) if tool_schemas else None
        total_prompt = total_completion = 0
        last: LLMResponse | None = None

        for _turn in range(max_react_turns):
            payload: Dict[str, Any] = {
                "model": self.model_name, "messages": oai_messages,
                "temperature": temperature, "top_p": 1.0,
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens
            if tools:
                payload["tools"] = tools

            raw = await self._call(payload)
            last = self._to_response(raw)
            total_prompt += last.prompt_tokens
            total_completion += last.completion_tokens

            if not last.function_calls:
                break

            message = ((raw.get("choices") or [{}])[0] or {}).get("message") or {}
            oai_messages.append({
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": message.get("tool_calls") or [],
            })
            results = await execute_tool_fn(last.function_calls)
            for tc, tr in zip(message.get("tool_calls") or [], results or []):
                oai_messages.append({
                    "role": "tool",
                    "tool_call_id": (tc or {}).get("id", ""),
                    "content": str((tr or {}).get("output", "")),
                })

        if last is None:  # pragma: no cover — max_react_turns is always >= 1
            return LLMResponse(output="", model_name=self.model_name, provider=self.provider)
        last.prompt_tokens = total_prompt
        last.completion_tokens = total_completion
        last.latency_ms = int((time.monotonic() - started) * 1000)
        return last
