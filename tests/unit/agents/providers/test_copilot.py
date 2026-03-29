"""Tests for CopilotProvider ModelProvider implementation."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from breqy.agents.providers.base import (
    ModelProvider,
    ProviderRequest,
    ToolDefinition,
)


def _make_request(prompt: str = "hello", **kwargs) -> ProviderRequest:
    return ProviderRequest(
        prompt=prompt,
        work_dir=Path("/tmp/test"),
        **kwargs,
    )


class TestProviderProperties:
    def test_provider_id(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        assert provider.provider_id == "copilot"

    def test_model_id(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="claude-sonnet-4-20250514",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        assert provider.model_id == "claude-sonnet-4-20250514"

    def test_supports_tool_calls(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        assert provider.supports_tool_calls is True

    def test_is_model_provider(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        assert isinstance(provider, ModelProvider)


class TestMessageConversion:
    def test_prompt_to_messages(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        messages = provider._build_messages(_make_request("what is 2+2?"))
        assert messages == [{"role": "user", "content": "what is 2+2?"}]

    def test_prompt_with_persona(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        request = _make_request("hello", extra_env={"BREQY_PERSONA": "You are helpful."})
        messages = provider._build_messages(request)
        assert messages == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hello"},
        ]


class TestToolConversion:
    def test_tool_definition_to_openai(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        tools = [
            ToolDefinition(
                name="read_file",
                description="Read file contents",
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            )
        ]
        openai_tools = provider._convert_tools(tools)
        assert openai_tools == [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read file contents",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                },
            }
        ]


class TestStreamTextEvents:
    def test_stream_text_events(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_token.return_value = "gho_test"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter([
            {"choices": [{"delta": {"content": "Hello"}, "index": 0}]},
            {"choices": [{"delta": {"content": " there"}, "index": 0}]},
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
        ])

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        text_events = [e for e in events if e.kind == "text"]
        assert len(text_events) == 2
        assert text_events[0].text == "Hello"
        assert text_events[1].text == " there"

        complete_events = [e for e in events if e.kind == "complete"]
        assert len(complete_events) == 1
        assert complete_events[0].metadata is not None
        assert complete_events[0].metadata.exit_code == 0
        assert complete_events[0].metadata.provider_id == "copilot"


class TestStreamToolCallEvents:
    def test_stream_tool_call_events(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_token.return_value = "gho_test"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter([
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "read_file", "arguments": ""}}]}, "index": 0}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"path": "/tmp"}'}}]}, "index": 0}]},
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
        ])

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("read /tmp")))

        tool_events = [e for e in events if e.kind == "tool_call"]
        assert len(tool_events) == 2
        assert tool_events[0].tool_call is not None
        assert tool_events[0].tool_call.call_id == "call_1"
        assert tool_events[0].tool_call.tool_name == "read_file"
        assert tool_events[1].tool_call is not None
        assert tool_events[1].tool_call.arguments_chunk == '{"path": "/tmp"}'


class TestApiErrors:
    def test_non_401_api_error_yields_complete_and_raises(self) -> None:
        import pytest

        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_client import CopilotApiError

        mock_auth = MagicMock()
        mock_auth.get_token.return_value = "gho_test"

        mock_client = MagicMock()
        mock_client.stream_chat.side_effect = CopilotApiError(500, "Internal Server Error")

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)

        collected_events = []
        with pytest.raises(CopilotApiError, match="500"):
            for event in provider.stream(_make_request("hi")):
                collected_events.append(event)

        assert len(collected_events) == 1
        assert collected_events[0].kind == "complete"
        assert collected_events[0].metadata is not None
        assert collected_events[0].metadata.exit_code == 1
        assert collected_events[0].metadata.provider_id == "copilot"


class TestAuthRetry:
    def test_auth_retry_on_401(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_client import CopilotApiError

        mock_auth = MagicMock()
        mock_auth.get_token.side_effect = ["gho_old", "gho_new"]

        mock_client = MagicMock()
        # First call raises 401, second succeeds
        mock_client.stream_chat.side_effect = [
            CopilotApiError(401, "Unauthorized"),
            iter([
                {"choices": [{"delta": {"content": "ok"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]),
        ]

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        # Should have cleared token and retried
        mock_auth.clear_token.assert_called_once()
        text_events = [e for e in events if e.kind == "text"]
        assert len(text_events) == 1
        assert text_events[0].text == "ok"

    def test_no_token_triggers_device_flow(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_auth import DeviceFlowInfo

        mock_auth = MagicMock()
        # First call returns None (no token), then returns token after device flow
        mock_auth.get_token.side_effect = [None, "gho_new"]
        mock_auth.start_device_flow.return_value = DeviceFlowInfo(
            user_code="ABCD-EFGH",
            verification_uri="https://github.com/login/device",
            device_code="dc_123",
            interval=5,
            expires_in=900,
        )
        mock_auth.poll_for_token.return_value = "gho_new"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter([
            {"choices": [{"delta": {"content": "hi"}, "index": 0}]},
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
        ])

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        mock_auth.start_device_flow.assert_called_once()
        mock_auth.poll_for_token.assert_called_once_with("dc_123", interval=5)
        assert any(e.kind == "text" for e in events)

    def test_device_flow_yields_auth_instructions_as_text(self) -> None:
        """When device flow is triggered, the user code and URL should be
        yielded as a text ProviderEvent so the TUI can display them."""
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_auth import DeviceFlowInfo

        mock_auth = MagicMock()
        mock_auth.get_token.return_value = None
        mock_auth.start_device_flow.return_value = DeviceFlowInfo(
            user_code="ABCD-1234",
            verification_uri="https://github.com/login/device",
            device_code="dc_test",
            interval=5,
            expires_in=900,
        )
        mock_auth.poll_for_token.return_value = "gho_new"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter([
            {"choices": [{"delta": {"content": "hello"}, "index": 0}]},
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
        ])

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        text_events = [e for e in events if e.kind == "text"]
        # The first text event(s) should contain the auth instructions
        auth_texts = [e.text for e in text_events if e.text and "ABCD-1234" in e.text]
        assert len(auth_texts) >= 1, "Device flow user code should appear in text events"
        auth_text = auth_texts[0]
        assert "https://github.com/login/device" in auth_text
        assert "ABCD-1234" in auth_text
