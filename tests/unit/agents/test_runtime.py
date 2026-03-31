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
    provider = FakeProvider(
        events=[
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
                metadata=CompletionMetadata(
                    provider_id="claude", model_id="claude-test", exit_code=0
                ),
            ),
        ]
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
