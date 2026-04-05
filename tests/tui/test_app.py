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
        assert "ctrl+shift+m" in keys

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

    def test_dispatcher_has_handler_for_reasoning_started(self) -> None:
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.REASONING_STARTED)

    def test_dispatcher_has_handler_for_reasoning_done(self) -> None:
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.REASONING_DONE)

    def test_dispatcher_has_handler_for_reasoning_text_chunk(self) -> None:
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.REASONING_TEXT_CHUNK)


# ============================================================================ #
# Task 5: Reasoning event routing to ChatScreen
# ============================================================================ #


class TestReasoningEventRouting:
    """Tests that REASONING_STARTED/DONE events are routed to the active ChatScreen."""

    @pytest.mark.asyncio
    async def test_reasoning_started_routes_to_chat_screen(self) -> None:
        """REASONING_STARTED dispatched routes to ChatScreen.handle_reasoning_started()."""
        from breqy.domain.events import ReasoningStartedEvent
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            chat.handle_reasoning_started = MagicMock()  # type: ignore[assignment]

            event = ReasoningStartedEvent(session_id="ses_test")
            app._dispatcher.dispatch(event)
            chat.handle_reasoning_started.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_reasoning_done_routes_to_chat_screen(self) -> None:
        """REASONING_DONE dispatched routes to ChatScreen.handle_reasoning_done()."""
        from breqy.domain.events import ReasoningDoneEvent
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            chat.handle_reasoning_done = MagicMock()  # type: ignore[assignment]

            event = ReasoningDoneEvent(session_id="ses_test")
            app._dispatcher.dispatch(event)
            chat.handle_reasoning_done.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_reasoning_text_chunk_routes_to_chat_screen(self) -> None:
        """REASONING_TEXT_CHUNK dispatched routes to ChatScreen.handle_reasoning_text_chunk()."""
        from breqy.domain.events import ReasoningTextChunkEvent
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            chat.handle_reasoning_text_chunk = MagicMock()  # type: ignore[assignment]

            event = ReasoningTextChunkEvent(session_id="ses_test", chunk="Hello thinking")
            app._dispatcher.dispatch(event)
            chat.handle_reasoning_text_chunk.assert_called_once_with(event)


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
    async def test_action_push_model_select_sends_request_when_chat_active(self) -> None:
        """ctrl+m now sends ModelListRequestedEvent instead of directly pushing screen."""
        from breqy.domain.events import ModelListRequestedEvent
        from breqy.tui.screens.chat import ChatScreen

        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_nav_test")
            app.push_screen(chat)
            await pilot.pause()

            app._agent_connected = True  # Agent must be connected
            app.action_push_model_select()
            await pilot.pause()

            assert len(sent_events) == 1
            assert isinstance(sent_events[0], ModelListRequestedEvent)

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
            session_list.post_message(SessionListScreen.SessionSelected(session_id="ses_abc"))
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
            session_list.post_message(SessionListScreen.SessionSelected(session_id="ses_abc"))
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

            app.screen.query_one("MessageInput").post_message(MessageSubmitted(text="Hello agent!"))
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


# ============================================================================ #
# Observability: Task 9 — DEBUG trace calls in TUI event flow
# ============================================================================ #


class TestTuiDebugTracing:
    """Tests that key TUI event flow methods contain debug logging."""

    def test_on_message_submitted_has_debug_logging(self) -> None:
        """on_message_submitted should include debug logging."""
        import inspect

        source = inspect.getsource(BreqyApp.on_message_submitted)
        assert "logger.debug" in source

    def test_start_listener_has_debug_logging(self) -> None:
        """_start_listener should log when events are received."""
        import inspect

        source = inspect.getsource(BreqyApp._start_listener)
        assert "logger.debug" in source

    def test_route_to_chat_has_debug_logging(self) -> None:
        """_route_to_chat should log when dispatching to a screen."""
        import inspect

        source = inspect.getsource(BreqyApp._route_to_chat)
        assert "logger.debug" in source

    def test_send_event_has_debug_logging(self) -> None:
        """send_event should log when sending events to the engine."""
        import inspect

        source = inspect.getsource(BreqyApp.send_event)
        assert "logger.debug" in source


class TestLogBuffer:
    """Tests for BreqyApp._log_buffer background event buffer."""

    def test_breqy_app_has_log_buffer(self) -> None:
        """BreqyApp should have a _log_buffer deque for background logging."""
        import collections

        app = BreqyApp()
        assert hasattr(app, "_log_buffer")
        assert isinstance(app._log_buffer, collections.deque)

    def test_route_to_logs_appends_to_buffer(self) -> None:
        """_route_to_logs should always append to _log_buffer, even without LogsScreen."""
        from breqy.domain.enums import EventType, MessageRole
        from breqy.domain.events import MessageSentEvent

        app = BreqyApp()
        event = MessageSentEvent(
            session_id="ses_test",
            message_id="msg_001",
            role=MessageRole.USER,
            content="Hello",
        )
        # No LogsScreen on the stack, but buffer should still get the entry
        app._route_to_logs(event)
        assert len(app._log_buffer) == 1

    def test_log_buffer_has_maxlen(self) -> None:
        """_log_buffer should have a maxlen to avoid unbounded growth."""
        app = BreqyApp()
        assert app._log_buffer.maxlen is not None
        assert app._log_buffer.maxlen > 0


# ============================================================================ #
# Phase 5c: MODEL_INFO dispatcher routing
# ============================================================================ #


class TestModelInfoDispatcher:
    """Tests that MODEL_INFO events are dispatched to ChatScreen."""

    def test_dispatcher_has_handler_for_model_info(self) -> None:
        """Dispatcher should have a handler for MODEL_INFO events."""
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.MODEL_INFO)

    @pytest.mark.asyncio
    async def test_model_info_routes_to_chat_screen(self) -> None:
        """MODEL_INFO event should be dispatched to ChatScreen.handle_model_info()."""
        from breqy.domain.events import ModelInfoEvent
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            chat.handle_model_info = MagicMock()  # type: ignore[assignment]

            event = ModelInfoEvent(
                session_id="ses_test",
                provider_id="copilot",
                model_id="gpt-4o",
            )
            app._dispatcher.dispatch(event)
            chat.handle_model_info.assert_called_once_with(event)


# ============================================================================ #
# Phase 5c: MODEL_LIST_RESPONSE dispatcher routing
# ============================================================================ #


class TestModelListResponseDispatcher:
    """Tests that MODEL_LIST_RESPONSE events push ModelSelectScreen."""

    def test_dispatcher_has_handler_for_model_list_response(self) -> None:
        """Dispatcher should have a handler for MODEL_LIST_RESPONSE events."""
        from breqy.domain.enums import EventType

        app = BreqyApp()
        assert app._dispatcher.has_handler(EventType.MODEL_LIST_RESPONSE)

    @pytest.mark.asyncio
    async def test_model_list_response_pushes_model_select_screen(self) -> None:
        """MODEL_LIST_RESPONSE event should push ModelSelectScreen with converted models."""
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.models import ModelEntry
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.screens.model_select import ModelSelectScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # Simulate pending request (as if ctrl+m was pressed)
            app._model_list_pending = True

            event = ModelListResponseEvent(
                session_id="ses_test",
                models=[
                    ModelEntry(
                        provider="copilot",
                        model_id="gpt-4o",
                        display_name="GPT-4o",
                        is_authenticated=True,
                    ),
                    ModelEntry(
                        provider="copilot",
                        model_id="gpt-4o-mini",
                        display_name="GPT-4o Mini",
                        is_authenticated=True,
                    ),
                ],
                current_provider="copilot",
                current_model="gpt-4o",
            )
            app._dispatcher.dispatch(event)
            await pilot.pause()

            # ModelSelectScreen should be pushed on top
            assert isinstance(app.screen, ModelSelectScreen)

    @pytest.mark.asyncio
    async def test_model_list_response_converts_model_entry_to_model_option(self) -> None:
        """ModelEntry objects should be converted to ModelOption for ModelSelectScreen."""
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.models import ModelEntry
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.screens.model_select import ModelSelectScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # Simulate pending request (as if ctrl+m was pressed)
            app._model_list_pending = True

            event = ModelListResponseEvent(
                session_id="ses_test",
                models=[
                    ModelEntry(
                        provider="copilot",
                        model_id="gpt-4o",
                        display_name="GPT-4o",
                        is_authenticated=True,
                    ),
                ],
                current_provider="copilot",
                current_model="gpt-4o",
            )
            app._dispatcher.dispatch(event)
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, ModelSelectScreen)
            assert len(screen._models) == 1
            assert screen._models[0].provider == "copilot"
            assert screen._models[0].model_id == "gpt-4o"
            assert screen._models[0].display_name == "GPT-4o"
            assert screen._current_model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_model_list_response_clears_pending_flag(self) -> None:
        """MODEL_LIST_RESPONSE should clear the _model_list_pending flag."""
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.models import ModelEntry
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # Simulate pending state
            app._model_list_pending = True

            event = ModelListResponseEvent(
                session_id="ses_test",
                models=[],
                current_provider="copilot",
                current_model="gpt-4o",
            )
            app._dispatcher.dispatch(event)
            await pilot.pause()

            assert app._model_list_pending is False

    @pytest.mark.asyncio
    async def test_model_list_response_noop_without_chat_screen(self) -> None:
        """MODEL_LIST_RESPONSE should not push ModelSelectScreen if no ChatScreen is active."""
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.models import ModelEntry
        from breqy.tui.screens.model_select import ModelSelectScreen

        app = BreqyApp()
        async with app.run_test() as pilot:
            # Only SessionListScreen on stack — no ChatScreen

            event = ModelListResponseEvent(
                session_id="ses_test",
                models=[
                    ModelEntry(
                        provider="copilot",
                        model_id="gpt-4o",
                        display_name="GPT-4o",
                        is_authenticated=True,
                    ),
                ],
                current_provider="copilot",
                current_model="gpt-4o",
            )
            # Should not raise
            app._dispatcher.dispatch(event)
            await pilot.pause()

            # ModelSelectScreen should NOT be pushed
            assert not isinstance(app.screen, ModelSelectScreen)


# ============================================================================ #
# Phase 5d: ctrl+m sends ModelListRequestedEvent + debounce
# ============================================================================ #


class TestCtrlMModelList:
    """Tests for ctrl+m sending ModelListRequestedEvent to engine."""

    @pytest.mark.asyncio
    async def test_ctrl_m_sends_model_list_requested_event(self) -> None:
        """Pressing ctrl+m with a ChatScreen active should send ModelListRequestedEvent."""
        from breqy.domain.events import ModelListRequestedEvent
        from breqy.tui.screens.chat import ChatScreen

        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_model_test")
            app.push_screen(chat)
            await pilot.pause()

            app._agent_connected = True  # Agent must be connected
            app.action_push_model_select()
            await pilot.pause()

            assert len(sent_events) == 1
            evt = sent_events[0]
            assert isinstance(evt, ModelListRequestedEvent)
            assert evt.session_id == "ses_model_test"

    @pytest.mark.asyncio
    async def test_ctrl_m_sets_pending_flag(self) -> None:
        """ctrl+m should set _model_list_pending to True."""
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()

        async def noop_send(event):
            pass

        app.send_event = noop_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            assert app._model_list_pending is False
            app._agent_connected = True  # Agent must be connected
            app.action_push_model_select()
            assert app._model_list_pending is True

    @pytest.mark.asyncio
    async def test_ctrl_m_debounce_ignores_duplicate(self) -> None:
        """When _model_list_pending is True, ctrl+m should not send another request."""
        from breqy.tui.screens.chat import ChatScreen

        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            app._agent_connected = True  # Agent must be connected
            # First press
            app.action_push_model_select()
            await pilot.pause()
            assert len(sent_events) == 1

            # Second press while pending — should be ignored
            app.action_push_model_select()
            await pilot.pause()
            assert len(sent_events) == 1

    @pytest.mark.asyncio
    async def test_ctrl_m_noop_without_chat_screen(self) -> None:
        """ctrl+m without a ChatScreen on stack should not send any event."""
        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            # Only SessionListScreen — no ChatScreen
            app.action_push_model_select()
            await pilot.pause()
            assert len(sent_events) == 0

    @pytest.mark.asyncio
    async def test_ctrl_m_does_not_push_model_select_directly(self) -> None:
        """ctrl+m should NOT immediately push ModelSelectScreen (waits for response)."""
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.screens.model_select import ModelSelectScreen

        app = BreqyApp()

        async def noop_send(event):
            pass

        app.send_event = noop_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            app._agent_connected = True  # Agent must be connected
            app.action_push_model_select()
            await pilot.pause()

            # Should still be on ChatScreen, NOT ModelSelectScreen
            assert isinstance(app.screen, ChatScreen)


# ============================================================================ #
# Phase 5e: ModelSelected → ModelSwitchRequestedEvent
# ============================================================================ #


class TestModelSelectedHandler:
    """Tests that selecting a model sends ModelSwitchRequestedEvent."""

    @pytest.mark.asyncio
    async def test_model_selected_sends_switch_event(self) -> None:
        """When ModelSelectScreen posts ModelSelected, app should send ModelSwitchRequestedEvent."""
        from breqy.domain.events import ModelSwitchRequestedEvent
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.screens.model_select import ModelSelectScreen

        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_switch_test")
            app.push_screen(chat)
            await pilot.pause()

            # Push a ModelSelectScreen (simulating response handler)
            from breqy.tui.screens.model_select import ModelOption

            model_screen = ModelSelectScreen(
                models=[
                    ModelOption(provider="copilot", model_id="gpt-4o", display_name="GPT-4o"),
                ],
                current_model="gpt-4o",
            )
            app.push_screen(model_screen)
            await pilot.pause()

            # Post the ModelSelected message
            model_screen.post_message(
                ModelSelectScreen.ModelSelected(provider="copilot", model_id="gpt-4o-mini")
            )
            await pilot.pause()

            assert len(sent_events) == 1
            evt = sent_events[0]
            assert isinstance(evt, ModelSwitchRequestedEvent)
            assert evt.provider_id == "copilot"
            assert evt.model_id == "gpt-4o-mini"
            assert evt.session_id == "ses_switch_test"

    @pytest.mark.asyncio
    async def test_model_selected_uses_correct_session_id(self) -> None:
        """ModelSwitchRequestedEvent should use the ChatScreen's session_id."""
        from breqy.domain.events import ModelSwitchRequestedEvent
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.screens.model_select import ModelOption, ModelSelectScreen

        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_unique_42")
            app.push_screen(chat)
            await pilot.pause()

            model_screen = ModelSelectScreen(
                models=[ModelOption(provider="claude", model_id="sonnet", display_name="Sonnet")],
                current_model="sonnet",
            )
            app.push_screen(model_screen)
            await pilot.pause()

            model_screen.post_message(
                ModelSelectScreen.ModelSelected(provider="claude", model_id="opus")
            )
            await pilot.pause()

            assert len(sent_events) == 1
            assert sent_events[0].session_id == "ses_unique_42"

    @pytest.mark.asyncio
    async def test_model_selected_noop_without_chat_screen(self) -> None:
        """ModelSelected without a ChatScreen on stack should not send any event."""
        from breqy.tui.screens.model_select import ModelOption, ModelSelectScreen

        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            # Push ModelSelectScreen directly (no ChatScreen underneath)
            model_screen = ModelSelectScreen(
                models=[ModelOption(provider="copilot", model_id="gpt-4o", display_name="GPT-4o")],
            )
            app.push_screen(model_screen)
            await pilot.pause()

            model_screen.post_message(
                ModelSelectScreen.ModelSelected(provider="copilot", model_id="gpt-4o")
            )
            await pilot.pause()

            assert len(sent_events) == 0


# ============================================================================ #
# Phase 6a: _model_list_pending deadlock prevention
# ============================================================================ #


class TestModelListPendingDeadlockPrevention:
    """Tests that _model_list_pending cannot get stuck True permanently."""

    @pytest.mark.asyncio
    async def test_pending_flag_cleared_on_agent_disconnect(self) -> None:
        """When an agent disconnects while a model list request is pending,
        _model_list_pending should be reset to False."""
        from breqy.domain.enums import EventType
        from breqy.domain.events import AgentLifecycleEvent
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()

        async def noop_send(event):
            pass

        app.send_event = noop_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # Set pending flag (simulating ctrl+m press)
            app._model_list_pending = True

            # Dispatch an agent disconnect event
            disconnect = AgentLifecycleEvent(
                session_id="ses_test",
                agent_id="agt_default",
                event_type=EventType.AGENT_DISCONNECTED,
            )
            app._dispatcher.dispatch(disconnect)
            await pilot.pause()

            # Pending flag should be cleared
            assert app._model_list_pending is False

    @pytest.mark.asyncio
    async def test_ctrl_m_starts_timeout_timer(self) -> None:
        """When ctrl+m fires, a timeout timer should be scheduled."""
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()

        async def noop_send(event):
            pass

        app.send_event = noop_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            app._agent_connected = True  # Agent must be connected
            app.action_push_model_select()
            await pilot.pause()

            # Timer should exist
            assert app._model_list_timer is not None

    @pytest.mark.asyncio
    async def test_timeout_resets_pending_flag(self) -> None:
        """When the model list timeout fires, _model_list_pending resets to False."""
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()

        async def noop_send(event):
            pass

        app.send_event = noop_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # Trigger ctrl+m
            app._agent_connected = True  # Agent must be connected
            app.action_push_model_select()
            await pilot.pause()
            assert app._model_list_pending is True

            # Manually fire the timeout handler
            app._on_model_list_timeout()

            assert app._model_list_pending is False
            assert app._model_list_timer is None

    @pytest.mark.asyncio
    async def test_timeout_shows_notification(self) -> None:
        """When timeout fires, user should see an error notification."""
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()

        async def noop_send(event):
            pass

        app.send_event = noop_send  # type: ignore[assignment]

        notifications: list[str] = []
        original_notify = app.notify

        def capture_notify(message, **kwargs):
            notifications.append(str(message))
            original_notify(message, **kwargs)

        app.notify = capture_notify  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            app._model_list_pending = True
            app._on_model_list_timeout()
            await pilot.pause()

            assert any("timed out" in n.lower() or "timeout" in n.lower() for n in notifications)

    @pytest.mark.asyncio
    async def test_successful_response_cancels_timer(self) -> None:
        """When MODEL_LIST_RESPONSE arrives, the timeout timer should be cancelled."""
        from breqy.domain.events import ModelListResponseEvent
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()

        async def noop_send(event):
            pass

        app.send_event = noop_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # Simulate pending request with timer
            app._agent_connected = True
            app.action_push_model_select()
            await pilot.pause()
            assert app._model_list_timer is not None

            # Dispatch a response
            response = ModelListResponseEvent(
                session_id="ses_test",
                models=[],
                current_provider="copilot",
                current_model="gpt-4o",
            )
            app._handle_model_list_response(response)
            await pilot.pause()

            # Timer should be cancelled/cleared
            assert app._model_list_timer is None

    @pytest.mark.asyncio
    async def test_late_response_after_timeout_does_not_push_screen(self) -> None:
        """If MODEL_LIST_RESPONSE arrives after timeout, it should not push ModelSelectScreen."""
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.models import ModelEntry
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.screens.model_select import ModelSelectScreen

        app = BreqyApp()

        async def noop_send(event):
            pass

        app.send_event = noop_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # Simulate: request was sent, then timed out
            app._model_list_pending = False  # timeout already reset it
            app._model_list_timer = None

            # Late response arrives
            response = ModelListResponseEvent(
                session_id="ses_test",
                models=[
                    ModelEntry(
                        provider="copilot",
                        model_id="gpt-4o",
                        display_name="GPT-4o",
                        is_authenticated=True,
                    ),
                ],
                current_provider="copilot",
                current_model="gpt-4o",
            )
            app._handle_model_list_response(response)
            await pilot.pause()

            # Should still be on ChatScreen, NOT ModelSelectScreen
            assert isinstance(app.screen, ChatScreen)

    @pytest.mark.asyncio
    async def test_ctrl_m_shows_loading_notification(self) -> None:
        """When ctrl+m fires, a loading notification should be shown."""
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()

        async def noop_send(event):
            pass

        app.send_event = noop_send  # type: ignore[assignment]

        notifications: list[str] = []
        original_notify = app.notify

        def capture_notify(message, **kwargs):
            notifications.append(str(message))
            original_notify(message, **kwargs)

        app.notify = capture_notify  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            app.action_push_model_select()
            await pilot.pause()

            assert any("model" in n.lower() for n in notifications)


# ============================================================================ #
# Phase 6d: Switching state triggered from model selection
# ============================================================================ #


class TestModelSelectionTriggersSwitching:
    """Model selection should trigger switching state in the status bar."""

    @pytest.mark.asyncio
    async def test_model_selected_sets_switching_state(self) -> None:
        """When ModelSelected is handled, AgentStatusBar should show switching state."""
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.screens.model_select import ModelOption, ModelSelectScreen
        from breqy.tui.widgets.agent_status import AgentStatusBar

        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_switch_test")
            app.push_screen(chat)
            await pilot.pause()

            # Set up initial model info
            bar = chat.query_one(AgentStatusBar)
            bar.update_model_info("copilot", "gpt-4o")
            await pilot.pause()

            # Push model select screen and make a selection
            model_screen = ModelSelectScreen(
                models=[
                    ModelOption(provider="claude", model_id="sonnet", display_name="Sonnet"),
                ],
                current_model="gpt-4o",
            )
            app.push_screen(model_screen)
            await pilot.pause()

            model_screen.post_message(
                ModelSelectScreen.ModelSelected(provider="claude", model_id="sonnet")
            )
            await pilot.pause()

            # The status bar should be in switching state
            assert bar._switching is True


# ============================================================================ #
# Keybinding fix: ctrl+m -> ctrl+shift+m
# ============================================================================ #


class TestModelSelectKeyBinding:
    """Tests that ctrl+shift+m replaced ctrl+m for model selection."""

    def test_has_ctrl_shift_m_binding(self) -> None:
        app = BreqyApp()
        keys = [b.key for b in app.BINDINGS]
        assert "ctrl+shift+m" in keys

    def test_no_ctrl_m_binding(self) -> None:
        """ctrl+m conflicts with Enter in terminals — must not be bound."""
        app = BreqyApp()
        keys = [b.key for b in app.BINDINGS]
        assert "ctrl+m" not in keys


# ============================================================================ #
# Slash commands: /models and /help wiring
# ============================================================================ #


class TestSlashCommandRegistry:
    """Tests that ChatScreen provides a CommandRegistry with /models and /help."""

    @pytest.mark.asyncio
    async def test_chat_screen_message_input_has_registry(self) -> None:
        """MessageInput in ChatScreen should have a non-empty CommandRegistry."""
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.widgets.message_input import MessageInput

        app = BreqyApp()
        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            mi = chat.query_one(MessageInput)
            commands = mi.command_registry.list_commands()
            assert len(commands) > 0

    @pytest.mark.asyncio
    async def test_models_command_registered(self) -> None:
        """A /models command should be registered in the ChatScreen's registry."""
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.widgets.message_input import MessageInput

        app = BreqyApp()
        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            mi = chat.query_one(MessageInput)
            commands = mi.command_registry.list_commands()
            assert "models" in commands

    @pytest.mark.asyncio
    async def test_help_command_registered(self) -> None:
        """A /help command should be registered in the ChatScreen's registry."""
        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.widgets.message_input import MessageInput

        app = BreqyApp()
        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            mi = chat.query_one(MessageInput)
            commands = mi.command_registry.list_commands()
            assert "help" in commands


class TestSlashModelsCommand:
    """Tests that /models triggers the model list request flow."""

    @pytest.mark.asyncio
    async def test_models_command_triggers_model_list_request(self) -> None:
        """Typing /models should send ModelListRequestedEvent, same as ctrl+shift+m."""
        from breqy.domain.events import ModelListRequestedEvent
        from breqy.tui.screens.chat import ChatScreen
        from textual.widgets import Input

        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_cmd_test")
            app.push_screen(chat)
            await pilot.pause()

            app._agent_connected = True
            # Type /models in the input
            inp = chat.query_one("#message-input", Input)
            inp.value = "/models"
            await inp.action_submit()
            await pilot.pause()

            assert len(sent_events) == 1
            assert isinstance(sent_events[0], ModelListRequestedEvent)
            assert sent_events[0].session_id == "ses_cmd_test"

    @pytest.mark.asyncio
    async def test_models_command_respects_debounce(self) -> None:
        """Typing /models while a request is pending should not send duplicate."""
        from breqy.tui.screens.chat import ChatScreen
        from textual.widgets import Input

        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            app._agent_connected = True
            # First /models
            inp = chat.query_one("#message-input", Input)
            inp.value = "/models"
            await inp.action_submit()
            await pilot.pause()
            assert len(sent_events) == 1

            # Second /models while pending
            inp.value = "/models"
            await inp.action_submit()
            await pilot.pause()
            # Should still be 1 — debounced
            assert len(sent_events) == 1


class TestSlashHelpCommand:
    """Tests that /help shows a notification with available commands."""

    @pytest.mark.asyncio
    async def test_help_command_shows_notification(self) -> None:
        """Typing /help should show a notification listing available commands."""
        from breqy.tui.screens.chat import ChatScreen
        from textual.widgets import Input

        app = BreqyApp()

        notifications: list[str] = []
        original_notify = app.notify

        def capture_notify(message, **kwargs):
            notifications.append(str(message))
            original_notify(message, **kwargs)

        app.notify = capture_notify  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            inp = chat.query_one("#message-input", Input)
            inp.value = "/help"
            await inp.action_submit()
            await pilot.pause()

            # Should have shown a notification containing command names
            assert any("/models" in n for n in notifications)

    @pytest.mark.asyncio
    async def test_help_command_lists_help_itself(self) -> None:
        """The /help output should mention /help."""
        from breqy.tui.screens.chat import ChatScreen
        from textual.widgets import Input

        app = BreqyApp()

        notifications: list[str] = []
        original_notify = app.notify

        def capture_notify(message, **kwargs):
            notifications.append(str(message))
            original_notify(message, **kwargs)

        app.notify = capture_notify  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            inp = chat.query_one("#message-input", Input)
            inp.value = "/help"
            await inp.action_submit()
            await pilot.pause()

            assert any("/help" in n for n in notifications)


class TestUnknownSlashCommand:
    """Tests that unknown slash commands show an error."""

    @pytest.mark.asyncio
    async def test_unknown_command_shows_error_notification(self) -> None:
        """Typing an unregistered command should show an error notification."""
        from breqy.tui.screens.chat import ChatScreen
        from textual.widgets import Input

        app = BreqyApp()

        notifications: list[str] = []
        original_notify = app.notify

        def capture_notify(message, **kwargs):
            notifications.append(str(message))
            original_notify(message, **kwargs)

        app.notify = capture_notify  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            inp = chat.query_one("#message-input", Input)
            inp.value = "/nonexistent"
            await inp.action_submit()
            await pilot.pause()

            assert any("unknown" in n.lower() or "nknown" in n.lower() for n in notifications)


# ============================================================================ #
# Model list blocked when agent disconnected
# ============================================================================ #


class TestModelListBlockedWhenAgentDisconnected:
    """Model list requests should not be sent when the agent is disconnected.

    Root cause: after agent crash/disconnect, TUI sends model.list.requested
    to the engine which silently drops it (agent not registered).  The TUI
    then hangs for 15s waiting for a response that never comes.
    """

    @pytest.mark.asyncio
    async def test_app_tracks_agent_connected_state(self) -> None:
        """App should have _agent_connected attribute, initially False."""
        app = BreqyApp()
        assert app._agent_connected is False

    @pytest.mark.asyncio
    async def test_agent_connected_event_sets_flag_true(self) -> None:
        """Receiving AGENT_CONNECTED should set _agent_connected = True."""
        from breqy.domain.enums import EventType
        from breqy.domain.events import AgentLifecycleEvent
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            connect_event = AgentLifecycleEvent(
                session_id="ses_test",
                agent_id="breqy",
                event_type=EventType.AGENT_CONNECTED,
            )
            app._dispatcher.dispatch(connect_event)
            await pilot.pause()

            assert app._agent_connected is True

    @pytest.mark.asyncio
    async def test_agent_disconnected_event_sets_flag_false(self) -> None:
        """Receiving AGENT_DISCONNECTED should set _agent_connected = False."""
        from breqy.domain.enums import EventType
        from breqy.domain.events import AgentLifecycleEvent
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # First connect
            connect_event = AgentLifecycleEvent(
                session_id="ses_test",
                agent_id="breqy",
                event_type=EventType.AGENT_CONNECTED,
            )
            app._dispatcher.dispatch(connect_event)
            await pilot.pause()
            assert app._agent_connected is True

            # Then disconnect
            disconnect_event = AgentLifecycleEvent(
                session_id="ses_test",
                agent_id="breqy",
                event_type=EventType.AGENT_DISCONNECTED,
            )
            app._dispatcher.dispatch(disconnect_event)
            await pilot.pause()

            assert app._agent_connected is False

    @pytest.mark.asyncio
    async def test_model_list_blocked_when_agent_disconnected(self) -> None:
        """action_push_model_select should NOT send events when agent is disconnected."""
        from breqy.tui.screens.chat import ChatScreen

        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # Agent is not connected (default state)
            app.action_push_model_select()
            await pilot.pause()

            assert len(sent_events) == 0
            assert app._model_list_pending is False

    @pytest.mark.asyncio
    async def test_model_list_shows_notification_when_agent_disconnected(self) -> None:
        """action_push_model_select should notify user when agent is disconnected."""
        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()

        notifications: list[str] = []
        original_notify = app.notify

        def capture_notify(message, **kwargs):
            notifications.append(str(message))
            original_notify(message, **kwargs)

        app.notify = capture_notify  # type: ignore[assignment]

        async def noop_send(event):
            pass

        app.send_event = noop_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # Agent is not connected
            app.action_push_model_select()
            await pilot.pause()

            assert any("agent" in n.lower() or "connect" in n.lower() for n in notifications)

    @pytest.mark.asyncio
    async def test_model_list_works_after_agent_reconnects(self) -> None:
        """After agent connects, model list requests should work again."""
        from breqy.domain.enums import EventType
        from breqy.domain.events import AgentLifecycleEvent, ModelListRequestedEvent
        from breqy.tui.screens.chat import ChatScreen

        sent_events: list = []

        app = BreqyApp()

        async def capture_send(event):
            sent_events.append(event)

        app.send_event = capture_send  # type: ignore[assignment]

        async with app.run_test() as pilot:
            chat = ChatScreen(session_id="ses_test")
            app.push_screen(chat)
            await pilot.pause()

            # Connect the agent
            connect_event = AgentLifecycleEvent(
                session_id="ses_test",
                agent_id="breqy",
                event_type=EventType.AGENT_CONNECTED,
            )
            app._dispatcher.dispatch(connect_event)
            await pilot.pause()

            # Now model list should work
            app.action_push_model_select()
            await pilot.pause()

            assert len(sent_events) == 1
            assert isinstance(sent_events[0], ModelListRequestedEvent)


# ============================================================================ #
# Auto-copy on text selection
# ============================================================================ #


class TestAutoCopyOnTextSelected:
    """When the user finishes a mouse text selection, the selected text
    should be automatically copied to the clipboard."""

    @pytest.mark.asyncio
    async def test_text_selected_copies_to_clipboard(self) -> None:
        """on_text_selected should call copy_to_clipboard with the selected text."""
        from unittest.mock import patch

        from breqy.tui.screens.chat import ChatScreen

        app = BreqyApp()
        copied: list[str] = []

        async with app.run_test(size=(80, 24)) as pilot:
            chat = ChatScreen(session_id="ses_copy_test")
            app.push_screen(chat)
            await pilot.pause()

            # Write text to the chat log
            chat_view = chat.query_one("ChatView")
            chat_view.log_widget.write("Hello clipboard world")
            await pilot.pause()

            # Patch copy_to_clipboard to capture what gets copied
            original_copy = app.copy_to_clipboard

            def capture_copy(text: str) -> None:
                copied.append(text)
                original_copy(text)

            with patch.object(app, "copy_to_clipboard", side_effect=capture_copy):
                # Simulate: Screen sets a selection, then posts TextSelected
                from textual.geometry import Offset
                from textual.selection import Selection

                widget = chat_view.log_widget
                selection = Selection(start=Offset(0, 0), end=Offset(21, 0))
                app.screen.selections = {widget: selection}
                await pilot.pause()

                # Fire TextSelected (what the Screen does on mouse-up)
                from textual.events import TextSelected

                app.screen.post_message(TextSelected())
                await pilot.pause()

            assert len(copied) == 1
            assert "Hello clipboard world" in copied[0]

    @pytest.mark.asyncio
    async def test_text_selected_noop_when_no_selection(self) -> None:
        """on_text_selected should not copy when there is no active selection."""
        from unittest.mock import patch

        app = BreqyApp()
        copied: list[str] = []

        async with app.run_test(size=(80, 24)) as pilot:
            with patch.object(
                app,
                "copy_to_clipboard",
                side_effect=lambda t: copied.append(t),
            ):
                from textual.events import TextSelected

                app.screen.post_message(TextSelected())
                await pilot.pause()

            assert len(copied) == 0

    @pytest.mark.asyncio
    async def test_mouse_drag_creates_selection_with_highlight(self) -> None:
        """Full E2E: mouse down+drag on chat log creates a visible selection.

        This verifies the entire stack: mouse events -> Screen selection
        system -> widget.text_selection -> render_line highlight.
        """
        from textual.geometry import Offset

        from breqy.tui.screens.chat import ChatScreen
        from breqy.tui.widgets.selectable_rich_log import SelectableRichLog

        app = BreqyApp()
        async with app.run_test(size=(80, 24)) as pilot:
            chat = ChatScreen(session_id="ses_highlight_test")
            app.push_screen(chat)
            await pilot.pause()

            widget = chat.query_one("#chat-log", SelectableRichLog)
            widget.write("Mouse selection highlight test")
            await pilot.pause()

            # Simulate mouse drag
            await pilot.mouse_down(widget, offset=Offset(2, 0))
            await pilot.hover(widget, offset=Offset(18, 0))
            await pilot.pause()

            # Selection must be set
            assert widget.text_selection is not None

            # Rendered strip must have distinct bgcolor for selected range
            strip = widget.render_line(0)
            bg_colors = set()
            for seg in strip:
                if seg.text.strip() and seg.style and seg.style.bgcolor:
                    bg_colors.add(str(seg.style.bgcolor))
            assert len(bg_colors) >= 2, (
                "Selection highlight not visible — expected at least 2 distinct "
                f"bgcolors but got {bg_colors}"
            )
