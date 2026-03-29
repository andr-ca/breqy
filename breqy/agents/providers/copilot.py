"""GitHub Copilot ModelProvider implementation."""
from __future__ import annotations

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
from breqy.agents.providers.copilot_auth import CopilotAuthenticator
from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

logger = structlog.get_logger(__name__)


class CopilotProvider(ModelProvider):
    """Direct HTTP provider for GitHub Copilot chat completions API."""

    def __init__(
        self,
        *,
        model_id: str,
        authenticator: CopilotAuthenticator,
        client: CopilotApiClient,
    ) -> None:
        self._model_id = model_id
        self._authenticator = authenticator
        self._client = client

    @property
    def provider_id(self) -> str:
        return "copilot"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def supports_tool_calls(self) -> bool:
        return True

    def stream(self, request: ProviderRequest) -> Iterator[ProviderEvent]:
        token, auth_event = self._ensure_token()
        if auth_event is not None:
            yield auth_event
        messages = self._build_messages(request)
        tools = self._convert_tools(request.tools) if request.tools else None

        try:
            yield from self._do_stream(token, messages, tools)
        except CopilotApiError as exc:
            if exc.status_code == 401:
                logger.info("copilot_token_expired_retrying")
                self._authenticator.clear_token()
                token, auth_event = self._ensure_token()
                if auth_event is not None:
                    yield auth_event
                yield from self._do_stream(token, messages, tools)
            else:
                yield ProviderEvent(
                    kind="complete",
                    metadata=CompletionMetadata(
                        provider_id=self.provider_id,
                        model_id=self.model_id,
                        exit_code=1,
                    ),
                )
                raise

    def _ensure_token(self) -> tuple[str, ProviderEvent | None]:
        """Get existing token or run device flow.

        Returns (token, optional_auth_text_event). The auth text event
        contains instructions for the user to complete the device flow
        and should be yielded to the TUI so the user can see them.
        """
        token = self._authenticator.get_token()
        if token is not None:
            return token, None

        logger.info("copilot_no_token_starting_device_flow")
        flow_info = self._authenticator.start_device_flow()
        auth_message = (
            f"\n**GitHub Copilot Authentication Required**\n\n"
            f"1. Open {flow_info.verification_uri}\n"
            f"2. Enter code: **{flow_info.user_code}**\n\n"
            f"Waiting for authorization...\n"
        )
        logger.info(
            "copilot_device_flow_instructions",
            url=flow_info.verification_uri,
            code=flow_info.user_code,
        )
        auth_event = ProviderEvent(kind="text", text=auth_message)
        token = self._authenticator.poll_for_token(
            flow_info.device_code, interval=flow_info.interval
        )
        return token, auth_event

    def _do_stream(
        self,
        token: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> Iterator[ProviderEvent]:
        """Stream from API and map chunks to ProviderEvent."""
        active_tool_calls: dict[int, ToolCallDelta] = {}

        for chunk in self._client.stream_chat(
            token=token,
            model=self._model_id,
            messages=messages,
            tools=tools,
        ):
            choices = chunk.get("choices", [])
            if not choices:
                continue

            choice = choices[0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")

            # Text content
            content = delta.get("content")
            if isinstance(content, str) and content:
                yield ProviderEvent(kind="text", text=content)

            # Tool calls
            tool_calls = delta.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    index = tc.get("index", 0)
                    call_id = tc.get("id")
                    function = tc.get("function", {})
                    tool_name = function.get("name")
                    arguments = function.get("arguments", "")

                    if call_id and tool_name:
                        active_tool_calls[index] = ToolCallDelta(
                            call_id=call_id,
                            tool_name=tool_name,
                            arguments_chunk=arguments,
                        )
                        yield ProviderEvent(
                            kind="tool_call",
                            tool_call=active_tool_calls[index],
                        )
                    elif index in active_tool_calls and arguments:
                        yield ProviderEvent(
                            kind="tool_call",
                            tool_call=ToolCallDelta(
                                call_id=active_tool_calls[index].call_id,
                                tool_name=active_tool_calls[index].tool_name,
                                arguments_chunk=arguments,
                            ),
                        )

            # Stream complete
            if finish_reason:
                yield ProviderEvent(
                    kind="complete",
                    metadata=CompletionMetadata(
                        provider_id=self.provider_id,
                        model_id=self.model_id,
                        exit_code=0,
                    ),
                )

    def _build_messages(self, request: ProviderRequest) -> list[dict[str, Any]]:
        """Convert ProviderRequest to OpenAI messages format."""
        messages: list[dict[str, Any]] = []
        persona = request.extra_env.get("BREQY_PERSONA")
        if persona:
            messages.append({"role": "system", "content": persona})
        messages.append({"role": "user", "content": request.prompt})
        return messages

    def _convert_tools(
        self, tools: list[ToolDefinition]
    ) -> list[dict[str, Any]]:
        """Convert Breqy ToolDefinition to OpenAI tool format."""
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
