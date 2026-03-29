"""BreqyApp — Textual TUI application shell.

Provides the main App class with key bindings, real screen wiring,
EventDispatcher-based event routing, and an A2A background worker
that streams events from the engine.
"""
from __future__ import annotations

import asyncio
import collections

import structlog
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

from breqy.domain.enums import EventType, MessageRole
from breqy.domain.events import (
    Event,
    MessageSentEvent,
    ModelInfoEvent,
    ModelListRequestedEvent,
    ModelListResponseEvent,
    ModelSwitchRequestedEvent,
    SessionCreateRequestedEvent,
    SessionCreatedEvent,
)
from breqy.domain.ids import generate_prefixed_id
from breqy.tui.events import EventDispatcher
from breqy.tui.screens.auth import AuthScreen
from breqy.tui.screens.chat import ChatScreen
from breqy.tui.screens.logs import LogEntry, LogsScreen
from breqy.tui.screens.model_select import ModelOption, ModelSelectScreen
from breqy.tui.screens.session_list import SessionListScreen
from breqy.tui.widgets.message_input import MessageSubmitted

logger = structlog.get_logger(__name__)

# Initial backoff (seconds) for reconnection; doubles each retry.
_INITIAL_BACKOFF = 0.1
_MAX_BACKOFF = 30.0


# --------------------------------------------------------------------------- #
# Placeholder fallback (kept for backward compat in case tests import it)
# --------------------------------------------------------------------------- #


class PlaceholderSessionListScreen(Screen):
    """Temporary session-list screen — kept as fallback."""

    def compose(self) -> ComposeResult:
        yield Static("Breqy \u2014 Sessions")


# --------------------------------------------------------------------------- #
# BreqyApp
# --------------------------------------------------------------------------- #


class BreqyApp(App):
    """Breqy TUI application."""

    CSS_PATH = "styles/breqy.tcss"
    TITLE = "Breqy"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+l", "push_logs", "Logs", show=True),
        Binding("ctrl+a", "push_auth", "Auth", show=True),
        Binding("ctrl+m", "push_model_select", "Models", show=True),
        Binding("escape", "pop_screen_safe", "Back", show=False),
    ]

    # ------------------------------------------------------------------ #
    # Init
    # ------------------------------------------------------------------ #

    def __init__(self, socket_path: str = "", **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.socket_path = socket_path

        # A2A client — only created when socket_path is non-empty
        if socket_path:
            from breqy.a2a.client import A2AClient

            self._client: A2AClient | None = A2AClient(socket_path)
        else:
            self._client = None

        # Background log buffer — stores recent events for LogsScreen pre-population
        self._log_buffer: collections.deque[LogEntry] = collections.deque(maxlen=1000)

        # Debounce flag for model list requests (ctrl+m)
        self._model_list_pending: bool = False

        # Timer handle for model list request timeout
        self._model_list_timer: object | None = None

        # Event dispatcher — routes domain events to screen handlers
        self._dispatcher = EventDispatcher()
        self._setup_dispatcher()

    # ------------------------------------------------------------------ #
    # Dispatcher setup
    # ------------------------------------------------------------------ #

    def _setup_dispatcher(self) -> None:
        """Register event-type → handler mappings on the dispatcher."""

        # Message events → ChatScreen
        self._dispatcher.register(
            EventType.MESSAGE_SENT,
            lambda e: self._route_to_chat("handle_message_sent", e),
        )
        self._dispatcher.register(
            EventType.MESSAGE_CHUNK,
            lambda e: self._route_to_chat("handle_message_chunk", e),
        )

        # Task events → ChatScreen
        for et in (EventType.TASK_CREATED, EventType.TASK_UPDATED, EventType.TASK_COMPLETED):
            self._dispatcher.register(
                et,
                lambda e: self._route_to_chat("handle_task_updated", e),
            )

        # Tool events → ChatScreen
        self._dispatcher.register(
            EventType.TOOL_INVOCATION_STARTED,
            lambda e: self._route_to_chat("handle_tool_started", e),
        )
        self._dispatcher.register(
            EventType.TOOL_INVOCATION_COMPLETED,
            lambda e: self._route_to_chat("handle_tool_completed", e),
        )
        self._dispatcher.register(
            EventType.TOOL_INVOCATION_FAILED,
            lambda e: self._route_to_chat("handle_tool_failed", e),
        )
        self._dispatcher.register(
            EventType.TOOL_OUTPUT_CHUNK,
            lambda e: self._route_to_chat("handle_tool_output", e),
        )

        # Approval → ChatScreen
        self._dispatcher.register(
            EventType.APPROVAL_REQUESTED,
            lambda e: self._route_to_chat("handle_approval_requested", e),
        )

        # Agent lifecycle → ChatScreen + app-level cleanup
        self._dispatcher.register(
            EventType.AGENT_CONNECTED,
            lambda e: self._route_to_chat("handle_agent_lifecycle", e),
        )
        self._dispatcher.register(
            EventType.AGENT_DISCONNECTED,
            self._handle_agent_disconnected,
        )

        # Session creation → push ChatScreen
        self._dispatcher.register(
            EventType.SESSION_CREATED,
            self._handle_session_created,
        )

        # Model events
        self._dispatcher.register(
            EventType.MODEL_INFO,
            lambda e: self._route_to_chat("handle_model_info", e),
        )
        self._dispatcher.register(
            EventType.MODEL_LIST_RESPONSE,
            self._handle_model_list_response,
        )

        # Route ALL events to LogsScreen if one is on the stack
        for et in EventType:
            self._dispatcher.register(et, self._route_to_logs)

    # ------------------------------------------------------------------ #
    # Event routing helpers
    # ------------------------------------------------------------------ #

    def _route_to_chat(self, handler_name: str, event: Event) -> None:
        """Route an event to the active ChatScreen if one is on the stack."""
        for screen in reversed(self.screen_stack):
            if isinstance(screen, ChatScreen):
                logger.debug(
                    "Dispatched to ChatScreen",
                    handler=handler_name,
                    event_type=event.event_type.value,
                )
                getattr(screen, handler_name)(event)
                break

    def _route_to_logs(self, event: Event) -> None:
        """Buffer an event for LogsScreen and route live if one is visible."""
        entry = LogEntry(
            timestamp=event.timestamp,
            source=event.agent_id or "engine",
            event_type=event.event_type.value,
            summary=str(getattr(event, "content", ""))
            or str(getattr(event, "summary", ""))
            or "",
        )
        self._log_buffer.append(entry)

        for screen in reversed(self.screen_stack):
            if isinstance(screen, LogsScreen):
                screen.add_event(
                    timestamp=entry.timestamp,
                    source=entry.source,
                    event_type=entry.event_type,
                    summary=entry.summary,
                )
                break

    def _handle_session_created(self, event: Event) -> None:
        """Handle a SessionCreatedEvent by pushing a ChatScreen."""
        if isinstance(event, SessionCreatedEvent):
            self.push_screen(ChatScreen(session_id=event.session_id))

    def _handle_agent_disconnected(self, event: Event) -> None:
        """Handle agent disconnect: route to ChatScreen and reset pending state."""
        self._route_to_chat("handle_agent_lifecycle", event)
        self._cancel_model_list_timer()
        self._model_list_pending = False

    def _handle_model_list_response(self, event: Event) -> None:
        """Handle a ModelListResponseEvent by pushing ModelSelectScreen.

        Converts ``ModelEntry`` domain objects to ``ModelOption`` dataclasses
        used by the TUI screen.  Only pushes if a ``ChatScreen`` is active
        and the request has not already timed out.
        """
        was_pending = self._model_list_pending
        self._model_list_pending = False
        self._cancel_model_list_timer()

        if not isinstance(event, ModelListResponseEvent):
            return

        # Ignore late responses that arrive after timeout
        if not was_pending:
            return

        # Only push ModelSelectScreen if a ChatScreen is on the stack
        has_chat = any(isinstance(s, ChatScreen) for s in self.screen_stack)
        if not has_chat:
            return

        options = [
            ModelOption(
                provider=entry.provider,
                model_id=entry.model_id,
                display_name=entry.display_name,
            )
            for entry in event.models
        ]
        self.push_screen(
            ModelSelectScreen(models=options, current_model=event.current_model)
        )

    def _on_model_list_timeout(self) -> None:
        """Called when the model list request times out."""
        self._model_list_pending = False
        self._model_list_timer = None
        self.notify(
            "Model discovery timed out",
            severity="warning",
            timeout=5,
        )

    def _cancel_model_list_timer(self) -> None:
        """Cancel the model list timeout timer if active."""
        if self._model_list_timer is not None:
            self._model_list_timer.stop()
            self._model_list_timer = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def on_mount(self) -> None:
        """Push the initial screen and start the A2A listener if configured."""
        self.push_screen(SessionListScreen())
        if self._client is not None:
            self._start_listener()

    # ------------------------------------------------------------------ #
    # A2A Worker
    # ------------------------------------------------------------------ #

    @work(thread=False)
    async def _start_listener(self) -> None:
        """Background worker that listens for A2A events from the engine.

        Connects to the engine socket, streams envelopes, converts them
        to typed events, and dispatches through the EventDispatcher.
        On disconnect, retries with exponential backoff.
        """
        if self._client is None:
            return

        backoff = _INITIAL_BACKOFF

        while True:
            try:
                await self._client.connect()
                backoff = _INITIAL_BACKOFF  # reset on successful connect

                async for envelope in self._client.listen():
                    event = envelope.to_event()
                    logger.debug(
                        "Event received from engine",
                        event_type=event.event_type.value,
                        session_id=event.session_id,
                    )
                    self._dispatcher.dispatch(event)

                # listen() ended normally — server disconnected
                logger.warning("Disconnected from engine, reconnecting")
                await self._client.disconnect()

            except ConnectionError as exc:
                logger.warning("Connection failed", error=str(exc), retry_in=backoff)
                self.notify(
                    f"Connection failed: {exc}",
                    severity="error",
                    timeout=5,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)

            except asyncio.CancelledError:
                # Worker cancelled (app shutting down)
                await self._safe_disconnect()
                return

            except Exception as exc:
                logger.error("Unexpected error in A2A listener", error=str(exc), exc_info=True)
                self.notify(
                    f"Listener error: {exc}",
                    severity="error",
                    timeout=5,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)

    async def _safe_disconnect(self) -> None:
        """Disconnect the A2A client, swallowing errors."""
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Send events
    # ------------------------------------------------------------------ #

    async def send_event(self, event: Event) -> None:
        """Send a domain event to the engine via A2A.

        No-op when no client is configured (socket_path empty).
        """
        if self._client is None:
            return
        logger.debug(
            "Sending event to engine",
            event_type=event.event_type.value,
            session_id=event.session_id,
        )
        await self._client.send_event(event)

    # ------------------------------------------------------------------ #
    # Screen actions
    # ------------------------------------------------------------------ #

    def action_push_logs(self) -> None:
        """Push logs screen overlay."""
        self.push_screen(LogsScreen())

    def action_push_auth(self) -> None:
        """Push auth screen overlay."""
        self.push_screen(AuthScreen())

    def action_push_model_select(self) -> None:
        """Request model list from engine (ctrl+m).

        Instead of pushing ``ModelSelectScreen`` directly, sends a
        ``ModelListRequestedEvent`` to the engine.  The screen is
        pushed when the ``MODEL_LIST_RESPONSE`` arrives.  A debounce
        flag prevents duplicate requests.
        """
        # Only works when a ChatScreen is on the stack
        chat_screen: ChatScreen | None = None
        for screen in reversed(self.screen_stack):
            if isinstance(screen, ChatScreen):
                chat_screen = screen
                break
        if chat_screen is None:
            return

        if self._model_list_pending:
            return

        self._model_list_pending = True

        # Start timeout timer (15 seconds)
        self._cancel_model_list_timer()
        self._model_list_timer = self.set_timer(
            15.0, self._on_model_list_timeout
        )

        self.notify("Discovering models…", timeout=3)

        event = ModelListRequestedEvent(session_id=chat_screen.session_id)
        self.run_worker(self.send_event(event), exclusive=False)

    def action_pop_screen_safe(self) -> None:
        """Pop screen if not on the base screen."""
        if len(self.screen_stack) > 1:
            self.pop_screen()

    # ------------------------------------------------------------------ #
    # SessionListScreen message handlers
    # ------------------------------------------------------------------ #

    def on_session_list_screen_session_selected(
        self, message: SessionListScreen.SessionSelected,
    ) -> None:
        """Push a ChatScreen for the selected session."""
        self.push_screen(ChatScreen(session_id=message.session_id))

    def on_session_list_screen_new_session_requested(
        self, message: SessionListScreen.NewSessionRequested,
    ) -> None:
        """Request a new session from the engine."""
        event = SessionCreateRequestedEvent(
            session_id="",
            requested_agent_id="default",
        )
        self.run_worker(self.send_event(event), exclusive=False)

    # ------------------------------------------------------------------ #
    # MessageInput message handlers
    # ------------------------------------------------------------------ #

    def on_message_submitted(self, message: MessageSubmitted) -> None:
        """Convert a user-typed message into a MessageSentEvent and send to the engine."""
        # Find the active ChatScreen to get the session_id
        chat_screen: ChatScreen | None = None
        for screen in reversed(self.screen_stack):
            if isinstance(screen, ChatScreen):
                chat_screen = screen
                break
        if chat_screen is None:
            return

        logger.debug(
            "User message submitted",
            session_id=chat_screen.session_id,
            content_length=len(message.text),
        )

        event = MessageSentEvent(
            session_id=chat_screen.session_id,
            message_id=generate_prefixed_id("msg"),
            role=MessageRole.USER,
            content=message.text,
        )
        # Local echo: show the user message in ChatView immediately
        self._route_to_chat("handle_message_sent", event)
        self.run_worker(self.send_event(event), exclusive=False)

    # ------------------------------------------------------------------ #
    # ModelSelectScreen message handlers
    # ------------------------------------------------------------------ #

    def on_model_select_screen_model_selected(
        self, message: ModelSelectScreen.ModelSelected,
    ) -> None:
        """Convert a model selection into a ModelSwitchRequestedEvent and send to engine."""
        # Find the active ChatScreen to get the session_id
        chat_screen: ChatScreen | None = None
        for screen in reversed(self.screen_stack):
            if isinstance(screen, ChatScreen):
                chat_screen = screen
                break
        if chat_screen is None:
            return

        # Show switching state in the status bar
        from breqy.tui.widgets.agent_status import AgentStatusBar

        try:
            bar = chat_screen.query_one(AgentStatusBar)
            bar.set_switching()
        except Exception:
            pass  # Status bar may not be mounted yet

        event = ModelSwitchRequestedEvent(
            session_id=chat_screen.session_id,
            provider_id=message.provider,
            model_id=message.model_id,
        )
        self.run_worker(self.send_event(event), exclusive=False)
