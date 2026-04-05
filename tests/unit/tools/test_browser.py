from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from breqy.tools.browser import BrowserInterventionRequired, BrowserTool
from breqy.tools.browser_runtime import PlaywrightBrowserRuntime, _BrowserSession


class FakeBrowserRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.results: dict[str, dict[str, Any]] = {}
        self.failures: dict[str, Exception] = {}

    async def navigate(self, action) -> dict[str, Any]:
        return self._handle("navigate", action)

    async def click(self, action) -> dict[str, Any]:
        return self._handle("click", action)

    async def type_text(self, action) -> dict[str, Any]:
        return self._handle("type_text", action)

    async def fill(self, action) -> dict[str, Any]:
        return self._handle("fill", action)

    async def select_option(self, action) -> dict[str, Any]:
        return self._handle("select_option", action)

    async def wait(self, action) -> dict[str, Any]:
        return self._handle("wait", action)

    async def extract(self, action) -> dict[str, Any]:
        return self._handle("extract", action)

    async def screenshot(self, action) -> dict[str, Any]:
        return self._handle("screenshot", action)

    async def go_back(self, action) -> dict[str, Any]:
        return self._handle("go_back", action)

    async def go_forward(self, action) -> dict[str, Any]:
        return self._handle("go_forward", action)

    async def new_tab(self, action) -> dict[str, Any]:
        return self._handle("new_tab", action)

    async def switch_tab(self, action) -> dict[str, Any]:
        return self._handle("switch_tab", action)

    async def close_tab(self, action) -> dict[str, Any]:
        return self._handle("close_tab", action)

    async def set_cookies(self, action) -> dict[str, Any]:
        return self._handle("set_cookies", action)

    async def set_headers(self, action) -> dict[str, Any]:
        return self._handle("set_headers", action)

    def _handle(self, name: str, action: Any) -> dict[str, Any]:
        self.calls.append((name, action))
        failure = self.failures.get(name)
        if failure is not None:
            raise failure
        return self.results.get(name, {"ok": True})


def test_browser_tool_has_required_input_schema() -> None:
    tool = BrowserTool(runtime=FakeBrowserRuntime())

    assert tool.name == "browser"
    assert "action" in tool.input_schema["properties"]
    assert "browser_mode" in tool.input_schema["properties"]
    assert "session_id" in tool.input_schema["properties"]
    assert "cookies" in tool.input_schema["properties"]
    assert "headers" in tool.input_schema["properties"]


def test_browser_tool_approval_request_spec_requires_url_for_stable_grant_key() -> None:
    tool = BrowserTool(runtime=FakeBrowserRuntime())

    spec = tool.approval_request_spec({"action": "click", "session_id": "browser-1"})

    assert spec is None


def test_browser_tool_approval_request_spec_ignores_blocked_actions() -> None:
    tool = BrowserTool(runtime=FakeBrowserRuntime())

    spec = tool.approval_request_spec({"action": "download", "url": "https://example.com/file"})

    assert spec is None


def test_browser_tool_approval_request_spec_ignores_non_http_urls() -> None:
    tool = BrowserTool(runtime=FakeBrowserRuntime())

    spec = tool.approval_request_spec({"action": "navigate", "url": "file:///etc/passwd"})

    assert spec is None


@pytest.mark.asyncio
async def test_browser_tool_dispatches_navigate_action() -> None:
    runtime = FakeBrowserRuntime()
    runtime.results["navigate"] = {
        "url": "https://example.com",
        "title": "Example Domain",
    }
    tool = BrowserTool(runtime=runtime)

    result = await tool.execute(
        {
            "action": "navigate",
            "url": "https://example.com",
            "session_id": "session-a",
            "browser_mode": "headed",
            "headers": {"User-Agent": "BreqyTest"},
            "cookies": [
                {
                    "name": "currency",
                    "value": "CAD",
                    "domain": "example.com",
                }
            ],
        }
    )

    assert result.success is True
    assert result.output["url"] == "https://example.com"
    assert result.summary == "Browser action navigate completed"
    action_name, action = runtime.calls[0]
    assert action_name == "navigate"
    assert action.browser_mode == "headed"
    assert action.headers == {"User-Agent": "BreqyTest"}
    assert action.cookies[0].name == "currency"


@pytest.mark.asyncio
async def test_browser_tool_uses_runtime_session_from_execution_context_when_missing() -> None:
    runtime = FakeBrowserRuntime()
    tool = BrowserTool(runtime=runtime)

    result = await tool.execute(
        {
            "action": "fill",
            "selector": "#search",
            "value": "barcelona",
            "_execution_context": {"session_id": "ses_123", "agent_id": "breqy"},
        }
    )

    assert result.success is True
    action_name, action = runtime.calls[0]
    assert action_name == "fill"
    assert action.session_id == "ses_123:browser"


@pytest.mark.asyncio
async def test_browser_tool_accepts_mode_alias() -> None:
    runtime = FakeBrowserRuntime()
    tool = BrowserTool(runtime=runtime)

    result = await tool.execute({"action": "navigate", "url": "https://example.com", "mode": "headed"})

    assert result.success is True
    _, action = runtime.calls[0]
    assert action.browser_mode == "headed"


@pytest.mark.asyncio
async def test_browser_tool_rejects_non_http_urls() -> None:
    tool = BrowserTool(runtime=FakeBrowserRuntime())

    result = await tool.execute({"action": "navigate", "url": "file:///etc/passwd"})

    assert result.success is False
    assert "http or https" in result.error


@pytest.mark.asyncio
async def test_browser_tool_requires_page_context_for_dom_actions() -> None:
    tool = BrowserTool(runtime=FakeBrowserRuntime())

    result = await tool.execute({"action": "click", "selector": "#submit"})

    assert result.success is False
    assert "session_id or url" in result.error


@pytest.mark.asyncio
async def test_browser_tool_rejects_dom_wait_state_without_selector() -> None:
    tool = BrowserTool(runtime=FakeBrowserRuntime())

    result = await tool.execute(
        {
            "action": "wait",
            "session_id": "browser-1",
            "wait_state": "visible",
        }
    )

    assert result.success is False
    assert "selector" in result.error.lower()


@pytest.mark.asyncio
async def test_browser_tool_allows_page_load_wait_state_without_selector() -> None:
    runtime = FakeBrowserRuntime()
    tool = BrowserTool(runtime=runtime)

    result = await tool.execute(
        {
            "action": "wait",
            "session_id": "browser-1",
            "wait_state": "load",
        }
    )

    assert result.success is True
    action_name, action = runtime.calls[0]
    assert action_name == "wait"
    assert action.wait_state == "load"


@pytest.mark.asyncio
async def test_browser_tool_dispatches_fill_action_to_typed_runtime_method() -> None:
    runtime = FakeBrowserRuntime()
    runtime.results["fill"] = {"filled": True}
    tool = BrowserTool(runtime=runtime)

    result = await tool.execute(
        {
            "action": "fill",
            "selector": "#from",
            "value": "Toronto",
            "session_id": "browser-1",
        }
    )

    assert result.success is True
    action_name, action = runtime.calls[0]
    assert action_name == "fill"
    assert action.selector == "#from"
    assert action.value == "Toronto"


@pytest.mark.asyncio
async def test_browser_tool_rejects_download_and_upload_actions() -> None:
    tool = BrowserTool(runtime=FakeBrowserRuntime())

    download = await tool.execute({"action": "download", "url": "https://example.com/file"})
    upload = await tool.execute({"action": "upload", "selector": "#file", "path": "/tmp/file"})

    assert download.success is False
    assert "out of scope" in download.error.lower()
    assert upload.success is False
    assert "out of scope" in upload.error.lower()


@pytest.mark.asyncio
async def test_browser_tool_returns_safe_intervention_failure_for_blocked_flows() -> None:
    runtime = FakeBrowserRuntime()
    runtime.failures["navigate"] = BrowserInterventionRequired(
        reason="captcha",
        message="User intervention required for CAPTCHA challenge",
        metadata={"url": "https://example.com/captcha"},
    )
    tool = BrowserTool(runtime=runtime)

    result = await tool.execute({"action": "navigate", "url": "https://example.com/captcha"})

    assert result.success is False
    assert "user intervention" in result.error.lower()
    assert result.output["intervention_required"] is True
    assert result.output["reason"] == "captcha"


@pytest.mark.asyncio
async def test_browser_tool_returns_transport_safe_screenshot_reference(tmp_path: Path) -> None:
    runtime = FakeBrowserRuntime()
    screenshot_path = tmp_path / "shot.png"
    runtime.results["screenshot"] = {
        "artifact_ref": {
            "kind": "screenshot",
            "path": str(screenshot_path),
            "mime_type": "image/png",
        }
    }
    tool = BrowserTool(runtime=runtime)

    result = await tool.execute({"action": "screenshot", "session_id": "browser-1"})

    assert result.success is True
    artifact_ref = result.output["artifact_ref"]
    assert artifact_ref["kind"] == "screenshot"
    assert artifact_ref["path"] == str(screenshot_path)
    assert "bytes" not in artifact_ref


def test_runtime_resolves_relative_screenshot_paths_inside_artifacts_dir() -> None:
    path = PlaywrightBrowserRuntime._resolve_screenshot_output_path("screens/shot.png")

    assert "breqy-browser-artifacts" in str(path)
    assert path.name == "shot.png"
    assert path.parent.name == "screens"


def test_runtime_rejects_absolute_screenshot_paths() -> None:
    with pytest.raises(ValueError, match="relative"):
        PlaywrightBrowserRuntime._resolve_screenshot_output_path("/tmp/evil.png")


def test_runtime_rejects_traversing_screenshot_paths() -> None:
    with pytest.raises(ValueError, match="within the artifacts directory"):
        PlaywrightBrowserRuntime._resolve_screenshot_output_path("../evil.png")


@pytest.mark.asyncio
async def test_runtime_close_cleans_up_browser_processes() -> None:
    class FakeContext:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class FakeBrowser:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class FakePlaywright:
        def __init__(self) -> None:
            self.stopped = False

        async def stop(self) -> None:
            self.stopped = True

    runtime = PlaywrightBrowserRuntime()
    context = FakeContext()
    browser = FakeBrowser()
    playwright = FakePlaywright()
    runtime._sessions["browser-1"] = _BrowserSession(
        browser_mode="headless",
        browser=browser,
        context=context,
        tabs={},
        current_tab_id="tab-1",
    )
    runtime._playwright = playwright

    await runtime.close()

    assert browser.closed is True
    assert context.closed is True
    assert playwright.stopped is True
    assert runtime._sessions == {}


@pytest.mark.asyncio
async def test_runtime_close_continues_cleanup_after_session_failures() -> None:
    class FailingContext:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True
            raise RuntimeError("context close failed")

    class HealthyContext:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class FailingBrowser:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True
            raise RuntimeError("browser close failed")

    class HealthyBrowser:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class FakePlaywright:
        def __init__(self) -> None:
            self.stopped = False

        async def stop(self) -> None:
            self.stopped = True

    runtime = PlaywrightBrowserRuntime()
    playwright = FakePlaywright()
    bad_context = FailingContext()
    good_context = HealthyContext()
    bad_browser = FailingBrowser()
    good_browser = HealthyBrowser()
    runtime._playwright = playwright
    runtime._sessions["bad"] = _BrowserSession(
        browser_mode="headless",
        browser=bad_browser,
        context=bad_context,
        tabs={},
        current_tab_id="tab-1",
    )
    runtime._sessions["good"] = _BrowserSession(
        browser_mode="headless",
        browser=good_browser,
        context=good_context,
        tabs={},
        current_tab_id="tab-2",
    )

    with pytest.raises(RuntimeError, match="context close failed"):
        await runtime.close()

    assert bad_context.closed is True
    assert good_context.closed is True
    assert bad_browser.closed is True
    assert good_browser.closed is True
    assert playwright.stopped is True
    assert runtime._sessions == {}
    assert runtime._playwright is None
