from __future__ import annotations
import json
import subprocess

_RATE_LIMIT_KEYWORDS = (
    "rate limit",
    "rate_limit",
    "overloaded",
    "too many requests",
)


def is_rate_limit_output(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _RATE_LIMIT_KEYWORDS)


class SessionManager:
    """Claude-specific session continuity: stores session IDs, polls ccusage."""

    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], str] = {}

    def save_session(self, task_id: str, role: str, session_id: str) -> None:
        self._sessions[(task_id, role)] = session_id

    def get_session(self, task_id: str, role: str) -> str | None:
        return self._sessions.get((task_id, role))

    def is_window_available(self) -> bool:
        """True if ccusage reports zero active blocks (rate limit window clear)."""
        try:
            result = subprocess.run(
                ["ccusage", "blocks", "--json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get("blocks", 1) == 0
        except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError):
            pass
        return True   # assume available if ccusage not installed
