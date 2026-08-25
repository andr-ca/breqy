"""Tests for M2 Phase 3: Agent runtime model info, list, and switch handlers.

Covers MDL-02, MSW-03, MSW-04, MSW-05, MAI-01, MAI-02 success criteria:
1. CredentialStore injected into AgentRuntime via credential_store param
2. Agent sends ModelInfoEvent after AGENT_CONNECTED
3. Agent handles ModelListRequestedEvent via _discover_models()
4. Agent handles ModelSwitchRequestedEvent by rebuilding provider
5. Same-model guard: no rebuild, confirming ModelInfoEvent sent
6. Switch failure: old provider preserved, error + old ModelInfoEvent sent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from breqy.agents.providers.base import CompletionMetadata, ProviderEvent, ProviderRequest
from breqy.domain.enums import EventType, MessageRole
from breqy.domain.events import (
    AgentLifecycleEvent,
    AgentWorkRequestedEvent,
    MessageSentEvent,
    ModelInfoEvent,
    ModelListRequestedEvent,
    ModelListResponseEvent,
    ModelSwitchRequestedEvent,
)
from breqy.domain.models import Message, SessionContextBundle


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


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
        self._listen_envelopes = list(envelopes)

    async def listen(self):
        for envelope in self._listen_envelopes:
            yield envelope


@dataclass
class FakeProvider:
    events: list[ProviderEvent] = field(default_factory=list)
    supports_tool_calls: bool = True
    provider_id: str = "copilot"
    model_id: str = "gpt-4o"
    _list_models_result: list[tuple[str, str]] = field(
        default_factory=lambda: [("gpt-4o", "GPT-4o")]
    )

    def stream(self, request: ProviderRequest):
        for event in self.events:
            yield event

    def list_models(self) -> list[tuple[str, str]]:
        return self._list_models_result


def _make_runtime(
    *,
    provider: Any = None,
    credential_store: Any = None,
    session_id: str = "ses_test",
):
    from breqy.agents.runtime import AgentRuntime
    from breqy.config.models import AgentConfig

    config = AgentConfig(
        id="breqy",
        name="Breqy",
        display_name="Breqy",
        provider="copilot",
        model="gpt-4o",
    )
    client = FakeA2AClient()
    runtime = AgentRuntime(
        config=config,
        agent_dir=Path("agents/breqy"),
        client=cast(Any, client),
        provider=cast(Any, provider or FakeProvider()),
        skill_loader=None,
        private_memory_runtime=None,
        tool_result_waiter=None,
        session_id=session_id,
        credential_store=credential_store,
    )
    return runtime, client


# --------------------------------------------------------------------------- #
# SC-1: CredentialStore injected into AgentRuntime
# --------------------------------------------------------------------------- #


class TestCredentialStoreInjection:
    """AgentRuntime accepts credential_store parameter."""

    def test_accepts_credential_store_kwarg(self):
        mock_store = MagicMock()
        runtime, _ = _make_runtime(credential_store=mock_store)
        assert runtime._credential_store is mock_store

    def test_credential_store_defaults_to_none(self):
        runtime, _ = _make_runtime()
        assert runtime._credential_store is None


# --------------------------------------------------------------------------- #
# SC-2: ModelInfoEvent sent after AGENT_CONNECTED
# --------------------------------------------------------------------------- #


class TestModelInfoOnConnect:
    """Agent sends ModelInfoEvent right after AGENT_CONNECTED in start()."""

    @pytest.mark.asyncio
    async def test_model_info_sent_after_connected(self):
        provider = FakeProvider(provider_id="copilot", model_id="gpt-4o")
        runtime, client = _make_runtime(provider=provider)

        await runtime.start()

        # First event: AGENT_CONNECTED, second: MODEL_INFO
        assert len(client.sent_events) >= 2
        connected_event = cast(AgentLifecycleEvent, client.sent_events[0])
        assert connected_event.event_type == EventType.AGENT_CONNECTED

        model_info = cast(ModelInfoEvent, client.sent_events[1])
        assert model_info.event_type == EventType.MODEL_INFO
        assert model_info.provider_id == "copilot"
        assert model_info.model_id == "gpt-4o"

    @pytest.mark.asyncio
    async def test_model_info_uses_session_id(self):
        runtime, client = _make_runtime(session_id="ses_real")

        await runtime.start()

        model_info = cast(ModelInfoEvent, client.sent_events[1])
        assert model_info.session_id == "ses_real"

    @pytest.mark.asyncio
    async def test_model_info_for_null_provider(self):
        """_NullProvider sends ModelInfoEvent with null/null."""
        from breqy.agents.runtime import _NullProvider

        runtime, client = _make_runtime(provider=_NullProvider())

        await runtime.start()

        model_info = cast(ModelInfoEvent, client.sent_events[1])
        assert model_info.provider_id == "null"
        assert model_info.model_id == "null"


# --------------------------------------------------------------------------- #
# SC-3: ModelListRequestedEvent handling
# --------------------------------------------------------------------------- #


class TestModelListHandler:
    """Agent handles MODEL_LIST_REQUESTED by discovering models and responding."""

    @pytest.mark.asyncio
    async def test_handles_model_list_requested(self):
        from breqy.a2a.envelope import Envelope

        provider = FakeProvider(
            provider_id="copilot",
            model_id="gpt-4o",
            _list_models_result=[("gpt-4o", "GPT-4o"), ("o3-mini", "O3 Mini")],
        )
        runtime, client = _make_runtime(provider=provider)

        list_req = ModelListRequestedEvent(session_id="ses_test")
        client.set_listen_envelopes([Envelope.from_event(list_req)])

        await runtime.run()

        # Find the ModelListResponseEvent
        responses = [e for e in client.sent_events if isinstance(e, ModelListResponseEvent)]
        assert len(responses) == 1
        resp = responses[0]
        assert resp.current_provider == "copilot"
        assert resp.current_model == "gpt-4o"
        assert len(resp.models) > 0

    @pytest.mark.asyncio
    async def test_discover_models_includes_all_providers(self):
        """_discover_models() returns entries for all supported providers, not just active."""
        from breqy.a2a.envelope import Envelope

        provider = FakeProvider(
            provider_id="copilot",
            model_id="gpt-4o",
            _list_models_result=[("gpt-4o", "GPT-4o")],
        )
        mock_store = MagicMock()
        mock_store.get.return_value = None  # No credentials for any provider
        runtime, client = _make_runtime(provider=provider, credential_store=mock_store)

        list_req = ModelListRequestedEvent(session_id="ses_test")
        client.set_listen_envelopes([Envelope.from_event(list_req)])

        await runtime.run()

        responses = [e for e in client.sent_events if isinstance(e, ModelListResponseEvent)]
        assert len(responses) == 1
        providers_in_response = {m.provider for m in responses[0].models}
        # Should include all supported providers
        assert providers_in_response == {"copilot", "claude", "codex", "gemini", "qwen", "ollama"}


# --------------------------------------------------------------------------- #
# SC-4: ModelSwitchRequestedEvent handling
# --------------------------------------------------------------------------- #


class TestModelSwitchHandler:
    """Agent handles MODEL_SWITCH_REQUESTED by rebuilding provider."""

    @pytest.mark.asyncio
    async def test_switch_rebuilds_provider(self):
        from breqy.a2a.envelope import Envelope

        old_provider = FakeProvider(provider_id="copilot", model_id="gpt-4o")
        runtime, client = _make_runtime(provider=old_provider)

        # Mock _build_provider to return a new provider
        new_provider = FakeProvider(provider_id="claude", model_id="sonnet")
        with patch("breqy.agents.runtime._build_provider", return_value=new_provider):
            switch_req = ModelSwitchRequestedEvent(
                session_id="ses_test",
                provider_id="claude",
                model_id="sonnet",
            )
            client.set_listen_envelopes([Envelope.from_event(switch_req)])
            await runtime.run()

        # Should have sent a new ModelInfoEvent with the switched model
        info_events = [e for e in client.sent_events if isinstance(e, ModelInfoEvent)]
        # At least 2: one from start(), one from switch
        assert len(info_events) >= 2
        last_info = info_events[-1]
        assert last_info.provider_id == "claude"
        assert last_info.model_id == "sonnet"

    @pytest.mark.asyncio
    async def test_switch_passes_credential_store_to_build_provider(self):
        """_handle_model_switch must pass self._credential_store to _build_provider."""
        from breqy.a2a.envelope import Envelope

        mock_store = MagicMock()
        old_provider = FakeProvider(provider_id="copilot", model_id="gpt-4o")
        new_provider = FakeProvider(provider_id="claude", model_id="sonnet")
        runtime, client = _make_runtime(
            provider=old_provider,
            credential_store=mock_store,
        )

        with patch("breqy.agents.runtime._build_provider", return_value=new_provider) as mock_build:
            switch_req = ModelSwitchRequestedEvent(
                session_id="ses_test",
                provider_id="claude",
                model_id="sonnet",
            )
            client.set_listen_envelopes([Envelope.from_event(switch_req)])
            await runtime.run()

            # _build_provider MUST have been called with credential_store
            mock_build.assert_called_once()
            _, kwargs = mock_build.call_args
            assert "credential_store" in kwargs
            assert kwargs["credential_store"] is mock_store


# --------------------------------------------------------------------------- #
# SC-5: Same-model guard
# --------------------------------------------------------------------------- #


class TestSameModelGuard:
    """Selecting the same model skips rebuild and sends confirming ModelInfoEvent."""

    @pytest.mark.asyncio
    async def test_same_model_skips_rebuild(self):
        from breqy.a2a.envelope import Envelope

        provider = FakeProvider(provider_id="copilot", model_id="gpt-4o")
        runtime, client = _make_runtime(provider=provider)

        with patch("breqy.agents.runtime._build_provider") as mock_build:
            switch_req = ModelSwitchRequestedEvent(
                session_id="ses_test",
                provider_id="copilot",
                model_id="gpt-4o",
            )
            client.set_listen_envelopes([Envelope.from_event(switch_req)])
            await runtime.run()

            # _build_provider should NOT have been called
            mock_build.assert_not_called()

        # Should still send a confirming ModelInfoEvent
        info_events = [e for e in client.sent_events if isinstance(e, ModelInfoEvent)]
        assert len(info_events) >= 2  # one from start, one confirming
        last_info = info_events[-1]
        assert last_info.provider_id == "copilot"
        assert last_info.model_id == "gpt-4o"


# --------------------------------------------------------------------------- #
# SC-6: Switch failure handling
# --------------------------------------------------------------------------- #


class TestSwitchFailure:
    """Switch failure preserves old provider and sends error."""

    @pytest.mark.asyncio
    async def test_switch_failure_preserves_old_provider(self):
        from breqy.agents.runtime import _NullProvider
        from breqy.a2a.envelope import Envelope

        old_provider = FakeProvider(provider_id="copilot", model_id="gpt-4o")
        runtime, client = _make_runtime(provider=old_provider)

        # _build_provider returns _NullProvider on failure
        with patch("breqy.agents.runtime._build_provider", return_value=_NullProvider()):
            switch_req = ModelSwitchRequestedEvent(
                session_id="ses_test",
                provider_id="invalid",
                model_id="bad-model",
            )
            client.set_listen_envelopes([Envelope.from_event(switch_req)])
            await runtime.run()

        # Provider should still be the old one
        assert runtime._provider is old_provider

    @pytest.mark.asyncio
    async def test_switch_failure_sends_error_message(self):
        from breqy.agents.runtime import _NullProvider
        from breqy.a2a.envelope import Envelope

        old_provider = FakeProvider(provider_id="copilot", model_id="gpt-4o")
        runtime, client = _make_runtime(provider=old_provider)

        with patch("breqy.agents.runtime._build_provider", return_value=_NullProvider()):
            switch_req = ModelSwitchRequestedEvent(
                session_id="ses_test",
                provider_id="invalid",
                model_id="bad-model",
            )
            client.set_listen_envelopes([Envelope.from_event(switch_req)])
            await runtime.run()

        # Should send a system error message
        error_msgs = [
            e
            for e in client.sent_events
            if isinstance(e, MessageSentEvent) and e.role == MessageRole.SYSTEM
        ]
        assert len(error_msgs) >= 1
        assert (
            "invalid" in error_msgs[-1].content.lower()
            or "failed" in error_msgs[-1].content.lower()
        )

    @pytest.mark.asyncio
    async def test_switch_failure_sends_old_model_info(self):
        from breqy.agents.runtime import _NullProvider
        from breqy.a2a.envelope import Envelope

        old_provider = FakeProvider(provider_id="copilot", model_id="gpt-4o")
        runtime, client = _make_runtime(provider=old_provider)

        with patch("breqy.agents.runtime._build_provider", return_value=_NullProvider()):
            switch_req = ModelSwitchRequestedEvent(
                session_id="ses_test",
                provider_id="invalid",
                model_id="bad-model",
            )
            client.set_listen_envelopes([Envelope.from_event(switch_req)])
            await runtime.run()

        # Last ModelInfoEvent should still be the old model
        info_events = [e for e in client.sent_events if isinstance(e, ModelInfoEvent)]
        last_info = info_events[-1]
        assert last_info.provider_id == "copilot"
        assert last_info.model_id == "gpt-4o"


# --------------------------------------------------------------------------- #
# Phase 6b: _NullProvider hardening
# --------------------------------------------------------------------------- #


class TestNullProviderListModels:
    """_NullProvider should have a list_models() method for safety."""

    def test_null_provider_has_list_models(self):
        from breqy.agents.runtime import _NullProvider

        provider = _NullProvider()
        result = provider.list_models()
        assert isinstance(result, list)

    def test_null_provider_list_models_returns_pair(self):
        from breqy.agents.runtime import _NullProvider

        provider = _NullProvider()
        result = provider.list_models()
        # Should return at least one (id, display_name) pair
        assert len(result) >= 1
        assert result[0] == ("null", "null")


# --------------------------------------------------------------------------- #
# Phase 6b: _handle_model_list error handling
# --------------------------------------------------------------------------- #


class TestModelListErrorHandling:
    """_handle_model_list should not crash on _discover_models failure."""

    @pytest.mark.asyncio
    async def test_handle_model_list_catches_discover_exception(self):
        """If _discover_models raises, _handle_model_list sends empty response."""
        runtime, client = _make_runtime()

        with patch.object(runtime, "_discover_models", side_effect=RuntimeError("boom")):
            event = ModelListRequestedEvent(session_id="ses_test")
            await runtime._handle_model_list(event)

        # Should send a ModelListResponseEvent (possibly empty) rather than crashing
        responses = [e for e in client.sent_events if isinstance(e, ModelListResponseEvent)]
        assert len(responses) == 1
        # The response should be valid (empty models list is acceptable)
        assert isinstance(responses[0].models, list)


# --------------------------------------------------------------------------- #
# Phase 6b: _handle_model_switch exception handling
# --------------------------------------------------------------------------- #


class TestModelSwitchExceptionHandling:
    """_handle_model_switch should not crash on _build_provider exception."""

    @pytest.mark.asyncio
    async def test_switch_catches_build_provider_exception(self):
        """If _build_provider raises, _handle_model_switch preserves old provider."""
        from breqy.a2a.envelope import Envelope

        old_provider = FakeProvider(provider_id="copilot", model_id="gpt-4o")
        runtime, client = _make_runtime(provider=old_provider)

        with patch(
            "breqy.agents.runtime._build_provider", side_effect=RuntimeError("factory crash")
        ):
            switch_req = ModelSwitchRequestedEvent(
                session_id="ses_test",
                provider_id="claude",
                model_id="sonnet",
            )
            client.set_listen_envelopes([Envelope.from_event(switch_req)])
            await runtime.run()

        # Provider should still be the old one
        assert runtime._provider is old_provider

    @pytest.mark.asyncio
    async def test_switch_exception_sends_error_message(self):
        """If _build_provider raises, error message should be sent."""
        from breqy.a2a.envelope import Envelope

        old_provider = FakeProvider(provider_id="copilot", model_id="gpt-4o")
        runtime, client = _make_runtime(provider=old_provider)

        with patch(
            "breqy.agents.runtime._build_provider", side_effect=RuntimeError("factory crash")
        ):
            switch_req = ModelSwitchRequestedEvent(
                session_id="ses_test",
                provider_id="claude",
                model_id="sonnet",
            )
            client.set_listen_envelopes([Envelope.from_event(switch_req)])
            await runtime.run()

        error_msgs = [
            e
            for e in client.sent_events
            if isinstance(e, MessageSentEvent) and e.role == MessageRole.SYSTEM
        ]
        assert len(error_msgs) >= 1

    @pytest.mark.asyncio
    async def test_switch_exception_sends_old_model_info(self):
        """If _build_provider raises, old model ModelInfoEvent should be sent."""
        from breqy.a2a.envelope import Envelope

        old_provider = FakeProvider(provider_id="copilot", model_id="gpt-4o")
        runtime, client = _make_runtime(provider=old_provider)

        with patch(
            "breqy.agents.runtime._build_provider", side_effect=RuntimeError("factory crash")
        ):
            switch_req = ModelSwitchRequestedEvent(
                session_id="ses_test",
                provider_id="claude",
                model_id="sonnet",
            )
            client.set_listen_envelopes([Envelope.from_event(switch_req)])
            await runtime.run()

        info_events = [e for e in client.sent_events if isinstance(e, ModelInfoEvent)]
        last_info = info_events[-1]
        assert last_info.provider_id == "copilot"
        assert last_info.model_id == "gpt-4o"


# --------------------------------------------------------------------------- #
# Phase 6c: credential_store extraction in _build_provider
# --------------------------------------------------------------------------- #


class TestBuildProviderAcceptsCredentialStore:
    """_build_provider accepts an optional credential_store parameter."""

    def test_build_provider_accepts_credential_store_kwarg(self):
        """_build_provider should accept a credential_store keyword arg."""
        from breqy.agents.runtime import _build_provider
        from breqy.config.models import AgentConfig

        config = AgentConfig(
            id="breqy",
            name="Breqy",
            provider="copilot",
            model="gpt-4o",
        )
        mock_store = MagicMock()

        # Should not raise TypeError for unexpected kwarg
        result = _build_provider(config, credential_store=mock_store)
        # Just ensure it returns something (provider or _NullProvider)
        assert result is not None

    def test_build_provider_uses_injected_credential_store(self):
        """When credential_store is provided, _build_provider should use it
        instead of creating its own."""
        from breqy.agents.runtime import _build_provider
        from breqy.config.models import AgentConfig

        config = AgentConfig(
            id="breqy",
            name="Breqy",
            provider="copilot",
            model="gpt-4o",
        )
        mock_store = MagicMock()

        with patch("breqy.agents.providers.adapters.build_model_providers") as mock_build:
            mock_build.return_value = {}
            _build_provider(config, credential_store=mock_store)
            # build_model_providers should be called with our injected store
            mock_build.assert_called_once()
            call_kwargs = mock_build.call_args
            assert call_kwargs.kwargs.get("credential_store") is mock_store
