"""PolicyEvaluator: layered rule resolution, most restrictive wins.

Resolution order (most restrictive wins):
1. DENY at any scope → denied
2. REQUIRE_APPROVAL at any scope (no DENY) → requires approval
3. ALLOW at any scope (no DENY/REQUIRE_APPROVAL) → allowed
4. No matching rules → allowed (default open)
"""
from __future__ import annotations

from breqy.domain.enums import PolicyAction, PolicyScope
from breqy.domain.models import PolicyRule
from breqy.policy.models import PolicyDecision

# Priority: DENY > REQUIRE_APPROVAL > ALLOW
_ACTION_PRIORITY: dict[PolicyAction, int] = {
    PolicyAction.DENY: 3,
    PolicyAction.REQUIRE_APPROVAL: 2,
    PolicyAction.ALLOW: 1,
}


class PolicyEvaluator:
    """Evaluates policy rules to determine access decisions."""

    def __init__(self, rules: list[PolicyRule]) -> None:
        self._rules = rules

    def evaluate(
        self,
        resource: str,
        agent_id: str = "",
        session_id: str = "",
    ) -> PolicyDecision:
        """Evaluate all matching rules. Most restrictive wins."""
        matching = self._find_matching_rules(resource, agent_id, session_id)

        if not matching:
            return PolicyDecision(action=PolicyAction.ALLOW, reason="no matching rules")

        # Sort by restrictiveness (DENY > REQUIRE_APPROVAL > ALLOW)
        matching.sort(
            key=lambda r: _ACTION_PRIORITY.get(r.action, 0),
            reverse=True,
        )
        winner = matching[0]

        return PolicyDecision(
            action=winner.action,
            matched_rule_id=winner.id,
            reason=f"matched {winner.scope}:{winner.resource}",
        )

    def _find_matching_rules(
        self,
        resource: str,
        agent_id: str,
        session_id: str,
    ) -> list[PolicyRule]:
        """Find all rules that match the given resource and scope context."""
        matched = []
        for rule in self._rules:
            if not self._resource_matches(rule.resource, resource):
                continue
            if self._scope_matches(rule, agent_id=agent_id, session_id=session_id):
                matched.append(rule)
        return matched

    @staticmethod
    def _scope_matches(rule: PolicyRule, *, agent_id: str, session_id: str) -> bool:
        """Whether *rule*'s scope applies to this agent/session context."""
        if rule.scope == PolicyScope.GLOBAL:
            return True
        if rule.scope == PolicyScope.AGENT:
            return rule.scope_id == agent_id
        if rule.scope == PolicyScope.SESSION:
            return rule.scope_id == session_id
        return False

    @staticmethod
    def _resource_matches(rule_resource: str, target_resource: str) -> bool:
        """Exact match or colon-prefix match (e.g. 'tool:' matches 'tool:shell')."""
        if rule_resource == target_resource:
            return True
        return rule_resource.endswith(":") and target_resource.startswith(rule_resource)
