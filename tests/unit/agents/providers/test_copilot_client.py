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


def _mock_streaming_response(
    lines: list[str], status_code: int = 200
) -> MagicMock:
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

        text_chunks = [r for r in results if r.get("choices", [{}])[0].get("delta", {}).get("content")]
        assert len(text_chunks) == 2
        assert text_chunks[0]["choices"][0]["delta"]["content"] == "Hello"
        assert text_chunks[1]["choices"][0]["delta"]["content"] == " world"


class TestStreamToolCall:
    def test_stream_tool_call(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "read_file", "arguments": ""}}]}, "index": 0}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"path":'}}]}, "index": 0}]},
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
            r for r in results
            if r.get("choices", [{}])[0].get("delta", {}).get("tool_calls")
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
