"""Phase 8 agent runtime loop and CLI entrypoint."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Protocol

from breqy.a2a.client import A2AClient
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
    ToolExecutionRequestedEvent,
    ToolExecutionResultEvent,
)
from breqy.domain.ids import generate_prefixed_id


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
    ) -> None:
        self._config = config
        self._agent_dir = agent_dir
        self._client = client
        self._provider = provider
        self._skill_loader = skill_loader
        self._private_memory_runtime = private_memory_runtime
        self._tool_result_waiter = tool_result_waiter
        self._session_id = session_id
        self._cancel_requested = asyncio.Event()
        self._steer_direction: str | None = None

    async def start(self) -> None:
        await self._client.connect()
        await self._client.send_event(
            AgentLifecycleEvent(
                event_type=EventType.AGENT_CONNECTED,
                session_id=self._session_id,
                agent_id=self._config.id,
            )
        )

    async def stop(self) -> None:
        await self._client.send_event(
            AgentLifecycleEvent(
                event_type=EventType.AGENT_DISCONNECTED,
                session_id=self._session_id,
                agent_id=self._config.id,
            )
        )
        await self._client.disconnect()

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

    async def handle_work(self, event: AgentWorkRequestedEvent) -> None:
        self._cancel_requested.clear()
        assistant_message_id = generate_prefixed_id("msg")
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
        for provider_event in self._provider.stream(request):
            # Cancellation checkpoint 1: before processing each provider event
            if self._cancel_requested.is_set():
                break

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


def main() -> None:
    args = _parse_args()
    agent_dir = Path(args.agent_dir)
    config = load_agent_config(str(agent_dir))
    if args.engine_socket:
        config = config.model_copy(update={"engine_socket": args.engine_socket})
    session_id = args.session_id or "runtime"
    runtime = AgentRuntime(
        config=config,
        agent_dir=agent_dir,
        client=A2AClient(config.engine_socket),
        provider=_NullProvider(),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
        session_id=session_id,
    )

    import asyncio

    async def run() -> None:
        await runtime.start()

    asyncio.run(run())


class _NullProvider:
    provider_id = "null"
    model_id = "null"
    supports_tool_calls = False

    def stream(self, request: ProviderRequest):
        if False:
            yield request


if __name__ == "__main__":
    main()
