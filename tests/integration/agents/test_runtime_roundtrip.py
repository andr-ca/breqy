from __future__ import annotations

from pathlib import Path

import pytest

from breqy.agents.runtime import AgentRuntime
from breqy.agents.providers.base import CompletionMetadata, ProviderEvent
from breqy.a2a.envelope import Envelope
from breqy.config.loader import load_agent_config
from breqy.domain.enums import MessageRole
from breqy.domain.events import MessageSentEvent
from breqy.engine.server import EngineServer
from breqy.storage.sqlite.approval_repo import SqliteApprovalRepository
from breqy.storage.sqlite.connection import create_connection
from breqy.storage.sqlite.event_repo import SqliteEventRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository
from breqy.storage.sqlite.migrations import run_migrations
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.task_repo import SqliteTaskRepository
from breqy.storage.sqlite.tool_invocation_repo import SqliteToolInvocationRepository


class RecordingClient:
    def __init__(self) -> None:
        self.sent_events: list[object] = []

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def send_event(self, event: object) -> None:
        self.sent_events.append(event)


class ProviderDouble:
    provider_id = "claude"
    model_id = "claude-test"
    supports_tool_calls = False

    def stream(self, request):
        yield ProviderEvent(kind="text", text="Hello from runtime")
        yield ProviderEvent(
            kind="complete",
            metadata=CompletionMetadata(provider_id="claude", model_id="claude-test", exit_code=0),
        )


@pytest.mark.asyncio
async def test_runtime_roundtrip_persists_user_and_assistant_messages(
    tmp_path: Path, fake_agent_dir: Path
) -> None:
    db_path = tmp_path / "test.db"
    conn = await create_connection(str(db_path))
    await run_migrations(conn)
    session_repo = SqliteSessionRepository(conn)
    message_repo = SqliteMessageRepository(conn)
    event_repo = SqliteEventRepository(conn)
    task_repo = SqliteTaskRepository(conn)
    approval_repo = SqliteApprovalRepository(conn)
    invocation_repo = SqliteToolInvocationRepository(conn)

    server = EngineServer(
        socket_path=str(tmp_path / "engine.sock"),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        tool_invocation_repo=invocation_repo,
    )
    session = await server.session_manager.create_session("breqy")
    server.agent_registry.register("breqy", client_id="cli_agent")

    captured_work: list[Envelope] = []

    async def capture_send_to(client_id: str, envelope: Envelope) -> None:
        captured_work.append(envelope)

    server.a2a_server.send_to = capture_send_to  # type: ignore[method-assign]

    user_event = MessageSentEvent(
        session_id=session.id,
        message_id="msg_user",
        role=MessageRole.USER,
        content="Say hello",
    )
    await server._handle_envelope(Envelope.from_event(user_event), client_id="cli_tui")

    runtime_client = RecordingClient()
    runtime = AgentRuntime(
        config=load_agent_config(str(fake_agent_dir)),
        agent_dir=fake_agent_dir,
        client=runtime_client,
        provider=ProviderDouble(),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
    )

    work_event = captured_work[0].to_event()
    await runtime.handle_work(work_event)

    for event in runtime_client.sent_events:
        await server._handle_envelope(Envelope.from_event(event), client_id="cli_agent")

    messages = await message_repo.list_by_session(session.id)
    assert [message.role for message in messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert [message.content for message in messages] == ["Say hello", "Hello from runtime"]

    await conn.close()
