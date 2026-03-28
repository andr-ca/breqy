"""ChatScreen — assembly of all chat widgets for a Breqy session.

Composes ``ChatView``, ``MessageInput``, ``TaskPanel``, ``ToolPanel``,
``ApprovalPrompt``, ``ControlBar``, and ``AgentStatusBar`` into a single
Textual ``Screen``.  Provides ``handle_*`` methods that the application
event dispatcher calls to route incoming domain events to the correct
widget.

The screen does **not** own A2A connections — that is the ``App``'s
responsibility (Task 15).
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input

from breqy.domain.enums import ApprovalStatus, EventType
from breqy.domain.events import (
    AgentLifecycleEvent,
    ApprovalRequestedEvent,
    MessageChunkEvent,
    MessageSentEvent,
    TaskUpdatedEvent,
    ToolInvocationCompletedEvent,
    ToolInvocationFailedEvent,
    ToolInvocationStartedEvent,
    ToolOutputChunkEvent,
)
from breqy.domain.models import ApprovalRequest
from breqy.tui.widgets.agent_status import AgentStatusBar
from breqy.tui.widgets.approval_prompt import ApprovalPrompt
from breqy.tui.widgets.chat_view import ChatView
from breqy.tui.widgets.control_bar import ControlBar
from breqy.tui.widgets.message_input import MessageInput
from breqy.tui.widgets.task_panel import TaskPanel
from breqy.tui.widgets.tool_panel import ToolPanel


class ChatScreen(Screen[None]):
    """Main chat screen composing all chat widgets for a session.

    Layout::

        ┌──────────────────────────────┬──────────────┐
        │  AgentStatusBar              │              │
        ├──────────────────────────────┤  TaskPanel   │
        │                              │  (side)      │
        │  ChatView                    ├──────────────┤
        │  (main area)                 │  ToolPanel   │
        │                              │  (side)      │
        ├──────────────────────────────┴──────────────┤
        │  ApprovalPrompt (shown when needed)         │
        ├─────────────────────────────────────────────┤
        │  MessageInput                               │
        ├─────────────────────────────────────────────┤
        │  ControlBar                                 │
        └─────────────────────────────────────────────┘
    """

    DEFAULT_CSS = """
    ChatScreen > Vertical > Horizontal {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
    ]

    def __init__(self, session_id: str, **kwargs) -> None:  # type: ignore[override]
        super().__init__(**kwargs)
        self.session_id = session_id

    def compose(self):  # noqa: ANN201
        """Yield the full chat screen layout."""
        with Vertical():
            yield AgentStatusBar()
            with Horizontal():
                yield ChatView()
                with Vertical():
                    yield TaskPanel()
                    yield ToolPanel()
            yield ApprovalPrompt()
            yield MessageInput()
            yield ControlBar()

    def on_mount(self) -> None:
        """Focus the message input so the user can type immediately."""
        self.query_one("#message-input", Input).focus()

    def action_pop_screen(self) -> None:
        """Pop this screen (go back to session list)."""
        self.app.pop_screen()

    # ------------------------------------------------------------------ #
    # Event routing — called by the app's event dispatcher
    # ------------------------------------------------------------------ #

    def handle_message_sent(self, event: MessageSentEvent) -> None:
        """Route a ``MessageSentEvent`` to the ``ChatView``."""
        chat_view = self.query_one(ChatView)
        chat_view.add_message(
            role=event.role,
            content=event.content,
            agent_id=event.agent_id,
        )

    def handle_message_chunk(self, event: MessageChunkEvent) -> None:
        """Route a ``MessageChunkEvent`` to the ``ChatView`` for streaming."""
        chat_view = self.query_one(ChatView)
        chat_view.add_chunk(
            message_id=event.message_id,
            chunk=event.chunk,
            chunk_index=event.chunk_index,
        )

    def handle_task_updated(self, event: TaskUpdatedEvent) -> None:
        """Route a ``TaskUpdatedEvent`` to the ``TaskPanel``."""
        task_panel = self.query_one(TaskPanel)
        task_panel.update_task(
            task_id=event.task_id,
            title=event.title,
            status=event.status,
        )

    def handle_tool_started(self, event: ToolInvocationStartedEvent) -> None:
        """Route a ``ToolInvocationStartedEvent`` to the ``ToolPanel``."""
        tool_panel = self.query_one(ToolPanel)
        tool_panel.tool_started(
            invocation_id=event.invocation_id,
            tool_name=event.tool_name,
            summary=event.summary,
        )

    def handle_tool_completed(self, event: ToolInvocationCompletedEvent) -> None:
        """Route a ``ToolInvocationCompletedEvent`` to the ``ToolPanel``."""
        tool_panel = self.query_one(ToolPanel)
        tool_panel.tool_completed(
            invocation_id=event.invocation_id,
            summary=event.summary,
        )

    def handle_tool_failed(self, event: ToolInvocationFailedEvent) -> None:
        """Route a ``ToolInvocationFailedEvent`` to the ``ToolPanel``."""
        tool_panel = self.query_one(ToolPanel)
        tool_panel.tool_failed(
            invocation_id=event.invocation_id,
            error=event.error,
        )

    def handle_tool_output(self, event: ToolOutputChunkEvent) -> None:
        """Route a ``ToolOutputChunkEvent`` to the ``ToolPanel``."""
        tool_panel = self.query_one(ToolPanel)
        tool_panel.tool_output(
            invocation_id=event.invocation_id,
            chunk=event.chunk,
        )

    def handle_approval_requested(self, event: ApprovalRequestedEvent) -> None:
        """Route an ``ApprovalRequestedEvent`` to the ``ApprovalPrompt``.

        Constructs an ``ApprovalRequest`` domain model from event data.
        """
        request = ApprovalRequest(
            id=event.approval_id,
            session_id=event.session_id,
            agent_id=event.agent_id,
            tool_invocation_id=event.invocation_id,
            description=event.description,
            status=ApprovalStatus.PENDING,
        )
        prompt = self.query_one(ApprovalPrompt)
        prompt.add_request(request)

    def handle_agent_lifecycle(self, event: AgentLifecycleEvent) -> None:
        """Route an ``AgentLifecycleEvent`` to the ``AgentStatusBar``."""
        status_bar = self.query_one(AgentStatusBar)
        connected = event.event_type == EventType.AGENT_CONNECTED
        status_bar.update_agent(agent_id=event.agent_id, connected=connected)
