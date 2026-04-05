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
    ModelInfoEvent,
    ReasoningDoneEvent,
    ReasoningStartedEvent,
    TaskUpdatedEvent,
    ToolInvocationCompletedEvent,
    ToolInvocationFailedEvent,
    ToolInvocationStartedEvent,
    ToolOutputChunkEvent,
)
from breqy.domain.models import ApprovalRequest
from breqy.tui.commands import CommandRegistry, CommandResult
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
        self._command_registry = self._build_command_registry()

    @staticmethod
    def _build_command_registry() -> CommandRegistry:
        """Create the slash-command registry for chat input."""
        registry = CommandRegistry()
        registry.register(
            "models",
            lambda: CommandResult(success=True, message="models"),
            description="Open the model selector",
        )
        registry.register(
            "help",
            lambda: CommandResult(success=True, message="help"),
            description="Show available commands",
        )
        registry.register(
            "logs",
            lambda: CommandResult(success=True, message="logs"),
            description="Open agent log file viewer",
        )
        return registry

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
            yield MessageInput(command_registry=self._command_registry)
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
        """Route a ``MessageSentEvent`` to the ``ChatView``.

        If the message was being streamed (chunks are in the buffer),
        complete the stream instead of adding a duplicate message.
        """
        chat_view = self.query_one(ChatView)
        if chat_view._stream_buffer.has_message(event.message_id):
            chat_view.complete_stream(
                message_id=event.message_id,
                role=event.role,
                agent_id=event.agent_id,
            )
        else:
            chat_view.add_message(
                role=event.role,
                content=event.content,
                agent_id=event.agent_id,
            )

    def handle_message_chunk(self, event: MessageChunkEvent) -> None:
        """Route a ``MessageChunkEvent`` to the ``ChatView`` for streaming.

        Also hides the thinking indicator if it is still showing (safety net).
        """
        chat_view = self.query_one(ChatView)
        chat_view.hide_thinking_indicator()
        chat_view.add_chunk(
            message_id=event.message_id,
            chunk=event.chunk,
            chunk_index=event.chunk_index,
        )

    def handle_reasoning_started(self, event: ReasoningStartedEvent) -> None:
        """Show the 'Thinking...' indicator when the model enters a reasoning phase."""
        self.query_one(ChatView).show_thinking_indicator()

    def handle_reasoning_done(self, event: ReasoningDoneEvent) -> None:
        """No-op: do NOT hide the indicator when the reasoning phase ends.

        The Responses API sends ``reasoning_started`` and ``reasoning_done``
        back-to-back (before any text delta), so hiding on ``reasoning_done``
        would remove the indicator before a single frame is rendered.
        The indicator is instead hidden by ``handle_message_chunk`` when the
        first text chunk arrives.
        """

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
        """Route an ``AgentLifecycleEvent`` to the ``AgentStatusBar``.

        On disconnect, also clears the model info display since the agent
        is no longer running.
        """
        status_bar = self.query_one(AgentStatusBar)
        connected = event.event_type == EventType.AGENT_CONNECTED
        status_bar.update_agent(agent_id=event.agent_id, connected=connected)
        if not connected:
            status_bar.clear_model_info()

    def handle_model_info(self, event: ModelInfoEvent) -> None:
        """Route a ``ModelInfoEvent`` to the ``AgentStatusBar``."""
        status_bar = self.query_one(AgentStatusBar)
        status_bar.update_model_info(
            provider_id=event.provider_id,
            model_id=event.model_id,
        )
