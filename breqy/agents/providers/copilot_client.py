"""GitHub Copilot streaming chat completions API client."""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class CopilotApiError(Exception):
    """Raised on API-level errors (HTTP 4xx/5xx)."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"Copilot API error {status_code}: {message}")


class CopilotApiClient:
    """Streaming HTTP client for GitHub Copilot chat completions."""

    BASE_URL: str = "https://api.githubcopilot.com"

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client or httpx.Client()

    def stream_chat(
        self,
        *,
        token: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream chat completions. Yields parsed SSE chunk dicts."""
        url = f"{self.BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "breqy/0.1.0",
            "Copilot-Integration-Id": "breqy",
            "Editor-Version": "breqy/0.1.0",
            "Openai-Intent": "conversation-edits",
            "x-initiator": "user",
            "Accept": "text/event-stream",
        }
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if tools is not None:
            body["tools"] = tools

        logger.debug(
            "copilot_api_request",
            model=model,
            message_count=len(messages),
            has_tools=bool(tools),
            body_keys=list(body.keys()),
        )

        with self._http_client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code >= 400:
                error_text = ""
                try:
                    for chunk in response.iter_text():
                        error_text += chunk
                except Exception:
                    error_text = f"HTTP {response.status_code}"
                logger.warning(
                    "copilot_api_error",
                    status_code=response.status_code,
                    model=model,
                    error_body=error_text[:500],
                    response_headers=dict(response.headers),
                )
                raise CopilotApiError(response.status_code, error_text)

            yield from self._parse_sse(response)

    def _parse_sse(self, response: httpx.Response) -> Iterator[dict[str, Any]]:
        """Parse SSE stream from httpx response."""
        for line in response.iter_lines():
            if not line:
                continue

            if not line.startswith("data: "):
                continue

            data = line[6:]  # strip "data: " prefix

            if data == "[DONE]":
                logger.debug("copilot_sse_done")
                return

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("copilot_sse_parse_error", data=data[:100])
                continue

            yield chunk
