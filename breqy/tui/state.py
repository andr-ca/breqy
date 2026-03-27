"""Client-side session state for the TUI.

Plain dataclass — no Pydantic, no Textual dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from breqy.domain.enums import SessionStatus, TaskStatus, ToolStatus
from breqy.domain.models import ApprovalRequest, Message, Task, ToolInvocation


@dataclass
class SessionState:
    """Tracks the client-side view of a session."""

    session_id: str
    status: SessionStatus = SessionStatus.ACTIVE
    messages: list[Message] = field(default_factory=list)
    tasks: dict[str, Task] = field(default_factory=dict)
    participants: dict[str, str] = field(default_factory=dict)
    pending_approvals: dict[str, ApprovalRequest] = field(default_factory=dict)
    active_tools: dict[str, ToolInvocation] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Message management
    # ------------------------------------------------------------------ #

    def add_message(self, message: Message) -> None:
        """Append a message to the conversation history."""
        self.messages.append(message)

    # ------------------------------------------------------------------ #
    # Task management
    # ------------------------------------------------------------------ #

    def update_task(
        self,
        task_id: str,
        title: str,
        status: TaskStatus,
        description: str = "",
        agent_id: str | None = None,
        parent_id: str | None = None,
    ) -> None:
        """Create or update a task in the local state."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.title = title
            task.status = status
            if description:
                task.description = description
            if agent_id is not None:
                task.agent_id = agent_id
            if parent_id is not None:
                task.parent_id = parent_id
        else:
            self.tasks[task_id] = Task(
                id=task_id,
                session_id=self.session_id,
                title=title,
                description=description,
                status=status,
                agent_id=agent_id,
                parent_id=parent_id,
            )

    # ------------------------------------------------------------------ #
    # Agent / participant management
    # ------------------------------------------------------------------ #

    def set_agent_status(self, agent_id: str, *, connected: bool) -> None:
        """Record an agent as connected or disconnected."""
        self.participants[agent_id] = "connected" if connected else "disconnected"

    # ------------------------------------------------------------------ #
    # Approval management
    # ------------------------------------------------------------------ #

    def add_approval(self, request: ApprovalRequest) -> None:
        """Track a pending approval request."""
        self.pending_approvals[request.id] = request

    def resolve_approval(self, approval_id: str) -> None:
        """Remove a resolved approval from the pending set."""
        self.pending_approvals.pop(approval_id, None)

    # ------------------------------------------------------------------ #
    # Tool invocation management
    # ------------------------------------------------------------------ #

    def update_tool(self, invocation: ToolInvocation) -> None:
        """Track an active tool invocation."""
        self.active_tools[invocation.id] = invocation

    def complete_tool(self, invocation_id: str, status: ToolStatus) -> None:
        """Mark a tool invocation as completed and remove from active set."""
        self.active_tools.pop(invocation_id, None)
