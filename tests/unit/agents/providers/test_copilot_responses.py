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


class TestStreamResponsesReasoningParam:
    """stream_responses must send reasoning: {summary: auto} in the request body."""

    def test_stream_responses_sends_reasoning_summary_auto(self) -> None:
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
        assert "reasoning" in body, "reasoning key missing from request body"
        assert body["reasoning"] == {"summary": "auto"}, (
            f"Expected reasoning={{summary: auto}}, got {body['reasoning']}"
        )


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


class TestStreamResponsesReasoningTextDelta:
    """_do_stream_responses emits reasoning_text events for response.reasoning_summary_text.delta."""

    def _make_provider(self):
        from breqy.agents.providers.copilot import CopilotProvider
        from unittest.mock import MagicMock

        authenticator = MagicMock()
        authenticator.get_copilot_token.return_value = "tok"
        return CopilotProvider(
            model_id="gpt-5.4-mini", authenticator=authenticator, client=MagicMock()
        )

    def test_reasoning_summary_text_delta_yields_reasoning_text_event(self) -> None:
        from breqy.agents.providers.base import ProviderRequest
        from pathlib import Path

        reasoning_delta_1 = {
            "type": "response.reasoning_summary_text.delta",
            "delta": "First thought",
        }
        reasoning_delta_2 = {
            "type": "response.reasoning_summary_text.delta",
            "delta": " continues here",
        }
        completed = {"type": "response.completed", "response": {"status": "completed"}}

        provider = self._make_provider()
        provider._client.stream_responses.return_value = iter(
            [reasoning_delta_1, reasoning_delta_2, completed]
        )

        request = ProviderRequest(prompt="hi", work_dir=Path("/tmp"))
        events = list(provider._do_stream_responses("tok", request))

        reasoning_text_events = [e for e in events if e.kind == "reasoning_text"]
        assert len(reasoning_text_events) == 2
        assert reasoning_text_events[0].text == "First thought"
        assert reasoning_text_events[1].text == " continues here"

    def test_empty_reasoning_delta_is_not_yielded(self) -> None:
        """Empty or missing delta strings must not produce reasoning_text events."""
        from breqy.agents.providers.base import ProviderRequest
        from pathlib import Path

        reasoning_delta_empty = {
            "type": "response.reasoning_summary_text.delta",
            "delta": "",
        }
        completed = {"type": "response.completed", "response": {"status": "completed"}}

        provider = self._make_provider()
        provider._client.stream_responses.return_value = iter([reasoning_delta_empty, completed])

        request = ProviderRequest(prompt="hi", work_dir=Path("/tmp"))
        events = list(provider._do_stream_responses("tok", request))

        reasoning_text_events = [e for e in events if e.kind == "reasoning_text"]
        assert reasoning_text_events == []


# --------------------------------------------------------------------------- #
# _build_responses_input: multi-turn tool history translation
# --------------------------------------------------------------------------- #


class TestBuildResponsesInputToolHistory:
    """Verify _build_responses_input translates Chat Completions tool history to Responses API format.

    The runtime builds conversation_history in Chat Completions format:
      {"role": "assistant", "content": None, "tool_calls": [{...}]}
      {"role": "tool", "tool_call_id": "...", "name": "...", "content": "..."}

    The Responses API rejects content: null and does not understand "role: tool".
    _build_responses_input must translate to:
      {"type": "function_call", "call_id": "...", "name": "...", "arguments": "..."}
      {"type": "function_call_output", "call_id": "...", "output": "..."}
    """

    def _make_provider(self):
        from unittest.mock import MagicMock
        from breqy.agents.providers.copilot import CopilotProvider

        return CopilotProvider(
            model_id="gpt-5.4-mini",
            authenticator=MagicMock(),
            client=MagicMock(),
        )

    def test_plain_user_message_becomes_single_input_item(self) -> None:
        """With no conversation_history, input is a single user message."""
        from pathlib import Path
        from breqy.agents.providers.base import ProviderRequest

        provider = self._make_provider()
        request = ProviderRequest(prompt="hello", work_dir=Path("/tmp"))
        input_messages, _ = provider._build_responses_input(request)

        assert input_messages == [{"role": "user", "content": "hello"}]

    def test_assistant_tool_call_with_null_content_is_translated(self) -> None:
        """Chat Completions assistant tool-call item (content=None) becomes function_call type."""
        import json
        from pathlib import Path
        from breqy.agents.providers.base import ProviderRequest

        history = [
            {"role": "user", "content": "run ls"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {"name": "shell", "arguments": '{"command": "ls"}'},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_abc",
                "name": "shell",
                "content": "file1.txt\nfile2.txt",
            },
        ]
        provider = self._make_provider()
        request = ProviderRequest(
            prompt="run ls", work_dir=Path("/tmp"), conversation_history=history
        )
        input_messages, _ = provider._build_responses_input(request)

        # The assistant tool-call message must NOT appear with content=null
        for msg in input_messages:
            assert msg.get("content") is not None or msg.get("type") in (
                "function_call",
                "function_call_output",
            ), f"Found null content in non-translated message: {msg}"

        # Must contain a function_call item
        fc_items = [m for m in input_messages if m.get("type") == "function_call"]
        assert len(fc_items) == 1
        assert fc_items[0]["call_id"] == "call_abc"
        assert fc_items[0]["name"] == "shell"
        assert json.loads(fc_items[0]["arguments"]) == {"command": "ls"}

        # Must contain a function_call_output item
        fco_items = [m for m in input_messages if m.get("type") == "function_call_output"]
        assert len(fco_items) == 1
        assert fco_items[0]["call_id"] == "call_abc"
        assert fco_items[0]["output"] == "file1.txt\nfile2.txt"

    def test_regular_user_and_assistant_messages_are_preserved(self) -> None:
        """User and assistant text messages in history are preserved as-is."""
        from pathlib import Path
        from breqy.agents.providers.base import ProviderRequest

        history = [
            {"role": "user", "content": "First question."},
            {"role": "assistant", "content": "First answer."},
            {"role": "user", "content": "Second question."},
        ]
        provider = self._make_provider()
        request = ProviderRequest(
            prompt="Second question.", work_dir=Path("/tmp"), conversation_history=history
        )
        input_messages, _ = provider._build_responses_input(request)

        assert input_messages == history

    def test_multiple_tool_calls_in_one_round_are_all_translated(self) -> None:
        """When there are multiple tool_calls in one assistant message, each becomes a function_call."""
        from pathlib import Path
        from breqy.agents.providers.base import ProviderRequest

        history = [
            {"role": "user", "content": "do two things"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "shell", "arguments": '{"command": "ls"}'},
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "shell", "arguments": '{"command": "pwd"}'},
                    },
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "name": "shell",
                "content": "file.txt",
            },
            {
                "role": "tool",
                "tool_call_id": "call_2",
                "name": "shell",
                "content": "/home/user",
            },
        ]
        provider = self._make_provider()
        request = ProviderRequest(
            prompt="do two things", work_dir=Path("/tmp"), conversation_history=history
        )
        input_messages, _ = provider._build_responses_input(request)

        fc_items = [m for m in input_messages if m.get("type") == "function_call"]
        fco_items = [m for m in input_messages if m.get("type") == "function_call_output"]
        assert len(fc_items) == 2
        assert len(fco_items) == 2
        assert {m["call_id"] for m in fc_items} == {"call_1", "call_2"}
        assert {m["call_id"] for m in fco_items} == {"call_1", "call_2"}
