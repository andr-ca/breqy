"""ApprovalPrompt widget — displays pending approval requests with action buttons.

Manages a FIFO queue of ``ApprovalRequest`` objects. Shows the current
request's description and three action buttons: Approve, Approve for Session,
and Deny.  Posts ``ApprovalPrompt.Approved`` or ``ApprovalPrompt.Denied``
Textual messages when the user makes a decision.
"""
from __future__ import annotations

from collections import deque

from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static

from breqy.domain.enums import ApprovalGrantScope
from breqy.domain.models import ApprovalRequest


class ApprovalPrompt(Widget):
    """Displays pending approval requests and lets the user decide."""

    can_focus = True

    DEFAULT_CSS = """
    ApprovalPrompt {
        height: auto;
        max-height: 10;
    }
    """

    BINDINGS = [
        Binding("a", "approve", "Approve", show=False),
        Binding("s", "approve_session", "Approve for Session", show=False),
        Binding("f", "approve_forever", "Approve Forever", show=False),
        Binding("d", "deny", "Deny", show=False),
    ]

    # ------------------------------------------------------------------ #
    # Textual messages posted by this widget
    # ------------------------------------------------------------------ #

    class Approved(Message):
        """Posted when the user approves a request."""

        def __init__(
            self,
            approval_id: str,
            grant_scope: ApprovalGrantScope = ApprovalGrantScope.ONCE,
        ) -> None:
            super().__init__()
            self.approval_id = approval_id
            self.grant_scope = grant_scope

        @property
        def extend_to_session(self) -> bool:
            return self.grant_scope == ApprovalGrantScope.SESSION

    class Denied(Message):
        """Posted when the user denies a request."""

        def __init__(self, approval_id: str) -> None:
            super().__init__()
            self.approval_id = approval_id

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def __init__(self, **kwargs) -> None:  # type: ignore[override]
        super().__init__(**kwargs)
        self._queue: deque[ApprovalRequest] = deque()
        self._description_widget: Static | None = None
        self._button_bar: Horizontal | None = None

    def compose(self):  # noqa: ANN201
        """Yield nothing initially — content is rendered dynamically."""
        yield from ()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def current_request(self) -> ApprovalRequest | None:
        """Return the front-of-queue request, or ``None`` if empty."""
        return self._queue[0] if self._queue else None

    def add_request(self, request: ApprovalRequest) -> None:
        """Queue a new approval request and refresh the display."""
        self._queue.append(request)
        if len(self._queue) == 1:
            self._show_current()

    # ------------------------------------------------------------------ #
    # Actions (bound to keys and buttons)
    # ------------------------------------------------------------------ #

    def action_approve(self) -> None:
        """Approve the current request."""
        self._decide_approve(grant_scope=ApprovalGrantScope.ONCE)

    def action_approve_session(self) -> None:
        """Approve the current request for the entire session."""
        self._decide_approve(grant_scope=ApprovalGrantScope.SESSION)

    def action_approve_forever(self) -> None:
        """Approve the current request permanently."""
        self._decide_approve(grant_scope=ApprovalGrantScope.FOREVER)

    def action_deny(self) -> None:
        """Deny the current request."""
        request = self.current_request
        if request is None:
            return
        self._queue.popleft()
        self.post_message(self.Denied(approval_id=request.id))
        self._advance()

    # ------------------------------------------------------------------ #
    # Button handlers
    # ------------------------------------------------------------------ #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Route button presses to the correct action."""
        button_id = event.button.id
        if button_id == "btn-approve":
            self.action_approve()
        elif button_id == "btn-approve-session":
            self.action_approve_session()
        elif button_id == "btn-approve-forever":
            self.action_approve_forever()
        elif button_id == "btn-deny":
            self.action_deny()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _decide_approve(self, *, grant_scope: ApprovalGrantScope) -> None:
        """Common logic for approve / approve-for-session."""
        request = self.current_request
        if request is None:
            return
        self._queue.popleft()
        self.post_message(
            self.Approved(
                approval_id=request.id,
                grant_scope=grant_scope,
            )
        )
        self._advance()

    def _advance(self) -> None:
        """Show the next request or clear the display."""
        if self._queue:
            self._update_display()
        else:
            self._clear_display()

    def _show_current(self) -> None:
        """Mount widgets for the current request."""
        request = self.current_request
        if request is None:
            return

        if self._description_widget is not None:
            # Already showing — just update content
            self._update_display()
            return

        self._description_widget = Static(
            f"? {request.description}",
            id="approval-description",
        )
        approve_btn = Button("Approve (A)", id="btn-approve", variant="success")
        session_btn = Button(
            "Approve for Session (S)",
            id="btn-approve-session",
            variant="warning",
        )
        forever_btn = Button(
            "Approve Forever (F)",
            id="btn-approve-forever",
            variant="primary",
        )
        deny_btn = Button("Deny (D)", id="btn-deny", variant="error")
        self._button_bar = Horizontal(
            approve_btn, session_btn, forever_btn, deny_btn, id="approval-buttons"
        )
        self.mount(self._description_widget, self._button_bar)

    def _update_display(self) -> None:
        """Update the description text to reflect the current request."""
        request = self.current_request
        if request is None or self._description_widget is None:
            return
        self._description_widget.update(f"? {request.description}")

    def _clear_display(self) -> None:
        """Remove all child widgets."""
        if self._description_widget is not None:
            self._description_widget.remove()
            self._description_widget = None
        if self._button_bar is not None:
            self._button_bar.remove()
            self._button_bar = None
