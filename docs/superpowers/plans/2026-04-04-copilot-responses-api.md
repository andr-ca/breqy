# Copilot Responses API Support

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable models like `gpt-5.4-mini` that only support the `/responses` endpoint (not `/chat/completions`) to work through the Copilot provider, by adding Responses API streaming support alongside the existing Chat Completions path.

**Architecture:** The Copilot `/models` API returns per-model metadata including `capabilities.type`, `model_picker_enabled`, and `supported_endpoints` (e.g. `["/chat/completions"]` or `["/responses"]` or both). Currently `list_models()` ignores all of this and returns every model. The fix: (1) filter models to `capabilities.type == "chat"` and `model_picker_enabled == True`; (2) return endpoint metadata alongside models so the provider knows which API to use; (3) add a `stream_responses()` method to `CopilotApiClient` for the Responses API SSE protocol; (4) add a `_do_stream_responses()` method to `CopilotProvider` that maps Responses API events to `ProviderEvent`; (5) route to the correct streaming method based on endpoint metadata. Also add `x-github-api-version: 2025-10-01` header to all Copilot API calls.

**Tech Stack:** Python 3.12, httpx, pydantic, structlog, pytest

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `breqy/agents/providers/copilot.py` | Filter models, store endpoint metadata, route stream to correct API |
| Modify | `breqy/agents/providers/copilot_client.py` | Add `stream_responses()` method, add API version header |
| Modify | `breqy/agents/providers/copilot_auth.py` | Add `x-github-api-version` header to token exchange |
| Modify | `breqy/domain/models.py` | Add `supported_endpoints` field to `ModelEntry` (optional list) |
| Modify | `tests/unit/agents/providers/test_list_models.py` | Update tests for filtering + endpoint metadata |
| Create | `tests/unit/agents/providers/test_copilot_responses.py` | Tests for Responses API streaming |
| Modify | `tests/unit/agents/providers/test_copilot_client.py` | Tests for `stream_responses()` |
| Modify | `tests/unit/agents/providers/test_copilot.py` | Tests for endpoint routing in provider |

---

### Task 1: Filter models by capabilities and model_picker_enabled

The `/models` API returns models with:
```json
{
  "id": "gpt-4o",
  "name": "GPT-4o",
  "capabilities": {"type": "chat", ...},
  "model_picker_enabled": true,
  "supported_endpoints": ["/chat/completions", "/responses"],
  "version": "2025-03-01"
}
```

Models without `capabilities.type == "chat"` or with `model_picker_enabled == false` should be filtered out. The `supported_endpoints` list should be returned alongside each model for routing.

**Files:**
- Modify: `breqy/agents/providers/copilot.py:61-93` (`list_models`)
- Modify: `tests/unit/agents/providers/test_list_models.py`

- [ ] **Step 1: Write failing test — filter by capabilities.type**

Add to `tests/unit/agents/providers/test_list_models.py`:

```python
class TestCopilotListModelsFiltering:
    """CopilotProvider.list_models() filters by capabilities and model_picker_enabled."""

    def _make_provider(self, *, authenticator=None, client=None):
        from breqy.agents.providers.copilot import CopilotProvider
        return CopilotProvider(
            model_id="gpt-4o",
            authenticator=authenticator or MagicMock(),
            client=client or MagicMock(),
        )

    def test_filters_out_non_chat_models(self):
        """Models without capabilities.type == 'chat' are excluded."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4o", "name": "GPT-4o", "capabilities": {"type": "chat"}, "model_picker_enabled": True},
                {"id": "text-embedding-ada", "name": "Ada Embedding", "capabilities": {"type": "embeddings"}, "model_picker_enabled": True},
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        model_ids = [m[0] for m in result]
        assert "gpt-4o" in model_ids
        assert "text-embedding-ada" not in model_ids

    def test_filters_out_model_picker_disabled(self):
        """Models with model_picker_enabled == false are excluded."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4o", "name": "GPT-4o", "capabilities": {"type": "chat"}, "model_picker_enabled": True},
                {"id": "gpt-internal", "name": "Internal", "capabilities": {"type": "chat"}, "model_picker_enabled": False},
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        model_ids = [m[0] for m in result]
        assert "gpt-4o" in model_ids
        assert "gpt-internal" not in model_ids

    def test_graceful_with_missing_capabilities(self):
        """Models without capabilities field are excluded (defensive)."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4o", "name": "GPT-4o", "capabilities": {"type": "chat"}, "model_picker_enabled": True},
                {"id": "mystery", "name": "Mystery Model"},
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        model_ids = [m[0] for m in result]
        assert "gpt-4o" in model_ids
        assert "mystery" not in model_ids

    def test_deduplicates_by_name_keeping_highest_version(self):
        """When multiple models share a name, keep the one with highest version."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4o-2024-08-06", "name": "GPT-4o", "capabilities": {"type": "chat"}, "model_picker_enabled": True, "version": "2024-08-06"},
                {"id": "gpt-4o-2025-03-01", "name": "GPT-4o", "capabilities": {"type": "chat"}, "model_picker_enabled": True, "version": "2025-03-01"},
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        model_ids = [m[0] for m in result]
        assert "gpt-4o-2025-03-01" in model_ids
        assert "gpt-4o-2024-08-06" not in model_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/agents/providers/test_list_models.py::TestCopilotListModelsFiltering -v`
Expected: FAIL — current code does not filter

- [ ] **Step 3: Implement model filtering in list_models()**

Update `breqy/agents/providers/copilot.py` `list_models()`:

```python
def list_models(self) -> list[tuple[str, str]]:
    """Query Copilot API for available models.

    Filters to models with capabilities.type == 'chat' and
    model_picker_enabled == True. Deduplicates by name, keeping
    the highest version.
    """
    token = self._authenticator.get_copilot_token()
    if token is None:
        return [(self.model_id, self.model_id)]
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Copilot-Integration-Id": "vscode-chat",
        "Editor-Version": "vscode/1.97.2",
        "Editor-Plugin-Version": "copilot-chat/0.22.2",
        "User-Agent": "GitHubCopilotChat/0.22.2",
        "x-github-api-version": "2025-10-01",
    }
    try:
        resp = httpx.get(
            "https://api.githubcopilot.com/models",
            headers=headers,
            timeout=10.0,
        )
        if resp.status_code != 200:
            logger.debug(
                "copilot_list_models_non_200",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
            return [(self.model_id, self.model_id)]
        data = resp.json()
        raw_models = data.get("data", [])

        # Filter: chat models with model_picker_enabled
        chat_models = []
        for m in raw_models:
            caps = m.get("capabilities", {})
            if caps.get("type") != "chat":
                continue
            if not m.get("model_picker_enabled", False):
                continue
            chat_models.append(m)

        # Deduplicate by name, keeping highest version
        name_map: dict[str, dict] = {}
        for m in chat_models:
            name = m.get("name", m["id"])
            existing = name_map.get(name)
            if existing is None or m.get("version", "") > existing.get("version", ""):
                name_map[name] = m

        # Store endpoint metadata for routing
        self._model_endpoints: dict[str, list[str]] = {}
        models = []
        for m in name_map.values():
            model_id = m["id"]
            display_name = m.get("name", model_id)
            self._model_endpoints[model_id] = m.get("supported_endpoints", ["/chat/completions"])
            models.append((model_id, display_name))

        logger.debug("copilot_list_models_ok", count=len(models), total_raw=len(raw_models))
        return models
    except Exception:
        logger.debug("copilot_list_models_failed", exc_info=True)
        return [(self.model_id, self.model_id)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/agents/providers/test_list_models.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add breqy/agents/providers/copilot.py tests/unit/agents/providers/test_list_models.py
git commit -m "feat(copilot): filter model list by capabilities.type and model_picker_enabled"
```

---

### Task 2: Add x-github-api-version header to all Copilot API calls

CopilotChat.nvim sends `x-github-api-version: 2025-10-01` on all requests. This may affect which models are returned and which endpoints are available.

**Files:**
- Modify: `breqy/agents/providers/copilot_client.py:42-51` (headers in `stream_chat`)
- Modify: `breqy/agents/providers/copilot_auth.py:95-103` (headers in token exchange)
- Modify: `tests/unit/agents/providers/test_copilot_client.py` (header assertion)

- [ ] **Step 1: Write failing test — API version header in stream_chat**

Add to `tests/unit/agents/providers/test_copilot_client.py`:

```python
class TestApiVersionHeader:
    def test_stream_chat_sends_api_version_header(self) -> None:
        """x-github-api-version header must be sent on chat completions."""
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        list(client.stream_chat(
            token="gho_test", model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
        ))

        call_args = mock_client.stream.call_args
        headers = call_args[1]["headers"] if "headers" in call_args[1] else call_args[0][2]
        assert headers.get("x-github-api-version") == "2025-10-01"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agents/providers/test_copilot_client.py::TestApiVersionHeader -v`
Expected: FAIL (header not present)

- [ ] **Step 3: Add header to stream_chat and token exchange**

In `copilot_client.py`, add `"x-github-api-version": "2025-10-01"` to `stream_chat` headers.

In `copilot_auth.py`, add `"x-github-api-version": "2025-10-01"` to `get_copilot_token` headers.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/agents/providers/test_copilot_client.py tests/unit/agents/providers/test_copilot_auth.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add breqy/agents/providers/copilot_client.py breqy/agents/providers/copilot_auth.py tests/unit/agents/providers/test_copilot_client.py
git commit -m "feat(copilot): add x-github-api-version header to all API calls"
```

---

### Task 3: Add stream_responses() to CopilotApiClient

The Responses API uses `POST /responses` with a different body format (`input` instead of `messages`) and different SSE event schema (events have a `type` field like `response.output_text.delta`, `response.output_item.done`, `response.completed`).

**Files:**
- Modify: `breqy/agents/providers/copilot_client.py`
- Create: `tests/unit/agents/providers/test_copilot_responses.py`

- [ ] **Step 1: Write failing tests for stream_responses()**

Create `tests/unit/agents/providers/test_copilot_responses.py`:

```python
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
            {"type": "response.completed", "response": {"status": "completed", "usage": {"total_tokens": 50}, "model": "gpt-5.4-mini"}},
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(client.stream_responses(
            token="gho_test", model="gpt-5.4-mini",
            input_messages=[{"role": "user", "content": "hi"}],
        ))

        text_events = [r for r in results if r.get("type") == "response.output_text.delta"]
        assert len(text_events) == 2
        assert text_events[0]["delta"] == "Hello"
        assert text_events[1]["delta"] == " world"


class TestStreamResponsesToolCall:
    def test_yields_tool_call_output_item(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {"type": "response.output_item.done", "item": {
                "type": "function_call",
                "call_id": "call_1",
                "name": "read_file",
                "arguments": '{"path": "/tmp/test"}',
            }},
            {"type": "response.completed", "response": {"status": "completed", "usage": {"total_tokens": 30}, "model": "gpt-5.4-mini"}},
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(client.stream_responses(
            token="gho_test", model="gpt-5.4-mini",
            input_messages=[{"role": "user", "content": "read file"}],
        ))

        tool_events = [r for r in results if r.get("type") == "response.output_item.done"
                       and r.get("item", {}).get("type") == "function_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["item"]["call_id"] == "call_1"


class TestStreamResponsesCompleted:
    def test_completed_event_yielded(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {"type": "response.output_text.delta", "delta": "hi"},
            {"type": "response.completed", "response": {"status": "completed", "usage": {"total_tokens": 10}, "model": "gpt-5.4-mini"}},
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(client.stream_responses(
            token="gho_test", model="gpt-5.4-mini",
            input_messages=[{"role": "user", "content": "hi"}],
        ))

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
        list(client.stream_responses(
            token="gho_test", model="gpt-5.4-mini",
            input_messages=[{"role": "user", "content": "hi"}],
        ))

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
        list(client.stream_responses(
            token="gho_test", model="gpt-5.4-mini",
            input_messages=[{"role": "user", "content": "hi"}],
        ))

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
        list(client.stream_responses(
            token="gho_test", model="gpt-5.4-mini",
            input_messages=[{"role": "user", "content": "hi"}],
        ))

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
            list(client.stream_responses(
                token="gho_test", model="bad-model",
                input_messages=[{"role": "user", "content": "hi"}],
            ))
        assert exc_info.value.status_code == 400


class TestStreamResponsesTools:
    def test_tools_included_in_request(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines("[DONE]")
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        tools = [{"type": "function", "name": "read_file", "description": "Read a file", "parameters": {}}]

        client = CopilotApiClient(http_client=mock_client)
        list(client.stream_responses(
            token="gho_test", model="gpt-5.4-mini",
            input_messages=[{"role": "user", "content": "hi"}],
            tools=tools,
        ))

        call_args = mock_client.stream.call_args
        body = call_args[1].get("json", {})
        assert "tools" in body
        assert body["tools"] == tools
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/agents/providers/test_copilot_responses.py -v`
Expected: FAIL — `stream_responses` does not exist

- [ ] **Step 3: Implement stream_responses() in CopilotApiClient**

Add to `breqy/agents/providers/copilot_client.py`:

```python
def stream_responses(
    self,
    *,
    token: str,
    model: str,
    input_messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    instructions: str | None = None,
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
        "x-initiator": "user",
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/agents/providers/test_copilot_responses.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add breqy/agents/providers/copilot_client.py tests/unit/agents/providers/test_copilot_responses.py
git commit -m "feat(copilot): add stream_responses() for Responses API endpoint"
```

---

### Task 4: Add _do_stream_responses() to CopilotProvider and route by endpoint

The provider needs to map Responses API SSE events to `ProviderEvent`. The event types differ from Chat Completions:

| Responses API Event | Maps To |
|---|---|
| `response.output_text.delta` (delta field) | `ProviderEvent(kind="text", text=delta)` |
| `response.output_item.done` with `item.type == "function_call"` | `ProviderEvent(kind="tool_call", ...)` |
| `response.completed` | `ProviderEvent(kind="complete", ...)` |
| `response.failed` | `ProviderEvent(kind="complete", exit_code=1)` |

The routing logic: if `self._model_endpoints.get(self._model_id)` contains `/responses`, use `stream_responses()`. Otherwise use `stream_chat()`. Default to `/chat/completions` for backwards compatibility.

**Files:**
- Modify: `breqy/agents/providers/copilot.py`
- Modify: `tests/unit/agents/providers/test_copilot.py`

- [ ] **Step 1: Write failing tests for _do_stream_responses() and routing**

Add to `tests/unit/agents/providers/test_copilot.py`:

```python
class TestResponsesApiStreamEvents:
    """CopilotProvider maps Responses API events to ProviderEvent."""

    def test_text_delta_mapped_to_text_event(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_responses.return_value = iter([
            {"type": "response.output_text.delta", "delta": "Hello"},
            {"type": "response.output_text.delta", "delta": " world"},
            {"type": "response.completed", "response": {"status": "completed", "usage": {"total_tokens": 10}, "model": "gpt-5.4-mini"}},
        ])

        provider = CopilotProvider(model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client)
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
        mock_client.stream_responses.return_value = iter([
            {"type": "response.output_item.done", "item": {
                "type": "function_call",
                "call_id": "call_1",
                "name": "read_file",
                "arguments": '{"path": "/tmp"}',
            }},
            {"type": "response.completed", "response": {"status": "completed", "usage": {"total_tokens": 10}, "model": "gpt-5.4-mini"}},
        ])

        provider = CopilotProvider(model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client)
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
        mock_client.stream_responses.return_value = iter([
            {"type": "response.output_text.delta", "delta": "done"},
            {"type": "response.completed", "response": {"status": "completed", "usage": {"total_tokens": 5}, "model": "gpt-5.4-mini"}},
        ])

        provider = CopilotProvider(model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client)
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
        mock_client.stream_responses.return_value = iter([
            {"type": "response.failed", "error": {"message": "model overloaded"}},
        ])

        provider = CopilotProvider(model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client)
        provider._model_endpoints = {"gpt-5.4-mini": ["/responses"]}
        events = list(provider.stream(_make_request("hi")))

        complete_events = [e for e in events if e.kind == "complete"]
        assert len(complete_events) == 1
        assert complete_events[0].metadata.exit_code == 1


class TestEndpointRouting:
    """CopilotProvider routes to correct API based on model endpoints."""

    def test_routes_to_chat_completions_by_default(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter([
            {"choices": [{"delta": {"content": "ok"}, "index": 0}]},
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
        ])

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        # No _model_endpoints set → defaults to chat completions
        list(provider.stream(_make_request("hi")))

        mock_client.stream_chat.assert_called_once()
        mock_client.stream_responses.assert_not_called()

    def test_routes_to_responses_when_only_responses_supported(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_client = MagicMock()
        mock_client.stream_responses.return_value = iter([
            {"type": "response.output_text.delta", "delta": "ok"},
            {"type": "response.completed", "response": {"status": "completed", "usage": {"total_tokens": 5}, "model": "gpt-5.4-mini"}},
        ])

        provider = CopilotProvider(model_id="gpt-5.4-mini", authenticator=mock_auth, client=mock_client)
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
        mock_client.stream_responses.return_value = iter([
            {"type": "response.output_text.delta", "delta": "ok"},
            {"type": "response.completed", "response": {"status": "completed", "usage": {"total_tokens": 5}, "model": "gpt-4o"}},
        ])

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        provider._model_endpoints = {"gpt-4o": ["/chat/completions", "/responses"]}
        list(provider.stream(_make_request("hi")))

        mock_client.stream_responses.assert_called_once()
        mock_client.stream_chat.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/agents/providers/test_copilot.py::TestResponsesApiStreamEvents tests/unit/agents/providers/test_copilot.py::TestEndpointRouting -v`
Expected: FAIL

- [ ] **Step 3: Implement _do_stream_responses() and routing logic**

In `breqy/agents/providers/copilot.py`:

1. Add `_model_endpoints: dict[str, list[str]]` attribute in `__init__`
2. Add `_use_responses_api()` method
3. Add `_do_stream_responses()` method
4. Add `_build_responses_input()` method (converts ProviderRequest to Responses API format)
5. Add `_convert_tools_responses()` method
6. Modify `stream()` to route based on endpoint

```python
# In __init__:
self._model_endpoints: dict[str, list[str]] = {}

# New helper:
def _use_responses_api(self) -> bool:
    """Determine if this model should use the /responses endpoint."""
    endpoints = self._model_endpoints.get(self._model_id, [])
    if "/responses" in endpoints:
        return True
    return False

# In _do_stream (existing), modify the call to be the one for chat completions only.
# Add a parallel _do_stream_responses for the Responses API.
```

The routing happens in `_do_stream` — delegate to either `self._client.stream_chat()` or `self._client.stream_responses()`.

The `_do_stream_responses()` maps events:
- `response.output_text.delta` → `ProviderEvent(kind="text", text=event["delta"])`
- `response.output_item.done` where `item.type == "function_call"` → `ProviderEvent(kind="tool_call", ...)`
- `response.completed` → `ProviderEvent(kind="complete", exit_code=0)`
- `response.failed` → `ProviderEvent(kind="complete", exit_code=1)`

The `_build_responses_input()` converts messages to Responses API format:
- system messages → `instructions` parameter
- user/assistant messages → `input` array items

The `_convert_tools_responses()` converts tools to Responses API format:
```python
[{"type": "function", "name": tool.name, "description": tool.description, "parameters": tool.input_schema}]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/agents/providers/test_copilot.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest --tb=short -q`
Expected: 1578+ tests pass (new tests added)

- [ ] **Step 6: Commit**

```bash
git add breqy/agents/providers/copilot.py tests/unit/agents/providers/test_copilot.py
git commit -m "feat(copilot): add Responses API streaming and endpoint routing"
```

---

### Task 5: Update existing test assertions for filtering

Some existing tests in `test_list_models.py` and `test_copilot.py` mock the `/models` API response without `capabilities` or `model_picker_enabled` fields. These tests need updating to include the new required fields so they continue to pass after filtering is implemented.

**Files:**
- Modify: `tests/unit/agents/providers/test_list_models.py`
- Modify: `tests/unit/agents/providers/test_copilot.py`

- [ ] **Step 1: Review existing test mocks**

Existing tests that mock `/models` responses:
- `test_list_models.py::TestCopilotListModels::test_returns_models_from_api` — mock lacks `capabilities` and `model_picker_enabled`
- `test_list_models.py::TestCopilotListModels::test_sends_auth_header` — same
- `test_list_models.py::TestCopilotListModels::test_model_name_defaults_to_id` — same
- `test_copilot.py::TestCopilotTokenUsage::test_list_models_uses_copilot_session_token` — same

- [ ] **Step 2: Update mocks to include capabilities and model_picker_enabled**

Update each mock to include:
```python
{"id": "gpt-4o", "name": "GPT-4o", "capabilities": {"type": "chat"}, "model_picker_enabled": True}
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/unit/agents/providers/test_list_models.py tests/unit/agents/providers/test_copilot.py
git commit -m "test(copilot): update model API mocks with capabilities and model_picker_enabled"
```

---

### Task 6: Full verification

- [ ] **Step 1: Run complete test suite**

Run: `.venv/bin/python -m pytest --tb=short -q`
Expected: ALL pass (1578 original + ~15 new)

- [ ] **Step 2: Manual verification**

Ask user to restart TUI and:
1. Open model selector (Ctrl+Shift+M)
2. Verify model list only shows chat-capable models
3. Select gpt-5.4-mini
4. Send a message — should work via /responses endpoint
5. Verify gpt-4o still works via /chat/completions
