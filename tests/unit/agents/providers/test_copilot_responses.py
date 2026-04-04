"""Tests for Copilot Responses API streaming client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


def _make_sse_lines(*data_values: str | dict) -> list[str]:
    """Build SSE text lines from data payloads."""
    lines: list[str] = []
    for value in data_values:
        if isinstance(value, dict):
            lines.append(f"data: {json.dumps(value)}")
        else:
            lines.append(f"data: {value}")
        lines.append("")
    return lines


def _mock_streaming_response(lines: list[str], status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"content-type": "text/event-stream"}
    response.iter_lines.return_value = iter(lines)
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


class TestStreamResponsesTextDelta:
    def test_yields_text_delta_events(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {"type": "response.output_text.delta", "delta": "Hello"},
            {"type": "response.output_text.delta", "delta": " world"},
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"total_tokens": 50},
                    "model": "gpt-5.4-mini",
                },
            },
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_responses(
                token="gho_test",
                model="gpt-5.4-mini",
                input_messages=[{"role": "user", "content": "hi"}],
            )
        )

        text_events = [r for r in results if r.get("type") == "response.output_text.delta"]
        assert len(text_events) == 2
        assert text_events[0]["delta"] == "Hello"
        assert text_events[1]["delta"] == " world"


class TestStreamResponsesToolCall:
    def test_yields_tool_call_output_item(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "read_file",
                    "arguments": '{"path": "/tmp/test"}',
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"total_tokens": 30},
                    "model": "gpt-5.4-mini",
                },
            },
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_responses(
                token="gho_test",
                model="gpt-5.4-mini",
                input_messages=[{"role": "user", "content": "read file"}],
            )
        )

        tool_events = [
            r
            for r in results
            if r.get("type") == "response.output_item.done"
            and r.get("item", {}).get("type") == "function_call"
        ]
        assert len(tool_events) == 1
        assert tool_events[0]["item"]["call_id"] == "call_1"


class TestStreamResponsesCompleted:
    def test_completed_event_yielded(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {"type": "response.output_text.delta", "delta": "hi"},
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"total_tokens": 10},
                    "model": "gpt-5.4-mini",
                },
            },
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_responses(
                token="gho_test",
                model="gpt-5.4-mini",
                input_messages=[{"role": "user", "content": "hi"}],
            )
        )

        completed = [r for r in results if r.get("type") == "response.completed"]
        assert len(completed) == 1


class TestStreamResponsesRequestFormat:
    def test_sends_correct_url(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_responses(
                token="gho_test",
                model="gpt-5.4-mini",
                input_messages=[{"role": "user", "content": "hi"}],
            )
        )

        call_args = mock_client.stream.call_args
        url = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("url")
        assert "/responses" in url
        assert "/chat/completions" not in url

    def test_sends_input_not_messages(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_responses(
                token="gho_test",
                model="gpt-5.4-mini",
                input_messages=[{"role": "user", "content": "hi"}],
            )
        )

        call_args = mock_client.stream.call_args
        body = call_args[1].get("json", {})
        assert "input" in body
        assert "messages" not in body

    def test_sends_api_version_header(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_responses(
                token="gho_test",
                model="gpt-5.4-mini",
                input_messages=[{"role": "user", "content": "hi"}],
            )
        )

        call_args = mock_client.stream.call_args
        headers = call_args[1]["headers"]
        assert headers.get("x-github-api-version") == "2025-10-01"


class TestStreamResponsesErrors:
    def test_400_raises_api_error(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

        error_response = MagicMock()
        error_response.status_code = 400
        error_response.iter_text.return_value = iter(["Bad Request"])
        error_response.headers = {}

        mock_client = MagicMock()
        mock_client.stream.return_value.__enter__ = MagicMock(return_value=error_response)
        mock_client.stream.return_value.__exit__ = MagicMock(return_value=False)

        client = CopilotApiClient(http_client=mock_client)
        with pytest.raises(CopilotApiError) as exc_info:
            list(
                client.stream_responses(
                    token="gho_test",
                    model="bad-model",
                    input_messages=[{"role": "user", "content": "hi"}],
                )
            )
        assert exc_info.value.status_code == 400


class TestStreamResponsesTools:
    def test_tools_included_in_request(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        tools = [
            {
                "type": "function",
                "name": "read_file",
                "description": "Read a file",
                "parameters": {},
            }
        ]

        client = CopilotApiClient(http_client=mock_client)
        list(
            client.stream_responses(
                token="gho_test",
                model="gpt-5.4-mini",
                input_messages=[{"role": "user", "content": "hi"}],
                tools=tools,
            )
        )

        call_args = mock_client.stream.call_args
        body = call_args[1].get("json", {})
        assert "tools" in body
        assert body["tools"] == tools


class TestStreamResponsesReasoningItem:
    """_do_stream_responses emits reasoning_started / reasoning_done for reasoning output items."""

    def _make_provider(self) -> "CopilotProvider":
        from breqy.agents.providers.copilot import CopilotProvider
        from unittest.mock import MagicMock

        authenticator = MagicMock()
        authenticator.get_copilot_token.return_value = "tok"
        client = MagicMock()
        return CopilotProvider(model_id="gpt-5-mini", authenticator=authenticator, client=client)

    def _make_sse(self, *events) -> list[str]:
        import json

        lines = []
        for ev in events:
            lines.append(f"data: {json.dumps(ev)}")
            lines.append("")
        return lines

    def test_reasoning_output_item_emits_reasoning_started_then_done(self) -> None:
        from unittest.mock import MagicMock, patch
        from breqy.agents.providers.base import ProviderEvent, ProviderRequest
        from pathlib import Path

        reasoning_added = {
            "type": "response.output_item.added",
            "item": {"id": "r1", "type": "reasoning", "summary": []},
            "output_index": 0,
        }
        reasoning_done = {
            "type": "response.output_item.done",
            "item": {"id": "r1", "type": "reasoning", "summary": []},
            "output_index": 0,
        }
        text_delta = {"type": "response.output_text.delta", "delta": "Hello"}
        completed = {"type": "response.completed", "response": {"status": "completed"}}

        lines = self._make_sse(reasoning_added, reasoning_done, text_delta, completed, "[DONE]")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = iter(lines)
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        provider = self._make_provider()
        provider._client.stream_responses.return_value = iter(
            [
                reasoning_added,
                reasoning_done,
                text_delta,
                completed,
            ]
        )

        request = ProviderRequest(prompt="hi", work_dir=Path("/tmp"))
        events = list(provider._do_stream_responses("tok", request))

        kinds = [e.kind for e in events]
        assert "reasoning_started" in kinds
        assert "reasoning_done" in kinds
        # reasoning_started must come before reasoning_done
        assert kinds.index("reasoning_started") < kinds.index("reasoning_done")

    def test_non_reasoning_output_item_does_not_emit_reasoning_events(self) -> None:
        from breqy.agents.providers.base import ProviderRequest
        from pathlib import Path

        function_call_done = {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": "c1",
                "name": "read_file",
                "arguments": '{"path": "/tmp/x"}',
            },
        }
        completed = {"type": "response.completed", "response": {"status": "completed"}}

        provider = self._make_provider()
        provider._client.stream_responses.return_value = iter(
            [
                function_call_done,
                completed,
            ]
        )

        request = ProviderRequest(prompt="hi", work_dir=Path("/tmp"))
        events = list(provider._do_stream_responses("tok", request))

        kinds = [e.kind for e in events]
        assert "reasoning_started" not in kinds
        assert "reasoning_done" not in kinds
