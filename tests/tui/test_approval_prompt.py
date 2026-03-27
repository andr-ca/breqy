"""Tests for breqy.tui.widgets.approval_prompt — ApprovalPrompt widget."""
from __future__ import annotations

import pytest

from textual.app import App, ComposeResult
from textual.widgets import Button, Static

from breqy.domain.enums import ApprovalStatus
from breqy.domain.models import ApprovalRequest
from breqy.tui.widgets.approval_prompt import ApprovalPrompt


class ApprovalPromptApp(App[None]):
    """Minimal app that mounts an ApprovalPrompt for testing."""

    BINDINGS = []

    def compose(self) -> ComposeResult:
        yield ApprovalPrompt()


def _make_request(
    id: str = "apr_001",
    description: str = "Execute shell command: ls -la",
) -> ApprovalRequest:
    """Create a sample approval request for tests."""
    return ApprovalRequest(
        id=id,
        session_id="ses_test123",
        agent_id="agt_breqy",
        tool_invocation_id="inv_001",
        description=description,
        status=ApprovalStatus.PENDING,
    )


class TestApprovalPromptShowsDetails:
    """Test that ApprovalPrompt shows approval request details."""

    @pytest.mark.asyncio
    async def test_shows_tool_description(
        self, sample_approval_request: ApprovalRequest
    ) -> None:
        app = ApprovalPromptApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(sample_approval_request)
            await pilot.pause()
            # The description widget should contain the description text
            assert prompt._description_widget is not None
            content = str(prompt._description_widget._Static__content)  # noqa: SLF001
            assert "Execute shell command: ls -la" in content

    @pytest.mark.asyncio
    async def test_shows_three_buttons_when_request_pending(
        self, sample_approval_request: ApprovalRequest
    ) -> None:
        app = ApprovalPromptApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(sample_approval_request)
            await pilot.pause()
            buttons = prompt.query(Button)
            assert len(buttons) == 3


class TestApprovalPromptApprove:
    """Test that Approve button sends Approved message."""

    @pytest.mark.asyncio
    async def test_approve_button_posts_approved_message(
        self, sample_approval_request: ApprovalRequest
    ) -> None:
        messages: list[ApprovalPrompt.Approved] = []

        class CapturingApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ApprovalPrompt()

            def on_approval_prompt_approved(
                self, message: ApprovalPrompt.Approved
            ) -> None:
                messages.append(message)

        app = CapturingApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(sample_approval_request)
            await pilot.pause()
            # Press the Approve button directly
            approve_btn = prompt.query_one("#btn-approve", Button)
            approve_btn.press()
            await pilot.pause()
            assert len(messages) == 1
            assert messages[0].approval_id == "apr_001"
            assert messages[0].extend_to_session is False


class TestApprovalPromptDeny:
    """Test that Deny button sends Denied message."""

    @pytest.mark.asyncio
    async def test_deny_button_posts_denied_message(
        self, sample_approval_request: ApprovalRequest
    ) -> None:
        messages: list[ApprovalPrompt.Denied] = []

        class CapturingApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ApprovalPrompt()

            def on_approval_prompt_denied(
                self, message: ApprovalPrompt.Denied
            ) -> None:
                messages.append(message)

        app = CapturingApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(sample_approval_request)
            await pilot.pause()
            # Press the Deny button directly
            deny_btn = prompt.query_one("#btn-deny", Button)
            deny_btn.press()
            await pilot.pause()
            assert len(messages) == 1
            assert messages[0].approval_id == "apr_001"


class TestApprovalPromptApproveForSession:
    """Test that Approve-for-Session button sends Approved with extend_to_session."""

    @pytest.mark.asyncio
    async def test_approve_session_posts_approved_with_extend(
        self, sample_approval_request: ApprovalRequest
    ) -> None:
        messages: list[ApprovalPrompt.Approved] = []

        class CapturingApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ApprovalPrompt()

            def on_approval_prompt_approved(
                self, message: ApprovalPrompt.Approved
            ) -> None:
                messages.append(message)

        app = CapturingApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(sample_approval_request)
            await pilot.pause()
            # Press the Approve-for-Session button directly
            session_btn = prompt.query_one("#btn-approve-session", Button)
            session_btn.press()
            await pilot.pause()
            assert len(messages) == 1
            assert messages[0].approval_id == "apr_001"
            assert messages[0].extend_to_session is True


class TestApprovalPromptDismissedAfterDecision:
    """Test that the prompt is dismissed after a decision is made."""

    @pytest.mark.asyncio
    async def test_request_removed_after_approve(
        self, sample_approval_request: ApprovalRequest
    ) -> None:
        app = ApprovalPromptApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(sample_approval_request)
            await pilot.pause()
            assert prompt.current_request is not None
            # Press approve
            approve_btn = prompt.query_one("#btn-approve", Button)
            approve_btn.press()
            await pilot.pause()
            # Request should be removed
            assert prompt.current_request is None

    @pytest.mark.asyncio
    async def test_request_removed_after_deny(
        self, sample_approval_request: ApprovalRequest
    ) -> None:
        app = ApprovalPromptApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(sample_approval_request)
            await pilot.pause()
            assert prompt.current_request is not None
            # Press deny
            deny_btn = prompt.query_one("#btn-deny", Button)
            deny_btn.press()
            await pilot.pause()
            assert prompt.current_request is None


class TestApprovalPromptMultiplePending:
    """Test that multiple pending approvals are queued correctly."""

    @pytest.mark.asyncio
    async def test_queued_requests_show_next_after_decision(self) -> None:
        req1 = _make_request(id="apr_001", description="First command")
        req2 = _make_request(id="apr_002", description="Second command")

        app = ApprovalPromptApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(req1)
            prompt.add_request(req2)
            await pilot.pause()
            # Current request should be the first one
            assert prompt.current_request is not None
            assert prompt.current_request.id == "apr_001"
            # Approve the first via key binding (avoids button click issues)
            prompt.focus()
            await pilot.press("a")
            await pilot.pause()
            # Now the second request should be current
            assert prompt.current_request is not None
            assert prompt.current_request.id == "apr_002"

    @pytest.mark.asyncio
    async def test_queue_length_tracks_pending(self) -> None:
        req1 = _make_request(id="apr_001", description="First")
        req2 = _make_request(id="apr_002", description="Second")
        req3 = _make_request(id="apr_003", description="Third")

        app = ApprovalPromptApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(req1)
            prompt.add_request(req2)
            prompt.add_request(req3)
            await pilot.pause()
            assert len(prompt._queue) == 3


class TestApprovalPromptKeyBindings:
    """Test key bindings for A/D/S."""

    @pytest.mark.asyncio
    async def test_key_a_approves(
        self, sample_approval_request: ApprovalRequest
    ) -> None:
        messages: list[ApprovalPrompt.Approved] = []

        class CapturingApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ApprovalPrompt()

            def on_approval_prompt_approved(
                self, message: ApprovalPrompt.Approved
            ) -> None:
                messages.append(message)

        app = CapturingApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(sample_approval_request)
            await pilot.pause()
            prompt.focus()
            await pilot.press("a")
            await pilot.pause()
            assert len(messages) == 1
            assert messages[0].approval_id == "apr_001"
            assert messages[0].extend_to_session is False

    @pytest.mark.asyncio
    async def test_key_d_denies(
        self, sample_approval_request: ApprovalRequest
    ) -> None:
        messages: list[ApprovalPrompt.Denied] = []

        class CapturingApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ApprovalPrompt()

            def on_approval_prompt_denied(
                self, message: ApprovalPrompt.Denied
            ) -> None:
                messages.append(message)

        app = CapturingApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(sample_approval_request)
            await pilot.pause()
            prompt.focus()
            await pilot.press("d")
            await pilot.pause()
            assert len(messages) == 1
            assert messages[0].approval_id == "apr_001"

    @pytest.mark.asyncio
    async def test_key_s_approves_for_session(
        self, sample_approval_request: ApprovalRequest
    ) -> None:
        messages: list[ApprovalPrompt.Approved] = []

        class CapturingApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ApprovalPrompt()

            def on_approval_prompt_approved(
                self, message: ApprovalPrompt.Approved
            ) -> None:
                messages.append(message)

        app = CapturingApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.add_request(sample_approval_request)
            await pilot.pause()
            prompt.focus()
            await pilot.press("s")
            await pilot.pause()
            assert len(messages) == 1
            assert messages[0].approval_id == "apr_001"
            assert messages[0].extend_to_session is True


class TestApprovalPromptEmptyState:
    """Test empty state when no pending approvals."""

    @pytest.mark.asyncio
    async def test_no_buttons_when_empty(self) -> None:
        app = ApprovalPromptApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            await pilot.pause()
            buttons = prompt.query(Button)
            assert len(buttons) == 0

    @pytest.mark.asyncio
    async def test_current_request_is_none_when_empty(self) -> None:
        app = ApprovalPromptApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            assert prompt.current_request is None

    @pytest.mark.asyncio
    async def test_key_bindings_noop_when_empty(self) -> None:
        """Key presses should not crash or post messages when queue is empty."""
        app = ApprovalPromptApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(ApprovalPrompt)
            prompt.focus()
            await pilot.press("a")
            await pilot.press("d")
            await pilot.press("s")
            await pilot.pause()
            # No crash, still empty
            assert prompt.current_request is None
