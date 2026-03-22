# Phase 4 Plan 01: PolicyEvaluator & FilesystemPolicyChecker

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `PolicyEvaluator` (resource-level layered rule resolution) and `FilesystemPolicyChecker` (path-based file access policy) in `breqy/policy/`.

**Architecture:** Two classes in `breqy/policy/`. `PolicyEvaluator` consumes `PolicyRule` domain objects and applies most-restrictive-wins logic across global/agent/session scopes. `FilesystemPolicyChecker` consumes `FilesystemPolicy` domain objects and checks path+operation access. Both are pure in-memory components with no storage or async dependencies.

**Tech Stack:** Python 3.12, pydantic v2 (domain models already exist)

**Worktree:** `/home/andrey/projects/breqy/.worktrees/exp-full-build`
**Run tests with:** `uv run pytest`

---

## Key Domain Facts (read before coding)

From `breqy/domain/enums.py`:
- `PolicyAction.ALLOW`, `PolicyAction.DENY`, `PolicyAction.REQUIRE_APPROVAL` (NOT `APPROVE`)
- `PolicyScope.GLOBAL`, `PolicyScope.AGENT`, `PolicyScope.SESSION`
- `FilesystemOperation.READ`, `WRITE`, `DELETE`, `EXECUTE`, `LIST`

From `breqy/domain/models.py`:
- `PolicyRule(id, scope, scope_id: str|None, action, resource, operations, path_pattern, created_at)`
- `FilesystemPolicy(id, session_id: str|None, path_pattern, allowed_operations, created_at)`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `breqy/policy/__init__.py` | Create | Package init |
| `breqy/policy/models.py` | Create | `PolicyDecision` result model |
| `breqy/policy/evaluator.py` | Create | `PolicyEvaluator` — layered rule resolution |
| `breqy/policy/filesystem.py` | Create | `FilesystemPolicyChecker` — path-based access |
| `tests/unit/policy/__init__.py` | Create | Test package stub |
| `tests/unit/policy/test_evaluator.py` | Create | 8 TDD tests for PolicyEvaluator |
| `tests/unit/policy/test_filesystem.py` | Create | 5 TDD tests for FilesystemPolicyChecker |

---

## Task 1: PolicyDecision Model & PolicyEvaluator

**Files:**
- Create: `breqy/policy/__init__.py`
- Create: `breqy/policy/models.py`
- Create: `breqy/policy/evaluator.py`
- Create: `tests/unit/policy/__init__.py`
- Create: `tests/unit/policy/test_evaluator.py`

- [ ] **Step 1: Write failing tests for PolicyEvaluator**

Create `tests/unit/policy/__init__.py` (empty) and `tests/unit/policy/test_evaluator.py`:

```python
"""Tests for PolicyEvaluator — most restrictive rule wins."""
from __future__ import annotations

import pytest

from breqy.domain.enums import PolicyAction, PolicyScope
from breqy.domain.models import PolicyRule
from breqy.policy.evaluator import PolicyEvaluator
from breqy.policy.models import PolicyDecision


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
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/unit/policy/test_evaluator.py -v
```
Expected: `ModuleNotFoundError: No module named 'breqy.policy'`

- [ ] **Step 3: Create `breqy/policy/__init__.py`** (empty)

- [ ] **Step 4: Create `breqy/policy/models.py`**

```python
"""Policy evaluation result models."""
from __future__ import annotations

from pydantic import BaseModel

from breqy.domain.enums import PolicyAction


class PolicyDecision(BaseModel):
    """Result of evaluating a policy check."""

    action: PolicyAction
    matched_rule_id: str = ""
    reason: str = ""
```

- [ ] **Step 5: Create `breqy/policy/evaluator.py`**

```python
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
            if rule.scope == PolicyScope.GLOBAL:
                matched.append(rule)
            elif rule.scope == PolicyScope.AGENT and rule.scope_id == agent_id:
                matched.append(rule)
            elif rule.scope == PolicyScope.SESSION and rule.scope_id == session_id:
                matched.append(rule)
        return matched

    @staticmethod
    def _resource_matches(rule_resource: str, target_resource: str) -> bool:
        """Exact match or colon-prefix match (e.g. 'tool:' matches 'tool:shell')."""
        if rule_resource == target_resource:
            return True
        if rule_resource.endswith(":") and target_resource.startswith(rule_resource):
            return True
        return False
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
uv run pytest tests/unit/policy/test_evaluator.py -v
```
Expected: 8 passed

- [ ] **Step 7: Commit**

```bash
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  add breqy/policy/__init__.py breqy/policy/models.py breqy/policy/evaluator.py \
      tests/unit/policy/__init__.py tests/unit/policy/test_evaluator.py
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  commit -m "feat(policy): add PolicyEvaluator with most-restrictive-wins rule resolution"
```

---

## Task 2: FilesystemPolicyChecker

**Files:**
- Create: `breqy/policy/filesystem.py`
- Create: `tests/unit/policy/test_filesystem.py`

- [ ] **Step 1: Write failing tests for FilesystemPolicyChecker**

Create `tests/unit/policy/test_filesystem.py`:

```python
"""Tests for FilesystemPolicyChecker — path-based access control."""
from __future__ import annotations

import pytest

from breqy.domain.enums import FilesystemOperation, PolicyAction
from breqy.domain.models import FilesystemPolicy
from breqy.policy.filesystem import FilesystemPolicyChecker


def test_allow_when_no_rules():
    """No rules → default allow."""
    checker = FilesystemPolicyChecker(rules=[])
    result = checker.check("/home/user/file.txt", FilesystemOperation.READ)
    assert result == PolicyAction.ALLOW


def test_exact_path_deny():
    """Exact path match with empty allowed_operations produces DENY."""
    rules = [
        FilesystemPolicy(
            path_pattern="/etc/passwd",
            allowed_operations=[],  # nothing allowed → any access is DENY
        ),
    ]
    checker = FilesystemPolicyChecker(rules=rules)
    result = checker.check("/etc/passwd", FilesystemOperation.READ)
    assert result == PolicyAction.DENY


def test_allowed_operation_returns_allow():
    """If the operation is in allowed_operations, access is ALLOW."""
    rules = [
        FilesystemPolicy(
            path_pattern="/home/user",
            allowed_operations=[FilesystemOperation.READ, FilesystemOperation.LIST],
        ),
    ]
    checker = FilesystemPolicyChecker(rules=rules)
    result = checker.check("/home/user/notes.txt", FilesystemOperation.READ)
    assert result == PolicyAction.ALLOW


def test_disallowed_operation_returns_deny():
    """If path matches but operation not in allowed_operations, DENY."""
    rules = [
        FilesystemPolicy(
            path_pattern="/home/user",
            allowed_operations=[FilesystemOperation.READ],
        ),
    ]
    checker = FilesystemPolicyChecker(rules=rules)
    result = checker.check("/home/user/notes.txt", FilesystemOperation.WRITE)
    assert result == PolicyAction.DENY


def test_unmatched_path_defaults_allow():
    """A rule for a different path does not affect an unrelated path."""
    rules = [
        FilesystemPolicy(
            path_pattern="/etc",
            allowed_operations=[],
        ),
    ]
    checker = FilesystemPolicyChecker(rules=rules)
    result = checker.check("/home/user/file.txt", FilesystemOperation.READ)
    assert result == PolicyAction.ALLOW
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/unit/policy/test_filesystem.py -v
```
Expected: `ModuleNotFoundError: No module named 'breqy.policy.filesystem'`

- [ ] **Step 3: Create `breqy/policy/filesystem.py`**

The `FilesystemPolicy` model uses `allowed_operations: list[FilesystemOperation]` — if the path matches and the operation is in `allowed_operations`, it's ALLOW; if the path matches and the operation is NOT in `allowed_operations`, it's DENY; if no rule matches the path at all, default is ALLOW.

```python
"""Filesystem path-based policy checker.

Uses prefix-path matching (no globs in v1).
If a rule matches the path:
  - operation in allowed_operations → ALLOW
  - operation not in allowed_operations → DENY
If no rule matches → ALLOW (default open).
"""
from __future__ import annotations

from pathlib import PurePosixPath

from breqy.domain.enums import FilesystemOperation, PolicyAction
from breqy.domain.models import FilesystemPolicy


class FilesystemPolicyChecker:
    """Checks filesystem access against path-based rules."""

    def __init__(self, rules: list[FilesystemPolicy]) -> None:
        self._rules = rules

    def check(self, path: str, operation: FilesystemOperation) -> PolicyAction:
        """Check if the given path+operation is allowed.

        Finds the most-specific matching rule (longest path prefix).
        If no rule matches → ALLOW.
        If a rule matches → ALLOW if operation is in allowed_operations, else DENY.
        """
        target = PurePosixPath(path)
        matching = []
        for rule in self._rules:
            rule_path = PurePosixPath(rule.path_pattern)
            if target == rule_path or self._is_under(target, rule_path):
                matching.append(rule)

        if not matching:
            return PolicyAction.ALLOW

        # Most specific rule wins (longest path)
        matching.sort(key=lambda r: len(r.path_pattern), reverse=True)
        winner = matching[0]

        if operation in winner.allowed_operations:
            return PolicyAction.ALLOW
        return PolicyAction.DENY

    @staticmethod
    def _is_under(target: PurePosixPath, rule_path: PurePosixPath) -> bool:
        """True if target is under rule_path directory."""
        try:
            target.relative_to(rule_path)
            return True
        except ValueError:
            return False
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/unit/policy/test_filesystem.py -v
```
Expected: 5 passed

- [ ] **Step 5: Run full suite — verify no regressions**

```bash
uv run pytest --tb=no -q
```
Expected: all prior + 13 new tests pass

- [ ] **Step 6: Commit**

```bash
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  add breqy/policy/filesystem.py tests/unit/policy/test_filesystem.py
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  commit -m "feat(policy): add FilesystemPolicyChecker with path-prefix rule matching"
```

---

## Final Verification

```bash
uv run pytest tests/unit/policy/ -v
```
Expected: 13 tests pass (8 evaluator + 5 filesystem), full suite green.
