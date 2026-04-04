"""Phase 8 agent runtime loop and CLI entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Protocol

import structlog

from breqy.a2a.client import A2AClient
from breqy.agents.credentials import CredentialStore
from breqy.agents.private_memory import PrivateMemoryRuntime
from breqy.agents.providers.base import ModelProvider, ProviderRequest, ToolDefinition
from breqy.agents.skills import SkillLoader, SkillActivationError
from breqy.config.loader import load_agent_config
from breqy.config.models import AgentConfig
from breqy.domain.enums import EventType, MessageRole
from breqy.domain.events import (
    AgentLifecycleEvent,
    AgentWorkRequestedEvent,
    ControlEvent,
    MessageChunkEvent,
    MessageSentEvent,
    ModelInfoEvent,
    ModelListRequestedEvent,
    ModelListResponseEvent,
    ModelSwitchRequestedEvent,
    ToolExecutionRequestedEvent,
    ToolExecutionResultEvent,
)
from breqy.domain.models import ModelEntry
from breqy.domain.ids import generate_prefixed_id
from breqy.utils.logging import default_log_file, setup_logging

logger = structlog.get_logger(__name__)


class ToolResultWaiter(Protocol):
    async def wait_for(self, invocation_id: str) -> ToolExecutionResultEvent: ...


_MAX_TOOL_ROUNDS = 10


class ToolResultBroker:
    """Asyncio Future-based mediator that connects run() to handle_work().

    ``run()`` calls ``deliver()`` when a ``ToolExecutionResultEvent`` arrives
    from the engine.  ``handle_work()`` calls ``wait_for()`` to suspend until
    the matching result is delivered.
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[ToolExecutionResultEvent]] = {}

    async def wait_for(self, invocation_id: str) -> ToolExecutionResultEvent:
        """Register interest in *invocation_id* and await its result."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[ToolExecutionResultEvent] = loop.create_future()
        self._pending[invocation_id] = fut
        try:
            return await fut
        finally:
            self._pending.pop(invocation_id, None)

    def deliver(self, event: ToolExecutionResultEvent) -> None:
        """Resolve the future waiting for *event.invocation_id*, if any."""
        fut = self._pending.get(event.invocation_id)
        if fut is not None and not fut.done():
            fut.set_result(event)


class AgentRuntime:
    def __init__(
        self,
        *,
        config: AgentConfig,
        agent_dir: Path,
        client: A2AClient,
        provider: ModelProvider,
        skill_loader: SkillLoader | None,
        private_memory_runtime: PrivateMemoryRuntime | None,
        tool_result_waiter: ToolResultWaiter | None,
        session_id: str = "runtime",
        credential_store: Any = None,
    ) -> None:
        self._config = config
        self._agent_dir = agent_dir
        self._client = client
        self._provider = provider
        self._skill_loader = skill_loader
        self._private_memory_runtime = private_memory_runtime
        self._tool_result_waiter = tool_result_waiter
        self._session_id = session_id
        self._credential_store = credential_store
        self._cancel_requested = asyncio.Event()
        self._steer_direction: str | None = None

    async def start(self) -> None:
        await self._client.connect()
        logger.info(
            "Agent runtime started",
            agent_id=self._config.id,
            session_id=self._session_id,
        )
        await self._client.send_event(
            AgentLifecycleEvent(
                event_type=EventType.AGENT_CONNECTED,
                session_id=self._session_id,
                agent_id=self._config.id,
            )
        )
        await self._client.send_event(
            ModelInfoEvent(
                session_id=self._session_id,
                provider_id=self._provider.provider_id,
                model_id=self._provider.model_id,
            )
        )

    async def stop(self) -> None:
        logger.info("Agent runtime stopping", agent_id=self._config.id)
        await self._client.send_event(
            AgentLifecycleEvent(
                event_type=EventType.AGENT_DISCONNECTED,
                session_id=self._session_id,
                agent_id=self._config.id,
            )
        )
        await self._client.disconnect()

    async def run(self) -> None:
        """Start, listen for incoming events, and stop on disconnect."""
        await self.start()
        broker = ToolResultBroker()
        # Install broker as the tool_result_waiter so handle_work uses it
        self._tool_result_waiter = broker
        active_work_task: asyncio.Task[None] | None = None
        try:
            async for envelope in self._client.listen():
                event = envelope.to_event()
                logger.debug(
                    "Event received from engine",
                    event_type=type(event).__name__,
                    session_id=getattr(event, "session_id", ""),
                )
                if isinstance(event, AgentWorkRequestedEvent):
                    # Wait for any prior work task before starting a new one.
                    # In practice there is only ever one active task at a time.
                    if active_work_task is not None:
                        await active_work_task
                    active_work_task = asyncio.create_task(self.handle_work(event))
                elif isinstance(event, ToolExecutionResultEvent):
                    # Route result to broker while handle_work is awaiting it
                    broker.deliver(event)
                elif isinstance(event, ModelListRequestedEvent):
                    await self._handle_model_list(event)
                elif isinstance(event, ModelSwitchRequestedEvent):
                    await self._handle_model_switch(event)
                elif isinstance(event, ControlEvent):
                    self.handle_control(event)
            # Drain the last work task after the listen loop ends
            if active_work_task is not None:
                await active_work_task
        finally:
            if active_work_task is not None and not active_work_task.done():
                active_work_task.cancel()
            await self.stop()

    def _with_broker(self, broker: ToolResultBroker) -> "AgentRuntime":
        """Return a lightweight view of this runtime that uses *broker* as the tool_result_waiter."""
        # We mutate self._tool_result_waiter in-place for simplicity — the
        # broker is re-created per run() call so there are no concurrency issues.
        self._tool_result_waiter = broker
        return self

    def handle_control(self, event: ControlEvent) -> None:
        """Process a control event from the engine."""
        if event.event_type in (
            EventType.CONTROL_STOP,
            EventType.CONTROL_STOP_AND_STEER,
            EventType.CONTROL_CIRCUIT_BREAK,
        ):
            self._cancel_requested.set()
        if event.event_type in (
            EventType.CONTROL_STEER,
            EventType.CONTROL_STOP_AND_STEER,
        ):
            self._steer_direction = event.new_direction

    @property
    def steer_direction(self) -> str | None:
        """Return the pending steer direction, if any."""
        return self._steer_direction

    def clear_steer(self) -> None:
        """Clear the steer direction after it has been consumed."""
        self._steer_direction = None

    @property
    def cancel_requested(self) -> bool:
        """Return True if cancellation has been requested."""
        return self._cancel_requested.is_set()

    async def _handle_model_list(self, event: ModelListRequestedEvent) -> None:
        """Handle a model list request by discovering models and responding."""
        try:
            models = await self._discover_models()
        except Exception:
            logger.warning("Model discovery failed, sending empty response")
            models = []
        await self._client.send_event(
            ModelListResponseEvent(
                session_id=event.session_id,
                models=models,
                current_provider=self._provider.provider_id,
                current_model=self._provider.model_id,
            )
        )

    async def _handle_model_switch(self, event: ModelSwitchRequestedEvent) -> None:
        """Handle a model switch request by rebuilding the provider."""
        # Same-model guard: skip rebuild if already using this model
        if (
            event.provider_id == self._provider.provider_id
            and event.model_id == self._provider.model_id
        ):
            await self._client.send_event(
                ModelInfoEvent(
                    session_id=event.session_id,
                    provider_id=self._provider.provider_id,
                    model_id=self._provider.model_id,
                )
            )
            return

        # Attempt provider rebuild
        try:
            new_config = self._config.model_copy(
                update={"provider": event.provider_id, "model": event.model_id}
            )
            new_provider = _build_provider(new_config, credential_store=self._credential_store)
        except Exception:
            logger.warning(
                "Provider build failed during switch",
                provider=event.provider_id,
                model=event.model_id,
                exc_info=True,
            )
            new_provider = _NullProvider()
            new_config = self._config  # preserve original config

        if isinstance(new_provider, _NullProvider):
            # Switch failed — preserve old provider, send error + old model info
            await self._client.send_event(
                MessageSentEvent(
                    session_id=event.session_id,
                    agent_id=self._config.id,
                    message_id=generate_prefixed_id("msg"),
                    role=MessageRole.SYSTEM,
                    content=f"Failed to switch to {event.provider_id}/{event.model_id}",
                )
            )
            await self._client.send_event(
                ModelInfoEvent(
                    session_id=event.session_id,
                    provider_id=self._provider.provider_id,
                    model_id=self._provider.model_id,
                )
            )
            return

        # Switch succeeded
        self._provider = new_provider
        self._config = new_config
        await self._client.send_event(
            ModelInfoEvent(
                session_id=event.session_id,
                provider_id=self._provider.provider_id,
                model_id=self._provider.model_id,
            )
        )

    async def _discover_models(self) -> list[ModelEntry]:
        """Discover models from all providers.

        For the active provider, call list_models() (may involve HTTP).
        For other providers, use hardcoded fallback lists.
        """
        from breqy.agents.providers.adapters import PROVIDER_FALLBACK_MODELS

        models: list[ModelEntry] = []

        # Active provider: dynamic discovery via list_models()
        active_provider_id = self._provider.provider_id
        try:
            active_models = await asyncio.to_thread(self._provider.list_models)
        except Exception:
            active_models = PROVIDER_FALLBACK_MODELS.get(
                active_provider_id, [(self._provider.model_id, self._provider.model_id)]
            )

        is_active_authenticated = True  # Active provider is already in use
        for model_id, display_name in active_models:
            models.append(
                ModelEntry(
                    provider=active_provider_id,
                    model_id=model_id,
                    display_name=display_name,
                    is_authenticated=is_active_authenticated,
                )
            )

        # Other providers: fallback lists
        for provider_id, fallback_models in PROVIDER_FALLBACK_MODELS.items():
            if provider_id == active_provider_id:
                continue
            is_authenticated = False
            if self._credential_store is not None:
                try:
                    is_authenticated = self._credential_store.get(provider_id) is not None
                except Exception:
                    pass
            for model_id, display_name in fallback_models:
                models.append(
                    ModelEntry(
                        provider=provider_id,
                        model_id=model_id,
                        display_name=display_name,
                        is_authenticated=is_authenticated,
                    )
                )

        return models

    async def handle_work(self, event: AgentWorkRequestedEvent) -> None:
        self._cancel_requested.clear()
        assistant_message_id = generate_prefixed_id("msg")
        logger.debug(
            "Work received",
            session_id=event.session_id,
            agent_id=event.agent_id,
            message_id=assistant_message_id,
        )
        if event.active_skill_ids:
            if self._skill_loader is None:
                await self._emit_skill_failure(event, invalid_skill_ids=event.active_skill_ids)
                return
            try:
                self._skill_loader.resolve_active(
                    active_skill_ids=event.active_skill_ids,
                    skill_permissions=self._config.skill_permissions,
                    tool_permissions=self._config.tool_permissions,
                )
            except SkillActivationError as exc:
                failure_event = ToolExecutionResultEvent(
                    session_id=event.session_id,
                    agent_id=event.agent_id,
                    correlation_id=event.correlation_id,
                    invocation_id=event.correlation_id,
                    failure_payload=exc.payload,
                )
                await self._client.send_event(failure_event)
                return

        tools = self._filter_tools(event.available_tools)
        extra_env: dict[str, str] = {}
        if self._config.persona_content:
            extra_env["BREQY_PERSONA"] = self._config.persona_content

        # Multi-turn state: seed from prior session turns, then append current user message.
        _prior_messages: list[dict[str, Any]] = []
        for msg in event.session_context.messages:
            if msg.role == MessageRole.USER:
                _prior_messages.append({"role": "user", "content": msg.content})
            elif msg.role == MessageRole.ASSISTANT:
                _prior_messages.append({"role": "assistant", "content": msg.content})
            # SYSTEM and TOOL roles are skipped

        if _prior_messages:
            _prior_messages.append({"role": "user", "content": event.user_message_content})
            logger.info(
                "session_context_loaded",
                prior_message_count=len(_prior_messages) - 1,
                session_id=event.session_id,
            )
            conversation_history: list[dict[str, Any]] | None = _prior_messages
        else:
            conversation_history = None
        # Accumulate text content across all rounds (including partial rounds on cancel)
        final_content_parts: list[str] = []
        stream_error: Exception | None = None

        for _round in range(_MAX_TOOL_ROUNDS):
            if self._cancel_requested.is_set():
                break

            request = ProviderRequest(
                prompt=event.user_message_content,
                work_dir=self._agent_dir,
                tools=tools,
                extra_env=extra_env,
                conversation_history=conversation_history,
            )

            logger.debug(
                "Provider stream started",
                provider=self._provider.provider_id,
                model=self._provider.model_id,
                round=_round,
            )

            chunk_index = 0
            # (call_id, tool_name, args, result_event_or_None)
            tool_calls_this_round: list[
                tuple[str, str, dict[str, Any], ToolExecutionResultEvent | None]
            ] = []

            try:
                for provider_event in self._provider.stream(request):
                    if self._cancel_requested.is_set():
                        break

                    if provider_event.kind == "notice" and provider_event.text is not None:
                        notice_message_id = generate_prefixed_id("msg")
                        await self._client.send_event(
                            MessageSentEvent(
                                session_id=event.session_id,
                                agent_id=event.agent_id,
                                correlation_id=event.correlation_id,
                                message_id=notice_message_id,
                                role=MessageRole.SYSTEM,
                                content=provider_event.text,
                            )
                        )
                        assistant_message_id = generate_prefixed_id("msg")
                        chunk_index = 0
                        continue

                    if provider_event.kind == "text" and provider_event.text is not None:
                        final_content_parts.append(provider_event.text)
                        await self._client.send_event(
                            MessageChunkEvent(
                                session_id=event.session_id,
                                agent_id=event.agent_id,
                                correlation_id=event.correlation_id,
                                message_id=assistant_message_id,
                                chunk=provider_event.text,
                                chunk_index=chunk_index,
                            )
                        )
                        chunk_index += 1
                        continue

                    if provider_event.kind == "tool_call" and provider_event.tool_call is not None:
                        tc = provider_event.tool_call
                        arguments: dict[str, Any] = {}
                        if tc.arguments_chunk:
                            arguments = json.loads(tc.arguments_chunk)
                        await self._client.send_event(
                            ToolExecutionRequestedEvent(
                                session_id=event.session_id,
                                agent_id=event.agent_id,
                                correlation_id=tc.call_id,
                                invocation_id=tc.call_id,
                                tool_name=tc.tool_name,
                                arguments=arguments,
                            )
                        )
                        # Await result inline so cancel can interrupt streaming
                        result_event: ToolExecutionResultEvent | None = None
                        if self._tool_result_waiter is not None:
                            result_event = await self._tool_result_waiter.wait_for(tc.call_id)
                        tool_calls_this_round.append(
                            (tc.call_id, tc.tool_name, arguments, result_event)
                        )
                        # Cancellation checkpoint after tool result (waiter may set cancel)
                        if self._cancel_requested.is_set():
                            break
                        continue

            except Exception as exc:
                stream_error = exc
                logger.error(
                    "Provider stream error",
                    provider=self._provider.provider_id,
                    model=self._provider.model_id,
                    error=str(exc),
                )
                break

            if self._cancel_requested.is_set():
                break

            # No tool calls this round → final text response, done
            if not tool_calls_this_round:
                break

            # Tool calls present — but only loop if we have a waiter
            # (if no waiter, results are None and we can't build conversation history)
            if self._tool_result_waiter is None:
                break

            # Build next conversation_history from collected tool calls + their results
            assistant_tool_calls = [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": tool_name, "arguments": json.dumps(args)},
                }
                for call_id, tool_name, args, _result in tool_calls_this_round
            ]

            # Build the new conversation_history for the next round
            if conversation_history is None:
                next_history: list[dict[str, Any]] = [
                    {"role": "user", "content": event.user_message_content}
                ]
            else:
                next_history = list(conversation_history)

            # Add the assistant's tool call message
            next_history.append(
                {"role": "assistant", "content": None, "tool_calls": assistant_tool_calls}
            )

            # Append each tool result (already fetched inline during streaming)
            for call_id, tool_name, _args, result_event in tool_calls_this_round:
                output_text = ""
                if result_event is not None:
                    if result_event.success_payload is not None:
                        output_text = result_event.success_payload.summary
                    elif result_event.failure_payload is not None:
                        output_text = str(result_event.failure_payload)
                next_history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": tool_name,
                        "content": output_text,
                    }
                )

            conversation_history = next_history
            # Continue to next round

        # Emit final result
        if stream_error is not None:
            error_message_id = generate_prefixed_id("msg")
            await self._client.send_event(
                MessageSentEvent(
                    session_id=event.session_id,
                    agent_id=event.agent_id,
                    correlation_id=event.correlation_id,
                    message_id=error_message_id,
                    role=MessageRole.SYSTEM,
                    content=f"Error from {self._provider.provider_id}/{self._provider.model_id}: {stream_error}",
                )
            )
        else:
            await self._client.send_event(
                MessageSentEvent(
                    session_id=event.session_id,
                    agent_id=event.agent_id,
                    correlation_id=event.correlation_id,
                    message_id=assistant_message_id,
                    role=MessageRole.ASSISTANT,
                    content="".join(final_content_parts),
                )
            )
        logger.debug(
            "Response complete",
            message_id=assistant_message_id,
            content_length=len("".join(final_content_parts)),
        )

    def _filter_tools(self, available_tools: list[ToolDefinition]) -> list[ToolDefinition]:
        """Filter available tools by agent tool_permissions from config.

        If tool_permissions is empty, all tools are allowed (backward compat).
        """
        permissions = self._config.tool_permissions
        if not permissions:
            return list(available_tools)
        allowed = set(permissions)
        return [t for t in available_tools if t.name in allowed]

    async def _emit_skill_failure(
        self,
        event: AgentWorkRequestedEvent,
        *,
        invalid_skill_ids: list[str],
    ) -> None:
        await self._client.send_event(
            ToolExecutionResultEvent(
                session_id=event.session_id,
                agent_id=event.agent_id,
                correlation_id=event.correlation_id,
                invocation_id=event.correlation_id,
                failure_payload={
                    "code": "invalid_skill_activation",
                    "message": "One or more requested skills are unknown or disallowed for this agent",
                    "details": {"invalid_skill_ids": invalid_skill_ids},
                },
            )
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-dir", required=True)
    parser.add_argument("--engine-socket", required=False)
    parser.add_argument("--session-id", required=False, default=None)
    return parser.parse_args()


def _build_provider(
    config: AgentConfig,
    credential_store: CredentialStore | None = None,
) -> ModelProvider | _NullProvider:
    """Build a real ModelProvider from agent config.

    Falls back to _NullProvider if provider construction fails
    (e.g., missing credentials backend or unsupported provider).

    When *credential_store* is provided it is used directly; otherwise
    a fresh ``CredentialStore`` is created internally (legacy path).
    """
    try:
        from breqy.agents.providers.adapters import build_model_providers

        if credential_store is None:
            from breqy.secrets.provider import FileSecretProvider, KeyringSecretProvider

            try:
                secret_provider = KeyringSecretProvider()
                # Probe: verify keyring is functional
                secret_provider.get("__probe__")
            except Exception:
                structlog.get_logger().info(
                    "keyring_unavailable_using_file_store",
                    provider=config.provider,
                )
                secret_provider = FileSecretProvider()

            credential_store = CredentialStore(secret_provider)

        providers = build_model_providers(
            credential_store=credential_store,
            model_by_provider={config.provider: config.model},
        )
        provider = providers.get(config.provider)
        if provider is not None:
            return provider
    except Exception as exc:
        structlog.get_logger().error(
            "provider_build_failed",
            provider=config.provider,
            model=config.model,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
    return _NullProvider()


def _create_credential_store() -> CredentialStore:
    """Create a CredentialStore with the best available secret backend."""
    from breqy.secrets.provider import FileSecretProvider, KeyringSecretProvider

    try:
        secret_provider = KeyringSecretProvider()
        secret_provider.get("__probe__")
    except Exception:
        structlog.get_logger().info("keyring_unavailable_using_file_store")
        secret_provider = FileSecretProvider()

    return CredentialStore(secret_provider)


def main() -> None:
    args = _parse_args()
    agent_dir = Path(args.agent_dir)
    config = load_agent_config(str(agent_dir))
    if args.engine_socket:
        config = config.model_copy(update={"engine_socket": args.engine_socket})
    session_id = args.session_id or "runtime"

    # Initialize logging for agent subprocess
    import os

    data_dir = Path(os.environ.get("BREQY_DATA_DIR", str(Path.home() / ".breqy" / "data")))
    log_dir = data_dir / "logs"
    setup_logging(
        level=config.log_level,
        log_file=default_log_file(log_dir, process="agent", agent_id=config.id),
        console=False,
        context={"process": "agent", "agent_id": config.id},
    )

    # Create credential store once — shared by provider builder and runtime
    credential_store = _create_credential_store()

    runtime = AgentRuntime(
        config=config,
        agent_dir=agent_dir,
        client=A2AClient(config.engine_socket),
        provider=_build_provider(config, credential_store=credential_store),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
        session_id=session_id,
        credential_store=credential_store,
    )

    import asyncio

    async def run() -> None:
        await runtime.run()

    asyncio.run(run())


class _NullProvider:
    provider_id = "null"
    model_id = "null"
    supports_tool_calls = False

    def stream(self, request: ProviderRequest):
        if False:
            yield request

    def list_models(self) -> list[tuple[str, str]]:
        return [("null", "null")]


if __name__ == "__main__":
    main()
