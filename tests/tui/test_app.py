"""Tests for BreqyApp main application shell."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from breqy.tui.app import BreqyApp


# ============================================================================ #
# Existing tests — preserve backward compatibility
# ============================================================================ #


class TestBreqyAppInit:
    """Tests for BreqyApp initialisation."""

    def test_creates_app_with_default_socket_path(self) -> None:
        app = BreqyApp()
        assert app.socket_path == ""

    def test_creates_app_with_custom_socket_path(self) -> None:
        app = BreqyApp(socket_path="/tmp/test.sock")
        assert app.socket_path == "/tmp/test.sock"

    def test_app_has_title(self) -> None:
        app = BreqyApp()
        assert app.TITLE == "Breqy"

    def test_css_path_is_set(self) -> None:
        app = BreqyApp()
        assert app.CSS_PATH == "styles/breqy.tcss"

    def test_creates_dispatcher(self) -> None:
        """App creates an EventDispatcher on init."""
        from breqy.tui.events import EventDispatcher

        app = BreqyApp()
        assert isinstance(app._dispatcher, EventDispatcher)

    def test_creates_client_when_socket_path_set(self) -> None:
        """App creates an A2AClient when socket_path is non-empty."""
        from breqy.a2a.client import A2AClient

        app = BreqyApp(socket_path="/tmp/test.sock")
        assert isinstance(app._client, A2AClient)

    def test_no_client_when_socket_path_empty(self) -> None:
        """App does NOT create an A2AClient when socket_path is empty."""
        app = BreqyApp()
        assert app._client is None


class TestBreqyAppBindings:
    """Tests for key bindings."""

    def test_has_quit_binding(self) -> None:
        app = BreqyApp()
        keys = [b.key for b in app.BINDINGS]
        assert "ctrl+q" in keys

    def test_has_logs_binding(self) -> None:
        app = BreqyApp()
        keys = [b.key for b in app.BINDINGS]
        assert "ctrl+l" in keys

    def test_has_auth_binding(self) -> None:
        app = BreqyApp()
        keys = [b.key for b in app.BINDINGS]
        assert "ctrl+a" in keys

    def test_has_model_select_binding(self) -> None:
        app = BreqyApp()
        keys = [b.key for b in app.BINDINGS]
        assert "ctrl+m" in keys

    def test_has_escape_binding(self) -> None:
        app = BreqyApp()
        keys = [b.key for b in app.BINDINGS]
        assert "escape" in keys


# ============================================================================ #
# Task 15: Mount pushes real SessionListScreen
# ============================================================================ #


class TestBreqyAppMount:
    """Tests for app mounting and screen management."""

    @pytest.mark.asyncio
    async def test_app_mounts_without_error(self) -> None:
        app = BreqyApp()
        async with app.run_test() as pilot:
            # Verify it mounted without crashing
            assert app.is_running

    @pytest.mark.asyncio
    async def test_initial_screen_is_session_list(self) -> None:
        """on_mount pushes real SessionListScreen (not the placeholder)."""
        from breqy.tui.screens.session_list import SessionListScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            assert isinstance(app.screen, SessionListScreen)

    @pytest.mark.asyncio
    async def test_pop_screen_safe_pops_pushed_screen(self) -> None:
        app = BreqyApp()
        async with app.run_test() as pilot:
            # SessionListScreen was pushed on mount (stack = 2)
            assert len(app.screen_stack) == 2
            app.action_pop_screen_safe()
            # Should have popped back to the default screen (stack = 1)
            assert len(app.screen_stack) == 1

    @pytest.mark.asyncio
    async def test_pop_screen_safe_does_not_pop_last_screen(self) -> None:
        app = BreqyApp()
        async with app.run_test() as pilot:
            # Pop pushed screen first, leaving only default
            app.action_pop_screen_safe()
            assert len(app.screen_stack) == 1
            # Now pop_screen_safe should be a no-op
            app.action_pop_screen_safe()
            assert len(app.screen_stack) == 1

    @pytest.mark.asyncio
    async def test_no_worker_started_when_no_socket(self) -> None:
        """When socket_path is empty, no A2A listener worker is started."""
        app = BreqyApp()
        async with app.run_test() as pilot:
            # Workers list should be empty — no listener started
            assert len(app.workers) == 0


# ============================================================================ #
# Task 15: EventDispatcher setup
# ============================================================================ #


class TestDispatcherSetup:
    """Tests for _setup_dispatcher event routing."""

    def test_dispatcher_has_handlers_for_message_sent(self) -> None:
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.MESSAGE_SENT)

    def test_dispatcher_has_handlers_for_message_chunk(self) -> None:
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.MESSAGE_CHUNK)

    def test_dispatcher_has_handlers_for_task_events(self) -> None:
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.TASK_CREATED)
        assert app._dispatcher.has_handler(EventType.TASK_UPDATED)
        assert app._dispatcher.has_handler(EventType.TASK_COMPLETED)

    def test_dispatcher_has_handlers_for_tool_events(self) -> None:
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.TOOL_INVOCATION_STARTED)
        assert app._dispatcher.has_handler(EventType.TOOL_INVOCATION_COMPLETED)
        assert app._dispatcher.has_handler(EventType.TOOL_INVOCATION_FAILED)
        assert app._dispatcher.has_handler(EventType.TOOL_OUTPUT_CHUNK)

    def test_dispatcher_has_handlers_for_approval(self) -> None:
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.APPROVAL_REQUESTED)

    def test_dispatcher_has_handlers_for_agent_lifecycle(self) -> None:
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.AGENT_CONNECTED)
        assert app._dispatcher.has_handler(EventType.AGENT_DISCONNECTED)


# ============================================================================ #
# Task 15: Event routing to ChatScreen
# ============================================================================ #


class TestEventRouting:
    """Tests that events dispatched are routed to the active ChatScreen."""

    @pytest.mark.asyncio
    async def test_route_to_chat_calls_handler(self) -> None:
        """When a ChatScreen is on the stack, dispatch calls its handler."""
        from breqy.domain.enums import EventType, MessageRole
        from breqy.domain.events import MessageSentEvent
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            # Push a ChatScreen on top
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # Mock the handler
            chat.handle_message_sent = MagicMock()  # type: ignore[assignment]

            event = MessageSentEvent(
                session_id="ses_test",
                message_id="msg_001",
                role=MessageRole.USER,
                content="Hello",
            )
            app._dispatcher.dispatch(event)
            chat.handle_message_sent.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_route_to_chat_noop_without_chat_screen(self) -> None:
        """When no ChatScreen is on the stack, dispatch is a silent no-op."""
        from breqy.domain.enums import EventType, MessageRole
        from breqy.domain.events import MessageSentEvent

        app = BreqyApp()
        async with app.run_test() as pilot:
            # Only SessionListScreen on stack, no ChatScreen
            event = MessageSentEvent(
                session_id="ses_test",
                message_id="msg_001",
                role=MessageRole.USER,
                content="Hello",
            )
            # Should not raise
            app._dispatcher.dispatch(event)


# ============================================================================ #
# Task 15: A2A Worker
# ============================================================================ #


class TestA2AWorker:
    """Tests for the background A2A listener worker."""

    @pytest.mark.asyncio
    async def test_worker_connects_to_engine_socket(self) -> None:
        """Worker calls client.connect() at least once."""
        from breqy.a2a.client import A2AClient

        connect_count = 0

        async def counting_connect():
            nonlocal connect_count
            connect_count += 1
            if connect_count >= 2:
                # Stop after first successful connect + reconnect attempt
                raise ConnectionError("stop")

        mock_client = AsyncMock(spec=A2AClient)
        mock_client.connect = AsyncMock(side_effect=counting_connect)
        mock_client.listen = MagicMock(side_effect=lambda: _async_iter([]))

        app = BreqyApp(socket_path="/tmp/test.sock")
        app._client = mock_client

        async with app.run_test() as pilot:
            app._start_listener()
            await pilot.pause()
            await asyncio.sleep(0.15)

            assert connect_count >= 1

    @pytest.mark.asyncio
    async def test_worker_receives_and_dispatches_events(self) -> None:
        """Worker listens for envelopes, converts to events, dispatches."""
        from breqy.a2a.client import A2AClient
        from breqy.a2a.envelope import Envelope
        from breqy.domain.enums import EventType, MessageRole
        from breqy.domain.events import MessageSentEvent

        event = MessageSentEvent(
            session_id="ses_test",
            message_id="msg_001",
            role=MessageRole.USER,
            content="Hello from engine",
        )
        envelope = Envelope.from_event(event)

        listen_call_count = 0

        def make_listen():
            nonlocal listen_call_count
            listen_call_count += 1
            if listen_call_count == 1:
                return _async_iter([envelope])
            # On reconnect, raise to stop the loop
            raise ConnectionError("stop after first listen")

        mock_client = AsyncMock(spec=A2AClient)
        mock_client.listen = MagicMock(side_effect=make_listen)

        app = BreqyApp(socket_path="/tmp/test.sock")
        app._client = mock_client

        dispatched: list = []
        app._dispatcher.register(EventType.MESSAGE_SENT, dispatched.append)

        async with app.run_test() as pilot:
            app._start_listener()
            await pilot.pause()
            await asyncio.sleep(0.1)

            assert len(dispatched) >= 1
            assert dispatched[0].content == "Hello from engine"

    @pytest.mark.asyncio
    async def test_connection_failure_shows_notification(self) -> None:
        """On ConnectionError, app notifies user of failure."""
        from breqy.a2a.client import A2AClient

        mock_client = AsyncMock(spec=A2AClient)
        mock_client.connect.side_effect = ConnectionError("refused")

        app = BreqyApp(socket_path="/tmp/test.sock")
        app._client = mock_client

        notifications: list[str] = []
        original_notify = app.notify

        def capture_notify(message, **kwargs):
            notifications.append(str(message))
            return original_notify(message, **kwargs)

        app.notify = capture_notify  # type: ignore[assignment]

        async with app.run_test() as pilot:
            app._start_listener()
            await pilot.pause()
            await asyncio.sleep(0.15)

            assert any("onnect" in n for n in notifications)

    @pytest.mark.asyncio
    async def test_disconnect_triggers_reconnect(self) -> None:
        """When listen() ends (disconnect), worker retries connect."""
        from breqy.a2a.client import A2AClient

        connect_count = 0

        async def mock_connect():
            nonlocal connect_count
            connect_count += 1
            if connect_count >= 3:
                raise ConnectionError("stop retrying in test")

        mock_client = AsyncMock(spec=A2AClient)
        mock_client.connect = AsyncMock(side_effect=mock_connect)
        # listen() returns immediately each time (simulates disconnect)
        mock_client.listen = MagicMock(side_effect=lambda: _async_iter([]))

        app = BreqyApp(socket_path="/tmp/test.sock")
        app._client = mock_client

        async with app.run_test() as pilot:
            app._start_listener()
            await pilot.pause()
            await asyncio.sleep(0.3)

            # Should have attempted connect at least twice (initial + reconnect)
            assert connect_count >= 2


# ============================================================================ #
# Task 15: Screen navigation
# ============================================================================ #


class TestScreenNavigation:
    """Tests for screen navigation actions."""

    @pytest.mark.asyncio
    async def test_action_push_logs_pushes_logs_screen(self) -> None:
        from breqy.tui.screens.logs import LogsScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            app.action_push_logs()
            await pilot.pause()
            assert isinstance(app.screen, LogsScreen)

    @pytest.mark.asyncio
    async def test_action_push_auth_pushes_auth_screen(self) -> None:
        from breqy.tui.screens.auth import AuthScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            app.action_push_auth()
            await pilot.pause()
            assert isinstance(app.screen, AuthScreen)

    @pytest.mark.asyncio
    async def test_action_push_model_select_pushes_model_screen(self) -> None:
        from breqy.tui.screens.model_select import ModelSelectScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            app.action_push_model_select()
            await pilot.pause()
            assert isinstance(app.screen, ModelSelectScreen)

    @pytest.mark.asyncio
    async def test_session_list_to_chat_navigation(self) -> None:
        """Selecting a session from SessionListScreen pushes ChatScreen."""
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.screens.session_list import SessionListScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            # Verify we start on SessionListScreen
            assert isinstance(app.screen, SessionListScreen)

            # Post a SessionSelected message
            session_list = app.screen
            session_list.post_message(
                SessionListScreen.SessionSelected(session_id="ses_abc")
            )
            await pilot.pause()

            assert isinstance(app.screen, ChatScreen)
            assert app.screen.session_id == "ses_abc"

    @pytest.mark.asyncio
    async def test_chat_back_to_session_list(self) -> None:
        """Popping ChatScreen returns to SessionListScreen."""
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.screens.session_list import SessionListScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            # Push ChatScreen
            session_list = app.screen
            session_list.post_message(
                SessionListScreen.SessionSelected(session_id="ses_abc")
            )
            await pilot.pause()
            assert isinstance(app.screen, ChatScreen)

            # Pop back
            app.pop_screen()
            await pilot.pause()
            assert isinstance(app.screen, SessionListScreen)


# ============================================================================ #
# Task 15: Send message round-trip (mock engine)
# ============================================================================ #


class TestSendEventRoundTrip:
    """Test that app can send events via the A2AClient."""

    @pytest.mark.asyncio
    async def test_send_event_calls_client(self) -> None:
        """App.send_event forwards to the A2A client."""
        from breqy.a2a.client import A2AClient
        from breqy.domain.enums import MessageRole
        from breqy.domain.events import MessageSentEvent

        mock_client = AsyncMock(spec=A2AClient)
        app = BreqyApp(socket_path="/tmp/test.sock")
        app._client = mock_client

        event = MessageSentEvent(
            session_id="ses_test",
            message_id="msg_001",
            role=MessageRole.USER,
            content="Hello",
        )

        await app.send_event(event)
        mock_client.send_event.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_send_event_noop_without_client(self) -> None:
        """send_event is a silent no-op when no client configured."""
        from breqy.domain.enums import MessageRole
        from breqy.domain.events import MessageSentEvent

        app = BreqyApp()  # no socket_path

        event = MessageSentEvent(
            session_id="ses_test",
            message_id="msg_001",
            role=MessageRole.USER,
            content="Hello",
        )

        # Should not raise
        await app.send_event(event)


# ============================================================================ #
# Helpers
# ============================================================================ #


async def _async_iter(items):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item


# ============================================================================ #
# Session creation via "N" key
# ============================================================================ #


class TestNewSessionCreation:
    """Tests for wiring the 'N' key to create sessions via the engine."""

    @pytest.mark.asyncio
    async def test_new_session_requested_sends_event_to_engine(self) -> None:
        """Pressing N sends a SessionCreateRequestedEvent via send_event."""
        from breqy.domain.events import SessionCreateRequestedEvent
        from breqy.tui.screens.session_list import SessionListScreen

        sent_events: list = []

        app = BreqyApp(socket_path="/tmp/test.sock")

        original_send = app.send_event

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            assert isinstance(app.screen, SessionListScreen)
            # Post the NewSessionRequested message (simulates N press)
            app.screen.post_message(SessionListScreen.NewSessionRequested())
            await pilot.pause()

            assert len(sent_events) == 1
            assert isinstance(sent_events[0], SessionCreateRequestedEvent)
            assert sent_events[0].requested_agent_id == "default"

    @pytest.mark.asyncio
    async def test_session_created_event_pushes_chat_screen(self) -> None:
        """When a SessionCreatedEvent is dispatched, app pushes ChatScreen."""
        from breqy.domain.enums import EventType
        from breqy.domain.events import SessionCreatedEvent
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()

        async with app.run_test() as pilot:
            # Dispatch a SessionCreatedEvent through the dispatcher
            event = SessionCreatedEvent(
                session_id="ses_new_123",
                primary_agent_id="agt_default",
            )
            app._dispatcher.dispatch(event)
            await pilot.pause()

            # ChatScreen should be pushed
            assert isinstance(app.screen, ChatScreen)
            assert app.screen.session_id == "ses_new_123"

    @pytest.mark.asyncio
    async def test_dispatcher_has_handler_for_session_created(self) -> None:
        """Dispatcher should have a handler for SESSION_CREATED events."""
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.SESSION_CREATED)

    @pytest.mark.asyncio
    async def test_new_session_no_op_without_client(self) -> None:
        """When no client is configured, the handler should not crash."""
        from breqy.tui.screens.session_list import SessionListScreen

        app = BreqyApp()  # no socket_path

        async with app.run_test() as pilot:
            assert isinstance(app.screen, SessionListScreen)
            # Post the NewSessionRequested message
            app.screen.post_message(SessionListScreen.NewSessionRequested())
            await pilot.pause()
            # Should not crash, should still be on session list
            # (no engine to create session, so no ChatScreen pushed)


# ============================================================================ #
# User message send: MessageSubmitted -> MessageSentEvent -> A2A
# ============================================================================ #


class TestUserMessageSend:
    """Test that typing a message in ChatScreen sends it to the engine."""

    @pytest.mark.asyncio
    async def test_message_submitted_sends_message_sent_event(self) -> None:
        """When MessageSubmitted bubbles from MessageInput, the app creates a
        MessageSentEvent with role=USER and sends it via A2A."""
        from breqy.domain.enums import MessageRole
        from breqy.domain.events import MessageSentEvent
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.screens.session_list import SessionListScreen

        sent_events: list = []

        app = BreqyApp()  # no socket — we capture send_event directly

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            # Push a ChatScreen
            app.push_screen(ChatScreen(session_id="ses_chat_test"))
            await pilot.pause()

            # Post MessageSubmitted (simulates user typing + Enter)
            from breqy.tui.widgets.message_input import MessageSubmitted

            app.screen.query_one("MessageInput").post_message(
                MessageSubmitted(text="Hello agent!")
            )
            await pilot.pause()

            assert len(sent_events) == 1
            evt = sent_events[0]
            assert isinstance(evt, MessageSentEvent)
            assert evt.session_id == "ses_chat_test"
            assert evt.role == MessageRole.USER
            assert evt.content == "Hello agent!"
            assert evt.message_id.startswith("msg_")

    @pytest.mark.asyncio
    async def test_message_submitted_echoes_locally_to_chat_view(self) -> None:
        """When user submits a message, it should immediately appear in ChatView
        as a local echo (USER message), before the engine round-trip completes."""
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.widgets.chat_view import ChatView
        from breqy.tui.widgets.message_input import MessageSubmitted

        app = BreqyApp()

        async def noop_send(event):
            pass

        app.send_event = noop_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            app.push_screen(ChatScreen(session_id="ses_echo_test"))
            await pilot.pause()

            # Post MessageSubmitted
            app.screen.query_one("MessageInput").post_message(
                MessageSubmitted(text="Hello, local echo!")
            )
            await pilot.pause()

            # ChatView should contain the user message
            chat_screen = app.screen
            assert isinstance(chat_screen, ChatScreen)
            chat_view = chat_screen.query_one(ChatView)
            assert len(chat_view.log_widget.lines) == 1

    @pytest.mark.asyncio
    async def test_message_submitted_noop_without_chat_screen(self) -> None:
        """MessageSubmitted with no ChatScreen on stack is a silent no-op."""
        from breqy.tui.widgets.message_input import MessageSubmitted

        sent_events: list = []

        app = BreqyApp()  # no socket

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            # Only SessionListScreen on stack — no ChatScreen
            # Manually call the handler (if it exists) with no ChatScreen
            msg = MessageSubmitted(text="orphan message")
            # The message would bubble but there's no ChatScreen
            # We can't easily post from SessionListScreen, so call directly
            if hasattr(app, "on_message_submitted"):
                app.on_message_submitted(msg)
                await pilot.pause()

            assert len(sent_events) == 0


# ============================================================================ #
# structlog migration
# ============================================================================ #

def test_tui_app_uses_structlog():
    """tui.app module-level logger is structlog, not stdlib."""
    import logging as _logging
    from breqy.tui import app as app_module
    assert hasattr(app_module, "logger")
    assert not isinstance(app_module.logger, _logging.Logger)
