"""Tests for the Phase 8 agent runtime loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from breqy.agents.providers.base import CompletionMetadata, ProviderEvent, ProviderRequest
from breqy.agents.skills import SkillActivationError
from breqy.domain.events import AgentLifecycleEvent, MessageSentEvent, ToolExecutionRequestedEvent
from breqy.domain.enums import EventType, MessageRole
from breqy.domain.events import AgentWorkRequestedEvent, ToolExecutionResultEvent
from breqy.domain.models import (
    Message,
    SessionContextBundle,
    StructuredErrorPayload,
    StructuredResultPayload,
)


class FakeA2AClient:
    def __init__(self) -> None:
        self.connected = False
        self.sent_events: list[object] = []
        self._listen_envelopes: list[Any] = []

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def send_event(self, event: object) -> None:
        self.sent_events.append(event)

    def set_listen_envelopes(self, envelopes: list[Any]) -> None:
        """Set envelopes to yield from listen()."""
        self._listen_envelopes = list(envelopes)

    async def listen(self):  # noqa: ANN201
        """Async generator that yields pre-set envelopes."""
        for envelope in self._listen_envelopes:
            yield envelope


@dataclass
class FakeProvider:
    events: list[ProviderEvent]
    supports_tool_calls: bool = True
    provider_id: str = "claude"
    model_id: str = "claude-test"
    requests: list[ProviderRequest] = field(default_factory=list)

    def stream(self, request: ProviderRequest):
        self.requests.append(request)
        for event in self.events:
            yield event


class FakeToolResultWaiter:
    def __init__(self, result_event: ToolExecutionResultEvent) -> None:
        self.calls: list[str] = []
        self._result_event = result_event

    async def wait_for(self, invocation_id: str) -> ToolExecutionResultEvent:
        self.calls.append(invocation_id)
        return self._result_event


class FailingSkillLoader:
    def resolve_active(self, **_: Any):
        raise SkillActivationError(
            StructuredErrorPayload(
                code="invalid_skill_activation",
                message="skill rejected",
                details={"invalid_skill_ids": ["bad-skill"]},
            )
        )


def _work_event(*, active_skill_ids: list[str] | None = None) -> AgentWorkRequestedEvent:
    return AgentWorkRequestedEvent(
        session_id="ses_123",
        agent_id="breqy",
        correlation_id="corr_turn_1",
        message_id="msg_user",
        user_message_content="Continue Phase 8.",
        session_context=SessionContextBundle(
            messages=[
                Message(
                    id="msg_prev",
                    session_id="ses_123",
                    role=MessageRole.USER,
                    content="Previous context",
                )
            ]
        ),
        active_skill_ids=active_skill_ids or [],
    )


@pytest.mark.asyncio
async def test_agent_runtime_starts_and_registers_with_engine(fake_agent_dir: Path) -> None:
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.loader import load_agent_config

    config = load_agent_config(str(fake_agent_dir))
    client = FakeA2AClient()
    runtime = AgentRuntime(
        config=config,
        agent_dir=fake_agent_dir,
        client=cast(Any, client),
        provider=cast(Any, FakeProvider(events=[])),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
    )

    await runtime.start()

    assert client.connected is True
    connected_event = cast(AgentLifecycleEvent, client.sent_events[0])
    assert connected_event.event_type == EventType.AGENT_CONNECTED


@pytest.mark.asyncio
async def test_agent_runtime_uses_session_id_in_lifecycle_events(fake_agent_dir: Path) -> None:
    """AgentRuntime sends the provided session_id in AGENT_CONNECTED and AGENT_DISCONNECTED events."""
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.loader import load_agent_config

    config = load_agent_config(str(fake_agent_dir))
    client = FakeA2AClient()
    runtime = AgentRuntime(
        config=config,
        agent_dir=fake_agent_dir,
        client=cast(Any, client),
        provider=cast(Any, FakeProvider(events=[])),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
        session_id="ses_real_session",
    )

    await runtime.start()

    connected_event = cast(AgentLifecycleEvent, client.sent_events[0])
    assert connected_event.event_type == EventType.AGENT_CONNECTED
    assert connected_event.session_id == "ses_real_session"
    assert connected_event.agent_id == "breqy"

    await runtime.stop()

    disconnected_event = cast(AgentLifecycleEvent, client.sent_events[2])
    assert disconnected_event.event_type == EventType.AGENT_DISCONNECTED
    assert disconnected_event.session_id == "ses_real_session"


@pytest.mark.asyncio
async def test_agent_runtime_defaults_session_id_to_runtime(fake_agent_dir: Path) -> None:
    """AgentRuntime defaults session_id to 'runtime' for backward compatibility."""
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.loader import load_agent_config

    config = load_agent_config(str(fake_agent_dir))
    client = FakeA2AClient()
    runtime = AgentRuntime(
        config=config,
        agent_dir=fake_agent_dir,
        client=cast(Any, client),
        provider=cast(Any, FakeProvider(events=[])),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
    )

    await runtime.start()

    connected_event = cast(AgentLifecycleEvent, client.sent_events[0])
    assert connected_event.session_id == "runtime"


def test_parse_args_accepts_session_id() -> None:
    """_parse_args() accepts --session-id argument."""
    from breqy.agents.runtime import _parse_args
    import sys
    from unittest.mock import patch as mock_patch

    with mock_patch.object(
        sys,
        "argv",
        [
            "runtime",
            "--agent-dir",
            "agents/breqy",
            "--engine-socket",
            "/tmp/test.sock",
            "--session-id",
            "ses_xyz",
        ],
    ):
        args = _parse_args()
        assert args.session_id == "ses_xyz"


def test_parse_args_session_id_defaults_to_none() -> None:
    """_parse_args() defaults --session-id to None when not provided."""
    from breqy.agents.runtime import _parse_args
    import sys
    from unittest.mock import patch as mock_patch

    with mock_patch.object(
        sys,
        "argv",
        ["runtime", "--agent-dir", "agents/breqy"],
    ):
        args = _parse_args()
        assert args.session_id is None


@pytest.mark.asyncio
async def test_agent_runtime_run_listens_and_dispatches_work(fake_agent_dir: Path) -> None:
    """AgentRuntime.run() starts, listens for events, dispatches work, and stops on disconnect."""
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.loader import load_agent_config
    from breqy.a2a.envelope import Envelope

    config = load_agent_config(str(fake_agent_dir))
    client = FakeA2AClient()

    work_event = _work_event()
    client.set_listen_envelopes([Envelope.from_event(work_event)])

    runtime = AgentRuntime(
        config=config,
        agent_dir=fake_agent_dir,
        client=cast(Any, client),
        provider=cast(
            Any,
            FakeProvider(
                events=[
                    ProviderEvent(kind="text", text="Done"),
                ]
            ),
        ),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
        session_id="ses_test",
    )

    await runtime.run()

    # Should have connected, sent AGENT_CONNECTED, processed work, sent AGENT_DISCONNECTED
    event_types = [getattr(e, "event_type", None) for e in client.sent_events]
    assert EventType.AGENT_CONNECTED in event_types
    assert EventType.AGENT_DISCONNECTED in event_types
    assert EventType.MESSAGE_SENT in event_types
    assert client.connected is False  # stop() disconnects


@pytest.mark.asyncio
async def test_agent_runtime_run_dispatches_control_events(fake_agent_dir: Path) -> None:
    """AgentRuntime.run() dispatches ControlEvent to handle_control."""
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.loader import load_agent_config
    from breqy.a2a.envelope import Envelope
    from breqy.domain.events import ControlEvent

    config = load_agent_config(str(fake_agent_dir))
    client = FakeA2AClient()

    control_event = ControlEvent(
        event_type=EventType.CONTROL_STOP,
        session_id="ses_test",
    )
    client.set_listen_envelopes([Envelope.from_event(control_event)])

    runtime = AgentRuntime(
        config=config,
        agent_dir=fake_agent_dir,
        client=cast(Any, client),
        provider=cast(Any, FakeProvider(events=[])),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
        session_id="ses_test",
    )

    await runtime.run()

    # Control event should have set the cancel flag
    assert runtime.cancel_requested is True


@pytest.mark.asyncio
async def test_agent_runtime_rejects_invalid_active_skill_ids_with_structured_error(
    fake_agent_dir: Path,
) -> None:
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.loader import load_agent_config

    config = load_agent_config(str(fake_agent_dir))
    client = FakeA2AClient()
    runtime = AgentRuntime(
        config=config,
        agent_dir=fake_agent_dir,
        client=cast(Any, client),
        provider=cast(Any, FakeProvider(events=[])),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
    )

    await runtime.handle_work(_work_event(active_skill_ids=["unknown-skill"]))

    failure_event = cast(ToolExecutionResultEvent, client.sent_events[0])
    assert failure_event.event_type == EventType.TOOL_EXECUTION_RESULT
    assert failure_event.failure_payload is not None
    assert failure_event.failure_payload.code == "invalid_skill_activation"


@pytest.mark.asyncio
async def test_agent_runtime_emits_chunks_requests_tools_and_final_message(
    fake_agent_dir: Path,
) -> None:
    from breqy.agents.runtime import AgentRuntime
    from breqy.agents.providers.base import ToolCallDelta
    from breqy.config.loader import load_agent_config

    config = load_agent_config(str(fake_agent_dir))
    client = FakeA2AClient()

    # Round 1: text + tool_call + text in one stream
    # Round 2: empty (LLM has nothing more to say after tool result)
    round1 = [
        ProviderEvent(kind="text", text="Hello"),
        ProviderEvent(
            kind="tool_call",
            tool_call=ToolCallDelta(
                call_id="inv_tool", tool_name="shell", arguments_chunk='{"command":"pwd"}'
            ),
        ),
        ProviderEvent(kind="text", text=" world"),
        ProviderEvent(
            kind="complete",
            metadata=CompletionMetadata(provider_id="claude", model_id="claude-test", exit_code=0),
        ),
    ]
    round2 = [
        ProviderEvent(
            kind="complete",
            metadata=CompletionMetadata(provider_id="claude", model_id="claude-test", exit_code=0),
        ),
    ]
    provider = MultiRoundProvider(
        rounds=[round1, round2], provider_id="claude", model_id="claude-test"
    )
    tool_waiter = FakeToolResultWaiter(
        ToolExecutionResultEvent(
            session_id="ses_123",
            agent_id="breqy",
            correlation_id="inv_tool",
            invocation_id="inv_tool",
            success_payload=StructuredResultPayload(summary="ok", content={"stdout": "/tmp"}),
        )
    )
    runtime = AgentRuntime(
        config=config,
        agent_dir=fake_agent_dir,
        client=cast(Any, client),
        provider=cast(Any, provider),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=tool_waiter,
    )

    await runtime.handle_work(_work_event())

    assert [cast(Any, event).event_type for event in client.sent_events] == [
        EventType.MESSAGE_CHUNK,
        EventType.TOOL_EXECUTION_REQUESTED,
        EventType.MESSAGE_CHUNK,
        EventType.MESSAGE_SENT,
    ]
    final_event = cast(MessageSentEvent, client.sent_events[-1])
    assert final_event.content == "Hello world"


@pytest.mark.asyncio
async def test_agent_runtime_stop_sends_disconnect_lifecycle_event(fake_agent_dir: Path) -> None:
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.loader import load_agent_config

    config = load_agent_config(str(fake_agent_dir))
    client = FakeA2AClient()
    runtime = AgentRuntime(
        config=config,
        agent_dir=fake_agent_dir,
        client=cast(Any, client),
        provider=cast(Any, FakeProvider(events=[])),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
    )

    await runtime.start()
    await runtime.stop()

    assert client.connected is False
    disconnected_event = cast(AgentLifecycleEvent, client.sent_events[-1])
    assert disconnected_event.event_type == EventType.AGENT_DISCONNECTED


@pytest.mark.asyncio
async def test_agent_runtime_uses_skill_loader_error_payload_when_validation_fails(
    fake_agent_dir: Path,
) -> None:
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.loader import load_agent_config

    config = load_agent_config(str(fake_agent_dir))
    client = FakeA2AClient()
    runtime = AgentRuntime(
        config=config,
        agent_dir=fake_agent_dir,
        client=cast(Any, client),
        provider=cast(Any, FakeProvider(events=[])),
        skill_loader=cast(Any, FailingSkillLoader()),
        private_memory_runtime=None,
        tool_result_waiter=None,
    )

    await runtime.handle_work(_work_event(active_skill_ids=["bad-skill"]))

    failure_event = cast(ToolExecutionResultEvent, client.sent_events[0])
    assert failure_event.event_type == EventType.TOOL_EXECUTION_RESULT
    assert failure_event.failure_payload is not None
    assert failure_event.failure_payload.message == "skill rejected"


def test_runtime_main_builds_runtime_and_runs_start(monkeypatch, tmp_path: Path) -> None:
    import asyncio
    import sys

    from breqy.agents import runtime as runtime_module
    from breqy.config.models import AgentConfig

    config = AgentConfig(id="breqy", name="Breqy", provider="copilot", model="gpt-4o")
    observed: dict[str, Any] = {}

    class FakeRuntime:
        def __init__(self, **kwargs: Any) -> None:
            observed["kwargs"] = kwargs

        async def run(self) -> None:
            observed["started"] = True

    def fake_run(coro: Any) -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(runtime_module, "AgentRuntime", FakeRuntime)
    monkeypatch.setattr(runtime_module, "load_agent_config", lambda path: config)
    monkeypatch.setattr(asyncio, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["runtime", "--agent-dir", str(tmp_path), "--engine-socket", "/tmp/override.sock"],
    )

    runtime_module.main()

    assert observed["started"] is True
    assert observed["kwargs"]["config"].engine_socket == "/tmp/override.sock"
    assert observed["kwargs"]["agent_dir"] == tmp_path


def test_runtime_null_provider_stream_is_empty() -> None:
    from breqy.agents.runtime import _NullProvider

    assert list(_NullProvider().stream(ProviderRequest(prompt="hi", work_dir=Path(".")))) == []


def test_runtime_main_builds_real_provider_from_config(monkeypatch, tmp_path: Path) -> None:
    """main() should call _build_provider() to construct a real ModelProvider,
    not use _NullProvider directly."""
    import asyncio
    import sys

    from breqy.agents import runtime as runtime_module
    from breqy.agents.runtime import _NullProvider
    from breqy.config.models import AgentConfig

    config = AgentConfig(id="breqy", name="Breqy", provider="copilot", model="gpt-4o")
    observed: dict[str, Any] = {}

    class FakeRuntime:
        def __init__(self, **kwargs: Any) -> None:
            observed["kwargs"] = kwargs

        async def run(self) -> None:
            observed["started"] = True

    # Track _build_provider calls
    build_provider_calls: list[AgentConfig] = []

    def fake_build_provider(cfg: AgentConfig, credential_store=None):
        build_provider_calls.append(cfg)
        return FakeProvider(events=[])

    def fake_run(coro: Any) -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(runtime_module, "AgentRuntime", FakeRuntime)
    monkeypatch.setattr(runtime_module, "load_agent_config", lambda path: config)
    monkeypatch.setattr(runtime_module, "_build_provider", fake_build_provider)
    monkeypatch.setattr(asyncio, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["runtime", "--agent-dir", str(tmp_path), "--engine-socket", "/tmp/override.sock"],
    )

    runtime_module.main()

    assert observed["started"] is True
    # _build_provider was called with the config
    assert len(build_provider_calls) == 1
    assert build_provider_calls[0].provider == "copilot"
    # The provider passed to AgentRuntime is a real one, not _NullProvider
    provider = observed["kwargs"]["provider"]
    assert not isinstance(provider, _NullProvider), (
        "main() should build a real ModelProvider, not _NullProvider"
    )


def test_build_provider_returns_real_provider_when_available(monkeypatch) -> None:
    """_build_provider() returns a real ModelProvider when construction succeeds."""
    from breqy.agents.runtime import _build_provider, _NullProvider
    from breqy.config.models import AgentConfig

    config = AgentConfig(id="breqy", name="Breqy", provider="copilot", model="gpt-4o")

    fake_provider = FakeProvider(events=[])

    def mock_build_model_providers(*, credential_store, model_by_provider):
        assert "copilot" in model_by_provider
        assert model_by_provider["copilot"] == "gpt-4o"
        return {"copilot": fake_provider}

    monkeypatch.setattr(
        "breqy.agents.providers.adapters.build_model_providers",
        mock_build_model_providers,
    )
    # Monkeypatch KeyringSecretProvider to avoid real keyring dependency
    monkeypatch.setattr(
        "breqy.secrets.provider.KeyringSecretProvider",
        lambda: MagicMock(),
    )

    result = _build_provider(config)
    assert result is fake_provider
    assert not isinstance(result, _NullProvider)


def test_build_provider_falls_back_to_null_on_error(monkeypatch) -> None:
    """_build_provider() returns _NullProvider when construction fails."""
    from breqy.agents.runtime import _build_provider, _NullProvider
    from breqy.config.models import AgentConfig

    config = AgentConfig(id="breqy", name="Breqy", provider="copilot", model="gpt-4o")

    def mock_build_raises(*, credential_store, model_by_provider):
        raise RuntimeError("keyring not available")

    monkeypatch.setattr(
        "breqy.agents.providers.adapters.build_model_providers",
        mock_build_raises,
    )

    result = _build_provider(config)
    assert isinstance(result, _NullProvider)


def test_build_provider_falls_back_to_file_secret_when_keyring_fails(monkeypatch) -> None:
    """_build_provider() tries FileSecretProvider when KeyringSecretProvider fails."""
    from breqy.agents.runtime import _build_provider, _NullProvider
    from breqy.config.models import AgentConfig
    from breqy.secrets.provider import FileSecretProvider

    config = AgentConfig(id="breqy", name="Breqy", provider="copilot", model="gpt-4o")

    fake_provider = FakeProvider(events=[])
    captured_stores = []

    def mock_build_model_providers(*, credential_store, model_by_provider):
        captured_stores.append(credential_store)
        return {"copilot": fake_provider}

    # Make KeyringSecretProvider raise on construction
    def keyring_raises():
        raise RuntimeError("keyring not available")

    monkeypatch.setattr(
        "breqy.secrets.provider.KeyringSecretProvider",
        keyring_raises,
    )
    monkeypatch.setattr(
        "breqy.agents.providers.adapters.build_model_providers",
        mock_build_model_providers,
    )

    result = _build_provider(config)
    assert result is fake_provider
    assert not isinstance(result, _NullProvider)
    # The credential store should be backed by the file-based provider
    assert len(captured_stores) == 1


def test_runtime_module_entrypoint_invokes_main(monkeypatch) -> None:
    import asyncio
    import sys
    import runpy

    from breqy.a2a.client import A2AClient
    from breqy.config.models import AgentConfig

    observed: dict[str, Any] = {"sent": []}

    def fake_run(coro: Any) -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(
        "breqy.config.loader.load_agent_config",
        lambda path: AgentConfig(id="breqy", name="Breqy", provider="copilot", model="gpt-4o"),
    )
    monkeypatch.setattr(asyncio, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["runtime.py", "--agent-dir", "/tmp/fake-agent"])

    async def fake_connect(self) -> None:
        observed["connected"] = True

    async def fake_send_event(self, event: object) -> None:
        observed["sent"].append(event)

    async def fake_disconnect(self) -> None:
        observed["disconnected"] = True

    async def fake_listen(self):
        return
        yield  # make it an async generator that yields nothing

    monkeypatch.setattr(A2AClient, "connect", fake_connect)
    monkeypatch.setattr(A2AClient, "send_event", fake_send_event)
    monkeypatch.setattr(A2AClient, "disconnect", fake_disconnect)
    monkeypatch.setattr(A2AClient, "listen", fake_listen)

    globals_after = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "breqy" / "agents" / "runtime.py"),
        run_name="__main__",
    )

    assert observed["connected"] is True
    assert observed["sent"]
    assert globals_after["__name__"] == "__main__"


# --------------------------------------------------------------------------- #
# Helpers for cooperative cancellation tests
# --------------------------------------------------------------------------- #


def _build_runtime(
    *,
    provider: Any = None,
    skill_loader: Any = None,
    tool_result_waiter: Any = None,
    client: Any = None,
) -> tuple[Any, FakeA2AClient]:
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.models import AgentConfig

    config = AgentConfig(id="breqy", name="Breqy", provider="copilot", model="gpt-4o")
    fake_client = client or FakeA2AClient()
    runtime = AgentRuntime(
        config=config,
        agent_dir=Path("."),
        client=cast(Any, fake_client),
        provider=cast(Any, provider or FakeProvider(events=[])),
        skill_loader=cast(Any, skill_loader) if skill_loader else None,
        private_memory_runtime=None,
        tool_result_waiter=tool_result_waiter,
    )
    return runtime, fake_client


class CancellingProvider:
    """Provider that sets cancel on the runtime after emitting N events."""

    def __init__(
        self,
        runtime: Any,
        events: list[ProviderEvent],
        cancel_after: int = 1,
    ) -> None:
        self.supports_tool_calls = True
        self.provider_id = "test"
        self.model_id = "test"
        self._events = events
        self._runtime = runtime
        self._cancel_after = cancel_after

    def stream(self, request: ProviderRequest):  # noqa: ANN201
        for i, event in enumerate(self._events):
            if i >= self._cancel_after:
                self._runtime._cancel_requested.set()
            yield event


class CancellingToolWaiter:
    """Waiter that sets cancel on the runtime when wait_for is called."""

    def __init__(self, runtime: Any, result_event: ToolExecutionResultEvent) -> None:
        self._runtime = runtime
        self._result_event = result_event

    async def wait_for(self, invocation_id: str) -> ToolExecutionResultEvent:
        self._runtime._cancel_requested.set()
        return self._result_event


# --------------------------------------------------------------------------- #
# Cooperative cancellation tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_handle_control_stop_sets_cancel_flag() -> None:
    from breqy.domain.events import ControlEvent

    runtime, _ = _build_runtime()
    runtime.handle_control(ControlEvent(event_type=EventType.CONTROL_STOP, session_id="ses_1"))
    assert runtime.cancel_requested is True


@pytest.mark.asyncio
async def test_handle_control_steer_sets_steer_direction() -> None:
    from breqy.domain.events import ControlEvent

    runtime, _ = _build_runtime()
    runtime.handle_control(
        ControlEvent(
            event_type=EventType.CONTROL_STEER,
            session_id="ses_1",
            new_direction="focus on tests",
        )
    )
    assert runtime.steer_direction == "focus on tests"
    assert runtime.cancel_requested is False


@pytest.mark.asyncio
async def test_handle_control_stop_and_steer_sets_both() -> None:
    from breqy.domain.events import ControlEvent

    runtime, _ = _build_runtime()
    runtime.handle_control(
        ControlEvent(
            event_type=EventType.CONTROL_STOP_AND_STEER,
            session_id="ses_1",
            new_direction="new plan",
        )
    )
    assert runtime.cancel_requested is True
    assert runtime.steer_direction == "new plan"


@pytest.mark.asyncio
async def test_handle_control_circuit_break_sets_cancel() -> None:
    from breqy.domain.events import ControlEvent

    runtime, _ = _build_runtime()
    runtime.handle_control(
        ControlEvent(event_type=EventType.CONTROL_CIRCUIT_BREAK, session_id="ses_1")
    )
    assert runtime.cancel_requested is True


@pytest.mark.asyncio
async def test_clear_steer_resets_direction() -> None:
    from breqy.domain.events import ControlEvent

    runtime, _ = _build_runtime()
    runtime.handle_control(
        ControlEvent(
            event_type=EventType.CONTROL_STEER,
            session_id="ses_1",
            new_direction="focus on tests",
        )
    )
    assert runtime.steer_direction == "focus on tests"
    runtime.clear_steer()
    assert runtime.steer_direction is None


@pytest.mark.asyncio
async def test_handle_work_resets_cancel_flag() -> None:
    from breqy.domain.events import ControlEvent

    runtime, _ = _build_runtime(provider=FakeProvider(events=[]))
    # Set the cancel flag before calling handle_work
    runtime.handle_control(ControlEvent(event_type=EventType.CONTROL_STOP, session_id="ses_1"))
    assert runtime.cancel_requested is True

    await runtime.handle_work(_work_event())

    # handle_work resets the cancel flag at the start
    assert runtime.cancel_requested is False


@pytest.mark.asyncio
async def test_handle_work_aborts_on_cancel_before_text() -> None:
    events = [
        ProviderEvent(kind="text", text="Hello"),
        ProviderEvent(kind="text", text=" World"),
        ProviderEvent(kind="text", text=" Extra"),
    ]
    # Build runtime first with a dummy provider, then swap to cancelling
    runtime, client = _build_runtime()
    cancelling_provider = CancellingProvider(runtime, events, cancel_after=1)
    runtime._provider = cancelling_provider  # type: ignore[attr-defined]

    await runtime.handle_work(_work_event())

    # Only 1 chunk event should have been emitted (the first text before cancel)
    chunk_events = [
        e for e in client.sent_events if getattr(e, "event_type", None) == EventType.MESSAGE_CHUNK
    ]
    assert len(chunk_events) == 1

    # Final message should still be emitted with partial content
    final_events = [
        e for e in client.sent_events if getattr(e, "event_type", None) == EventType.MESSAGE_SENT
    ]
    assert len(final_events) == 1
    assert cast(MessageSentEvent, final_events[0]).content == "Hello"


@pytest.mark.asyncio
async def test_handle_work_aborts_after_tool_call_on_cancel() -> None:
    from breqy.agents.providers.base import ToolCallDelta
    from breqy.domain.models import StructuredResultPayload

    events = [
        ProviderEvent(kind="text", text="Hello"),
        ProviderEvent(
            kind="tool_call",
            tool_call=ToolCallDelta(
                call_id="inv_tool", tool_name="shell", arguments_chunk='{"command":"pwd"}'
            ),
        ),
        ProviderEvent(kind="text", text=" More"),
    ]
    tool_result = ToolExecutionResultEvent(
        session_id="ses_123",
        agent_id="breqy",
        correlation_id="inv_tool",
        invocation_id="inv_tool",
        success_payload=StructuredResultPayload(summary="ok", content={"stdout": "/tmp"}),
    )
    runtime, client = _build_runtime()
    cancelling_waiter = CancellingToolWaiter(runtime, tool_result)
    runtime._tool_result_waiter = cancelling_waiter  # type: ignore[attr-defined]
    runtime._provider = FakeProvider(events=events)  # type: ignore[attr-defined]

    await runtime.handle_work(_work_event())

    # Final message should only contain "Hello" (before the tool call)
    final_events = [
        e for e in client.sent_events if getattr(e, "event_type", None) == EventType.MESSAGE_SENT
    ]
    assert len(final_events) == 1
    assert cast(MessageSentEvent, final_events[0]).content == "Hello"

    # The second text " More" should NOT appear in any chunk
    chunk_events = [
        e for e in client.sent_events if getattr(e, "event_type", None) == EventType.MESSAGE_CHUNK
    ]
    chunk_texts = [cast(Any, e).chunk for e in chunk_events]
    assert " More" not in chunk_texts


@pytest.mark.asyncio
async def test_handle_work_emits_final_message_even_when_cancelled() -> None:
    events = [
        ProviderEvent(kind="text", text="Hello"),
        ProviderEvent(kind="text", text=" World"),
    ]
    # cancel_after=0 means cancel is set before the first event is yielded
    runtime, client = _build_runtime()
    cancelling_provider = CancellingProvider(runtime, events, cancel_after=0)
    runtime._provider = cancelling_provider  # type: ignore[attr-defined]

    await runtime.handle_work(_work_event())

    # Should still emit a MessageSentEvent even though cancelled immediately
    final_events = [
        e for e in client.sent_events if getattr(e, "event_type", None) == EventType.MESSAGE_SENT
    ]
    assert len(final_events) == 1
    # Content should be empty since we cancelled before processing any text
    assert cast(MessageSentEvent, final_events[0]).content == ""


# ============================================================================ #
# structlog migration
# ============================================================================ #


def test_runtime_has_structlog_logger():
    """Agent runtime module should have a structlog logger."""
    import logging as _logging
    from breqy.agents import runtime

    assert hasattr(runtime, "logger")
    assert not isinstance(runtime.logger, _logging.Logger)


def test_runtime_imports_setup_logging():
    """Agent runtime should import setup_logging for subprocess init."""
    from breqy.agents import runtime

    assert hasattr(runtime, "setup_logging")


def test_runtime_imports_default_log_file():
    """Agent runtime should import default_log_file helper."""
    from breqy.agents import runtime

    assert hasattr(runtime, "default_log_file")


# ============================================================================ #
# notice event kind
# ============================================================================ #


def test_provider_event_accepts_notice_kind():
    """ProviderEvent should accept kind='notice' for immediate display messages."""
    event = ProviderEvent(kind="notice", text="auth instructions")
    assert event.kind == "notice"
    assert event.text == "auth instructions"


@pytest.mark.asyncio
async def test_handle_work_sends_notice_as_complete_message():
    """When the provider yields a notice event, handle_work should send it
    as a complete MessageSentEvent immediately (not just a chunk), so the
    TUI renders it without waiting for stream completion.

    Subsequent text events should use a NEW message_id.
    """
    from breqy.domain.events import MessageChunkEvent

    events = [
        ProviderEvent(kind="notice", text="Please authenticate at https://example.com"),
        ProviderEvent(kind="text", text="Hello"),
        ProviderEvent(kind="text", text=" world"),
    ]
    runtime, client = _build_runtime(provider=FakeProvider(events=events))

    await runtime.handle_work(_work_event())

    # Collect MessageSentEvents (complete messages)
    sent_messages = [
        cast(MessageSentEvent, e)
        for e in client.sent_events
        if getattr(e, "event_type", None) == EventType.MESSAGE_SENT
    ]
    # Should have TWO complete messages: the notice AND the final streamed message
    assert len(sent_messages) == 2

    notice_msg = sent_messages[0]
    final_msg = sent_messages[1]

    # Notice should contain the auth text
    assert "authenticate" in notice_msg.content
    assert notice_msg.role == MessageRole.SYSTEM

    # Final message should contain the streamed text
    assert final_msg.content == "Hello world"
    assert final_msg.role == MessageRole.ASSISTANT

    # They should have DIFFERENT message IDs
    assert notice_msg.message_id != final_msg.message_id

    # Chunks should only be for the streamed text, not the notice
    chunks = [
        cast(Any, e)
        for e in client.sent_events
        if getattr(e, "event_type", None) == EventType.MESSAGE_CHUNK
    ]
    chunk_texts = [c.chunk for c in chunks]
    assert "Please authenticate at https://example.com" not in chunk_texts
    assert "Hello" in chunk_texts
    assert " world" in chunk_texts


@dataclass
class ErroringProvider:
    """Provider that raises an exception during stream()."""

    error: Exception
    events_before_error: list[ProviderEvent] = field(default_factory=list)
    supports_tool_calls: bool = True
    provider_id: str = "copilot"
    model_id: str = "gpt-5.4-mini"
    requests: list[ProviderRequest] = field(default_factory=list)

    def stream(self, request: ProviderRequest):  # noqa: ANN201
        self.requests.append(request)
        for event in self.events_before_error:
            yield event
        raise self.error


class TestStreamErrorHandling:
    """Tests that provider stream errors are caught and reported to the TUI."""

    @pytest.mark.asyncio
    async def test_provider_error_sends_error_message_to_tui(self) -> None:
        """When provider.stream() raises, an error MessageSentEvent should be emitted."""
        from breqy.agents.providers.copilot_client import CopilotApiError

        provider = ErroringProvider(error=CopilotApiError(400, "model not available"))
        runtime, client = _build_runtime(provider=provider)
        await runtime.handle_work(_work_event())

        sent_types = [cast(Any, e).event_type for e in client.sent_events]
        assert EventType.MESSAGE_SENT in sent_types
        final = cast(MessageSentEvent, client.sent_events[-1])
        assert final.role == MessageRole.SYSTEM
        assert "error" in final.content.lower() or "400" in final.content

    @pytest.mark.asyncio
    async def test_provider_error_preserves_partial_content(self) -> None:
        """If some text was streamed before the error, chunks should still be emitted."""
        from breqy.agents.providers.copilot_client import CopilotApiError

        provider = ErroringProvider(
            error=CopilotApiError(500, "Internal Server Error"),
            events_before_error=[
                ProviderEvent(kind="text", text="Hello"),
            ],
        )
        runtime, client = _build_runtime(provider=provider)
        await runtime.handle_work(_work_event())

        sent_types = [cast(Any, e).event_type for e in client.sent_events]
        # Should have: MESSAGE_CHUNK (for "Hello") + MESSAGE_SENT (error)
        assert EventType.MESSAGE_CHUNK in sent_types
        assert EventType.MESSAGE_SENT in sent_types

    @pytest.mark.asyncio
    async def test_provider_generic_exception_sends_error_message(self) -> None:
        """Non-API exceptions (e.g. ConnectionError) should also produce error messages."""
        provider = ErroringProvider(error=ConnectionError("connection refused"))
        runtime, client = _build_runtime(provider=provider)
        await runtime.handle_work(_work_event())

        sent_types = [cast(Any, e).event_type for e in client.sent_events]
        assert EventType.MESSAGE_SENT in sent_types
        final = cast(MessageSentEvent, client.sent_events[-1])
        assert final.role == MessageRole.SYSTEM
        assert "error" in final.content.lower() or "connection" in final.content.lower()

    @pytest.mark.asyncio
    async def test_provider_error_does_not_crash_runtime(self) -> None:
        """After a stream error, the runtime should remain operational (not raise)."""
        from breqy.agents.providers.copilot_client import CopilotApiError

        provider = ErroringProvider(error=CopilotApiError(400, "bad request"))
        runtime, client = _build_runtime(provider=provider)

        # Should not raise — error is caught and reported
        await runtime.handle_work(_work_event())

        # Runtime should be able to handle another work event
        provider2 = FakeProvider(
            events=[
                ProviderEvent(kind="text", text="recovered"),
                ProviderEvent(
                    kind="complete",
                    metadata=CompletionMetadata(
                        provider_id="copilot",
                        model_id="gpt-4o",
                        exit_code=0,
                    ),
                ),
            ]
        )
        runtime._provider = cast(Any, provider2)
        await runtime.handle_work(_work_event())

        # The second call should produce normal events
        final = cast(MessageSentEvent, client.sent_events[-1])
        assert final.content == "recovered"


# --------------------------------------------------------------------------- #
# Tool wiring: available_tools → ProviderRequest.tools
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_handle_work_passes_available_tools_to_provider_request() -> None:
    """When the work event carries available_tools, they are forwarded to ProviderRequest.tools."""
    from breqy.agents.providers.base import ToolDefinition

    shell_def = ToolDefinition(
        name="shell",
        description="Execute shell commands",
        input_schema={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    )
    fs_def = ToolDefinition(
        name="filesystem",
        description="Filesystem operations",
        input_schema={
            "type": "object",
            "properties": {"operation": {"type": "string"}},
            "required": ["operation"],
        },
    )

    events = [
        ProviderEvent(
            kind="complete",
            metadata=CompletionMetadata(
                provider_id="copilot",
                model_id="gpt-4o",
                exit_code=0,
            ),
        ),
    ]
    provider = FakeProvider(events=events)
    runtime, _client = _build_runtime(provider=provider)

    work = AgentWorkRequestedEvent(
        session_id="ses_123",
        agent_id="breqy",
        correlation_id="corr_1",
        message_id="msg_user",
        user_message_content="run ls",
        session_context=SessionContextBundle(messages=[]),
        available_tools=[shell_def, fs_def],
    )

    await runtime.handle_work(work)

    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert len(request.tools) == 2
    tool_names = {t.name for t in request.tools}
    assert tool_names == {"shell", "filesystem"}


@pytest.mark.asyncio
async def test_handle_work_filters_tools_by_agent_tool_permissions() -> None:
    """Runtime filters available_tools by config.tool_permissions before sending to provider."""
    from breqy.agents.providers.base import ToolDefinition
    from breqy.config.models import AgentConfig

    shell_def = ToolDefinition(
        name="shell",
        description="Execute shell commands",
        input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
    )
    fs_def = ToolDefinition(
        name="filesystem",
        description="Filesystem operations",
        input_schema={"type": "object", "properties": {"operation": {"type": "string"}}},
    )
    memory_def = ToolDefinition(
        name="memory",
        description="Memory search",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
    )

    events = [
        ProviderEvent(
            kind="complete",
            metadata=CompletionMetadata(
                provider_id="copilot",
                model_id="gpt-4o",
                exit_code=0,
            ),
        ),
    ]
    provider = FakeProvider(events=events)

    # Config that only allows "shell" and "fs"
    config = AgentConfig(
        id="breqy",
        name="Breqy",
        provider="copilot",
        model="gpt-4o",
        tool_permissions=["shell", "filesystem"],
    )
    from breqy.agents.runtime import AgentRuntime

    runtime = AgentRuntime(
        config=config,
        agent_dir=Path("."),
        client=cast(Any, FakeA2AClient()),
        provider=cast(Any, provider),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
    )

    work = AgentWorkRequestedEvent(
        session_id="ses_123",
        agent_id="breqy",
        correlation_id="corr_1",
        message_id="msg_user",
        user_message_content="search memory",
        session_context=SessionContextBundle(messages=[]),
        available_tools=[shell_def, fs_def, memory_def],
    )

    await runtime.handle_work(work)

    assert len(provider.requests) == 1
    request = provider.requests[0]
    # Only shell and filesystem should be passed, not memory
    tool_names = {t.name for t in request.tools}
    assert tool_names == {"shell", "filesystem"}


@pytest.mark.asyncio
async def test_handle_work_empty_available_tools_means_no_tools_in_request() -> None:
    """When no tools are provided in work event, ProviderRequest.tools stays empty."""
    events = [
        ProviderEvent(
            kind="complete",
            metadata=CompletionMetadata(
                provider_id="copilot",
                model_id="gpt-4o",
                exit_code=0,
            ),
        ),
    ]
    provider = FakeProvider(events=events)
    runtime, _client = _build_runtime(provider=provider)

    work = _work_event()  # no available_tools

    await runtime.handle_work(work)

    assert len(provider.requests) == 1
    assert provider.requests[0].tools == []


@pytest.mark.asyncio
async def test_handle_work_passes_persona_content_in_extra_env() -> None:
    """When config has persona_content, it is passed as BREQY_PERSONA in extra_env."""
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.models import AgentConfig

    events = [
        ProviderEvent(
            kind="complete",
            metadata=CompletionMetadata(
                provider_id="copilot",
                model_id="gpt-4o",
                exit_code=0,
            ),
        ),
    ]
    provider = FakeProvider(events=events)
    config = AgentConfig(
        id="breqy",
        name="Breqy",
        provider="copilot",
        model="gpt-4o",
        persona_content="You are Breqy, a helpful coding assistant.",
    )
    runtime = AgentRuntime(
        config=config,
        agent_dir=Path("."),
        client=cast(Any, FakeA2AClient()),
        provider=cast(Any, provider),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
    )

    await runtime.handle_work(_work_event())

    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.extra_env.get("BREQY_PERSONA") == "You are Breqy, a helpful coding assistant."


# --------------------------------------------------------------------------- #
# Multi-turn tool execution loop (Bug 3)
# --------------------------------------------------------------------------- #


@dataclass
class MultiRoundProvider:
    """Provider that serves different event sequences on successive stream() calls."""

    rounds: list[list[ProviderEvent]]
    supports_tool_calls: bool = True
    provider_id: str = "test"
    model_id: str = "test-model"
    requests: list[ProviderRequest] = field(default_factory=list)
    call_count: int = 0

    def stream(self, request: ProviderRequest):  # noqa: ANN201
        self.requests.append(request)
        idx = min(self.call_count, len(self.rounds) - 1)
        self.call_count += 1
        yield from self.rounds[idx]


def _tool_call_event(
    call_id: str = "inv_1",
    tool_name: str = "shell",
    arguments: str = '{"command": "ls"}',
) -> ProviderEvent:
    from breqy.agents.providers.base import ToolCallDelta

    return ProviderEvent(
        kind="tool_call",
        tool_call=ToolCallDelta(
            call_id=call_id,
            tool_name=tool_name,
            arguments_chunk=arguments,
        ),
    )


def _complete_event() -> ProviderEvent:
    return ProviderEvent(
        kind="complete",
        metadata=CompletionMetadata(
            provider_id="test",
            model_id="test-model",
            exit_code=0,
        ),
    )


def _tool_result_event(
    call_id: str = "inv_1",
    output: str = "file1  file2",
) -> ToolExecutionResultEvent:
    return ToolExecutionResultEvent(
        session_id="ses_123",
        agent_id="breqy",
        correlation_id=call_id,
        invocation_id=call_id,
        success_payload=StructuredResultPayload(
            summary=output,
            content={"output": output},
        ),
    )


class TestToolResultBroker:
    """ToolResultBroker mediates tool result delivery between run() and handle_work()."""

    @pytest.mark.asyncio
    async def test_wait_for_resolves_when_result_delivered(self) -> None:
        """wait_for() should return the delivered result for the matching invocation_id."""
        import asyncio
        from breqy.agents.runtime import ToolResultBroker

        broker = ToolResultBroker()
        result = _tool_result_event("inv_abc")

        async def deliver_after_yield():
            await asyncio.sleep(0)  # yield control, let wait_for register
            broker.deliver(result)

        asyncio.create_task(deliver_after_yield())
        received = await broker.wait_for("inv_abc")

        assert received is result

    @pytest.mark.asyncio
    async def test_deliver_unknown_invocation_id_is_noop(self) -> None:
        """Delivering a result for an unknown invocation_id must not raise."""
        from breqy.agents.runtime import ToolResultBroker

        broker = ToolResultBroker()
        # Should not raise even when nobody is waiting for "unknown_id"
        broker.deliver(_tool_result_event("unknown_id"))

    @pytest.mark.asyncio
    async def test_multiple_pending_futures_resolved_independently(self) -> None:
        """Multiple concurrent wait_for calls must each resolve to their own result."""
        import asyncio
        from breqy.agents.runtime import ToolResultBroker

        broker = ToolResultBroker()
        result_1 = _tool_result_event("inv_1", "output_1")
        result_2 = _tool_result_event("inv_2", "output_2")

        async def deliver_both():
            await asyncio.sleep(0)
            broker.deliver(result_1)
            broker.deliver(result_2)

        asyncio.create_task(deliver_both())
        r1, r2 = await asyncio.gather(
            broker.wait_for("inv_1"),
            broker.wait_for("inv_2"),
        )
        assert r1 is result_1
        assert r2 is result_2


class TestMultiTurnToolLoop:
    """handle_work() must loop: stream → tool_call → execute → re-prompt → text."""

    @pytest.mark.asyncio
    async def test_tool_call_triggers_second_provider_round(self) -> None:
        """When LLM returns tool_call, handle_work calls provider a second time."""
        round1 = [_tool_call_event("inv_1"), _complete_event()]
        round2 = [ProviderEvent(kind="text", text="Done."), _complete_event()]

        provider = MultiRoundProvider(rounds=[round1, round2])
        waiter = FakeToolResultWaiter(_tool_result_event("inv_1"))
        runtime, client = _build_runtime(provider=provider, tool_result_waiter=waiter)

        await runtime.handle_work(_work_event())

        assert provider.call_count == 2, "Provider should be called twice (tool round + text round)"

    @pytest.mark.asyncio
    async def test_second_round_receives_conversation_history_with_tool_result(self) -> None:
        """The second provider call must include conversation_history containing the tool result."""
        round1 = [_tool_call_event("inv_1", "shell", '{"command": "ls"}'), _complete_event()]
        round2 = [ProviderEvent(kind="text", text="Files: foo"), _complete_event()]

        provider = MultiRoundProvider(rounds=[round1, round2])
        waiter = FakeToolResultWaiter(_tool_result_event("inv_1", output="foo  bar"))
        runtime, client = _build_runtime(provider=provider, tool_result_waiter=waiter)

        await runtime.handle_work(_work_event())

        assert provider.call_count == 2
        second_request = provider.requests[1]
        assert second_request.conversation_history is not None, (
            "Second round must use conversation_history"
        )
        # Tool result must appear as a tool-role message
        tool_msg = next(
            (m for m in second_request.conversation_history if m.get("role") == "tool"),
            None,
        )
        assert tool_msg is not None, "conversation_history must contain a tool-role message"
        assert tool_msg["tool_call_id"] == "inv_1"
        assert "foo  bar" in tool_msg["content"]

    @pytest.mark.asyncio
    async def test_final_message_contains_text_from_second_round(self) -> None:
        """MessageSentEvent content must include text from the LLM's post-tool response."""
        round1 = [_tool_call_event("inv_1"), _complete_event()]
        round2 = [ProviderEvent(kind="text", text="All done."), _complete_event()]

        provider = MultiRoundProvider(rounds=[round1, round2])
        waiter = FakeToolResultWaiter(_tool_result_event("inv_1"))
        runtime, client = _build_runtime(provider=provider, tool_result_waiter=waiter)

        await runtime.handle_work(_work_event())

        final_msg = next(
            (
                e
                for e in reversed(client.sent_events)
                if isinstance(e, MessageSentEvent) and e.role == MessageRole.ASSISTANT
            ),
            None,
        )
        assert final_msg is not None
        assert final_msg.content == "All done."

    @pytest.mark.asyncio
    async def test_no_tool_result_waiter_still_sends_tool_request_but_no_second_round(self) -> None:
        """When tool_result_waiter is None, tool request is sent but provider is not called again."""
        round1 = [_tool_call_event("inv_1"), _complete_event()]

        provider = MultiRoundProvider(rounds=[round1])
        runtime, client = _build_runtime(provider=provider, tool_result_waiter=None)

        await runtime.handle_work(_work_event())

        # Tool request must still be sent to the engine
        tool_req = next(
            (e for e in client.sent_events if isinstance(e, ToolExecutionRequestedEvent)),
            None,
        )
        assert tool_req is not None, "ToolExecutionRequestedEvent must be sent even without waiter"
        assert tool_req.tool_name == "shell"

        # But provider is only called once (no second round)
        assert provider.call_count == 1

    @pytest.mark.asyncio
    async def test_max_tool_rounds_guard_prevents_infinite_loop(self) -> None:
        """If the LLM keeps returning tool calls indefinitely, the loop must stop after 10 rounds."""
        # Every round returns a tool call
        tool_only_round = [_tool_call_event(f"inv_{i}") for i in range(1)] + [_complete_event()]

        provider = MultiRoundProvider(rounds=[tool_only_round] * 20)
        # Waiter always returns a result so the loop can continue
        waiter = FakeToolResultWaiter(_tool_result_event("inv_0"))
        runtime, client = _build_runtime(provider=provider, tool_result_waiter=waiter)

        await runtime.handle_work(_work_event())

        # Must stop after MAX_TOOL_ROUNDS calls
        assert provider.call_count <= 10, (
            f"Expected at most 10 provider calls; got {provider.call_count}"
        )


class TestRunDeliverToolResults:
    """run() must route ToolExecutionResultEvent to the broker while handle_work is running."""

    @pytest.mark.asyncio
    async def test_run_delivers_tool_result_to_broker_during_handle_work(
        self, fake_agent_dir: Path
    ) -> None:
        """run() must call broker.deliver() when ToolExecutionResultEvent arrives
        while handle_work is running as a task."""
        import asyncio
        from breqy.agents.runtime import AgentRuntime, ToolResultBroker
        from breqy.config.loader import load_agent_config

        # Provider: round 1 = tool call, round 2 = text
        tool_result = _tool_result_event("inv_run_1", "output_text")
        round1 = [_tool_call_event("inv_run_1"), _complete_event()]
        round2 = [ProviderEvent(kind="text", text="Done via run."), _complete_event()]
        provider = MultiRoundProvider(rounds=[round1, round2])

        config = load_agent_config(str(fake_agent_dir))
        client = FakeA2AClient()

        # Build the work and result envelopes for the fake listen loop
        work_event = _work_event()

        class FakeEnvelope:
            def __init__(self, event):
                self._event = event

            def to_event(self):
                return self._event

        # Deliver work, then tool result (after a small gap)
        async def _delayed_tool_result(client_ref):
            # Wait briefly so the work task starts and registers wait_for()
            await asyncio.sleep(0.01)
            client_ref._listen_envelopes.append(FakeEnvelope(tool_result))

        client.set_listen_envelopes([FakeEnvelope(work_event)])

        runtime = AgentRuntime(
            config=config,
            agent_dir=fake_agent_dir,
            client=cast(Any, client),
            provider=cast(Any, provider),
            skill_loader=None,
            private_memory_runtime=None,
            tool_result_waiter=None,  # run() will install its own broker
        )

        # Patch listen to yield work then pause, deliver tool result, end
        events_to_yield = [work_event, tool_result]
        yielded = []

        async def fake_listen():
            # yield work event first
            yield FakeEnvelope(work_event)
            # pause so the task can start and register wait_for
            await asyncio.sleep(0.02)
            # yield tool result
            yield FakeEnvelope(tool_result)
            # pause so handle_work can finish the second round
            await asyncio.sleep(0.05)

        client.listen = fake_listen

        await runtime.run()

        # Provider must have been called twice (tool round + text round)
        assert provider.call_count == 2, (
            f"Expected 2 provider calls (got {provider.call_count}): "
            "run() must deliver tool results so handle_work can complete"
        )

        # Final assistant message must have text from second round
        final_msg = next(
            (
                e
                for e in reversed(client.sent_events)
                if isinstance(e, MessageSentEvent) and e.role == MessageRole.ASSISTANT
            ),
            None,
        )
        assert final_msg is not None
        assert final_msg.content == "Done via run."


# --------------------------------------------------------------------------- #
# Session context — prior turns seeded into conversation_history
# --------------------------------------------------------------------------- #


class TestSessionContextInConversationHistory:
    """handle_work() must seed conversation_history from session_context.messages."""

    @pytest.mark.asyncio
    async def test_prior_session_messages_included_in_first_request(self) -> None:
        """When session_context has prior turns, they must appear in the first
        ProviderRequest's conversation_history so the LLM sees the full history."""
        provider = FakeProvider(events=[_complete_event_simple()])
        runtime, _ = _build_runtime(provider=provider)

        prior_user = Message(session_id="ses_123", role=MessageRole.USER, content="What is 2+2?")
        prior_assistant = Message(
            session_id="ses_123",
            role=MessageRole.ASSISTANT,
            content="4.",
            agent_id="breqy",
        )
        work = AgentWorkRequestedEvent(
            session_id="ses_123",
            agent_id="breqy",
            correlation_id="corr_1",
            message_id="msg_user",
            user_message_content="Now what is 3+3?",
            session_context=SessionContextBundle(messages=[prior_user, prior_assistant]),
        )

        await runtime.handle_work(work)

        assert len(provider.requests) == 1
        req = provider.requests[0]
        assert req.conversation_history is not None, (
            "conversation_history must be set when session_context has prior messages"
        )
        roles = [m["role"] for m in req.conversation_history]
        assert roles == ["user", "assistant", "user"], (
            "history must contain prior user, prior assistant, then the current user turn"
        )
        assert req.conversation_history[0]["content"] == "What is 2+2?"
        assert req.conversation_history[1]["content"] == "4."
        assert req.conversation_history[2]["content"] == "Now what is 3+3?"

    @pytest.mark.asyncio
    async def test_empty_session_context_leaves_conversation_history_none(self) -> None:
        """When session_context has no prior messages, conversation_history must be None
        so the provider falls back to the single-user-turn path."""
        provider = FakeProvider(events=[_complete_event_simple()])
        runtime, _ = _build_runtime(provider=provider)

        work = AgentWorkRequestedEvent(
            session_id="ses_123",
            agent_id="breqy",
            correlation_id="corr_1",
            message_id="msg_user",
            user_message_content="Hello.",
            session_context=SessionContextBundle(messages=[]),
        )

        await runtime.handle_work(work)

        assert len(provider.requests) == 1
        assert provider.requests[0].conversation_history is None, (
            "conversation_history must be None when there are no prior session messages"
        )

    @pytest.mark.asyncio
    async def test_session_context_seeding_emits_info_log(self) -> None:
        """An INFO-level structlog entry must be emitted when prior session messages are included."""
        import structlog.testing

        provider = FakeProvider(events=[_complete_event_simple()])
        runtime, _ = _build_runtime(provider=provider)

        prior = Message(session_id="ses_123", role=MessageRole.USER, content="previous message")
        work = AgentWorkRequestedEvent(
            session_id="ses_123",
            agent_id="breqy",
            correlation_id="corr_1",
            message_id="msg_user",
            user_message_content="Next message.",
            session_context=SessionContextBundle(messages=[prior]),
        )

        with structlog.testing.capture_logs() as logs:
            await runtime.handle_work(work)

        info_logs = [l for l in logs if l.get("log_level") == "info"]
        assert any("session" in str(l).lower() for l in info_logs), (
            f"Expected an INFO structlog entry referencing session context; got: {info_logs}"
        )


# --------------------------------------------------------------------------- #
# x-initiator binding — round 0 = "user", round 1+ = "agent"
# --------------------------------------------------------------------------- #


class TestAgentInitiatorBinding:
    """handle_work() must set initiator='user' for round 0 and 'agent' for follow-up rounds."""

    @pytest.mark.asyncio
    async def test_first_round_request_initiator_is_user(self) -> None:
        """Round 0 ProviderRequest must have initiator='user' (direct user request)."""
        provider = FakeProvider(events=[_complete_event()])
        runtime, _ = _build_runtime(provider=provider)

        await runtime.handle_work(_work_event())

        assert len(provider.requests) == 1
        assert provider.requests[0].initiator == "user", (
            "First round must be attributed to the user to avoid misclassifying as agent-originated"
        )

    @pytest.mark.asyncio
    async def test_tool_follow_up_round_initiator_is_agent(self) -> None:
        """After a tool call, round 1 ProviderRequest must have initiator='agent'.

        Tool-call follow-up rounds are agent-generated, not directly user-initiated.
        Marking them as 'agent' prevents GitHub Copilot from counting each tool
        continuation as a separate premium request.
        """
        round1 = [_tool_call_event("inv_1"), _complete_event()]
        round2 = [ProviderEvent(kind="text", text="Done."), _complete_event()]
        provider = MultiRoundProvider(rounds=[round1, round2])
        waiter = FakeToolResultWaiter(_tool_result_event("inv_1"))
        runtime, _ = _build_runtime(provider=provider, tool_result_waiter=waiter)

        await runtime.handle_work(_work_event())

        assert provider.call_count == 2
        assert provider.requests[1].initiator == "agent", (
            "Tool follow-up round must be marked 'agent' so Copilot does not charge it as premium"
        )


def _complete_event_simple() -> ProviderEvent:
    """A minimal complete event with no metadata for simple tests."""
    return ProviderEvent(
        kind="complete",
        metadata=CompletionMetadata(
            provider_id="test",
            model_id="test-model",
            exit_code=0,
        ),
    )


# --------------------------------------------------------------------------- #
# Tool output extraction — content dict should be used, not just summary
# --------------------------------------------------------------------------- #


def _realistic_shell_result(
    call_id: str = "inv_1",
    stdout: str = "file1\nfile2\nfile3",
    stderr: str = "",
    return_code: int = 0,
) -> ToolExecutionResultEvent:
    """Realistic shell tool result: summary is a status string, stdout is in content dict."""
    return ToolExecutionResultEvent(
        session_id="ses_123",
        agent_id="breqy",
        correlation_id=call_id,
        invocation_id=call_id,
        success_payload=StructuredResultPayload(
            summary=f"Shell command exited with code {return_code}",
            content={"stdout": stdout, "stderr": stderr, "return_code": return_code},
        ),
    )


def _realistic_fs_result(
    call_id: str = "inv_2",
    path: str = "/tmp/test.txt",
    content_text: str = "Hello, World!",
) -> ToolExecutionResultEvent:
    """Realistic filesystem read result: summary is status, file content is in content dict."""
    return ToolExecutionResultEvent(
        session_id="ses_123",
        agent_id="breqy",
        correlation_id=call_id,
        invocation_id=call_id,
        success_payload=StructuredResultPayload(
            summary=f"Read file {path}",
            content={"content": content_text, "path": path},
        ),
    )


class TestToolOutputInConversationHistory:
    """Tool stdout/file content must be extracted from content dict, not the status summary."""

    @pytest.mark.asyncio
    async def test_shell_stdout_included_in_tool_message(self) -> None:
        """When LLM calls the shell tool, the second-round conversation_history tool message
        must contain actual stdout, not the status string like 'Shell command exited with code 0'.
        """
        round1 = [_tool_call_event("inv_1", "shell", '{"command": "ls ~"}'), _complete_event()]
        round2 = [ProviderEvent(kind="text", text="Got files."), _complete_event()]

        provider = MultiRoundProvider(rounds=[round1, round2])
        waiter = FakeToolResultWaiter(
            _realistic_shell_result("inv_1", stdout="file1\nfile2\nfile3")
        )
        runtime, _ = _build_runtime(provider=provider, tool_result_waiter=waiter)

        await runtime.handle_work(_work_event())

        assert provider.call_count == 2
        second_request = provider.requests[1]
        tool_msg = next(
            (m for m in second_request.conversation_history if m.get("role") == "tool"),
            None,
        )
        assert tool_msg is not None, "conversation_history must contain a tool-role message"
        assert "file1" in tool_msg["content"], (
            f"Expected stdout in tool message content, got: {tool_msg['content']!r}"
        )

    @pytest.mark.asyncio
    async def test_filesystem_content_included_in_tool_message(self) -> None:
        """When LLM reads a file, the tool message must contain the file content,
        not just 'Read file /tmp/test.txt'.
        """
        round1 = [
            _tool_call_event(
                "inv_2", "filesystem", '{"operation": "read", "path": "/tmp/test.txt"}'
            ),
            _complete_event(),
        ]
        round2 = [ProviderEvent(kind="text", text="I read it."), _complete_event()]

        provider = MultiRoundProvider(rounds=[round1, round2])
        waiter = FakeToolResultWaiter(
            _realistic_fs_result("inv_2", path="/tmp/test.txt", content_text="Hello, World!")
        )
        runtime, _ = _build_runtime(provider=provider, tool_result_waiter=waiter)

        await runtime.handle_work(_work_event())

        assert provider.call_count == 2
        second_request = provider.requests[1]
        tool_msg = next(
            (m for m in second_request.conversation_history if m.get("role") == "tool"),
            None,
        )
        assert tool_msg is not None, "conversation_history must contain a tool-role message"
        assert "Hello, World!" in tool_msg["content"], (
            f"Expected file content in tool message, got: {tool_msg['content']!r}"
        )

    @pytest.mark.asyncio
    async def test_stderr_appended_when_non_empty(self) -> None:
        """When the shell tool produces both stdout and stderr, both must appear in the tool message."""
        round1 = [_tool_call_event("inv_3", "shell", '{"command": "ls /bad"}'), _complete_event()]
        round2 = [ProviderEvent(kind="text", text="Error noted."), _complete_event()]

        provider = MultiRoundProvider(rounds=[round1, round2])
        waiter = FakeToolResultWaiter(
            _realistic_shell_result(
                "inv_3",
                stdout="some output",
                stderr="warning: deprecated",
                return_code=0,
            )
        )
        runtime, _ = _build_runtime(provider=provider, tool_result_waiter=waiter)

        await runtime.handle_work(_work_event())

        assert provider.call_count == 2
        second_request = provider.requests[1]
        tool_msg = next(
            (m for m in second_request.conversation_history if m.get("role") == "tool"),
            None,
        )
        assert tool_msg is not None
        assert "some output" in tool_msg["content"], (
            f"Expected stdout in tool message, got: {tool_msg['content']!r}"
        )
        assert "warning: deprecated" in tool_msg["content"], (
            f"Expected stderr in tool message, got: {tool_msg['content']!r}"
        )


# --------------------------------------------------------------------------- #
# make_runtime fixture and _sample_work_event helper for reasoning event tests
# --------------------------------------------------------------------------- #


def _sample_work_event() -> AgentWorkRequestedEvent:
    """Minimal AgentWorkRequestedEvent for use in reasoning dispatch tests."""
    return AgentWorkRequestedEvent(
        session_id="ses_reasoning",
        agent_id="breqy",
        correlation_id="corr_reasoning",
        message_id="msg_reasoning",
        user_message_content="Think about this.",
        session_context=SessionContextBundle(messages=[]),
    )


@pytest.fixture()
def make_runtime():
    """Factory fixture that builds an AgentRuntime with a given list of provider events."""
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.models import AgentConfig

    def _factory(*, provider_events: list[ProviderEvent]) -> AgentRuntime:
        config = AgentConfig(id="breqy", name="Breqy", provider="copilot", model="gpt-4o")
        fake_client = FakeA2AClient()
        provider = FakeProvider(events=provider_events)
        runtime = AgentRuntime(
            config=config,
            agent_dir=Path("."),
            client=cast(Any, fake_client),
            provider=cast(Any, provider),
            skill_loader=None,
            private_memory_runtime=None,
            tool_result_waiter=None,
        )
        runtime._client = fake_client  # type: ignore[attr-defined]
        return runtime

    return _factory


# --------------------------------------------------------------------------- #
# Reasoning event dispatch tests
# --------------------------------------------------------------------------- #


class TestRuntimeReasoningEventDispatch:
    """Runtime dispatches ReasoningStartedEvent / ReasoningDoneEvent for reasoning provider events."""

    @pytest.mark.asyncio
    async def test_reasoning_started_published_to_client(self, make_runtime) -> None:
        """reasoning_started provider event → ReasoningStartedEvent sent to client."""
        from breqy.domain.events import ReasoningStartedEvent
        from breqy.domain.enums import EventType

        runtime = make_runtime(
            provider_events=[
                ProviderEvent(kind="reasoning_started"),
                ProviderEvent(kind="text", text="Hello"),
                _complete_event(),
            ]
        )
        await runtime.handle_work(_sample_work_event())

        sent_types = [e.event_type for e in runtime._client.sent_events]
        assert EventType.REASONING_STARTED in sent_types

    @pytest.mark.asyncio
    async def test_reasoning_done_published_to_client(self, make_runtime) -> None:
        """reasoning_done provider event → ReasoningDoneEvent sent to client."""
        from breqy.domain.enums import EventType

        runtime = make_runtime(
            provider_events=[
                ProviderEvent(kind="reasoning_started"),
                ProviderEvent(kind="reasoning_done"),
                ProviderEvent(kind="text", text="Hello"),
                _complete_event(),
            ]
        )
        await runtime.handle_work(_sample_work_event())

        sent_types = [e.event_type for e in runtime._client.sent_events]
        assert EventType.REASONING_DONE in sent_types

    @pytest.mark.asyncio
    async def test_reasoning_started_before_reasoning_done(self, make_runtime) -> None:
        """reasoning_started is dispatched before reasoning_done."""
        from breqy.domain.enums import EventType

        runtime = make_runtime(
            provider_events=[
                ProviderEvent(kind="reasoning_started"),
                ProviderEvent(kind="reasoning_done"),
                ProviderEvent(kind="text", text="Hi"),
                _complete_event(),
            ]
        )
        await runtime.handle_work(_sample_work_event())

        sent_types = [e.event_type for e in runtime._client.sent_events]
        started_idx = sent_types.index(EventType.REASONING_STARTED)
        done_idx = sent_types.index(EventType.REASONING_DONE)
        assert started_idx < done_idx
