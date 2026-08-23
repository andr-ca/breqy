"""Ollama local model server ModelProvider implementation."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import structlog

from breqy.agents.providers.base import (
    CompletionMetadata,
    ModelProvider,
    ProviderEvent,
    ProviderRequest,
    ToolCallDelta,
    ToolDefinition,
)
from breqy.agents.providers.ollama_client import OllamaApiClient, OllamaApiError

logger = structlog.get_logger(__name__)


class OllamaProvider(ModelProvider):
    """HTTP provider for a local or remote Ollama server."""

    def __init__(
        self,
        *,
        model_id: str,
        client: OllamaApiClient,
    ) -> None:
        self._model_id = model_id
        self._client = client

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def supports_tool_calls(self) -> bool:
        return True

    def list_models(self) -> list[tuple[str, str]]:
        try:
            return self._client.list_models()
        except Exception:
            logger.debug("ollama_list_models_failed", exc_info=True)
            return [(self.model_id, self.model_id)]

    def stream(self, request: ProviderRequest) -> Iterator[ProviderEvent]:
        messages = self._build_messages(request)
        tools = self._convert_tools(request.tools) if request.tools else None
        try:
            yield from self._do_stream(messages, tools)
        except OllamaApiError:
            yield ProviderEvent(
                kind="complete",
                metadata=CompletionMetadata(
                    provider_id=self.provider_id,
                    model_id=self.model_id,
                    exit_code=1,
                ),
            )
            raise

    def _do_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> Iterator[ProviderEvent]:
        reasoning_started = False

        for chunk in self._client.stream_chat(
            model=self._model_id,
            messages=messages,
            tools=tools,
        ):
            message = chunk.get("message")
            if not isinstance(message, dict):
                if chunk.get("done"):
                    yield self._completion_event()
                continue

            thinking = message.get("thinking")
            if isinstance(thinking, str) and thinking:
                if not reasoning_started:
                    reasoning_started = True
                    yield ProviderEvent(kind="reasoning_started")
                yield ProviderEvent(kind="reasoning_text", text=thinking)

            content = message.get("content")
            if isinstance(content, str) and content:
                yield ProviderEvent(kind="text", text=content)

            if chunk.get("done"):
                if reasoning_started:
                    yield ProviderEvent(kind="reasoning_done")

                tool_calls = message.get("tool_calls")
                if isinstance(tool_calls, list):
                    for index, tool_call in enumerate(tool_calls):
                        if not isinstance(tool_call, dict):
                            continue
                        function = tool_call.get("function")
                        if not isinstance(function, dict):
                            continue
                        tool_name = function.get("name")
                        if not isinstance(tool_name, str) or not tool_name:
                            continue
                        arguments = function.get("arguments", {})
                        if isinstance(arguments, dict):
                            arguments_chunk = json.dumps(arguments)
                        elif isinstance(arguments, str):
                            arguments_chunk = arguments
                        else:
                            arguments_chunk = "{}"
                        call_id = tool_call.get("id")
                        if not isinstance(call_id, str) or not call_id:
                            call_id = f"ollama-tool-{index}"
                        yield ProviderEvent(
                            kind="tool_call",
                            tool_call=ToolCallDelta(
                                call_id=call_id,
                                tool_name=tool_name,
                                arguments_chunk=arguments_chunk,
                            ),
                        )

                yield self._completion_event()

    def _completion_event(self) -> ProviderEvent:
        return ProviderEvent(
            kind="complete",
            metadata=CompletionMetadata(
                provider_id=self.provider_id,
                model_id=self._model_id,
                exit_code=0,
            ),
        )

    def _build_messages(self, request: ProviderRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        persona = request.extra_env.get("BREQY_PERSONA")
        if persona:
            messages.append({"role": "system", "content": persona})
        if request.conversation_history is not None:
            messages.extend(self._normalize_history_message(msg) for msg in request.conversation_history)
        else:
            messages.append({"role": "user", "content": request.prompt})
        return messages

    def _normalize_history_message(self, message: dict[str, Any]) -> dict[str, Any]:
        role = message.get("role")
        if role != "tool":
            return message
        tool_name = message.get("name") or message.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            tool_name = "tool"
        content = message.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content)
        return {
            "role": "tool",
            "tool_name": tool_name,
            "content": content,
        }

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]
