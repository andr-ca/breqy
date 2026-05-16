from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class BrowserCookie(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = False
    http_only: bool = Field(
        default=False,
        validation_alias=AliasChoices("http_only", "httpOnly"),
        serialization_alias="httpOnly",
    )
    same_site: Literal["Strict", "Lax", "None"] | None = Field(
        default=None,
        validation_alias=AliasChoices("same_site", "sameSite"),
        serialization_alias="sameSite",
    )


class BrowserActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    session_id: str | None = None
    browser_mode: Literal["headless", "headed"] = Field(
        default="headless",
        validation_alias=AliasChoices("browser_mode", "mode"),
    )
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: list[BrowserCookie] = Field(default_factory=list)


class BrowserPageAction(BrowserActionBase):
    url: str | None = None

    @model_validator(mode="after")
    def validate_page_context(self) -> "BrowserPageAction":
        if not self.url and not self.session_id:
            raise ValueError("browser page actions require session_id or url")
        _validate_allowed_url(self.url)
        return self


class NavigateAction(BrowserActionBase):
    action: Literal["navigate"] = "navigate"
    url: str

    @model_validator(mode="after")
    def validate_url(self) -> "NavigateAction":
        _validate_allowed_url(self.url)
        return self


class ClickAction(BrowserPageAction):
    action: Literal["click"] = "click"
    selector: str


class TypeAction(BrowserPageAction):
    action: Literal["type"] = "type"
    selector: str
    text: str


class FillAction(BrowserPageAction):
    action: Literal["fill"] = "fill"
    selector: str
    value: str


class SelectAction(BrowserPageAction):
    action: Literal["select"] = "select"
    selector: str
    value: str


class WaitAction(BrowserPageAction):
    action: Literal["wait"] = "wait"
    selector: str | None = None
    wait_state: Literal[
        "load",
        "domcontentloaded",
        "networkidle",
        "visible",
        "hidden",
        "attached",
        "detached",
    ] = "visible"
    timeout_seconds: int = Field(default=30, ge=1, le=300)

    @model_validator(mode="after")
    def validate_wait_target(self) -> "WaitAction":
        if self.selector is None and self.wait_state not in {"load", "domcontentloaded", "networkidle"}:
            raise ValueError("selector is required for DOM wait states")
        if self.selector is not None and self.wait_state in {"load", "domcontentloaded", "networkidle"}:
            return self
        return self


class ExtractAction(BrowserPageAction):
    action: Literal["extract"] = "extract"
    selector: str | None = None
    format: Literal["text", "html"] = "text"


class ScreenshotAction(BrowserPageAction):
    action: Literal["screenshot"] = "screenshot"
    selector: str | None = None
    output_path: str | None = None


class BackAction(BrowserActionBase):
    action: Literal["back"] = "back"

    @model_validator(mode="after")
    def validate_requires_session(self) -> "BackAction":
        if not self.session_id:
            raise ValueError("browser history actions require session_id")
        return self


class ForwardAction(BrowserActionBase):
    action: Literal["forward"] = "forward"

    @model_validator(mode="after")
    def validate_requires_session(self) -> "ForwardAction":
        if not self.session_id:
            raise ValueError("browser history actions require session_id")
        return self


class NewTabAction(BrowserActionBase):
    action: Literal["new_tab"] = "new_tab"
    url: str | None = None

    @model_validator(mode="after")
    def validate_url(self) -> "NewTabAction":
        _validate_allowed_url(self.url)
        return self


class SwitchTabAction(BrowserActionBase):
    action: Literal["switch_tab"] = "switch_tab"
    tab_id: str

    @model_validator(mode="after")
    def validate_requires_session(self) -> "SwitchTabAction":
        if not self.session_id:
            raise ValueError("tab actions require session_id")
        return self


class CloseTabAction(BrowserActionBase):
    action: Literal["close_tab"] = "close_tab"
    tab_id: str | None = None

    @model_validator(mode="after")
    def validate_requires_session(self) -> "CloseTabAction":
        if not self.session_id:
            raise ValueError("tab actions require session_id")
        return self


class SetCookiesAction(BrowserPageAction):
    action: Literal["set_cookies"] = "set_cookies"
    cookies: list[BrowserCookie] = Field(min_length=1)


class SetHeadersAction(BrowserPageAction):
    action: Literal["set_headers"] = "set_headers"
    headers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_headers(self) -> "SetHeadersAction":
        if not self.headers:
            raise ValueError("set_headers requires at least one header")
        return self


BrowserAction = Annotated[
    NavigateAction
    | ClickAction
    | TypeAction
    | FillAction
    | SelectAction
    | WaitAction
    | ExtractAction
    | ScreenshotAction
    | BackAction
    | ForwardAction
    | NewTabAction
    | SwitchTabAction
    | CloseTabAction
    | SetCookiesAction
    | SetHeadersAction,
    Field(discriminator="action"),
]

browser_action_adapter: TypeAdapter[BrowserAction] = TypeAdapter(BrowserAction)


def _validate_allowed_url(raw_url: str | None) -> None:
    if raw_url is None:
        return
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("browser url must use http or https")


@dataclass(slots=True)
class BrowserInterventionRequired(Exception):
    reason: Literal["captcha", "mfa", "blocked_access"]
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


class BrowserRuntime(Protocol):
    async def navigate(self, action: NavigateAction) -> dict[str, Any]: ...

    async def click(self, action: ClickAction) -> dict[str, Any]: ...

    async def type_text(self, action: TypeAction) -> dict[str, Any]: ...

    async def fill(self, action: FillAction) -> dict[str, Any]: ...

    async def select_option(self, action: SelectAction) -> dict[str, Any]: ...

    async def wait(self, action: WaitAction) -> dict[str, Any]: ...

    async def extract(self, action: ExtractAction) -> dict[str, Any]: ...

    async def screenshot(self, action: ScreenshotAction) -> dict[str, Any]: ...

    async def go_back(self, action: BackAction) -> dict[str, Any]: ...

    async def go_forward(self, action: ForwardAction) -> dict[str, Any]: ...

    async def new_tab(self, action: NewTabAction) -> dict[str, Any]: ...

    async def switch_tab(self, action: SwitchTabAction) -> dict[str, Any]: ...

    async def close_tab(self, action: CloseTabAction) -> dict[str, Any]: ...

    async def set_cookies(self, action: SetCookiesAction) -> dict[str, Any]: ...

    async def set_headers(self, action: SetHeadersAction) -> dict[str, Any]: ...

    async def close(self) -> None: ...


@dataclass
class _BrowserSession:
    browser_mode: str
    browser: Any
    context: Any
    tabs: dict[str, Any]
    current_tab_id: str


class PlaywrightBrowserRuntime:
    """Runtime adapter that maps typed browser actions to Playwright operations."""

    def __init__(self) -> None:
        self._playwright: Any | None = None
        self._sessions: dict[str, _BrowserSession] = {}

    async def navigate(self, action: NavigateAction) -> dict[str, Any]:
        session = await self._ensure_session(action)
        page = await self._current_page(session, action)
        await page.goto(action.url, wait_until="load")
        return {"url": page.url, "title": await page.title()}

    async def click(self, action: ClickAction) -> dict[str, Any]:
        page = await self._page_for_action(action)
        await page.locator(action.selector).click()
        return {"url": page.url, "selector": action.selector}

    async def type_text(self, action: TypeAction) -> dict[str, Any]:
        page = await self._page_for_action(action)
        await page.locator(action.selector).type(action.text)
        return {"url": page.url, "selector": action.selector}

    async def fill(self, action: FillAction) -> dict[str, Any]:
        page = await self._page_for_action(action)
        await page.locator(action.selector).fill(action.value)
        return {"url": page.url, "selector": action.selector}

    async def select_option(self, action: SelectAction) -> dict[str, Any]:
        page = await self._page_for_action(action)
        await page.locator(action.selector).select_option(action.value)
        return {"url": page.url, "selector": action.selector, "value": action.value}

    async def wait(self, action: WaitAction) -> dict[str, Any]:
        page = await self._page_for_action(action)
        timeout_ms = action.timeout_seconds * 1000
        if action.selector is None:
            await page.wait_for_load_state(action.wait_state, timeout=timeout_ms)
        else:
            await page.locator(action.selector).wait_for(state=action.wait_state, timeout=timeout_ms)
        return {"url": page.url, "wait_state": action.wait_state}

    async def extract(self, action: ExtractAction) -> dict[str, Any]:
        page = await self._page_for_action(action)
        if action.selector:
            locator = page.locator(action.selector)
            value = await (locator.inner_html() if action.format == "html" else locator.inner_text())
        else:
            value = await (page.content() if action.format == "html" else page.inner_text("body"))
        return {"url": page.url, "format": action.format, "content": value}

    async def screenshot(self, action: ScreenshotAction) -> dict[str, Any]:
        page = await self._page_for_action(action)
        output_path = self._resolve_screenshot_output_path(action.output_path)
        if action.selector:
            await page.locator(action.selector).screenshot(path=str(output_path))
        else:
            await page.screenshot(path=str(output_path))
        return {
            "artifact_ref": {
                "kind": "screenshot",
                "path": str(output_path),
                "mime_type": "image/png",
            }
        }

    async def go_back(self, action: BackAction) -> dict[str, Any]:
        session = self._require_session(action.session_id)
        page = session.tabs[session.current_tab_id]
        await page.go_back()
        return {"url": page.url}

    async def go_forward(self, action: ForwardAction) -> dict[str, Any]:
        session = self._require_session(action.session_id)
        page = session.tabs[session.current_tab_id]
        await page.go_forward()
        return {"url": page.url}

    async def new_tab(self, action: NewTabAction) -> dict[str, Any]:
        session = await self._ensure_session(action)
        page = await session.context.new_page()
        tab_id = f"tab_{uuid4().hex[:8]}"
        session.tabs[tab_id] = page
        session.current_tab_id = tab_id
        if action.url:
            await page.goto(action.url, wait_until="load")
        return {"tab_id": tab_id, "url": page.url}

    async def switch_tab(self, action: SwitchTabAction) -> dict[str, Any]:
        session = self._require_session(action.session_id)
        if action.tab_id not in session.tabs:
            raise RuntimeError(f"Unknown browser tab: {action.tab_id}")
        session.current_tab_id = action.tab_id
        return {"tab_id": action.tab_id, "url": session.tabs[action.tab_id].url}

    async def close_tab(self, action: CloseTabAction) -> dict[str, Any]:
        session = self._require_session(action.session_id)
        tab_id = action.tab_id or session.current_tab_id
        page = session.tabs.get(tab_id)
        if page is None:
            raise RuntimeError(f"Unknown browser tab: {tab_id}")
        await page.close()
        session.tabs.pop(tab_id, None)
        if session.tabs:
            session.current_tab_id = next(iter(session.tabs))
        else:
            new_page = await session.context.new_page()
            replacement_id = f"tab_{uuid4().hex[:8]}"
            session.tabs[replacement_id] = new_page
            session.current_tab_id = replacement_id
        return {"closed_tab_id": tab_id}

    async def set_cookies(self, action: SetCookiesAction) -> dict[str, Any]:
        session = await self._ensure_session(action)
        await session.context.add_cookies(
            [cookie.model_dump(exclude_none=True, by_alias=True) for cookie in action.cookies]
        )
        return {"cookie_count": len(action.cookies)}

    async def set_headers(self, action: SetHeadersAction) -> dict[str, Any]:
        page = await self._page_for_action(action)
        await page.set_extra_http_headers(action.headers)
        return {"header_count": len(action.headers)}

    async def _page_for_action(self, action: BrowserPageAction | SetHeadersAction) -> Any:
        session = await self._ensure_session(action)
        return await self._current_page(session, action)

    async def _current_page(self, session: _BrowserSession, action: BrowserActionBase) -> Any:
        page = session.tabs[session.current_tab_id]
        if isinstance(action, BrowserPageAction) and action.url and page.url != action.url:
            await page.goto(action.url, wait_until="load")
        if action.headers:
            await page.set_extra_http_headers(action.headers)
        if action.cookies:
            await session.context.add_cookies(
                [cookie.model_dump(exclude_none=True, by_alias=True) for cookie in action.cookies]
            )
        return page

    async def _ensure_session(self, action: BrowserActionBase) -> _BrowserSession:
        session_id = action.session_id or "default"
        existing = self._sessions.get(session_id)
        if existing is not None:
            if existing.browser_mode != action.browser_mode:
                raise RuntimeError(
                    f"Browser session '{session_id}' already exists with mode {existing.browser_mode}"
                )
            return existing

        playwright_api = await self._require_playwright()
        browser = await playwright_api.chromium.launch(headless=action.browser_mode == "headless")
        context = await browser.new_context(
            extra_http_headers=action.headers or None,
        )
        if action.cookies:
            await context.add_cookies(
                [cookie.model_dump(exclude_none=True, by_alias=True) for cookie in action.cookies]
            )
        page = await context.new_page()
        tab_id = f"tab_{uuid4().hex[:8]}"
        session = _BrowserSession(
            browser_mode=action.browser_mode,
            browser=browser,
            context=context,
            tabs={tab_id: page},
            current_tab_id=tab_id,
        )
        self._sessions[session_id] = session
        return session

    def _require_session(self, session_id: str | None) -> _BrowserSession:
        if session_id is None or session_id not in self._sessions:
            raise RuntimeError(f"Unknown browser session: {session_id or 'missing'}")
        return self._sessions[session_id]

    async def _require_playwright(self) -> Any:
        if self._playwright is None:
            try:
                from playwright.async_api import async_playwright
            except ModuleNotFoundError as exc:  # pragma: no cover
                raise RuntimeError(
                    "Playwright is not installed. Add the 'playwright' package and run browser setup."
                ) from exc
            self._playwright = await async_playwright().start()
        return self._playwright

    async def close(self) -> None:
        first_error: Exception | None = None
        try:
            for session in list(self._sessions.values()):
                try:
                    await session.context.close()
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
                try:
                    await session.browser.close()
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
        finally:
            self._sessions.clear()
            if self._playwright is not None:
                playwright = self._playwright
                try:
                    await playwright.stop()
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
                finally:
                    self._playwright = None
        if first_error is not None:
            raise first_error

    @staticmethod
    def _resolve_screenshot_output_path(output_path: str | None) -> Path:
        artifacts_dir_raw = Path(tempfile.gettempdir()) / "breqy-browser-artifacts"
        if artifacts_dir_raw.exists():
            if artifacts_dir_raw.is_symlink():
                raise ValueError(
                    f"Refusing to use symlinked artifacts directory: {artifacts_dir_raw}"
                )
            if not artifacts_dir_raw.is_dir():
                raise ValueError(
                    f"Expected a directory at artifacts path: {artifacts_dir_raw}"
                )
        else:
            artifacts_dir_raw.mkdir(parents=True, mode=0o700)
        artifacts_dir = artifacts_dir_raw.resolve()

        if output_path is None:
            return artifacts_dir / f"breqy-browser-{uuid4().hex}.png"

        requested_path = Path(output_path)
        if requested_path.is_absolute():
            raise ValueError("Screenshot output_path must be relative to the artifacts directory")

        safe_path = (artifacts_dir / requested_path).resolve()
        try:
            safe_path.relative_to(artifacts_dir)
        except ValueError as exc:
            raise ValueError("Screenshot output_path must stay within the artifacts directory") from exc

        safe_path.parent.mkdir(parents=True, exist_ok=True)
        return safe_path
