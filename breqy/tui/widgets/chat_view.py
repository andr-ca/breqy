"""ChatView widget — scrollable chat message display with streaming support.

Uses Textual's ``RichLog`` to render chat messages with role-based prefixes
and supports incremental streaming via ``StreamBuffer``.
"""
from __future__ import annotations

from textual.widget import Widget
from textual.widgets import RichLog

from breqy.domain.enums import MessageRole
from breqy.tui.widgets.stream_buffer import StreamBuffer


class ChatView(Widget):
    """Displays chat messages with streaming support."""

    def __init__(self, **kwargs) -> None:  # type: ignore[override]
        super().__init__(**kwargs)
        self._stream_buffer = StreamBuffer()

    def compose(self):  # noqa: ANN201
        yield RichLog(id="chat-log", wrap=True, markup=True)

    @property
    def log_widget(self) -> RichLog:
        """Return the inner RichLog widget."""
        return self.query_one("#chat-log", RichLog)

    def add_message(self, role: MessageRole, content: str, agent_id: str = "") -> None:
        """Add a complete message to the chat."""
        prefix = self._role_prefix(role, agent_id)
        self.log_widget.write(f"{prefix}{content}")

    def add_chunk(self, message_id: str, chunk: str, chunk_index: int) -> str:
        """Add a streaming chunk. Returns accumulated text so far."""
        return self._stream_buffer.add_chunk(message_id, chunk, chunk_index)

    def complete_stream(self, message_id: str, role: MessageRole, agent_id: str = "") -> None:
        """Finalize a streaming message and write it to the log."""
        text = self._stream_buffer.complete(message_id)
        if text:
            prefix = self._role_prefix(role, agent_id)
            self.log_widget.write(f"{prefix}{text}")

    def clear_messages(self) -> None:
        """Clear all messages from the chat."""
        self.log_widget.clear()

    @staticmethod
    def _role_prefix(role: MessageRole, agent_id: str = "") -> str:
        """Return a Rich-markup prefix for the given message role."""
        if role == MessageRole.USER:
            return "[bold]You:[/bold] "
        elif role == MessageRole.ASSISTANT:
            name = agent_id or "Assistant"
            return f"[bold cyan]{name}:[/bold cyan] "
        elif role == MessageRole.SYSTEM:
            return "[dim italic]System:[/dim italic] "
        elif role == MessageRole.TOOL:
            return "[bold yellow]Tool:[/bold yellow] "
        return ""
