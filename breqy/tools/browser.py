from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from breqy.tools.browser_runtime import (
    BackAction,
    BrowserActionBase,
    BrowserInterventionRequired,
    BrowserRuntime,
    ClickAction,
    CloseTabAction,
    ExtractAction,
    FillAction,
    ForwardAction,
    NavigateAction,
    NewTabAction,
    PlaywrightBrowserRuntime,
    ScreenshotAction,
    SelectAction,
    SetCookiesAction,
    SetHeadersAction,
    SwitchTabAction,
    TypeAction,
    WaitAction,
    browser_action_adapter,
)
from breqy.tools.executor import ApprovalRequestSpec, ToolExecutor, ToolResult

_BLOCKED_V1_ACTIONS = {"download", "upload"}
_SUPPORTED_ACTIONS = {
    "navigate",
    "click",
    "type",
    "fill",
    "select",
    "wait",
    "extract",
    "screenshot",
    "back",
    "forward",
    "new_tab",
    "switch_tab",
    "close_tab",
    "set_cookies",
    "set_headers",
}


class BrowserTool(ToolExecutor):
    name = "browser"
    description = "Automate headed or headless browser interactions on websites"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": sorted(_SUPPORTED_ACTIONS | _BLOCKED_V1_ACTIONS),
                "description": "Browser action to perform",
            },
            "url": {"type": "string", "description": "Target URL for navigation or page-scoped actions"},
            "session_id": {
                "type": "string",
                "description": "Optional browser session identifier for context reuse",
            },
            "browser_mode": {
                "type": "string",
                "enum": ["headless", "headed"],
                "description": "Execution mode for the browser",
            },
            "mode": {
                "type": "string",
                "enum": ["headless", "headed"],
                "description": "Alias for browser_mode",
            },
            "headers": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "Optional custom request headers",
            },
            "cookies": {
                "type": "array",
                "description": "Optional cookies applied to the browser context",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {"type": "string"},
                        "domain": {"type": "string"},
                        "path": {"type": "string"},
                    },
                    "required": ["name", "value", "domain"],
                },
            },
            "selector": {"type": "string", "description": "Element selector for DOM actions"},
            "text": {"type": "string", "description": "Text payload for browser typing"},
            "value": {"type": "string", "description": "Value payload for fill/select actions"},
            "wait_state": {"type": "string", "description": "Wait state for wait actions"},
            "timeout_seconds": {"type": "integer", "description": "Timeout for wait actions"},
            "tab_id": {"type": "string", "description": "Browser tab identifier for tab actions"},
            "output_path": {"type": "string", "description": "Optional path for screenshot output"},
            "format": {"type": "string", "enum": ["text", "html"], "description": "Extract format"},
        },
        "required": ["action"],
    }

    def __init__(self, runtime: BrowserRuntime | None = None) -> None:
        self._runtime = runtime or PlaywrightBrowserRuntime()

    def approval_request_spec(self, arguments: dict[str, Any]) -> ApprovalRequestSpec | None:
        action = arguments.get("action")
        if not isinstance(action, str) or not action:
            return None
        hostname = urlparse(str(arguments.get("url", ""))).hostname
        if not hostname:
            return None
        return ApprovalRequestSpec(
            description=f"Browser {action} on {hostname}",
            grant_key=f"browser:{action}:{hostname}",
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        action_name = arguments.get("action")
        if not isinstance(action_name, str) or not action_name:
            return ToolResult(success=False, error="Missing required argument: action")

        if action_name in _BLOCKED_V1_ACTIONS:
            return ToolResult(
                success=False,
                error=f"Browser action '{action_name}' is out of scope for v1",
                summary=f"Rejected browser action '{action_name}'",
            )

        if action_name not in _SUPPORTED_ACTIONS:
            return ToolResult(
                success=False,
                error=f"Unsupported browser action: {action_name}",
                summary=f"Unsupported browser action '{action_name}'",
            )

        normalized_arguments = dict(arguments)
        execution_context = normalized_arguments.pop("_execution_context", {})
        self._hydrate_default_session_argument(normalized_arguments, execution_context)
        try:
            action = browser_action_adapter.validate_python(normalized_arguments)
        except ValidationError as exc:
            return ToolResult(
                success=False,
                error=exc.errors()[0]["msg"],
                summary=f"Invalid browser action '{action_name}'",
            )

        try:
            result = await self._dispatch(action)
        except BrowserInterventionRequired as exc:
            output = {
                "intervention_required": True,
                "reason": exc.reason,
                **exc.metadata,
            }
            return ToolResult(
                success=False,
                output=output,
                error=f"Browser action requires user intervention: {exc.message}",
                summary="Browser action blocked",
            )
        except RuntimeError as exc:
            return ToolResult(success=False, error=str(exc), summary="Browser runtime failed")

        return ToolResult(
            success=True,
            output=result,
            summary=f"Browser action {action.action} completed",
        )

    async def _dispatch(self, action: BrowserActionBase) -> dict[str, Any]:
        if isinstance(action, NavigateAction):
            return await self._runtime.navigate(action)
        if isinstance(action, ClickAction):
            return await self._runtime.click(action)
        if isinstance(action, TypeAction):
            return await self._runtime.type_text(action)
        if isinstance(action, FillAction):
            return await self._runtime.fill(action)
        if isinstance(action, SelectAction):
            return await self._runtime.select_option(action)
        if isinstance(action, WaitAction):
            return await self._runtime.wait(action)
        if isinstance(action, ExtractAction):
            return await self._runtime.extract(action)
        if isinstance(action, ScreenshotAction):
            return await self._runtime.screenshot(action)
        if isinstance(action, BackAction):
            return await self._runtime.go_back(action)
        if isinstance(action, ForwardAction):
            return await self._runtime.go_forward(action)
        if isinstance(action, NewTabAction):
            return await self._runtime.new_tab(action)
        if isinstance(action, SwitchTabAction):
            return await self._runtime.switch_tab(action)
        if isinstance(action, CloseTabAction):
            return await self._runtime.close_tab(action)
        if isinstance(action, SetCookiesAction):
            return await self._runtime.set_cookies(action)
        if isinstance(action, SetHeadersAction):
            return await self._runtime.set_headers(action)
        raise RuntimeError(f"Unhandled browser action: {action.action}")

    @staticmethod
    def _hydrate_default_session_argument(
        arguments: dict[str, Any], execution_context: dict[str, Any]
    ) -> None:
        if arguments.get("session_id"):
            return
        session_id = execution_context.get("session_id")
        if isinstance(session_id, str) and session_id:
            arguments["session_id"] = f"{session_id}:browser"

    async def close(self) -> None:
        await self._runtime.close()
