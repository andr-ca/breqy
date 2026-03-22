"""Tests for FilesystemPolicyChecker — path-based access control."""
from __future__ import annotations

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


def test_most_specific_rule_wins():
    """When two rules match, the more specific (deeper path) wins."""
    rules = [
        FilesystemPolicy(
            path_pattern="/home",
            allowed_operations=[FilesystemOperation.READ, FilesystemOperation.WRITE],
        ),
        FilesystemPolicy(
            path_pattern="/home/user/secrets",
            allowed_operations=[],  # nothing allowed here
        ),
    ]
    checker = FilesystemPolicyChecker(rules=rules)
    # The more specific /home/user/secrets rule applies → WRITE is denied
    result = checker.check("/home/user/secrets/key.txt", FilesystemOperation.WRITE)
    assert result == PolicyAction.DENY
