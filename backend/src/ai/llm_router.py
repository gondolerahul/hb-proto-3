"""
LLM Router — Provider-Agnostic Dispatch Layer

Routes LLM calls to the appropriate provider (Gemini via Vertex AI, Anthropic via Vertex AI, Azure OpenAI)
based on the task type and system default configuration stored in ModelTaskDefaults.

Usage:
    router = LLMRouter(db=db, company_id=company_id)
    response = await router.call_llm(
        task_type="text_generation",
        system_prompt="...",
        user_prompt="...",
        tools=[],          # list of tool schema dicts
        temperature=0.7,
    )
    # response.output: str
    # response.function_calls: [{name, args}]
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SDK Compatibility Patch — google-genai v0.4.0 FinishReason enum gap
# ---------------------------------------------------------------------------
# The Gemini API may return finish_reason values (e.g. 'UNEXPECTED_TOOL_CALL')
# that are newer than the installed SDK's Pydantic Literal type definitions.
# This causes a pydantic ValidationError during response deserialization.
# We monkey-patch the SDK types at import time to prevent this crash.
# ---------------------------------------------------------------------------

def _patch_genai_finish_reason():
    """Extend the google-genai SDK's FinishReason Literal to include newer API values."""
    try:
        from google.genai import types as genai_types
        import typing

        # The FinishReason is defined as a Literal type alias in google.genai.types.
        # We need to patch the Candidate model's finish_reason field validator
        # to accept unknown string values gracefully.
        if hasattr(genai_types, 'Candidate'):
            candidate_cls = genai_types.Candidate
            if hasattr(candidate_cls, 'model_fields') and 'finish_reason' in candidate_cls.model_fields:
                field_info = candidate_cls.model_fields['finish_reason']
                permissive_type = typing.Optional[str]

                # Update BOTH the FieldInfo annotation and the class __annotations__
                # Pydantic v2 requires both to be in sync for model_rebuild to work.
                field_info.annotation = permissive_type
                candidate_cls.__annotations__['finish_reason'] = permissive_type
                try:
                    candidate_cls.model_rebuild(force=True)
                    logger.debug("Patched google-genai Candidate.finish_reason to accept any string")
                except Exception:
                    logger.warning("Failed to patch Candidate model, falling back")
    except Exception as e:
        logger.debug(f"google-genai FinishReason patch skipped: {e}")


_patch_genai_finish_reason()


# ---------------------------------------------------------------------------
# Unified response dataclass — provider-agnostic
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""
    output: str
    function_calls: List[Dict[str, Any]] = field(default_factory=list)
    # [{name: str, args: dict}]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    model_name: str = ""
    provider: str = ""
    finish_reason: str = "stop"


# ---------------------------------------------------------------------------
# Abstract base adapter
# ---------------------------------------------------------------------------

class BaseLLMAdapter(ABC):
    """Base class for all LLM provider adapters."""

    def __init__(self, api_key: str, model_name: str, service_metadata: Dict[str, Any]):
        self.api_key = api_key
        self.model_name = model_name
        self.service_metadata = service_metadata or {}

    @abstractmethod
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
        """Single-turn generation."""
        ...

    @abstractmethod
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
        """
        Full REACT loop: calls generate, executes tool calls, continues until
        no more tool calls or max turns reached.
        execute_tool_fn: async callable(function_calls: list) -> list of tool results
        """
        ...

    def get_tool_declarations(self, tool_schemas: List[Dict]) -> Any:
        """Convert generic JSON Schema tool defs to provider-specific format."""
        return tool_schemas  # Default: pass through as-is


# ---------------------------------------------------------------------------
# Google Gemini Adapter (via google-genai SDK)
# ---------------------------------------------------------------------------

class GeminiAdapter(BaseLLMAdapter):
    """Adapter for Google Gemini models via Vertex AI only."""

    @property
    def _provider_name(self):
        return "google"

    def _build_client(self):
        from src.common.genai_factory import build_vertex_genai_client_sync
        return build_vertex_genai_client_sync(self.service_metadata)

    _GEMINI_TYPE_MAP = {
        "string": "STRING",
        "integer": "INTEGER",
        "number": "NUMBER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
        "object": "OBJECT",
    }

    def _prop_to_schema(self, prop_def: Dict) -> Any:
        """Recursively convert a JSON-Schema property dict to a Gemini types.Schema.

        Handles nested objects, arrays with items, and enum values — all of which
        the Gemini API strictly validates.
        """
        from google.genai import types

        prop_type = self._GEMINI_TYPE_MAP.get(prop_def.get("type", "string"), "STRING")
        kwargs: Dict[str, Any] = {
            "type": prop_type,
            "description": prop_def.get("description", ""),
        }

        # Enum values
        if "enum" in prop_def:
            kwargs["enum"] = [str(v) for v in prop_def["enum"]]

        # Array → must have items
        if prop_type == "ARRAY":
            items_def = prop_def.get("items")
            if items_def and isinstance(items_def, dict):
                kwargs["items"] = self._prop_to_schema(items_def)
            else:
                # Fallback: Gemini requires items for ARRAY; default to STRING
                kwargs["items"] = types.Schema(type="STRING")

        # Nested object → recurse into properties
        if prop_type == "OBJECT":
            nested_props = prop_def.get("properties", {})
            if nested_props and isinstance(nested_props, dict):
                kwargs["properties"] = {
                    k: self._prop_to_schema(v)
                    for k, v in nested_props.items()
                }
            nested_required = prop_def.get("required")
            if nested_required:
                kwargs["required"] = nested_required

        return types.Schema(**kwargs)

    def get_tool_declarations(self, tool_schemas: List[Dict]) -> Any:
        """Convert JSON Schema tool defs to Gemini FunctionDeclaration objects."""
        try:
            from google.genai import types
        except ImportError:
            return []

        declarations = []
        for schema in tool_schemas:
            props = {}
            required = []
            raw_props = schema.get("parameters", {}).get("properties", {})
            raw_required = schema.get("parameters", {}).get("required", [])
            for prop_name, prop_def in raw_props.items():
                try:
                    props[prop_name] = self._prop_to_schema(prop_def)
                except Exception as e:
                    logger.warning(
                        f"Skipping malformed property '{prop_name}' in tool "
                        f"'{schema.get('name', '?')}': {e}"
                    )
                    # Fallback to basic STRING to avoid crashing the whole tool
                    props[prop_name] = types.Schema(
                        type="STRING",
                        description=prop_def.get("description", ""),
                    )
            if raw_required:
                required = raw_required

            declarations.append(
                types.FunctionDeclaration(
                    name=schema["name"],
                    description=schema.get("description", ""),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties=props,
                        required=required,
                    ),
                )
            )
        return declarations

    def _build_contents(self, system_prompt: str, messages: List[Dict]) -> Tuple[str, List]:
        """Convert unified message format to Gemini contents."""
        try:
            from google.genai import types
        except ImportError:
            raise RuntimeError("google-genai not installed")

        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                # Skip — Gemini uses system_instruction separately
                continue
            content_parts = []
            parts = msg.get("parts", [])
            if isinstance(parts, list):
                for p in parts:
                    if isinstance(p, dict) and "text" in p:
                        content_parts.append(types.Part.from_text(text=p["text"]))
                    elif isinstance(p, str):
                        content_parts.append(types.Part.from_text(text=p))
            elif isinstance(parts, str):
                content_parts.append(types.Part.from_text(text=parts))

            if content_parts:
                contents.append(types.Content(role=role, parts=content_parts))

        return system_prompt, contents

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
        from google.genai import types

        client = self._build_client()
        _, contents = self._build_contents(system_prompt, messages)

        generate_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            top_p=top_p,
        )
        if max_tokens:
            generate_config.max_output_tokens = max_tokens

        if tools:
            declarations = self.get_tool_declarations(tools)
            if declarations:
                generate_config.tools = [types.Tool(function_declarations=declarations)]

        start = time.monotonic()
        try:
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=generate_config,
            )
        except Exception as e:
            if "ValidationError" in type(e).__name__ and "finish_reason" in str(e):
                logger.warning(f"SDK finish_reason validation error (non-fatal), retrying with raw HTTP: {e}")
                raise RuntimeError(
                    f"Gemini SDK validation error for model {self.model_name}. "
                    f"Consider upgrading google-genai (current: 0.4.0). Error: {e}"
                ) from e
            raise
        latency_ms = int((time.monotonic() - start) * 1000)

        output = ""
        function_calls = []
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    function_calls.append({
                        "name": part.function_call.name,
                        "args": dict(part.function_call.args) if part.function_call.args else {},
                    })
                elif hasattr(part, "text") and part.text:
                    output += part.text
        if not output and response.text:
            output = response.text

        usage = response.usage_metadata
        return LLMResponse(
            output=output,
            function_calls=function_calls,
            prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            completion_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            latency_ms=latency_ms,
            model_name=self.model_name,
            provider=self._provider_name,
            finish_reason=str(response.candidates[0].finish_reason) if response.candidates else "stop",
        )

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
        from google.genai import types

        client = self._build_client()
        _, contents = self._build_contents(system_prompt, initial_messages)

        generate_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
        )
        if max_tokens:
            generate_config.max_output_tokens = max_tokens

        declarations = self.get_tool_declarations(tool_schemas)
        if declarations:
            generate_config.tools = [types.Tool(function_declarations=declarations)]

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_latency_ms = 0
        combined_output = ""
        all_function_calls_log = []

        for turn in range(max_react_turns):
            start = time.monotonic()
            try:
                response = await client.aio.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=generate_config,
                )
            except Exception as e:
                if "ValidationError" in type(e).__name__ and "finish_reason" in str(e):
                    logger.warning(
                        f"SDK finish_reason validation error on REACT turn {turn}. "
                        f"Treating as end-of-turn. Error: {e}"
                    )
                    # Treat unknown finish_reason as a stop signal
                    break
                raise
            latency_ms = int((time.monotonic() - start) * 1000)
            total_latency_ms += latency_ms

            usage = response.usage_metadata
            total_prompt_tokens += getattr(usage, "prompt_token_count", 0) or 0
            total_completion_tokens += getattr(usage, "candidates_token_count", 0) or 0

            turn_text = ""
            function_calls = []
            model_parts = []

            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    model_parts.append(part)
                    if hasattr(part, "function_call") and part.function_call:
                        function_calls.append({
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args) if part.function_call.args else {},
                        })
                    elif hasattr(part, "text") and part.text:
                        turn_text += part.text

            if not turn_text and not function_calls and response.text:
                turn_text = response.text

            # Append model turn
            contents.append(types.Content(role="model", parts=model_parts))

            if function_calls:
                all_function_calls_log.extend(function_calls)
                # Execute tools
                tool_results = await execute_tool_fn(function_calls)

                # Build function response parts (Gemini protocol)
                response_parts = [
                    types.Part.from_function_response(
                        name=tr["tool"],
                        response={"output": str(tr["output"]), "success": tr["success"]},
                    )
                    for tr in tool_results
                ]
                contents.append(types.Content(role="user", parts=response_parts))
                if turn_text:
                    combined_output += turn_text
                continue
            else:
                combined_output += turn_text
                break

        return LLMResponse(
            output=combined_output,
            function_calls=all_function_calls_log,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            latency_ms=total_latency_ms,
            model_name=self.model_name,
            provider=self._provider_name,
        )


# ---------------------------------------------------------------------------
# Anthropic Adapter (Claude via Vertex AI only)
# ---------------------------------------------------------------------------

class AnthropicAdapter(BaseLLMAdapter):
    """Adapter for Anthropic Claude models via Vertex AI only."""

    @property
    def _provider_name(self):
        return "anthropic"

    def _build_client(self):
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

        project = self.service_metadata.get("project_id")
        region = self.service_metadata.get("region", "us-east5")
        if not project:
            raise ValueError(
                "service_metadata.project_id is required for Anthropic via Vertex AI. "
                "Please configure the Anthropic integration with your GCP project ID."
            )
        return anthropic.AsyncAnthropicVertex(project_id=project, region=region)

    def _build_messages(self, system_prompt: str, messages: List[Dict]) -> Tuple[str, List]:
        """Convert unified format to Anthropic messages format."""
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                continue  # handled as system param
            if role == "model":
                role = "assistant"  # Anthropic uses 'assistant'

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
                anthropic_messages.append({"role": role, "content": content})

        return system_prompt, anthropic_messages

    def get_tool_declarations(self, tool_schemas: List[Dict]) -> List[Dict]:
        """Convert JSON Schema tool defs to Anthropic tool format."""
        tools = []
        for schema in tool_schemas:
            tools.append({
                "name": schema["name"],
                "description": schema.get("description", ""),
                "input_schema": schema.get("parameters", {"type": "object", "properties": {}}),
            })
        return tools

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
        client = self._build_client()
        _, anthropic_messages = self._build_messages(system_prompt, messages)

        kwargs_extra = {}
        if tools:
            kwargs_extra["tools"] = self.get_tool_declarations(tools)

        start = time.monotonic()
        response = await client.messages.create(
            model=self.model_name,
            system=system_prompt,
            messages=anthropic_messages,
            max_tokens=max_tokens or 8096,
            temperature=temperature,
            top_p=top_p,
            **kwargs_extra,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        output = ""
        function_calls = []
        for block in response.content:
            if block.type == "text":
                output += block.text
            elif block.type == "tool_use":
                function_calls.append({
                    "name": block.name,
                    "args": block.input or {},
                })

        return LLMResponse(
            output=output,
            function_calls=function_calls,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
            model_name=self.model_name,
            provider=self._provider_name,
            finish_reason=response.stop_reason or "stop",
        )

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
        client = self._build_client()
        _, messages = self._build_messages(system_prompt, initial_messages)
        tool_defs = self.get_tool_declarations(tool_schemas)

        total_prompt = 0
        total_completion = 0
        total_latency = 0
        combined_output = ""
        all_function_calls = []

        for turn in range(max_react_turns):
            start = time.monotonic()
            response = await client.messages.create(
                model=self.model_name,
                system=system_prompt,
                messages=messages,
                max_tokens=max_tokens or 8096,
                temperature=temperature,
                tools=tool_defs if tool_defs else [],
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            total_latency += latency_ms
            total_prompt += response.usage.input_tokens
            total_completion += response.usage.output_tokens

            turn_text = ""
            function_calls = []
            assistant_content = []

            for block in response.content:
                assistant_content.append(block)
                if block.type == "text":
                    turn_text += block.text
                elif block.type == "tool_use":
                    function_calls.append({"name": block.name, "args": block.input or {}})

            # Append assistant turn
            messages.append({"role": "assistant", "content": response.content})

            if function_calls:
                all_function_calls.extend(function_calls)
                tool_results = await execute_tool_fn(function_calls)

                # Build tool_result blocks for Anthropic
                tool_result_content = []
                for tr in tool_results:
                    # Find matching tool_use block id
                    matching_block = next(
                        (b for b in assistant_content if getattr(b, "type", "") == "tool_use" and b.name == tr["tool"]),
                        None
                    )
                    tool_use_id = getattr(matching_block, "id", tr["tool"]) if matching_block else tr["tool"]
                    tool_result_content.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": str(tr["output"]),
                    })

                messages.append({"role": "user", "content": tool_result_content})
                if turn_text:
                    combined_output += turn_text
                continue
            else:
                combined_output += turn_text
                break

        return LLMResponse(
            output=combined_output,
            function_calls=all_function_calls,
            prompt_tokens=total_prompt,
            completion_tokens=total_completion,
            latency_ms=total_latency,
            model_name=self.model_name,
            provider=self._provider_name,
        )


# ---------------------------------------------------------------------------
# Azure OpenAI Adapter (GPT-4o and compatible models)
# ---------------------------------------------------------------------------

class AzureOpenAIAdapter(BaseLLMAdapter):
    """Adapter for Azure OpenAI models (GPT-4o, GPT-4 Turbo, etc.)"""

    @property
    def _provider_name(self):
        return "azure_openai"

    def _build_client(self):
        try:
            from openai import AsyncAzureOpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

        azure_endpoint = self.service_metadata.get("azure_endpoint")
        api_version = self.service_metadata.get("api_version", "2025-01-01-preview")
        if not azure_endpoint:
            raise ValueError("service_metadata.azure_endpoint is required for azure_openai provider")

        return AsyncAzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )

    def _get_deployment(self) -> str:
        """Get deployment name from metadata or fall back to model_name."""
        return self.service_metadata.get("deployment_name", self.model_name)

    def _build_messages(self, system_prompt: str, messages: List[Dict]) -> List[Dict]:
        """Convert unified format to OpenAI messages format."""
        result = [{"role": "system", "content": system_prompt}]
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
        """Convert JSON Schema tool defs to OpenAI tool format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema.get("description", ""),
                    "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for schema in tool_schemas
        ]

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
        client = self._build_client()
        oai_messages = self._build_messages(system_prompt, messages)

        kwargs_extra: Dict[str, Any] = {}
        if tools:
            kwargs_extra["tools"] = self.get_tool_declarations(tools)
            kwargs_extra["tool_choice"] = "auto"

        start = time.monotonic()
        response = await client.chat.completions.create(
            model=self._get_deployment(),
            messages=oai_messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            **kwargs_extra,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        choice = response.choices[0]
        output = choice.message.content or ""
        function_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                import json
                args = {}
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {"raw": tc.function.arguments}
                function_calls.append({"name": tc.function.name, "args": args, "_id": tc.id})

        return LLMResponse(
            output=output,
            function_calls=function_calls,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
            latency_ms=latency_ms,
            model_name=self.model_name,
            provider=self._provider_name,
            finish_reason=choice.finish_reason or "stop",
        )

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
        import json
        client = self._build_client()
        messages = self._build_messages(system_prompt, initial_messages)
        tool_defs = self.get_tool_declarations(tool_schemas)

        total_prompt = 0
        total_completion = 0
        total_latency = 0
        combined_output = ""
        all_function_calls = []

        for turn in range(max_react_turns):
            start = time.monotonic()
            response = await client.chat.completions.create(
                model=self._get_deployment(),
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tool_defs if tool_defs else [],
                tool_choice="auto" if tool_defs else "none",
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            total_latency += latency_ms

            if response.usage:
                total_prompt += response.usage.prompt_tokens
                total_completion += response.usage.completion_tokens

            choice = response.choices[0]
            turn_text = choice.message.content or ""
            function_calls = []

            # Append assistant message
            messages.append({"role": "assistant", "content": choice.message.content, "tool_calls": choice.message.tool_calls})

            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    args = {}
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {"raw": tc.function.arguments}
                    function_calls.append({"name": tc.function.name, "args": args, "_id": tc.id})

            if function_calls:
                all_function_calls.extend(function_calls)
                tool_results = await execute_tool_fn(function_calls)

                # Append one tool message per result
                for tr, fc in zip(tool_results, function_calls):
                    messages.append({
                        "role": "tool",
                        "tool_call_id": fc.get("_id", fc["name"]),
                        "content": str(tr["output"]),
                    })

                if turn_text:
                    combined_output += turn_text
                continue
            else:
                combined_output += turn_text
                break

        return LLMResponse(
            output=combined_output,
            function_calls=all_function_calls,
            prompt_tokens=total_prompt,
            completion_tokens=total_completion,
            latency_ms=total_latency,
            model_name=self.model_name,
            provider=self._provider_name,
        )


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def _sanitize_model_name(model_name: str) -> str:
    """
    Strip Vertex AI resource-path prefixes if present.

    The google-genai SDK automatically builds the full resource URL, so
    the model_name must be the *short* form (e.g. 'gemini-2.5-flash').
    If someone stores 'publishers/google/models/gemini-2.5-flash' in the
    DB, this helper strips the prefix to avoid a doubled path that returns 404.
    """
    _PREFIXES = (
        "publishers/google/models/",
        "publishers/anthropic/models/",
        "models/",
    )
    for prefix in _PREFIXES:
        if model_name.startswith(prefix):
            model_name = model_name[len(prefix):]
            break
    return model_name


def _get_adapter(provider_name: str, api_key: str, model_name: str, service_metadata: Dict) -> BaseLLMAdapter:
    """
    Instantiate the correct adapter given a provider name.
    provider_name (from IntegrationRegistry) → adapter class mapping.
    """
    model_name = _sanitize_model_name(model_name)
    pn = (provider_name or "").lower()
    if pn in ("google", "gemini", "google_vertex"):
        return GeminiAdapter(api_key=api_key, model_name=model_name, service_metadata=service_metadata)
    elif pn in ("anthropic", "anthropic_vertex"):
        return AnthropicAdapter(api_key=api_key, model_name=model_name, service_metadata=service_metadata)
    elif pn in ("azure_openai", "azure", "openai"):
        return AzureOpenAIAdapter(api_key=api_key, model_name=model_name, service_metadata=service_metadata)
    else:
        # Default: try Gemini-compatible
        logger.warning(f"Unknown provider '{provider_name}', defaulting to GeminiAdapter")
        return GeminiAdapter(api_key=api_key, model_name=model_name, service_metadata=service_metadata)


# ---------------------------------------------------------------------------
# LLM Router — main entry point
# ---------------------------------------------------------------------------

class LLMRouter:
    """
    Main LLM dispatch class. Resolves the configured model for a task type
    and routes calls to the appropriate provider adapter.

    Usage:
        router = LLMRouter(db=db, company_id=company_id)
        response = await router.call_llm(task_type="text_generation", ...)
    """

    def __init__(self, db: AsyncSession, company_id: UUID):
        self.db = db
        self.company_id = company_id
        self._adapter_cache: dict = {}  # Phase 4: per-run cache to avoid repeated DB lookups

    async def _resolve_adapter(self, task_type: str, model_override: Optional[str] = None) -> BaseLLMAdapter:
        """Resolve the correct adapter based on task defaults.
        
        Phase 4 (PERF-4): Results are cached per (company_id, task_type,
        model_override) tuple for the lifetime of this LLMRouter instance
        to avoid repeated ConfigService DB queries within a single run.
        
        Args:
            task_type: The task type to resolve the model for.
            model_override: Optional model name override from entity config.
                           When set, the adapter uses this model instead of the
                           integration's default (e.g. "gemini-3.1-pro-preview").
        """
        cache_key = f"{self.company_id}:{task_type}:{model_override or ''}"
        if cache_key in self._adapter_cache:
            return self._adapter_cache[cache_key]

        from src.config.service import ConfigService
        config_svc = ConfigService(self.db)
        integration, api_key = await config_svc.resolve_model_for_task(
            company_id=self.company_id,
            task_type=task_type,
        )
        if not integration:
            raise RuntimeError(
                f"No model configured for task type '{task_type}' "
                f"(company_id={self.company_id}). "
                f"Please configure a default in the AI Model Configuration page."
            )
        if not api_key:
            raise RuntimeError(
                f"No API key found for integration '{integration.provider_name}/{integration.model_name}'. "
                f"Please check the Service Integration configuration."
            )
        # Fix D: Entity-level model override takes priority over company defaults
        effective_model = model_override or integration.model_name or ""
        if model_override:
            import logging as _log
            _log.getLogger(__name__).info(
                f"LLMRouter: Model override '{model_override}' "
                f"(default was '{integration.model_name}')"
            )
        adapter = _get_adapter(
            provider_name=integration.provider_name,
            api_key=api_key,
            model_name=effective_model,
            service_metadata=integration.service_metadata or {},
        )
        self._adapter_cache[cache_key] = adapter
        return adapter

    async def call_llm(
        self,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        history: Optional[List[Dict]] = None,
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        model_override: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Single-turn (or last-turn) LLM call.
        Constructs messages from history + current user_prompt.
        """
        adapter = await self._resolve_adapter(task_type, model_override=model_override)
        messages = list(history or [])
        messages.append({"role": "user", "parts": [{"text": user_prompt}]})

        return await adapter.generate(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            **kwargs,
        )

    async def call_llm_react(
        self,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        tool_schemas: List[Dict[str, Any]],
        execute_tool_fn,
        history: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_react_turns: int = 10,
        model_override: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Full REACT loop for agentic tasks.
        execute_tool_fn: async(function_calls: list) -> list of {tool, output, success}
        """
        adapter = await self._resolve_adapter(task_type, model_override=model_override)
        messages = list(history or [])
        messages.append({"role": "user", "parts": [{"text": user_prompt}]})

        return await adapter.generate_with_tools_react(
            system_prompt=system_prompt,
            initial_messages=messages,
            tool_schemas=tool_schemas,
            execute_tool_fn=execute_tool_fn,
            temperature=temperature,
            max_tokens=max_tokens,
            max_react_turns=max_react_turns,
            **kwargs,
        )

    async def get_adapter_for_task(self, task_type: str) -> BaseLLMAdapter:
        """Expose the resolved adapter (useful for streaming modules)."""
        return await self._resolve_adapter(task_type)

