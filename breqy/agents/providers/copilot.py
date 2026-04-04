"""GitHub Copilot ModelProvider implementation."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from breqy.agents.providers.base import (
    CompletionMetadata,
    ModelProvider,
    ProviderEvent,
    ProviderRequest,
    ToolCallDelta,
    ToolDefinition,
)
from breqy.agents.providers.copilot_auth import CopilotAuthError, CopilotAuthenticator
from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class _PendingDeviceFlow:
    """Carries device flow state between yield and poll."""

    device_code: str
    interval: int
    auth_event: ProviderEvent


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
        self._model_endpoints: dict[str, list[str]] = {}

    @property
    def provider_id(self) -> str:
        return "copilot"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def supports_tool_calls(self) -> bool:
        return True

    def list_models(self) -> list[tuple[str, str]]:
        """Query Copilot API for available models.

        Filters to models with capabilities.type == 'chat' and
        model_picker_enabled == True. Deduplicates by name, keeping
        the highest version. Stores supported_endpoints metadata per
        model for endpoint routing.
        """
        token = self._authenticator.get_copilot_token()
        if token is None:
            return [(self.model_id, self.model_id)]
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Copilot-Integration-Id": "vscode-chat",
            "Editor-Version": "vscode/1.97.2",
            "Editor-Plugin-Version": "copilot-chat/0.22.2",
            "User-Agent": "GitHubCopilotChat/0.22.2",
            "x-github-api-version": "2025-10-01",
        }
        try:
            resp = httpx.get(
                "https://api.githubcopilot.com/models",
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code != 200:
                logger.debug(
                    "copilot_list_models_non_200",
                    status_code=resp.status_code,
                    body=resp.text[:500],
                )
                return [(self.model_id, self.model_id)]
            data = resp.json()
            raw_models = data.get("data", [])

            # Filter: chat models with model_picker_enabled
            chat_models = []
            for m in raw_models:
                caps = m.get("capabilities", {})
                if caps.get("type") != "chat":
                    continue
                if not m.get("model_picker_enabled", False):
                    continue
                chat_models.append(m)

            # Deduplicate by name, keeping highest version
            name_map: dict[str, dict] = {}
            for m in chat_models:
                name = m.get("name", m["id"])
                existing = name_map.get(name)
                if existing is None or m.get("version", "") > existing.get("version", ""):
                    name_map[name] = m

            # Store endpoint metadata for routing
            models = []
            for m in name_map.values():
                model_id = m["id"]
                display_name = m.get("name", model_id)
                self._model_endpoints[model_id] = m.get(
                    "supported_endpoints", ["/chat/completions"]
                )
                models.append((model_id, display_name))

            logger.debug("copilot_list_models_ok", count=len(models), total_raw=len(raw_models))
            return models
        except Exception:
            logger.debug("copilot_list_models_failed", exc_info=True)
            return [(self.model_id, self.model_id)]

    def stream(self, request: ProviderRequest) -> Iterator[ProviderEvent]:
        try:
            token = self._authenticator.get_copilot_token()
        except CopilotAuthError:
            logger.info("copilot_auth_error_clearing_token")
            self._authenticator.clear_token()
            token = None

        if token is None:
            pending_flow = self._start_device_flow()
            yield pending_flow.auth_event  # Yield auth instructions BEFORE blocking poll
            self._authenticator.poll_for_token(
                pending_flow.device_code, interval=pending_flow.interval
            )
            # After device flow stores the OAuth token, exchange it for a session token
            token = self._authenticator.get_copilot_token()

        try:
            yield from self._do_stream_routed(token, request)
        except CopilotApiError as exc:
            if exc.status_code == 401:
                logger.info("copilot_token_expired_retrying")
                self._authenticator.clear_token()
                try:
                    token = self._authenticator.get_copilot_token()
                except CopilotAuthError:
                    logger.info("copilot_auth_error_during_retry")
                    token = None
                if token is None:
                    pending_flow = self._start_device_flow()
                    yield pending_flow.auth_event
                    self._authenticator.poll_for_token(
                        pending_flow.device_code, interval=pending_flow.interval
                    )
                    token = self._authenticator.get_copilot_token()
                yield from self._do_stream_routed(token, request)
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

    def _start_device_flow(self) -> _PendingDeviceFlow:
        """Initiate device flow and build the auth instructions event.

        Returns a lightweight object carrying the device code, interval,
        and a ``ProviderEvent`` with user-facing auth instructions.
        The caller is responsible for yielding the event to the TUI
        **before** calling ``poll_for_token`` so the user can see the
        code while the provider blocks on the poll loop.
        """
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
        return _PendingDeviceFlow(
            device_code=flow_info.device_code,
            interval=flow_info.interval,
            auth_event=ProviderEvent(kind="notice", text=auth_message),
        )

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

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
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

    def _convert_tools_responses(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        """Convert Breqy ToolDefinition to Responses API tool format."""
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            for tool in tools
        ]

    def _use_responses_api(self) -> bool:
        """Determine if this model should use the /responses endpoint."""
        endpoints = self._model_endpoints.get(self._model_id, [])
        if "/responses" in endpoints:
            return True
        return False

    def _do_stream_routed(
        self,
        token: str,
        request: ProviderRequest,
    ) -> Iterator[ProviderEvent]:
        """Route to the correct streaming method based on model endpoints."""
        if self._use_responses_api():
            yield from self._do_stream_responses(token, request)
        else:
            messages = self._build_messages(request)
            tools = self._convert_tools(request.tools) if request.tools else None
            yield from self._do_stream(token, messages, tools)

    def _build_responses_input(
        self, request: ProviderRequest
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Convert ProviderRequest to Responses API input format.

        Returns (input_messages, instructions) where system messages
        are extracted into the instructions parameter.
        """
        instructions: str | None = None
        persona = request.extra_env.get("BREQY_PERSONA")
        if persona:
            instructions = persona

        input_messages: list[dict[str, Any]] = [
            {"role": "user", "content": request.prompt},
        ]
        return input_messages, instructions

    def _do_stream_responses(
        self,
        token: str,
        request: ProviderRequest,
    ) -> Iterator[ProviderEvent]:
        """Stream from Responses API and map events to ProviderEvent."""
        input_messages, instructions = self._build_responses_input(request)
        tools = self._convert_tools_responses(request.tools) if request.tools else None

        for event in self._client.stream_responses(
            token=token,
            model=self._model_id,
            input_messages=input_messages,
            tools=tools,
            instructions=instructions,
        ):
            event_type = event.get("type", "")

            # Text content
            if event_type == "response.output_text.delta":
                delta = event.get("delta", "")
                if delta:
                    yield ProviderEvent(kind="text", text=delta)

            # Tool call (complete item)
            elif event_type == "response.output_item.done":
                item = event.get("item", {})
                if item.get("type") == "function_call":
                    yield ProviderEvent(
                        kind="tool_call",
                        tool_call=ToolCallDelta(
                            call_id=item.get("call_id", ""),
                            tool_name=item.get("name", ""),
                            arguments_chunk=item.get("arguments", ""),
                        ),
                    )

            # Stream complete (success)
            elif event_type == "response.completed":
                yield ProviderEvent(
                    kind="complete",
                    metadata=CompletionMetadata(
                        provider_id=self.provider_id,
                        model_id=self.model_id,
                        exit_code=0,
                    ),
                )

            # Stream complete (failure)
            elif event_type == "response.failed":
                yield ProviderEvent(
                    kind="complete",
                    metadata=CompletionMetadata(
                        provider_id=self.provider_id,
                        model_id=self.model_id,
                        exit_code=1,
                    ),
                )
