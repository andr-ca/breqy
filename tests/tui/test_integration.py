"""Integration tests for the Breqy TUI.

End-to-end tests that exercise the full BreqyApp with mocked A2A
communication.  Each test starts the real app (socket_path="" means no
A2A connection) and verifies complete workflows through the screen stack.
"""
from __future__ import annotations

import pytest
from textual.widgets import Button, DataTable, RichLog

from breqy.domain.enums import (
    AuthFlowKind,
    AuthSessionStatus,
    EventType,
    MessageRole,
    SessionStatus,
)
from breqy.domain.events import (
    ApprovalRequestedEvent,
    MessageSentEvent,
)
from breqy.domain.models import Session
from breqy.tui.app import BreqyApp
from breqy.tui.screens.auth import AuthScreen, ProviderInfo
from breqy.tui.screens.chat import ChatScreen
from breqy.tui.screens.logs import LogsScreen
from breqy.tui.screens.session_list import SessionListScreen
from breqy.tui.widgets.approval_prompt import ApprovalPrompt
from breqy.tui.widgets.chat_view import ChatView
from breqy.tui.widgets.control_bar import ControlBar
from breqy.tui.widgets.message_input import MessageInput


# ============================================================================ #
# Test 1: Full startup → session list → select session → ChatScreen
# ============================================================================ #


class TestStartupToSessionNavigation:
    """App starts, shows SessionListScreen, user selects session, ChatScreen pushed."""

    @pytest.mark.asyncio
    async def test_startup_to_chat_flow(self) -> None:
        """Full startup → load sessions → select → ChatScreen pushed."""
        app = BreqyApp()
        async with app.run_test() as pilot:
            # 1. Verify SessionListScreen is the initial screen
            assert isinstance(app.screen, SessionListScreen)

            # 2. Load sessions into the list
            session = Session(
                id="ses_integ_001",
                primary_agent_id="agt_main",
                status=SessionStatus.ACTIVE,
            )
            session_list: SessionListScreen = app.screen  # type: ignore[assignment]
            session_list.load_sessions([session])
            await pilot.pause()

            # 3. Verify the DataTable has one row
            table = session_list.query_one(DataTable)
            assert table.row_count == 1

            # 4. Select the session by posting SessionSelected message
            session_list.post_message(
                SessionListScreen.SessionSelected(session_id="ses_integ_001"),
            )
            await pilot.pause()

            # 5. Verify ChatScreen is now on top
            assert isinstance(app.screen, ChatScreen)
            assert app.screen.session_id == "ses_integ_001"


# ============================================================================ #
# Test 2: Message send + receive flow via dispatcher
# ============================================================================ #


class TestMessageRoundTrip:
    """User sends message, receives assistant response via dispatcher."""

    @pytest.mark.asyncio
    async def test_message_send_and_receive(self) -> None:
        """Push ChatScreen, dispatch MessageSentEvent, verify ChatView shows it."""
        app = BreqyApp()
        async with app.run_test() as pilot:
            # Push ChatScreen directly
            app.push_screen(ChatScreen(session_id="ses_integ_002"))
            await pilot.pause()
            assert isinstance(app.screen, ChatScreen)

            chat_screen: ChatScreen = app.screen  # type: ignore[assignment]

            # Simulate user message arriving via dispatcher
            user_event = MessageSentEvent(
                session_id="ses_integ_002",
                message_id="msg_user_001",
                role=MessageRole.USER,
                content="Hello, can you help?",
            )
            app._dispatcher.dispatch(user_event)
            await pilot.pause()

            # Verify the user message appeared in ChatView
            chat_view = chat_screen.query_one(ChatView)
            log_widget = chat_view.log_widget
            assert len(log_widget.lines) >= 1

            # Simulate assistant response arriving via dispatcher
            assistant_event = MessageSentEvent(
                session_id="ses_integ_002",
                message_id="msg_asst_001",
                role=MessageRole.ASSISTANT,
                content="Sure, I can help with that!",
                agent_id="agt_breqy",
            )
            app._dispatcher.dispatch(assistant_event)
            await pilot.pause()

            # Verify both messages are now in the ChatView
            assert len(log_widget.lines) >= 2


# ============================================================================ #
# Test 3: Approval flow — request → approve → Approved message posted
# ============================================================================ #


class TestApprovalFlow:
    """Approval requested → user approves → Approved message posted to app."""

    @pytest.mark.asyncio
    async def test_approval_request_approve_flow(self) -> None:
        """Dispatch ApprovalRequestedEvent, click approve, verify Approved posted."""
        approved_messages: list[ApprovalPrompt.Approved] = []

        class CapturingApp(BreqyApp):
            CSS_PATH = None  # type: ignore[assignment]

            def on_approval_prompt_approved(
                self, msg: ApprovalPrompt.Approved,
            ) -> None:
                approved_messages.append(msg)

        app = CapturingApp()
        async with app.run_test() as pilot:
            # Push ChatScreen
            app.push_screen(ChatScreen(session_id="ses_integ_003"))
            await pilot.pause()

            chat_screen: ChatScreen = app.screen  # type: ignore[assignment]

            # Dispatch an approval request via the app's dispatcher
            approval_event = ApprovalRequestedEvent(
                session_id="ses_integ_003",
                approval_id="apr_integ_001",
                invocation_id="inv_integ_001",
                description="Execute shell command: ls -la",
            )
            app._dispatcher.dispatch(approval_event)
            await pilot.pause()

            # Verify ApprovalPrompt shows the request
            prompt = chat_screen.query_one(ApprovalPrompt)
            assert prompt.current_request is not None
            assert prompt.current_request.id == "apr_integ_001"

            # Click the Approve button
            approve_btn = chat_screen.query_one("#btn-approve", Button)
            approve_btn.press()
            await pilot.pause()

            # Verify Approved message was posted
            assert len(approved_messages) == 1
            assert approved_messages[0].approval_id == "apr_integ_001"
            assert approved_messages[0].extend_to_session is False

            # Verify the prompt is cleared
            assert prompt.current_request is None


# ============================================================================ #
# Test 4: Control flow — enable control bar, click stop, verify action posted
# ============================================================================ #


class TestControlStopFlow:
    """User clicks stop → ControlAction message posted."""

    @pytest.mark.asyncio
    async def test_control_stop_action(self) -> None:
        """Push ChatScreen, enable controls, click stop, verify action posted."""
        control_actions: list[ControlBar.ControlAction] = []

        class CapturingApp(BreqyApp):
            CSS_PATH = None  # type: ignore[assignment]

            def on_control_bar_control_action(
                self, msg: ControlBar.ControlAction,
            ) -> None:
                control_actions.append(msg)

        app = CapturingApp()
        async with app.run_test() as pilot:
            # Push ChatScreen
            app.push_screen(ChatScreen(session_id="ses_integ_004"))
            await pilot.pause()

            chat_screen: ChatScreen = app.screen  # type: ignore[assignment]

            # Enable the control bar (stop button is disabled by default)
            control_bar = chat_screen.query_one(ControlBar)
            control_bar.set_active(True)
            await pilot.pause()

            # Verify stop button is now enabled
            stop_btn = chat_screen.query_one("#btn-stop", Button)
            assert stop_btn.disabled is False

            # Click stop
            stop_btn.press()
            await pilot.pause()

            # Verify ControlAction was posted with CONTROL_STOP
            assert len(control_actions) == 1
            assert control_actions[0].event_type == EventType.CONTROL_STOP


# ============================================================================ #
# Test 5: Auth screen accessible and shows provider list
# ============================================================================ #


class TestAuthScreenAccessible:
    """Ctrl+A pushes AuthScreen overlay with provider list."""

    @pytest.mark.asyncio
    async def test_auth_screen_push_and_provider_list(self) -> None:
        """Push auth screen via action, load providers, verify table rows."""
        app = BreqyApp()
        async with app.run_test() as pilot:
            # Start on SessionListScreen
            assert isinstance(app.screen, SessionListScreen)

            # Push AuthScreen via action
            app.action_push_auth()
            await pilot.pause()

            assert isinstance(app.screen, AuthScreen)

            # Load providers
            auth_screen: AuthScreen = app.screen  # type: ignore[assignment]
            providers = [
                ProviderInfo(
                    name="anthropic",
                    flow_kind=AuthFlowKind.API_KEY,
                    status=AuthSessionStatus.UNAUTHENTICATED,
                ),
                ProviderInfo(
                    name="openai",
                    flow_kind=AuthFlowKind.API_KEY,
                    status=AuthSessionStatus.AUTHENTICATED,
                ),
            ]
            auth_screen.load_providers(providers)
            await pilot.pause()

            # Verify the DataTable shows two provider rows
            table = auth_screen.query_one(DataTable)
            assert table.row_count == 2


# ============================================================================ #
# Test 6: Logs screen accessible and accepts dispatched events
# ============================================================================ #


class TestLogsScreenAcceptsEvents:
    """Ctrl+L pushes LogsScreen; dispatched events appear in the log."""

    @pytest.mark.asyncio
    async def test_logs_screen_receives_dispatched_events(self) -> None:
        """Push LogsScreen, dispatch event via app, verify it appears."""
        app = BreqyApp()
        async with app.run_test() as pilot:
            # Push LogsScreen via action
            app.action_push_logs()
            await pilot.pause()

            assert isinstance(app.screen, LogsScreen)

            logs_screen: LogsScreen = app.screen  # type: ignore[assignment]

            # Dispatch an event through the app's dispatcher — the app
            # routes ALL events to LogsScreen when one is on the stack.
            event = MessageSentEvent(
                session_id="ses_integ_005",
                message_id="msg_log_001",
                role=MessageRole.USER,
                content="Test log entry",
            )
            app._dispatcher.dispatch(event)
            await pilot.pause()

            # Verify the event was logged
            assert len(logs_screen._entries) == 1
            entry = logs_screen._entries[0]
            assert entry.event_type == EventType.MESSAGE_SENT.value
            assert entry.source == "engine"  # no agent_id → defaults to "engine"

            # Verify the RichLog display was updated (not empty-state)
            rich_log = logs_screen.query_one("#logs-display", RichLog)
            assert len(rich_log.lines) >= 1
