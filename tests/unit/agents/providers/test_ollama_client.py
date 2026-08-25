"""Tests for Ollama streaming HTTP client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


def _mock_streaming_response(lines: list[str], status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.iter_lines.return_value = iter(lines)
    response.iter_text.return_value = iter(["".join(lines)])
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


class TestStreamChat:
    def test_stream_text_chunks(self) -> None:
        from breqy.agents.providers.ollama_client import OllamaApiClient

        lines = [
            json.dumps(
                {
                    "model": "llama3.2",
                    "message": {"role": "assistant", "content": "Hello"},
                    "done": False,
                }
            ),
            json.dumps(
                {
                    "model": "llama3.2",
                    "message": {"role": "assistant", "content": " world"},
                    "done": False,
                }
            ),
            json.dumps(
                {
                    "model": "llama3.2",
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "done_reason": "stop",
                }
            ),
        ]
        mock_http = MagicMock()
        mock_http.stream.return_value = _mock_streaming_response(lines)

        client = OllamaApiClient(base_url="http://127.0.0.1:11434", http_client=mock_http)
        chunks = list(
            client.stream_chat(
                model="llama3.2",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        assert len(chunks) == 3
        assert chunks[0]["message"]["content"] == "Hello"
        mock_http.stream.assert_called_once()
        call_kwargs = mock_http.stream.call_args.kwargs
        assert call_kwargs["json"]["stream"] is True
        assert call_kwargs["json"]["model"] == "llama3.2"

    def test_stream_includes_tools_when_provided(self) -> None:
        from breqy.agents.providers.ollama_client import OllamaApiClient

        mock_http = MagicMock()
        mock_http.stream.return_value = _mock_streaming_response(
            [json.dumps({"message": {"role": "assistant", "content": "ok"}, "done": True})]
        )
        tools = [{"type": "function", "function": {"name": "shell", "parameters": {}}}]

        client = OllamaApiClient(http_client=mock_http)
        list(client.stream_chat(model="llama3.2", messages=[], tools=tools))

        body = mock_http.stream.call_args.kwargs["json"]
        assert body["tools"] == tools

    def test_stream_raises_on_http_error(self) -> None:
        from breqy.agents.providers.ollama_client import OllamaApiClient, OllamaApiError

        mock_http = MagicMock()
        mock_http.stream.return_value = _mock_streaming_response(["model not found"], status_code=404)

        client = OllamaApiClient(http_client=mock_http)
        with pytest.raises(OllamaApiError, match="404"):
            list(client.stream_chat(model="missing", messages=[]))


class TestListModels:
    def test_list_models_parses_tags(self) -> None:
        from breqy.agents.providers.ollama_client import OllamaApiClient

        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2:latest", "model": "llama3.2:latest"},
                {"name": "qwen2.5:7b", "model": "qwen2.5:7b"},
            ]
        }
        mock_http.get.return_value = mock_response

        client = OllamaApiClient(base_url="http://127.0.0.1:11434", http_client=mock_http)
        models = client.list_models()

        assert models == [
            ("llama3.2:latest", "llama3.2:latest"),
            ("qwen2.5:7b", "qwen2.5:7b"),
        ]
        mock_http.get.assert_called_once_with(
            "http://127.0.0.1:11434/api/tags",
            timeout=10.0,
        )
