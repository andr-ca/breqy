"""Tests for PolicyEvaluator — most restrictive rule wins."""
from __future__ import annotations

from breqy.domain.enums import PolicyAction, PolicyScope
from breqy.domain.models import PolicyRule
from breqy.policy.evaluator import PolicyEvaluator


def test_allow_when_no_rules():
    """No rules → default allow."""
    evaluator = PolicyEvaluator(rules=[])
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.ALLOW


def test_global_deny_overrides_agent_allow():
    """Global DENY beats agent-scoped ALLOW."""
    rules = [
        PolicyRule(scope=PolicyScope.GLOBAL, action=PolicyAction.DENY, resource="tool:shell"),
        PolicyRule(scope=PolicyScope.AGENT, scope_id="breqy", action=PolicyAction.ALLOW, resource="tool:shell"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.DENY


def test_agent_allow_works_when_no_global_deny():
    """Agent-scoped ALLOW works when there is no conflicting DENY."""
    rules = [
        PolicyRule(scope=PolicyScope.AGENT, scope_id="breqy", action=PolicyAction.ALLOW, resource="tool:shell"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.ALLOW


def test_require_approval_returned():
    """REQUIRE_APPROVAL is returned when that is the most restrictive matching rule."""
    rules = [
        PolicyRule(scope=PolicyScope.GLOBAL, action=PolicyAction.REQUIRE_APPROVAL, resource="tool:shell"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.REQUIRE_APPROVAL


def test_deny_beats_require_approval():
    """DENY overrides REQUIRE_APPROVAL across scopes."""
    rules = [
        PolicyRule(scope=PolicyScope.GLOBAL, action=PolicyAction.DENY, resource="tool:shell"),
        PolicyRule(scope=PolicyScope.AGENT, scope_id="breqy", action=PolicyAction.REQUIRE_APPROVAL, resource="tool:shell"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.DENY


def test_session_scope_rule():
    """Session-scoped DENY applies when session_id matches."""
    rules = [
        PolicyRule(scope=PolicyScope.SESSION, scope_id="ses_123", action=PolicyAction.DENY, resource="tool:ssh"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:ssh", agent_id="breqy", session_id="ses_123")
    assert decision.action == PolicyAction.DENY


def test_session_scope_does_not_apply_to_different_session():
    """Session rule does not apply to a different session."""
    rules = [
        PolicyRule(scope=PolicyScope.SESSION, scope_id="ses_123", action=PolicyAction.DENY, resource="tool:ssh"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:ssh", agent_id="breqy", session_id="ses_other")
    assert decision.action == PolicyAction.ALLOW


def test_unmatched_resource_defaults_allow():
    """A rule for a different resource does not affect this resource."""
    rules = [
        PolicyRule(scope=PolicyScope.GLOBAL, action=PolicyAction.DENY, resource="tool:ssh"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.ALLOW


def test_colon_prefix_resource_match():
    """A rule using a colon-prefix (e.g. 'tool:') matches any sub-resource."""
    rules = [
        PolicyRule(scope=PolicyScope.GLOBAL, action=PolicyAction.DENY, resource="tool:"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.DENY
