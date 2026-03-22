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

        # Most specific rule wins (deepest path by component count)
        matching.sort(key=lambda r: len(PurePosixPath(r.path_pattern).parts), reverse=True)
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
