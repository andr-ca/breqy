"""GitHub Copilot streaming API client (chat completions + responses)."""

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
    """Streaming HTTP client for GitHub Copilot chat completions and responses."""

    BASE_URL: str = "https://api.githubcopilot.com"

    # Streaming responses with tool definitions can take >5 s for first byte.
    # Use a generous read timeout; keep connect short to fail fast on network issues.
    _DEFAULT_TIMEOUT: httpx.Timeout = httpx.Timeout(read=120.0, connect=15.0, write=30.0, pool=5.0)

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client or httpx.Client(timeout=self._DEFAULT_TIMEOUT)

    def stream_chat(
        self,
        *,
        token: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        initiator: str = "user",
    ) -> Iterator[dict[str, Any]]:
        """Stream chat completions. Yields parsed SSE chunk dicts."""
        url = f"{self.BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "GitHubCopilotChat/0.22.2",
            "Copilot-Integration-Id": "vscode-chat",
            "Editor-Version": "vscode/1.97.2",
            "Editor-Plugin-Version": "copilot-chat/0.22.2",
            "Openai-Intent": "conversation-panel",
            "x-initiator": initiator,
            "x-github-api-version": "2025-10-01",
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
            initiator=initiator,
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

    def stream_responses(
        self,
        *,
        token: str,
        model: str,
        input_messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        instructions: str | None = None,
        initiator: str = "user",
    ) -> Iterator[dict[str, Any]]:
        """Stream from the Responses API. Yields parsed SSE event dicts."""
        url = f"{self.BASE_URL}/responses"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "GitHubCopilotChat/0.22.2",
            "Copilot-Integration-Id": "vscode-chat",
            "Editor-Version": "vscode/1.97.2",
            "Editor-Plugin-Version": "copilot-chat/0.22.2",
            "Openai-Intent": "conversation-panel",
            "x-initiator": initiator,
            "x-github-api-version": "2025-10-01",
            "Accept": "text/event-stream",
        }
        body: dict[str, Any] = {
            "model": model,
            "input": input_messages,
            "stream": True,
        }
        if tools is not None:
            body["tools"] = tools
        if instructions is not None:
            body["instructions"] = instructions

        logger.debug(
            "copilot_responses_api_request",
            model=model,
            input_count=len(input_messages),
            has_tools=bool(tools),
            initiator=initiator,
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
                    "copilot_responses_api_error",
                    status_code=response.status_code,
                    model=model,
                    error_body=error_text[:500],
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
