"""Ollama local model server HTTP client."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_BASE_URL = "http://127.0.0.1:11434"
_DEFAULT_TIMEOUT = httpx.Timeout(read=300.0, connect=5.0, write=30.0, pool=5.0)


class OllamaApiError(Exception):
    """Raised on Ollama HTTP errors."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"Ollama API error {status_code}: {message}")


def resolve_ollama_base_url(base_url: str | None = None) -> str:
    """Resolve Ollama server URL from explicit value or ``OLLAMA_HOST``."""
    if base_url:
        return base_url.rstrip("/")
    host = os.environ.get("OLLAMA_HOST", _DEFAULT_BASE_URL).strip()
    if not host:
        return _DEFAULT_BASE_URL
    if host.startswith(("http://", "https://")):
        return host.rstrip("/")
    return f"http://{host}".rstrip("/")


class OllamaApiClient:
    """Streaming HTTP client for Ollama ``/api/chat`` and ``/api/tags``."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._base_url = resolve_ollama_base_url(base_url)
        self._http_client = http_client or httpx.Client(timeout=_DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        return self._base_url

    def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream chat completions. Yields parsed NDJSON chunk dicts."""
        url = f"{self._base_url}/api/chat"
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if tools is not None:
            body["tools"] = tools

        logger.debug(
            "ollama_api_request",
            model=model,
            message_count=len(messages),
            has_tools=bool(tools),
            base_url=self._base_url,
        )

        with self._http_client.stream("POST", url, json=body) as response:
            if response.status_code >= 400:
                error_text = ""
                try:
                    for chunk in response.iter_text():
                        error_text += chunk
                except (httpx.HTTPError, OSError):
                    error_text = f"HTTP {response.status_code}"
                logger.warning(
                    "ollama_api_error",
                    status_code=response.status_code,
                    model=model,
                    error_body=error_text[:500],
                )
                raise OllamaApiError(response.status_code, error_text)

            yield from self._parse_ndjson(response)

    def list_models(self) -> list[tuple[str, str]]:
        """Return installed models as (model_id, display_name) pairs."""
        url = f"{self._base_url}/api/tags"
        response = self._http_client.get(url, timeout=10.0)
        if response.status_code >= 400:
            raise OllamaApiError(response.status_code, response.text[:500])
        data = response.json()
        models: list[tuple[str, str]] = []
        for entry in data.get("models", []):
            model_id = entry.get("name") or entry.get("model")
            if not isinstance(model_id, str) or not model_id:
                continue
            models.append((model_id, model_id))
        return models

    def _parse_ndjson(self, response: httpx.Response) -> Iterator[dict[str, Any]]:
        for line in response.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("ollama_ndjson_parse_error", data=line[:100])
                continue
            if isinstance(chunk, dict):
                yield chunk
