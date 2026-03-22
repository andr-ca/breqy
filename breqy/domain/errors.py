"""Domain exception hierarchy for the Breqy system."""
from __future__ import annotations


class BreqyError(Exception):
    """Base class for all Breqy domain errors."""


class SessionNotFoundError(BreqyError):
    """Raised when a session cannot be found by ID."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class AgentNotFoundError(BreqyError):
    """Raised when an agent cannot be found by ID."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent not found: {agent_id}")


class PolicyDeniedError(BreqyError):
    """Raised when a policy rule denies an action."""

    def __init__(self, resource: str, reason: str = "") -> None:
        self.resource = resource
        message = f"Policy denied for resource '{resource}'"
        if reason:
            message = f"{message}: {reason}"
        super().__init__(message)


class ApprovalRequiredError(BreqyError):
    """Raised when an action requires user approval."""

    def __init__(self, approval_request_id: str) -> None:
        self.approval_request_id = approval_request_id
        super().__init__(f"Approval required: {approval_request_id}")


class ApprovalTimeoutError(BreqyError):
    """Raised when an approval request times out."""

    def __init__(self, approval_request_id: str) -> None:
        self.approval_request_id = approval_request_id
        super().__init__(f"Approval timed out: {approval_request_id}")


class ToolExecutionError(BreqyError):
    """Raised when a tool fails to execute."""

    def __init__(self, tool_name: str, reason: str = "") -> None:
        self.tool_name = tool_name
        message = f"Tool execution failed: {tool_name}"
        if reason:
            message = f"{message}: {reason}"
        super().__init__(message)


class AgentSpawnError(BreqyError):
    """Raised when an agent fails to spawn."""

    def __init__(self, agent_id: str, reason: str = "") -> None:
        self.agent_id = agent_id
        message = f"Agent spawn failed: {agent_id}"
        if reason:
            message = f"{message}: {reason}"
        super().__init__(message)


class TransportError(BreqyError):
    """Raised when a transport-level error occurs (A2A, socket, etc.)."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Transport error: {message}")
