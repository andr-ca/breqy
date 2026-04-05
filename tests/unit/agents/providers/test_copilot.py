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


class TestCopilotTokenUsage:
    """Verify that CopilotProvider uses get_copilot_token() (session token)
    instead of raw get_token() (OAuth token) for API calls."""

    def test_stream_uses_copilot_session_token(self) -> None:
        """stream() must call get_copilot_token() for the token passed to the API."""
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=abc;exp=9999999999;sku=copilot_pro"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {"choices": [{"delta": {"content": "ok"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        list(provider.stream(_make_request("hi")))

        mock_auth.get_copilot_token.assert_called()
        # The session token (not OAuth) should be passed to stream_chat
        token_used = mock_client.stream_chat.call_args.kwargs.get("token")
        assert token_used == "tid=abc;exp=9999999999;sku=copilot_pro"

    def test_stream_does_not_call_get_token_for_api_auth(self) -> None:
        """stream() should use get_copilot_token(), not get_token(), when token exists."""
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=abc;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {"choices": [{"delta": {"content": "ok"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        list(provider.stream(_make_request("hi")))

        # get_token() should NOT be used for the API call token
        # get_copilot_token() should be the method called
        mock_auth.get_copilot_token.assert_called()

    def test_list_models_uses_copilot_session_token(self) -> None:
        """list_models() must use get_copilot_token() for Bearer auth."""
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=xyz;exp=9999999999;sku=copilot_pro"

        mock_client = MagicMock()

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)

        import httpx
        from unittest.mock import patch

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                },
                {
                    "id": "gpt-5.4-mini",
                    "name": "GPT-5.4 Mini",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                },
            ]
        }

        with patch.object(httpx, "get", return_value=mock_response) as mock_get:
            models = provider.list_models()

        mock_auth.get_copilot_token.assert_called_once()
        # Verify the session token was used in the Authorization header
        call_kwargs = mock_get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["Authorization"] == "Bearer tid=xyz;exp=9999999999;sku=copilot_pro"
        assert len(models) == 2

    def test_list_models_returns_fallback_when_no_session_token(self) -> None:
        """list_models() should return fallback when get_copilot_token() returns None."""
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = None

        mock_client = MagicMock()

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        models = provider.list_models()

        assert models == [("gpt-4o", "gpt-4o")]

    def test_stream_null_copilot_token_triggers_device_flow(self) -> None:
        """When get_copilot_token() returns None, device flow should start."""
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_auth import DeviceFlowInfo

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = None
        mock_auth.start_device_flow.return_value = DeviceFlowInfo(
            user_code="ABCD-EFGH",
            verification_uri="https://github.com/login/device",
            device_code="dc_123",
            interval=5,
            expires_in=900,
        )
        mock_auth.poll_for_token.return_value = "gho_fresh"
        # After device flow, get_copilot_token should return a session token
        mock_auth.get_copilot_token.side_effect = [None, "tid=new;exp=9999999999"]

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {"choices": [{"delta": {"content": "hi"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        mock_auth.start_device_flow.assert_called_once()
        mock_auth.poll_for_token.assert_called_once()
        assert any(e.kind == "notice" for e in events)

    def test_401_retry_uses_copilot_session_token(self) -> None:
        """On 401, after clearing token, retry should use get_copilot_token()."""
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_client import CopilotApiError

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.side_effect = [
            "tid=old;exp=9999999999",  # first call
            "tid=new;exp=9999999999",  # after clear_token, second call
        ]

        mock_client = MagicMock()
        mock_client.stream_chat.side_effect = [
            CopilotApiError(401, "Unauthorized"),
            iter(
                [
                    {"choices": [{"delta": {"content": "ok"}, "index": 0}]},
                    {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
                ]
            ),
        ]

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        mock_auth.clear_token.assert_called_once()
        assert mock_auth.get_copilot_token.call_count == 2
        # Second stream_chat call should use the new session token
        second_call = mock_client.stream_chat.call_args_list[1]
        assert second_call.kwargs.get("token") == "tid=new;exp=9999999999"


class TestStreamTextEvents:
    def test_stream_text_events(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {"choices": [{"delta": {"content": "Hello"}, "index": 0}]},
                {"choices": [{"delta": {"content": " there"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]
        )

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
        """_do_stream yields one complete tool_call event per tool call
        (args accumulated across SSE chunks), not one event per chunk."""
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_1",
                                        "function": {"name": "read_file", "arguments": ""},
                                    }
                                ]
                            },
                            "index": 0,
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"index": 0, "function": {"arguments": '{"path": "/tmp"}'}}
                                ]
                            },
                            "index": 0,
                        }
                    ]
                },
                {"choices": [{"delta": {}, "finish_reason": "tool_calls", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        provider._model_endpoints = {"gpt-4o": ["/chat/completions"]}
        events = list(provider.stream(_make_request("read /tmp")))

        tool_events = [e for e in events if e.kind == "tool_call"]
        # Exactly ONE event with the complete accumulated arguments
        assert len(tool_events) == 1
        assert tool_events[0].tool_call is not None
        assert tool_events[0].tool_call.call_id == "call_1"
        assert tool_events[0].tool_call.tool_name == "read_file"
        assert tool_events[0].tool_call.arguments_chunk == '{"path": "/tmp"}'


class TestApiErrors:
    def test_non_401_api_error_yields_complete_and_raises(self) -> None:
        import pytest

        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_client import CopilotApiError

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

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
        mock_auth.get_copilot_token.side_effect = [
            "tid=old;exp=9999999999",
            "tid=new;exp=9999999999",
        ]

        mock_client = MagicMock()
        # First call raises 401, second succeeds
        mock_client.stream_chat.side_effect = [
            CopilotApiError(401, "Unauthorized"),
            iter(
                [
                    {"choices": [{"delta": {"content": "ok"}, "index": 0}]},
                    {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
                ]
            ),
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
        # First call returns None (no session token), triggering device flow
        # After poll_for_token stores OAuth, second call returns session token
        mock_auth.get_copilot_token.side_effect = [None, "tid=new;exp=9999999999"]
        mock_auth.start_device_flow.return_value = DeviceFlowInfo(
            user_code="ABCD-EFGH",
            verification_uri="https://github.com/login/device",
            device_code="dc_123",
            interval=5,
            expires_in=900,
        )
        mock_auth.poll_for_token.return_value = "gho_new"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {"choices": [{"delta": {"content": "hi"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        mock_auth.start_device_flow.assert_called_once()
        mock_auth.poll_for_token.assert_called_once_with("dc_123", interval=5)
        assert any(e.kind == "text" for e in events)

    def test_device_flow_yields_auth_instructions_as_notice(self) -> None:
        """When device flow is triggered, the user code and URL should be
        yielded as a notice ProviderEvent so the TUI can display them
        immediately as a complete message."""
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_auth import DeviceFlowInfo

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.side_effect = [None, "tid=new;exp=9999999999"]
        mock_auth.start_device_flow.return_value = DeviceFlowInfo(
            user_code="ABCD-1234",
            verification_uri="https://github.com/login/device",
            device_code="dc_test",
            interval=5,
            expires_in=900,
        )
        mock_auth.poll_for_token.return_value = "gho_new"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {"choices": [{"delta": {"content": "hello"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        notice_events = [e for e in events if e.kind == "notice"]
        assert len(notice_events) >= 1, "Device flow should yield a notice event"
        auth_text = notice_events[0].text
        assert auth_text is not None
        assert "https://github.com/login/device" in auth_text
        assert "ABCD-1234" in auth_text

    def test_auth_event_yielded_before_poll_blocks(self) -> None:
        """The auth instructions event MUST be yielded to the caller
        BEFORE poll_for_token() is called.  This ensures the TUI can
        display the device-code while the provider polls for authorization.

        Bug: Previously, _ensure_token() called poll_for_token() (which
        blocks with time.sleep) before returning the auth event, so the
        event only reached the TUI after the user had already authorized
        — defeating its purpose.
        """
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_auth import DeviceFlowInfo

        call_order: list[str] = []

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.side_effect = [None, "tid=poll;exp=9999999999"]
        mock_auth.start_device_flow.return_value = DeviceFlowInfo(
            user_code="TEST-CODE",
            verification_uri="https://github.com/login/device",
            device_code="dc_order_test",
            interval=5,
            expires_in=900,
        )

        def poll_side_effect(device_code, interval):
            call_order.append("poll_for_token")
            return "gho_poll_result"

        mock_auth.poll_for_token.side_effect = poll_side_effect

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {"choices": [{"delta": {"content": "ok"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)

        # Iterate one event at a time to observe ordering
        stream_iter = provider.stream(_make_request("hi"))
        first_event = next(stream_iter)

        # Auth instructions must be the FIRST event yielded …
        assert first_event.kind == "notice"
        assert first_event.text is not None
        assert "TEST-CODE" in first_event.text

        # … and poll_for_token must NOT have been called yet
        assert "poll_for_token" not in call_order, (
            "poll_for_token was called before auth event was yielded — "
            "this blocks the event loop and prevents the TUI from "
            "showing the device code"
        )

        # Consume the rest — poll should happen now
        remaining = list(stream_iter)
        assert "poll_for_token" in call_order
        assert any(e.kind == "complete" for e in remaining)


class TestCopilotAuthErrorRecovery:
    """CopilotAuthError from get_copilot_token() (e.g. HTTP 404 on token
    exchange) should trigger device flow re-auth instead of propagating
    as a raw error to the TUI.

    Regression: previously, CopilotAuthError was not caught in stream(),
    so an expired/revoked OAuth token caused an unrecoverable error
    message instead of triggering re-authentication.
    """

    def test_auth_error_on_initial_token_triggers_device_flow(self) -> None:
        """When get_copilot_token() raises CopilotAuthError (e.g. HTTP 404),
        stream() should clear the bad token and start device flow."""
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_auth import (
            CopilotAuthError,
            DeviceFlowInfo,
        )

        mock_auth = MagicMock()
        # First call raises CopilotAuthError (bad OAuth token → 404)
        # After device flow completes, second call returns valid session token
        mock_auth.get_copilot_token.side_effect = [
            CopilotAuthError(
                "Failed to exchange OAuth for Copilot token (token exchange): HTTP 404"
            ),
            "tid=fresh;exp=9999999999",
        ]
        mock_auth.start_device_flow.return_value = DeviceFlowInfo(
            user_code="REAUTH-01",
            verification_uri="https://github.com/login/device",
            device_code="dc_reauth",
            interval=5,
            expires_in=900,
        )
        mock_auth.poll_for_token.return_value = "gho_reauthed"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {"choices": [{"delta": {"content": "recovered"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        # Should have cleared the bad token
        mock_auth.clear_token.assert_called_once()
        # Should have triggered device flow
        mock_auth.start_device_flow.assert_called_once()
        mock_auth.poll_for_token.assert_called_once_with("dc_reauth", interval=5)
        # Should yield notice event with auth instructions
        notice_events = [e for e in events if e.kind == "notice"]
        assert len(notice_events) >= 1
        assert notice_events[0].text is not None
        assert "REAUTH-01" in notice_events[0].text
        # Should successfully stream after recovery
        text_events = [e for e in events if e.kind == "text"]
        assert len(text_events) == 1
        assert text_events[0].text == "recovered"

    def test_auth_error_on_401_retry_token_triggers_device_flow(self) -> None:
        """When 401 retry calls get_copilot_token() and it raises
        CopilotAuthError, the provider should fall through to device flow
        instead of crashing."""
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_auth import (
            CopilotAuthError,
            DeviceFlowInfo,
        )
        from breqy.agents.providers.copilot_client import CopilotApiError

        mock_auth = MagicMock()
        # First call: valid token (initial stream)
        # Second call (after 401 + clear_token): raises CopilotAuthError
        # Third call (after device flow): returns fresh token
        mock_auth.get_copilot_token.side_effect = [
            "tid=old;exp=9999999999",
            CopilotAuthError(
                "Failed to exchange OAuth for Copilot token (token exchange): HTTP 404"
            ),
            "tid=recovered;exp=9999999999",
        ]
        mock_auth.start_device_flow.return_value = DeviceFlowInfo(
            user_code="RETRY-01",
            verification_uri="https://github.com/login/device",
            device_code="dc_retry",
            interval=5,
            expires_in=900,
        )
        mock_auth.poll_for_token.return_value = "gho_retried"

        mock_client = MagicMock()
        # First stream raises 401, second succeeds
        mock_client.stream_chat.side_effect = [
            CopilotApiError(401, "Unauthorized"),
            iter(
                [
                    {"choices": [{"delta": {"content": "ok"}, "index": 0}]},
                    {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
                ]
            ),
        ]

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        # Should have triggered device flow during 401 retry
        mock_auth.start_device_flow.assert_called_once()
        mock_auth.poll_for_token.assert_called_once_with("dc_retry", interval=5)
        # Should yield notice event with auth instructions
        notice_events = [e for e in events if e.kind == "notice"]
        assert len(notice_events) >= 1
        assert "RETRY-01" in notice_events[0].text
        # Should successfully stream after recovery
        text_events = [e for e in events if e.kind == "text"]
        assert len(text_events) == 1
        assert text_events[0].text == "ok"

    def test_auth_error_notice_yielded_before_poll(self) -> None:
        """Auth instructions from CopilotAuthError recovery must be yielded
        before poll_for_token blocks, same as the normal device flow path."""
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_auth import (
            CopilotAuthError,
            DeviceFlowInfo,
        )

        call_order: list[str] = []

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.side_effect = [
            CopilotAuthError("HTTP 404"),
            "tid=order;exp=9999999999",
        ]
        mock_auth.start_device_flow.return_value = DeviceFlowInfo(
            user_code="ORDER-01",
            verification_uri="https://github.com/login/device",
            device_code="dc_order",
            interval=5,
            expires_in=900,
        )

        def poll_side_effect(device_code, interval):
            call_order.append("poll_for_token")
            return "gho_order"

        mock_auth.poll_for_token.side_effect = poll_side_effect

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {"choices": [{"delta": {"content": "ok"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)

        stream_iter = provider.stream(_make_request("hi"))
        first_event = next(stream_iter)

        # Auth notice must come first
        assert first_event.kind == "notice"
        assert first_event.text is not None
        assert "ORDER-01" in first_event.text

        # poll_for_token must NOT have been called yet
        assert "poll_for_token" not in call_order

        # Consume remaining — poll should happen during consumption
        remaining = list(stream_iter)
        assert "poll_for_token" in call_order
        assert any(e.kind == "complete" for e in remaining)


# --------------------------------------------------------------------------- #
# Responses API event mapping
# --------------------------------------------------------------------------- #


class TestResponsesApiStreamEvents:
    """CopilotProvider maps Responses API events to ProviderEvent."""

    def test_text_delta_mapped_to_text_event(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_responses.return_value = iter(
            [
                {"type": "response.output_text.delta", "delta": "Hello"},
                {"type": "response.output_text.delta", "delta": " world"},
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"total_tokens": 10},
                        "model": "gpt-5.4-mini",
                    },
                },
            ]
        )

        provider = CopilotProvider(
            model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client
        )
        provider._model_endpoints = {"gpt-5.4-mini": ["/responses"]}
        events = list(provider.stream(_make_request("hi")))

        text_events = [e for e in events if e.kind == "text"]
        assert len(text_events) == 2
        assert text_events[0].text == "Hello"
        assert text_events[1].text == " world"

    def test_tool_call_mapped_to_tool_call_event(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_responses.return_value = iter(
            [
                {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "read_file",
                        "arguments": '{"path": "/tmp"}',
                    },
                },
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"total_tokens": 10},
                        "model": "gpt-5.4-mini",
                    },
                },
            ]
        )

        provider = CopilotProvider(
            model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client
        )
        provider._model_endpoints = {"gpt-5.4-mini": ["/responses"]}
        events = list(provider.stream(_make_request("read file")))

        tool_events = [e for e in events if e.kind == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0].tool_call.call_id == "call_1"
        assert tool_events[0].tool_call.tool_name == "read_file"
        assert tool_events[0].tool_call.arguments_chunk == '{"path": "/tmp"}'

    def test_completed_mapped_to_complete_event(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_responses.return_value = iter(
            [
                {"type": "response.output_text.delta", "delta": "done"},
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"total_tokens": 5},
                        "model": "gpt-5.4-mini",
                    },
                },
            ]
        )

        provider = CopilotProvider(
            model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client
        )
        provider._model_endpoints = {"gpt-5.4-mini": ["/responses"]}
        events = list(provider.stream(_make_request("hi")))

        complete_events = [e for e in events if e.kind == "complete"]
        assert len(complete_events) == 1
        assert complete_events[0].metadata.exit_code == 0

    def test_failed_response_yields_exit_code_1(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_responses.return_value = iter(
            [
                {"type": "response.failed", "error": {"message": "model overloaded"}},
            ]
        )

        provider = CopilotProvider(
            model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client
        )
        provider._model_endpoints = {"gpt-5.4-mini": ["/responses"]}
        events = list(provider.stream(_make_request("hi")))

        complete_events = [e for e in events if e.kind == "complete"]
        assert len(complete_events) == 1
        assert complete_events[0].metadata.exit_code == 1


# --------------------------------------------------------------------------- #
# Endpoint routing
# --------------------------------------------------------------------------- #


class TestEndpointRouting:
    """CopilotProvider routes to correct API based on model endpoints."""

    def test_routes_to_chat_completions_by_default(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {"choices": [{"delta": {"content": "ok"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        # No _model_endpoints set -> defaults to chat completions
        list(provider.stream(_make_request("hi")))

        mock_client.stream_chat.assert_called_once()
        mock_client.stream_responses.assert_not_called()

    def test_routes_to_responses_when_only_responses_supported(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_responses.return_value = iter(
            [
                {"type": "response.output_text.delta", "delta": "ok"},
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"total_tokens": 5},
                        "model": "gpt-5.4-mini",
                    },
                },
            ]
        )

        provider = CopilotProvider(
            model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client
        )
        provider._model_endpoints = {"gpt-5.4-mini": ["/responses"]}
        list(provider.stream(_make_request("hi")))

        mock_client.stream_responses.assert_called_once()
        mock_client.stream_chat.assert_not_called()

    def test_routes_to_responses_when_both_supported(self) -> None:
        """When model supports both endpoints, prefer /responses (newer API)."""
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_responses.return_value = iter(
            [
                {"type": "response.output_text.delta", "delta": "ok"},
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"total_tokens": 5},
                        "model": "gpt-4o",
                    },
                },
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        provider._model_endpoints = {"gpt-4o": ["/chat/completions", "/responses"]}
        list(provider.stream(_make_request("hi")))

        mock_client.stream_responses.assert_called_once()
        mock_client.stream_chat.assert_not_called()

    def test_lazy_endpoint_discovery_routes_to_responses(self) -> None:
        """Fresh provider (no list_models() call) must discover endpoints
        lazily and route to /responses for models that only support it.

        Regression: model switch creates a new CopilotProvider with empty
        _model_endpoints, causing all models to default to /chat/completions.
        """
        from unittest.mock import patch

        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_responses.return_value = iter(
            [
                {"type": "response.output_text.delta", "delta": "ok"},
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"total_tokens": 5},
                        "model": "gpt-5.4-mini",
                    },
                },
            ]
        )

        # Mock the /models API response so lazy discovery can populate endpoints
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "gpt-5.4-mini",
                    "name": "GPT-5.4 Mini",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                    "supported_endpoints": ["/responses"],
                },
            ]
        }

        provider = CopilotProvider(
            model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client
        )
        # Do NOT set _model_endpoints — simulates fresh provider after model switch

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            list(provider.stream(_make_request("hi")))

        mock_client.stream_responses.assert_called_once()
        mock_client.stream_chat.assert_not_called()

    def test_responses_api_receives_instructions_from_persona(self) -> None:
        """When using /responses, system message from persona should be passed as instructions."""
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_responses.return_value = iter(
            [
                {"type": "response.output_text.delta", "delta": "ok"},
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"total_tokens": 5},
                        "model": "gpt-5.4-mini",
                    },
                },
            ]
        )

        provider = CopilotProvider(
            model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client
        )
        provider._model_endpoints = {"gpt-5.4-mini": ["/responses"]}
        request = _make_request("hi", extra_env={"BREQY_PERSONA": "You are helpful."})
        list(provider.stream(request))

        call_kwargs = mock_client.stream_responses.call_args.kwargs
        assert call_kwargs["instructions"] == "You are helpful."
        # User message should be in input_messages, not system
        input_msgs = call_kwargs["input_messages"]
        assert all(m["role"] != "system" for m in input_msgs)
        assert any(m["role"] == "user" for m in input_msgs)


# --------------------------------------------------------------------------- #
# Tool call argument accumulation
# --------------------------------------------------------------------------- #


class TestToolCallArgumentAccumulation:
    """_do_stream() must accumulate argument chunks across SSE deltas so that
    consumers receive a single tool_call event per call with complete JSON
    arguments, not one event per chunk with partial JSON."""

    def test_chunked_args_yield_single_complete_tool_call_event(self) -> None:
        """Arguments split across multiple SSE chunks must arrive as ONE event.

        The OpenAI streaming protocol splits tool call arguments across many
        delta events.  The runtime calls json.loads() on arguments_chunk, so
        it must receive the full JSON string, not a partial fragment.
        """
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                # First chunk: id + name, empty args
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_abc",
                                        "function": {"name": "shell", "arguments": ""},
                                    }
                                ]
                            },
                            "index": 0,
                        }
                    ]
                },
                # Second chunk: first arg fragment
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [{"index": 0, "function": {"arguments": '{"comman'}}]
                            },
                            "index": 0,
                        }
                    ]
                },
                # Third chunk: second arg fragment
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [{"index": 0, "function": {"arguments": 'd": "ls"}'}}]
                            },
                            "index": 0,
                        }
                    ]
                },
                # Finish
                {"choices": [{"delta": {}, "finish_reason": "tool_calls", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        provider._model_endpoints = {"gpt-4o": ["/chat/completions"]}
        events = list(provider.stream(_make_request("ls")))

        tool_events = [e for e in events if e.kind == "tool_call"]
        # Must be exactly ONE tool_call event (not one per chunk)
        assert len(tool_events) == 1, (
            f"Expected 1 tool_call event with complete args; got {len(tool_events)}"
        )
        assert tool_events[0].tool_call is not None
        assert tool_events[0].tool_call.call_id == "call_abc"
        assert tool_events[0].tool_call.tool_name == "shell"
        # Arguments must be the complete, JSON-parseable string
        import json

        parsed = json.loads(tool_events[0].tool_call.arguments_chunk)
        assert parsed == {"command": "ls"}

    def test_multiple_tool_calls_each_accumulated_separately(self) -> None:
        """When the model requests two tools, each gets its own complete event."""
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                # Tool 0: id + name
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_0",
                                        "function": {"name": "shell", "arguments": '{"c'},
                                    }
                                ]
                            },
                            "index": 0,
                        }
                    ]
                },
                # Tool 1: id + name (simultaneous)
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 1,
                                        "id": "call_1",
                                        "function": {"name": "fs", "arguments": '{"p'},
                                    }
                                ]
                            },
                            "index": 0,
                        }
                    ]
                },
                # Tool 0: rest of args
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"index": 0, "function": {"arguments": 'md": "ls"}'}}
                                ]
                            },
                            "index": 0,
                        }
                    ]
                },
                # Tool 1: rest of args
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"index": 1, "function": {"arguments": 'ath": "/"}'}}
                                ]
                            },
                            "index": 0,
                        }
                    ]
                },
                {"choices": [{"delta": {}, "finish_reason": "tool_calls", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        provider._model_endpoints = {"gpt-4o": ["/chat/completions"]}
        events = list(provider.stream(_make_request("do stuff")))

        tool_events = [e for e in events if e.kind == "tool_call"]
        assert len(tool_events) == 2

        import json

        call_ids = {e.tool_call.call_id for e in tool_events}
        assert call_ids == {"call_0", "call_1"}

        by_id = {e.tool_call.call_id: e for e in tool_events}
        assert json.loads(by_id["call_0"].tool_call.arguments_chunk) == {"cmd": "ls"}
        assert json.loads(by_id["call_1"].tool_call.arguments_chunk) == {"path": "/"}

    def test_text_events_still_yielded_immediately_during_tool_accumulation(self) -> None:
        """Text delta events must still stream out immediately even if tool args
        are being accumulated in the same turn."""
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter(
            [
                {"choices": [{"delta": {"content": "Running..."}, "index": 0}]},
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_x",
                                        "function": {
                                            "name": "shell",
                                            "arguments": '{"command": "ls"}',
                                        },
                                    }
                                ]
                            },
                            "index": 0,
                        }
                    ]
                },
                {"choices": [{"delta": {}, "finish_reason": "tool_calls", "index": 0}]},
            ]
        )

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        provider._model_endpoints = {"gpt-4o": ["/chat/completions"]}
        events = list(provider.stream(_make_request("ls")))

        text_events = [e for e in events if e.kind == "text"]
        assert len(text_events) == 1
        assert text_events[0].text == "Running..."

        tool_events = [e for e in events if e.kind == "tool_call"]
        assert len(tool_events) == 1


class TestProviderEventKind:
    def test_reasoning_started_kind_is_valid(self) -> None:
        from breqy.agents.providers.base import ProviderEvent

        e = ProviderEvent(kind="reasoning_started")
        assert e.kind == "reasoning_started"

    def test_reasoning_done_kind_is_valid(self) -> None:
        from breqy.agents.providers.base import ProviderEvent

        e = ProviderEvent(kind="reasoning_done")
        assert e.kind == "reasoning_done"
