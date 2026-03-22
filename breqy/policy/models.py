"""Policy evaluation result models."""
from __future__ import annotations

from pydantic import BaseModel

from breqy.domain.enums import PolicyAction


class PolicyDecision(BaseModel):
    """Result of evaluating a policy check."""

    action: PolicyAction
    matched_rule_id: str = ""
    reason: str = ""
