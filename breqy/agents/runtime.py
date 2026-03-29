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
from breqy.agents.providers.base import ModelProvider, ProviderRequest
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
        try:
            async for envelope in self._client.listen():
                event = envelope.to_event()
                logger.debug(
                    "Event received from engine",
                    event_type=type(event).__name__,
                    session_id=getattr(event, "session_id", ""),
                )
                if isinstance(event, AgentWorkRequestedEvent):
                    await self.handle_work(event)
                elif isinstance(event, ModelListRequestedEvent):
                    await self._handle_model_list(event)
                elif isinstance(event, ModelSwitchRequestedEvent):
                    await self._handle_model_switch(event)
                elif isinstance(event, ControlEvent):
                    self.handle_control(event)
        finally:
            await self.stop()

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

        content_parts: list[str] = []
        chunk_index = 0
        request = ProviderRequest(
            prompt=event.user_message_content,
            work_dir=self._agent_dir,
        )
        logger.debug(
            "Provider stream started",
            provider=self._provider.provider_id,
            model=self._provider.model_id,
        )
        stream_error: Exception | None = None
        try:
            for provider_event in self._provider.stream(request):
                # Cancellation checkpoint 1: before processing each provider event
                if self._cancel_requested.is_set():
                    break

                if provider_event.kind == "notice" and provider_event.text is not None:
                    # Notice events are sent as complete standalone messages
                    # so the TUI renders them immediately (e.g. auth instructions).
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
                    # Reset for the next (real) streaming message
                    assistant_message_id = generate_prefixed_id("msg")
                    content_parts = []
                    chunk_index = 0
                    continue

                if provider_event.kind == "text" and provider_event.text is not None:
                    content_parts.append(provider_event.text)
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
                    arguments: dict[str, Any] = {}
                    if provider_event.tool_call.arguments_chunk:
                        arguments = json.loads(provider_event.tool_call.arguments_chunk)
                    await self._client.send_event(
                        ToolExecutionRequestedEvent(
                            session_id=event.session_id,
                            agent_id=event.agent_id,
                            correlation_id=provider_event.tool_call.call_id,
                            invocation_id=provider_event.tool_call.call_id,
                            tool_name=provider_event.tool_call.tool_name,
                            arguments=arguments,
                        )
                    )
                    if self._tool_result_waiter is not None:
                        await self._tool_result_waiter.wait_for(provider_event.tool_call.call_id)

                    # Cancellation checkpoint 2: after tool result
                    if self._cancel_requested.is_set():
                        break
        except Exception as exc:
            stream_error = exc
            logger.error(
                "Provider stream error",
                provider=self._provider.provider_id,
                model=self._provider.model_id,
                error=str(exc),
            )

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
                    content="".join(content_parts),
                )
            )
        logger.debug(
            "Response complete",
            message_id=assistant_message_id,
            content_length=len("".join(content_parts)),
            chunk_count=chunk_index,
        )

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

    data_dir = Path(
        os.environ.get("BREQY_DATA_DIR", str(Path.home() / ".breqy" / "data"))
    )
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
