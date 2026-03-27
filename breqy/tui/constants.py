"""TUI constants: status icons, key bindings, style mappings.

Pure data — no Textual dependency.
"""
from __future__ import annotations

from breqy.domain.enums import (
    ApprovalStatus,
    SessionStatus,
    TaskStatus,
    ToolStatus,
)

# --------------------------------------------------------------------------- #
# Task status → display icon
# --------------------------------------------------------------------------- #

TASK_STATUS_ICONS: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "\u25cb",      # ○
    TaskStatus.RUNNING: "\u25c6",      # ◆
    TaskStatus.COMPLETED: "\u2713",    # ✓
    TaskStatus.FAILED: "\u2717",       # ✗
    TaskStatus.CANCELLED: "\u2014",    # —
}

# --------------------------------------------------------------------------- #
# Tool status → display icon
# --------------------------------------------------------------------------- #

TOOL_STATUS_ICONS: dict[ToolStatus, str] = {
    ToolStatus.PENDING: "\u25cb",      # ○
    ToolStatus.APPROVED: "\u25cb",     # ○
    ToolStatus.DENIED: "\u2717",       # ✗
    ToolStatus.RUNNING: "\u25c6",      # ◆
    ToolStatus.COMPLETED: "\u2713",    # ✓
    ToolStatus.FAILED: "\u2717",       # ✗
}

# --------------------------------------------------------------------------- #
# Agent connection status icons
# --------------------------------------------------------------------------- #

AGENT_CONNECTED_ICON: str = "\u25cf"     # ●
AGENT_DISCONNECTED_ICON: str = "\u25cb"  # ○

# --------------------------------------------------------------------------- #
# Session status → Textual CSS class name
# --------------------------------------------------------------------------- #

SESSION_STATUS_STYLES: dict[SessionStatus, str] = {
    SessionStatus.ACTIVE: "success",
    SessionStatus.CLOSED: "muted",
    SessionStatus.SUSPENDED: "warning",
    SessionStatus.CIRCUIT_BROKEN: "error",
}

# --------------------------------------------------------------------------- #
# Approval status → display icon
# --------------------------------------------------------------------------- #

APPROVAL_STATUS_ICONS: dict[ApprovalStatus, str] = {
    ApprovalStatus.PENDING: "?",
    ApprovalStatus.GRANTED: "\u2713",   # ✓
    ApprovalStatus.DENIED: "\u2717",    # ✗
    ApprovalStatus.EXPIRED: "\u2014",   # —
}
