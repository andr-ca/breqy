"""ControlBar widget — control buttons for the active agent.

Provides Stop, Steer, Stop+Steer, and Circuit Break buttons.
Posts ``ControlBar.ControlAction`` messages when the user activates a control.
Circuit Break is always enabled (emergency). All other buttons start disabled
and are toggled via ``set_active(active)``.
"""
from __future__ import annotations

from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input

from breqy.domain.enums import EventType


class ControlBar(Widget):
    """Footer bar with agent control buttons."""

    DEFAULT_CSS = """
    ControlBar {
        height: auto;
        max-height: 5;
    }
    """

    class ControlAction(Message):
        """Posted when user activates a control action."""

        def __init__(self, event_type: EventType, new_direction: str = "") -> None:
            self.event_type = event_type
            self.new_direction = new_direction
            super().__init__()

    def __init__(self, **kwargs) -> None:  # type: ignore[override]
        super().__init__(**kwargs)
        self._pending_event_type: EventType | None = None

    def compose(self):
        with Horizontal():
            yield Button("Stop", id="btn-stop", classes="control-button", disabled=True)
            yield Button("Steer", id="btn-steer", classes="control-button", disabled=True)
            yield Button(
                "Stop+Steer",
                id="btn-stop-and-steer",
                classes="control-button",
                disabled=True,
            )
            yield Button(
                "Circuit Break",
                id="btn-circuit-break",
                classes="control-button",
                variant="error",
            )
        yield Input(
            placeholder="Enter new direction...",
            id="direction-input",
        )

    def on_mount(self) -> None:
        """Hide direction input on mount."""
        self.query_one("#direction-input", Input).display = False

    def set_active(self, active: bool) -> None:
        """Enable or disable control buttons based on session state.

        Circuit Break is always enabled regardless of *active*.
        """
        self.query_one("#btn-stop", Button).disabled = not active
        self.query_one("#btn-steer", Button).disabled = not active
        self.query_one("#btn-stop-and-steer", Button).disabled = not active
        # Circuit Break always stays enabled — never disable it

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses and dispatch appropriate actions."""
        button_id = event.button.id

        if button_id == "btn-stop":
            self.post_message(self.ControlAction(EventType.CONTROL_STOP))
        elif button_id == "btn-steer":
            self._pending_event_type = EventType.CONTROL_STEER
            self._show_direction_input()
        elif button_id == "btn-stop-and-steer":
            self._pending_event_type = EventType.CONTROL_STOP_AND_STEER
            self._show_direction_input()
        elif button_id == "btn-circuit-break":
            self.post_message(self.ControlAction(EventType.CONTROL_CIRCUIT_BREAK))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle direction input submission."""
        if event.input.id != "direction-input":
            return

        direction = event.value.strip()
        if self._pending_event_type is not None and direction:
            self.post_message(
                self.ControlAction(
                    event_type=self._pending_event_type,
                    new_direction=direction,
                )
            )
        self._pending_event_type = None
        self._hide_direction_input()

    def _show_direction_input(self) -> None:
        """Show the direction input and focus it."""
        inp = self.query_one("#direction-input", Input)
        inp.display = True
        inp.focus()

    def _hide_direction_input(self) -> None:
        """Hide and clear the direction input."""
        inp = self.query_one("#direction-input", Input)
        inp.value = ""
        inp.display = False
