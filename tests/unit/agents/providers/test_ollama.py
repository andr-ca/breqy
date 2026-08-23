"""Tests for OllamaProvider ModelProvider implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock

import pytest

from breqy.agents.providers.base import ModelProvider, ProviderEvent, ProviderRequest, ToolDefinition


def _make_request(prompt: str = "hello", **kwargs) -> ProviderRequest:
    return ProviderRequest(
        prompt=prompt,
        work_dir=Path("/tmp/test"),
        **kwargs,
    )


def _stream_lines(*payloads: dict) -> Iterator[dict]:
    for payload in payloads:
        yield payload


class TestProviderProperties:
    def test_provider_id(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        provider = OllamaProvider(model_id="llama3.2", client=MagicMock())
        assert provider.provider_id == "ollama"

    def test_model_id(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        provider = OllamaProvider(model_id="qwen2.5:7b", client=MagicMock())
        assert provider.model_id == "qwen2.5:7b"

    def test_supports_tool_calls(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        provider = OllamaProvider(model_id="llama3.2", client=MagicMock())
        assert provider.supports_tool_calls is True

    def test_is_model_provider(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        provider = OllamaProvider(model_id="llama3.2", client=MagicMock())
        assert isinstance(provider, ModelProvider)


class TestMessageConversion:
    def test_prompt_to_messages(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        provider = OllamaProvider(model_id="llama3.2", client=MagicMock())
        messages = provider._build_messages(_make_request("what is 2+2?"))
        assert messages == [{"role": "user", "content": "what is 2+2?"}]

    def test_prompt_with_persona(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        provider = OllamaProvider(model_id="llama3.2", client=MagicMock())
        request = _make_request("hello", extra_env={"BREQY_PERSONA": "You are helpful."})
        messages = provider._build_messages(request)
        assert messages == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hello"},
        ]

    def test_conversation_history_translates_tool_results(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        provider = OllamaProvider(model_id="llama3.2", client=MagicMock())
        history = [
            {"role": "user", "content": "run ls"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "shell", "arguments": '{"command":"ls"}'},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "name": "shell",
                "content": "file.txt",
            },
        ]
        messages = provider._build_messages(_make_request("ignored", conversation_history=history))
        assert messages[-1] == {
            "role": "tool",
            "tool_name": "shell",
            "content": "file.txt",
        }


class TestStreamMapping:
    def test_stream_maps_text_and_completion(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        client = MagicMock()
        client.stream_chat.return_value = _stream_lines(
            {"message": {"role": "assistant", "content": "Hello"}, "done": False},
            {"message": {"role": "assistant", "content": " there"}, "done": False},
            {
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "stop",
            },
        )
        provider = OllamaProvider(model_id="llama3.2", client=client)

        events = list(provider.stream(_make_request("hi")))

        assert [event.text for event in events if event.kind == "text"] == ["Hello", " there"]
        completion = next(event for event in events if event.kind == "complete")
        assert completion.metadata is not None
        assert completion.metadata.exit_code == 0
        assert completion.metadata.provider_id == "ollama"

    def test_stream_maps_tool_calls_on_done(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        client = MagicMock()
        client.stream_chat.return_value = _stream_lines(
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "shell",
                                "arguments": {"command": "ls -la"},
                            }
                        }
                    ],
                },
                "done": True,
                "done_reason": "stop",
            },
        )
        provider = OllamaProvider(model_id="llama3.2", client=client)

        events = list(
            provider.stream(
                _make_request(
                    "list files",
                    tools=[
                        ToolDefinition(
                            name="shell",
                            description="run shell",
                            input_schema={"type": "object"},
                        )
                    ],
                )
            )
        )

        tool_event = next(event for event in events if event.kind == "tool_call")
        assert tool_event.tool_call is not None
        assert tool_event.tool_call.tool_name == "shell"
        assert json.loads(tool_event.tool_call.arguments_chunk) == {"command": "ls -la"}

    def test_list_models_delegates_to_client(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        client = MagicMock()
        client.list_models.return_value = [("llama3.2", "llama3.2")]
        provider = OllamaProvider(model_id="llama3.2", client=client)

        assert provider.list_models() == [("llama3.2", "llama3.2")]

    def test_list_models_falls_back_on_error(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        client = MagicMock()
        client.list_models.side_effect = RuntimeError("connection refused")
        provider = OllamaProvider(model_id="llama3.2", client=client)

        assert provider.list_models() == [("llama3.2", "llama3.2")]
