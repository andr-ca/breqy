"""Tests for GitHub Copilot streaming API client."""

from __future__ import annotations

import json
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest


def _make_sse_lines(*data_values: str | dict) -> list[str]:
    """Build SSE text lines from data payloads."""
    lines: list[str] = []
    for value in data_values:
        if isinstance(value, dict):
            lines.append(f"data: {json.dumps(value)}")
        else:
            lines.append(f"data: {value}")
        lines.append("")  # blank line = event boundary
    return lines


def _mock_streaming_response(lines: list[str], status_code: int = 200) -> MagicMock:
    """Create a mock httpx streaming response with iter_lines."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"content-type": "text/event-stream"}
    response.iter_lines.return_value = iter(lines)
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


class TestStreamTextDeltas:
    def test_stream_text_deltas(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {"choices": [{"delta": {"content": "Hello"}, "index": 0}]},
            {"choices": [{"delta": {"content": " world"}, "index": 0}]},
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)

        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        text_chunks = [
            r for r in results if r.get("choices", [{}])[0].get("delta", {}).get("content")
        ]
        assert len(text_chunks) == 2
        assert text_chunks[0]["choices"][0]["delta"]["content"] == "Hello"
        assert text_chunks[1]["choices"][0]["delta"]["content"] == " world"


class TestStreamToolCall:
    def test_stream_tool_call(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
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
                            "tool_calls": [{"index": 0, "function": {"arguments": '{"path":'}}]
                        },
                        "index": 0,
                    }
                ]
            },
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "read file"}],
            )
        )

        tool_chunks = [
            r for r in results if r.get("choices", [{}])[0].get("delta", {}).get("tool_calls")
        ]
        assert len(tool_chunks) == 2


class TestStreamDoneTermination:
    def test_stream_done_termination(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {"choices": [{"delta": {"content": "hi"}, "index": 0}]},
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        # [DONE] should not appear as a parsed result
        for r in results:
            assert isinstance(r, dict)


class TestStreamErrors:
    def test_stream_401_raises_api_error(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

        error_response = MagicMock()
        error_response.status_code = 401
        error_response.iter_text.return_value = iter(["Unauthorized"])
        error_response.headers = {}

        mock_client = MagicMock()
        mock_client.stream.return_value.__enter__ = MagicMock(return_value=error_response)
        mock_client.stream.return_value.__exit__ = MagicMock(return_value=False)

        client = CopilotApiClient(http_client=mock_client)

        with pytest.raises(CopilotApiError) as exc_info:
            list(
                client.stream_chat(
                    token="gho_bad",
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "hi"}],
                )
            )
        assert exc_info.value.status_code == 401
        assert "Unauthorized" in exc_info.value.message

    def test_stream_403_raises_api_error(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

        error_response = MagicMock()
        error_response.status_code = 403
        error_response.iter_text.return_value = iter(["Forbidden"])
        error_response.headers = {}

        mock_client = MagicMock()
        mock_client.stream.return_value.__enter__ = MagicMock(return_value=error_response)
        mock_client.stream.return_value.__exit__ = MagicMock(return_value=False)

        client = CopilotApiClient(http_client=mock_client)

        with pytest.raises(CopilotApiError) as exc_info:
            list(
                client.stream_chat(
                    token="gho_test",
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "hi"}],
                )
            )
        assert exc_info.value.status_code == 403
        assert "Forbidden" in exc_info.value.message

    def test_stream_429_raises_api_error(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

        error_response = MagicMock()
        error_response.status_code = 429
        error_response.iter_text.return_value = iter(["Too Many Requests"])
        error_response.headers = {"retry-after": "30"}

        mock_client = MagicMock()
        mock_client.stream.return_value.__enter__ = MagicMock(return_value=error_response)
        mock_client.stream.return_value.__exit__ = MagicMock(return_value=False)

        client = CopilotApiClient(http_client=mock_client)

        with pytest.raises(CopilotApiError) as exc_info:
            list(
                client.stream_chat(
                    token="gho_test",
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "hi"}],
                )
            )
        assert exc_info.value.status_code == 429
        assert "Too Many Requests" in exc_info.value.message


class TestStreamEmpty:
    def test_stream_empty_response(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        mock_response = _mock_streaming_response(["data: [DONE]", ""])
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
            )
        )
        assert results == []


class TestStreamPartialChunks:
    def test_stream_partial_chunks(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {"choices": [{"delta": {"content": "part1"}, "index": 0}]},
            {"choices": [{"delta": {"content": "part2"}, "index": 0}]},
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        text_chunks = [
            r["choices"][0]["delta"]["content"]
            for r in results
            if r.get("choices", [{}])[0].get("delta", {}).get("content")
        ]
        assert text_chunks == ["part1", "part2"]


class TestOriginatorHeaders:
    """TUI-13: Verify originator identity headers are sent on every request."""

    def test_stream_chat_sends_copilot_integration_id(self) -> None:
        """Copilot-Integration-Id header must be set to 'vscode-chat'."""
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        call_args = mock_client.stream.call_args
        headers = call_args[1]["headers"] if "headers" in call_args[1] else call_args[0][2]
        assert headers["Copilot-Integration-Id"] == "vscode-chat"

    def test_stream_chat_sends_editor_version(self) -> None:
        """Editor-Version header must identify vscode."""
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_chat(
                token="gho_test",
                model="gpt-5.4-mini",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        call_args = mock_client.stream.call_args
        headers = call_args[1]["headers"] if "headers" in call_args[1] else call_args[0][2]
        assert "Editor-Version" in headers
        assert "vscode" in headers["Editor-Version"]

    def test_originator_headers_present_with_tools(self) -> None:
        """Originator headers must also be sent on tool-use follow-up requests."""
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": "read file"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {"name": "read_file", "arguments": "{}"},
                            }
                        ],
                    },
                    {"role": "tool", "tool_call_id": "c1", "content": "file contents"},
                ],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "description": "Read a file",
                            "parameters": {},
                        },
                    }
                ],
            )
        )

        call_args = mock_client.stream.call_args
        headers = call_args[1]["headers"] if "headers" in call_args[1] else call_args[0][2]
        assert headers["Copilot-Integration-Id"] == "vscode-chat"
        assert "vscode" in headers["Editor-Version"]


# --------------------------------------------------------------------------- #
# API version header
# --------------------------------------------------------------------------- #


class TestApiVersionHeader:
    def test_stream_chat_sends_api_version_header(self) -> None:
        """x-github-api-version header must be sent on chat completions."""
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        call_args = mock_client.stream.call_args
        headers = call_args[1]["headers"] if "headers" in call_args[1] else call_args[0][2]
        assert headers.get("x-github-api-version") == "2025-10-01"


# --------------------------------------------------------------------------- #
# Timeout configuration
# --------------------------------------------------------------------------- #


class TestHttpxTimeout:
    def test_default_client_has_long_read_timeout(self) -> None:
        """CopilotApiClient default httpx.Client must have read timeout >= 120s.

        The Copilot API can take >5 seconds to start streaming a response when
        tool definitions are included. The httpx default of 5 seconds is too
        short and causes ReadTimeout errors before any content is received.
        """
        import httpx
        from breqy.agents.providers.copilot_client import CopilotApiClient

        client = CopilotApiClient()
        # Access the internal client to inspect its timeout
        assert client._http_client.timeout.read >= 120.0

    def test_default_client_has_reasonable_connect_timeout(self) -> None:
        """Connect timeout should be set to a reasonable value (>= 10s)."""
        import httpx
        from breqy.agents.providers.copilot_client import CopilotApiClient

        client = CopilotApiClient()
        assert client._http_client.timeout.connect >= 10.0

    def test_custom_http_client_is_used_as_is(self) -> None:
        """When a custom http_client is passed, it must be used without modification."""
        import httpx
        from breqy.agents.providers.copilot_client import CopilotApiClient

        custom_client = httpx.Client(timeout=httpx.Timeout(999.0))
        client = CopilotApiClient(http_client=custom_client)
        assert client._http_client is custom_client


# --------------------------------------------------------------------------- #
# x-initiator header — premium request attribution
# --------------------------------------------------------------------------- #


class TestXInitiatorHeader:
    """x-initiator must be 'user' by default and 'agent' for follow-up tool rounds."""

    def test_stream_chat_x_initiator_defaults_to_user(self) -> None:
        """When initiator is not provided, x-initiator header must be 'user'."""
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_chat(
                token="t",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        headers = mock_client.stream.call_args[1]["headers"]
        assert headers["x-initiator"] == "user"

    def test_stream_chat_sends_agent_x_initiator(self) -> None:
        """When initiator='agent', x-initiator header must be 'agent'."""
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_chat(
                token="t",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                initiator="agent",
            )
        )

        headers = mock_client.stream.call_args[1]["headers"]
        assert headers["x-initiator"] == "agent"

    def test_stream_responses_x_initiator_defaults_to_user(self) -> None:
        """When initiator is not provided, x-initiator header must be 'user' on /responses."""
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_responses(
                token="t",
                model="gpt-5.4-mini",
                input_messages=[{"role": "user", "content": "hi"}],
            )
        )

        headers = mock_client.stream.call_args[1]["headers"]
        assert headers["x-initiator"] == "user"

    def test_stream_responses_sends_agent_x_initiator(self) -> None:
        """When initiator='agent', x-initiator header must be 'agent' on /responses."""
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_responses(
                token="t",
                model="gpt-5.4-mini",
                input_messages=[{"role": "user", "content": "hi"}],
                initiator="agent",
            )
        )

        headers = mock_client.stream.call_args[1]["headers"]
        assert headers["x-initiator"] == "agent"
