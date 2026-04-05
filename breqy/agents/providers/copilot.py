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
        initiator: str = "user",
    ) -> Iterator[ProviderEvent]:
        """Stream from API and map chunks to ProviderEvent.

        Tool call arguments arrive in fragments across many SSE delta events.
        We accumulate them per-index and emit a single complete ToolCallDelta
        event per tool call only when finish_reason is set, so consumers
        always receive parseable (complete) JSON arguments.
        """
        # index -> (call_id, tool_name, accumulated_args)
        active_tool_calls: dict[int, tuple[str, str, str]] = {}

        for chunk in self._client.stream_chat(
            token=token,
            model=self._model_id,
            messages=messages,
            tools=tools,
            initiator=initiator,
        ):
            choices = chunk.get("choices", [])
            if not choices:
                continue

            choice = choices[0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")

            # Text content — yield immediately for live streaming
            content = delta.get("content")
            if isinstance(content, str) and content:
                yield ProviderEvent(kind="text", text=content)

            # Tool call deltas — accumulate, don't yield yet
            tool_calls = delta.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    index = tc.get("index", 0)
                    call_id = tc.get("id")
                    function = tc.get("function", {})
                    tool_name = function.get("name")
                    arguments = function.get("arguments", "")

                    if call_id and tool_name:
                        # First delta for this tool call index
                        active_tool_calls[index] = (call_id, tool_name, arguments)
                    elif index in active_tool_calls:
                        # Subsequent argument fragment — accumulate
                        existing_id, existing_name, prev_args = active_tool_calls[index]
                        active_tool_calls[index] = (
                            existing_id,
                            existing_name,
                            prev_args + arguments,
                        )

            # On finish: emit all accumulated complete tool calls, then complete event
            if finish_reason:
                for idx in sorted(active_tool_calls):
                    call_id, tool_name, full_args = active_tool_calls[idx]
                    yield ProviderEvent(
                        kind="tool_call",
                        tool_call=ToolCallDelta(
                            call_id=call_id,
                            tool_name=tool_name,
                            arguments_chunk=full_args,
                        ),
                    )
                yield ProviderEvent(
                    kind="complete",
                    metadata=CompletionMetadata(
                        provider_id=self.provider_id,
                        model_id=self.model_id,
                        exit_code=0,
                    ),
                )

    def _build_messages(self, request: ProviderRequest) -> list[dict[str, Any]]:
        """Convert ProviderRequest to OpenAI messages format.

        When ``request.conversation_history`` is set (multi-turn tool loop),
        it replaces the single user turn and already contains the full history
        including tool calls and tool results.  A system persona message is
        still prepended when configured.
        """
        messages: list[dict[str, Any]] = []
        persona = request.extra_env.get("BREQY_PERSONA")
        if persona:
            messages.append({"role": "system", "content": persona})
        if request.conversation_history is not None:
            messages.extend(request.conversation_history)
        else:
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

    @staticmethod
    def _sanitize_tool_name(name: str) -> str:
        """Return a Responses API-compatible tool name.

        The Responses API only allows ``^[a-zA-Z0-9_-]+$``.
        Dots (used in memory tool names like ``mcp.memory.n--search``)
        are replaced with underscores.
        """
        return name.replace(".", "_")

    def _convert_tools_responses(
        self, tools: list[ToolDefinition]
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Convert Breqy ToolDefinition to Responses API tool format.

        Returns ``(tool_dicts, name_map)`` where ``name_map`` maps each
        sanitized tool name back to its original name.  The caller uses
        ``name_map`` to restore the original name when the model returns
        a tool call, ensuring the runtime can route it to the correct executor.
        """
        tool_dicts: list[dict[str, Any]] = []
        name_map: dict[str, str] = {}
        for tool in tools:
            sanitized = self._sanitize_tool_name(tool.name)
            name_map[sanitized] = tool.name
            tool_dicts.append(
                {
                    "type": "function",
                    "name": sanitized,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                }
            )
        return tool_dicts, name_map

    def _use_responses_api(self, token: str) -> bool:
        """Determine if this model should use the /responses endpoint.

        If endpoint metadata hasn't been populated yet (e.g. fresh provider
        created during model switch), lazily queries the /models API using
        the provided token to discover supported endpoints.
        """
        if self._model_id not in self._model_endpoints:
            logger.debug("copilot_lazy_endpoint_discovery", model=self._model_id)
            self._discover_endpoints(token)
        endpoints = self._model_endpoints.get(self._model_id, [])
        if "/responses" in endpoints:
            return True
        return False

    def _discover_endpoints(self, token: str) -> None:
        """Fetch model metadata and populate _model_endpoints cache.

        Reuses the provided session token so this can be called from
        stream() without triggering additional auth flows.
        """
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
                    "copilot_endpoint_discovery_non_200",
                    status_code=resp.status_code,
                )
                return
            data = resp.json()
            for m in data.get("data", []):
                model_id = m.get("id", "")
                if model_id:
                    self._model_endpoints[model_id] = m.get(
                        "supported_endpoints", ["/chat/completions"]
                    )
        except Exception:
            logger.debug("copilot_endpoint_discovery_failed", exc_info=True)

    def _do_stream_routed(
        self,
        token: str,
        request: ProviderRequest,
    ) -> Iterator[ProviderEvent]:
        """Route to the correct streaming method based on model endpoints."""
        if self._use_responses_api(token):
            yield from self._do_stream_responses(token, request)
        else:
            messages = self._build_messages(request)
            tools = self._convert_tools(request.tools) if request.tools else None
            yield from self._do_stream(token, messages, tools, initiator=request.initiator)

    def _build_responses_input(
        self, request: ProviderRequest
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Convert ProviderRequest to Responses API input format.

        Returns (input_messages, instructions) where system messages
        are extracted into the instructions parameter.

        When ``request.conversation_history`` is set (multi-turn tool loop),
        the full history is passed as input_messages instead of a single user
        turn.

        Chat Completions format for tool calls (produced by the runtime) is
        translated to Responses API format:
          - ``{"role": "assistant", "content": None, "tool_calls": [...]}``
            becomes one ``{"type": "function_call", ...}`` item per tool call.
          - ``{"role": "tool", "tool_call_id": "...", "content": "..."}``
            becomes ``{"type": "function_call_output", "call_id": "...", "output": "..."}``.
        """
        instructions: str | None = None
        persona = request.extra_env.get("BREQY_PERSONA")
        if persona:
            instructions = persona

        if request.conversation_history is not None:
            input_messages: list[dict[str, Any]] = []
            for msg in request.conversation_history:
                role = msg.get("role")
                if role == "assistant" and msg.get("tool_calls"):
                    # Translate each tool_call to a Responses API function_call item
                    for tc in msg["tool_calls"]:
                        fn = tc.get("function", {})
                        input_messages.append(
                            {
                                "type": "function_call",
                                "call_id": tc.get("id", ""),
                                "name": fn.get("name", ""),
                                "arguments": fn.get("arguments", "{}"),
                            }
                        )
                elif role == "tool":
                    # Translate to Responses API function_call_output item
                    input_messages.append(
                        {
                            "type": "function_call_output",
                            "call_id": msg.get("tool_call_id", ""),
                            "output": msg.get("content", ""),
                        }
                    )
                else:
                    input_messages.append(msg)
        else:
            input_messages = [{"role": "user", "content": request.prompt}]
        return input_messages, instructions

    def _do_stream_responses(
        self,
        token: str,
        request: ProviderRequest,
    ) -> Iterator[ProviderEvent]:
        """Stream from Responses API and map events to ProviderEvent."""
        input_messages, instructions = self._build_responses_input(request)
        tool_name_map: dict[str, str] = {}
        tools: list[dict[str, Any]] | None = None
        if request.tools:
            tools, tool_name_map = self._convert_tools_responses(request.tools)

        for event in self._client.stream_responses(
            token=token,
            model=self._model_id,
            input_messages=input_messages,
            tools=tools,
            instructions=instructions,
            initiator=request.initiator,
        ):
            event_type = event.get("type", "")

            # Text content
            if event_type == "response.output_text.delta":
                delta = event.get("delta", "")
                if delta:
                    yield ProviderEvent(kind="text", text=delta)

            # Reasoning summary text chunk
            elif event_type == "response.reasoning_summary_text.delta":
                delta = event.get("delta", "")
                if delta:
                    yield ProviderEvent(kind="reasoning_text", text=delta)

            # Reasoning item started
            elif event_type == "response.output_item.added":
                item = event.get("item", {})
                if item.get("type") == "reasoning":
                    yield ProviderEvent(kind="reasoning_started")

            # Tool call OR reasoning item done
            elif event_type == "response.output_item.done":
                item = event.get("item", {})
                if item.get("type") == "function_call":
                    api_name = item.get("name", "")
                    # Restore the original tool name: the API receives sanitized names
                    # (dots replaced with underscores); map back to the original so the
                    # runtime can route the call to the correct ToolExecutor.
                    original_name = tool_name_map.get(api_name, api_name)
                    yield ProviderEvent(
                        kind="tool_call",
                        tool_call=ToolCallDelta(
                            call_id=item.get("call_id", ""),
                            tool_name=original_name,
                            arguments_chunk=item.get("arguments", ""),
                        ),
                    )
                elif item.get("type") == "reasoning":
                    yield ProviderEvent(kind="reasoning_done")

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
