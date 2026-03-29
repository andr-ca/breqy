"""MessageInput widget — text input with slash-command dispatch.

Wraps a Textual ``Input`` widget. On submit:
- If the text starts with ``/``, dispatch via ``CommandRegistry``.
- Otherwise post a ``MessageSubmitted`` Textual message.
- Empty / whitespace-only input is ignored.
"""
from __future__ import annotations

from textual.events import Key
from textual.message import Message as TextualMessage
from textual.widget import Widget
from textual.widgets import Input

from breqy.tui.commands import CommandRegistry, CommandResult, SlashCommandSuggester


class MessageSubmitted(TextualMessage):
    """Posted when the user submits a non-command message."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class CommandExecuted(TextualMessage):
    """Posted when a slash command is executed."""

    def __init__(self, command: str, result: CommandResult) -> None:
        self.command = command
        self.result = result
        super().__init__()


class MessageInput(Widget):
    """Text input bar with slash-command support."""

    DEFAULT_CSS = """
    MessageInput {
        height: auto;
        max-height: 5;
    }
    """

    def __init__(self, command_registry: CommandRegistry | None = None, **kwargs) -> None:  # type: ignore[override]
        super().__init__(**kwargs)
        self.command_registry = command_registry or CommandRegistry()

    def compose(self):  # noqa: ANN201
        suggester = SlashCommandSuggester.from_registry(self.command_registry)
        yield Input(
            placeholder="Type a message or /command...",
            id="message-input",
            suggester=suggester,
        )

    def _on_key(self, event: Key) -> None:
        """Intercept Tab to accept an active slash-command suggestion."""
        if event.key == "tab":
            inp = self.query_one("#message-input", Input)
            suggestion: str | None = inp._suggestion  # noqa: SLF001 — private but stable
            if suggestion and inp.cursor_at_end:
                inp.value = suggestion
                inp.cursor_position = len(suggestion)
                event.prevent_default()
                event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle the inner Input's Submitted event."""
        text = event.value.strip()
        if not text:
            return

        event.input.value = ""

        if self.command_registry.is_command(text):
            result = self.command_registry.dispatch(text)
            self.post_message(CommandExecuted(command=text, result=result))
        else:
            self.post_message(MessageSubmitted(text=text))
