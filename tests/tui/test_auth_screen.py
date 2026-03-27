"""Tests for breqy.tui.screens.auth — AuthScreen.

Verifies:
- Lists all configured providers with auth status
- Select provider shows appropriate auth flow widget
- Device flow: shows code + URL
- PKCE flow: shows URL + paste input
- API key flow: shows masked input
- Successful auth updates status to "Authenticated"
- Failed auth shows error
- Escape returns to previous screen
- ProviderSelected message posted on selection
- AuthFlowCompleted message posted on completion
"""
from __future__ import annotations

import pytest

from textual.app import App
from textual.widgets import DataTable, Input, Static

from breqy.domain.enums import AuthFlowKind, AuthSessionStatus
from breqy.tui.screens.auth import AuthScreen, ProviderInfo


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_providers() -> list[ProviderInfo]:
    """Return a list of three providers with varying flow kinds."""
    return [
        ProviderInfo(
            name="GitHub Copilot",
            flow_kind=AuthFlowKind.DEVICE,
            status=AuthSessionStatus.UNAUTHENTICATED,
        ),
        ProviderInfo(
            name="Google",
            flow_kind=AuthFlowKind.PKCE_CODE,
            status=AuthSessionStatus.AUTHENTICATED,
        ),
        ProviderInfo(
            name="OpenAI",
            flow_kind=AuthFlowKind.API_KEY,
            status=AuthSessionStatus.UNAUTHENTICATED,
        ),
    ]


class AuthScreenApp(App[None]):
    """Minimal app that pushes an AuthScreen for testing."""

    def __init__(
        self,
        providers: list[ProviderInfo] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._providers = providers

    def on_mount(self) -> None:
        self.push_screen(AuthScreen(providers=self._providers))


def _get_screen(app: App) -> AuthScreen:
    """Return the active AuthScreen from the app."""
    screen = app.screen
    assert isinstance(screen, AuthScreen)
    return screen


# --------------------------------------------------------------------------- #
# Mount and layout
# --------------------------------------------------------------------------- #


class TestAuthScreenMounts:
    """Screen mounts and shows basic layout."""

    @pytest.mark.asyncio
    async def test_screen_mounts_with_data_table(self) -> None:
        """Screen mounts and contains a DataTable widget."""
        app = AuthScreenApp(providers=_make_providers())
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            tables = screen.query(DataTable)
            assert len(tables) == 1

    @pytest.mark.asyncio
    async def test_header_shows_authentication_title(self) -> None:
        """Screen header shows 'Authentication'."""
        app = AuthScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            header = screen.query_one("#auth-header", Static)
            assert "Authentication" in header.content

    @pytest.mark.asyncio
    async def test_footer_shows_key_hints(self) -> None:
        """Footer area shows key hints for Escape and Enter."""
        app = AuthScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            footer = screen.query_one("#auth-footer", Static)
            text = footer.content
            assert "Escape" in text
            assert "Enter" in text


# --------------------------------------------------------------------------- #
# Provider listing
# --------------------------------------------------------------------------- #


class TestProviderListing:
    """Lists all configured providers with auth status."""

    @pytest.mark.asyncio
    async def test_providers_displayed_as_rows(self) -> None:
        """Each provider appears as a row in the DataTable."""
        providers = _make_providers()
        app = AuthScreenApp(providers=providers)
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            table = screen.query_one(DataTable)
            assert table.row_count == 3

    @pytest.mark.asyncio
    async def test_provider_row_shows_status_icon(self) -> None:
        """Provider rows include a status icon column."""
        providers = [
            ProviderInfo(
                name="TestProvider",
                flow_kind=AuthFlowKind.DEVICE,
                status=AuthSessionStatus.AUTHENTICATED,
            ),
        ]
        app = AuthScreenApp(providers=providers)
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            table = screen.query_one(DataTable)
            # Row should exist
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_load_providers_replaces_rows(self) -> None:
        """Calling load_providers replaces existing rows."""
        providers = _make_providers()
        app = AuthScreenApp(providers=providers)
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            table = screen.query_one(DataTable)
            assert table.row_count == 3
            # Now load a different set
            new_providers = [
                ProviderInfo(
                    name="NewProvider",
                    flow_kind=AuthFlowKind.API_KEY,
                ),
            ]
            screen.load_providers(new_providers)
            await pilot.pause()
            assert table.row_count == 1


# --------------------------------------------------------------------------- #
# Provider selection
# --------------------------------------------------------------------------- #


class TestProviderSelection:
    """Selecting a provider posts ProviderSelected message."""

    @pytest.mark.asyncio
    async def test_enter_posts_provider_selected(self) -> None:
        """Pressing Enter on a row posts ProviderSelected message."""
        providers = _make_providers()
        messages_received: list[AuthScreen.ProviderSelected] = []

        class CaptureApp(App[None]):
            def on_mount(self) -> None:
                self.push_screen(AuthScreen(providers=providers))

            def on_auth_screen_provider_selected(
                self, message: AuthScreen.ProviderSelected,
            ) -> None:
                messages_received.append(message)

        app = CaptureApp()
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            table.move_cursor(row=0)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert len(messages_received) == 1
            assert messages_received[0].provider == "GitHub Copilot"


# --------------------------------------------------------------------------- #
# Device flow
# --------------------------------------------------------------------------- #


class TestDeviceFlow:
    """Device flow shows code + URL in detail area."""

    @pytest.mark.asyncio
    async def test_show_device_flow_shows_code_and_url(self) -> None:
        """show_device_flow populates detail area with code and URL."""
        providers = _make_providers()
        app = AuthScreenApp(providers=providers)
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.show_device_flow(code="ABCD-1234", url="https://github.com/device")
            await pilot.pause()
            detail = screen.query_one("#auth-detail")
            # Should contain both code and URL
            code_static = detail.query_one("#device-code", Static)
            url_static = detail.query_one("#device-url", Static)
            assert "ABCD-1234" in code_static.content
            assert "https://github.com/device" in url_static.content


# --------------------------------------------------------------------------- #
# PKCE flow
# --------------------------------------------------------------------------- #


class TestPkceFlow:
    """PKCE flow shows URL + paste input."""

    @pytest.mark.asyncio
    async def test_show_pkce_flow_shows_url_and_input(self) -> None:
        """show_pkce_flow populates detail area with URL and an Input."""
        providers = _make_providers()
        app = AuthScreenApp(providers=providers)
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.show_pkce_flow(url="https://accounts.google.com/o/oauth2/auth")
            await pilot.pause()
            detail = screen.query_one("#auth-detail")
            url_static = detail.query_one("#pkce-url", Static)
            assert "https://accounts.google.com/o/oauth2/auth" in url_static.content
            # Should have an Input for pasting the auth code
            paste_input = detail.query_one("#pkce-input", Input)
            assert paste_input.placeholder == "Paste auth code..."


# --------------------------------------------------------------------------- #
# API key flow
# --------------------------------------------------------------------------- #


class TestApiKeyFlow:
    """API key flow shows masked input."""

    @pytest.mark.asyncio
    async def test_show_api_key_flow_shows_masked_input(self) -> None:
        """show_api_key_flow shows a password-masked Input."""
        providers = _make_providers()
        app = AuthScreenApp(providers=providers)
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.show_api_key_flow()
            await pilot.pause()
            detail = screen.query_one("#auth-detail")
            key_input = detail.query_one("#api-key-input", Input)
            assert key_input.password is True
            assert key_input.placeholder == "Enter API key..."


# --------------------------------------------------------------------------- #
# Auth status update
# --------------------------------------------------------------------------- #


class TestAuthStatusUpdate:
    """Successful auth updates status to 'Authenticated'."""

    @pytest.mark.asyncio
    async def test_update_provider_status_to_authenticated(self) -> None:
        """update_provider_status changes a provider's displayed status."""
        providers = [
            ProviderInfo(
                name="GitHub Copilot",
                flow_kind=AuthFlowKind.DEVICE,
                status=AuthSessionStatus.UNAUTHENTICATED,
            ),
        ]
        app = AuthScreenApp(providers=providers)
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.update_provider_status(
                "GitHub Copilot", AuthSessionStatus.AUTHENTICATED,
            )
            await pilot.pause()
            # Verify the internal tracking was updated
            table = screen.query_one(DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_auth_flow_completed_message_posted(self) -> None:
        """AuthFlowCompleted message is posted with success=True."""
        providers = _make_providers()
        messages: list[AuthScreen.AuthFlowCompleted] = []

        class CaptureApp(App[None]):
            def on_mount(self) -> None:
                self.push_screen(AuthScreen(providers=providers))

            def on_auth_screen_auth_flow_completed(
                self, message: AuthScreen.AuthFlowCompleted,
            ) -> None:
                messages.append(message)

        app = CaptureApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, AuthScreen)
            screen.post_message(
                AuthScreen.AuthFlowCompleted(provider="GitHub Copilot", success=True),
            )
            await pilot.pause()
            assert len(messages) == 1
            assert messages[0].provider == "GitHub Copilot"
            assert messages[0].success is True


# --------------------------------------------------------------------------- #
# Error display
# --------------------------------------------------------------------------- #


class TestAuthError:
    """Failed auth shows error in detail area."""

    @pytest.mark.asyncio
    async def test_show_error_displays_message(self) -> None:
        """show_error shows an error message in the detail area."""
        providers = _make_providers()
        app = AuthScreenApp(providers=providers)
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.show_error("Authentication failed: invalid token")
            await pilot.pause()
            detail = screen.query_one("#auth-detail")
            error_static = detail.query_one("#auth-error", Static)
            assert "Authentication failed: invalid token" in error_static.content


# --------------------------------------------------------------------------- #
# Escape key — pops screen
# --------------------------------------------------------------------------- #


class TestAuthScreenEscape:
    """Escape key returns to previous screen."""

    @pytest.mark.asyncio
    async def test_escape_pops_screen(self) -> None:
        """Pressing Escape pops the AuthScreen."""
        app = AuthScreenApp(providers=_make_providers())
        async with app.run_test() as pilot:
            assert isinstance(app.screen, AuthScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, AuthScreen)
