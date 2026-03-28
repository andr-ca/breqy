"""Tests for AgentRegistry."""
from __future__ import annotations

from breqy.engine.agent_registry import AgentRegistry


def test_register_and_lookup():
    """register() adds an agent; get() returns it."""
    registry = AgentRegistry()
    registry.register("breqy", client_id="cli_123")

    info = registry.get("breqy")
    assert info is not None
    assert info.client_id == "cli_123"


def test_unregister():
    """unregister() removes an agent; get() returns None afterwards."""
    registry = AgentRegistry()
    registry.register("breqy", client_id="cli_123")
    registry.unregister("breqy")

    assert registry.get("breqy") is None


def test_list_agents():
    """list_agents() returns all registered agents."""
    registry = AgentRegistry()
    registry.register("breqy", client_id="cli_1")
    registry.register("docker-agent", client_id="cli_2")

    agents = registry.list_agents()
    assert len(agents) == 2


def test_unregister_by_client_id_removes_registered_agent() -> None:
    registry = AgentRegistry()
    registry.register("breqy", client_id="cli_123")

    registry.unregister_by_client_id("cli_123")

    assert registry.get("breqy") is None


def test_get_by_client_id_returns_none_for_unknown_client() -> None:
    registry = AgentRegistry()

    assert registry.get_by_client_id("missing-client") is None


# --- Session tracking tests ---


class TestSessionTracking:
    """Tests for AgentRegistry session association."""

    def test_agent_info_has_session_id_default_empty(self) -> None:
        """AgentInfo.session_id defaults to empty string."""
        from breqy.engine.agent_registry import AgentInfo

        info = AgentInfo(agent_id="a1", client_id="c1")
        assert info.session_id == ""

    def test_register_without_session_id_backward_compat(self) -> None:
        """Existing callers that omit session_id still work."""
        registry = AgentRegistry()
        registry.register("breqy", client_id="cli_1")

        info = registry.get("breqy")
        assert info is not None
        assert info.session_id == ""

    def test_register_with_session_id(self) -> None:
        """register() accepts session_id and stores it."""
        registry = AgentRegistry()
        registry.register("breqy", client_id="cli_1", session_id="sess-42")

        info = registry.get("breqy")
        assert info is not None
        assert info.session_id == "sess-42"

    def test_list_by_session_returns_matching_agents(self) -> None:
        """list_by_session() returns only agents in the given session."""
        registry = AgentRegistry()
        registry.register("a1", client_id="c1", session_id="sess-1")
        registry.register("a2", client_id="c2", session_id="sess-1")
        registry.register("a3", client_id="c3", session_id="sess-2")

        result = registry.list_by_session("sess-1")
        agent_ids = [info.agent_id for info in result]
        assert sorted(agent_ids) == ["a1", "a2"]

    def test_list_by_session_returns_empty_for_unknown(self) -> None:
        """list_by_session() returns empty list when no agents match."""
        registry = AgentRegistry()
        registry.register("a1", client_id="c1", session_id="sess-1")

        assert registry.list_by_session("nonexistent") == []

    def test_list_by_session_excludes_no_session_agents(self) -> None:
        """Agents with empty session_id are not returned for a named session."""
        registry = AgentRegistry()
        registry.register("a1", client_id="c1")  # no session
        registry.register("a2", client_id="c2", session_id="sess-1")

        result = registry.list_by_session("sess-1")
        assert len(result) == 1
        assert result[0].agent_id == "a2"

    def test_get_by_session_and_agent_found(self) -> None:
        """get_by_session_and_agent() returns info when both match."""
        registry = AgentRegistry()
        registry.register("a1", client_id="c1", session_id="sess-1")

        info = registry.get_by_session_and_agent("sess-1", "a1")
        assert info is not None
        assert info.agent_id == "a1"
        assert info.session_id == "sess-1"

    def test_get_by_session_and_agent_wrong_session(self) -> None:
        """get_by_session_and_agent() returns None if session doesn't match."""
        registry = AgentRegistry()
        registry.register("a1", client_id="c1", session_id="sess-1")

        assert registry.get_by_session_and_agent("sess-2", "a1") is None

    def test_get_by_session_and_agent_wrong_agent(self) -> None:
        """get_by_session_and_agent() returns None if agent_id doesn't exist."""
        registry = AgentRegistry()
        registry.register("a1", client_id="c1", session_id="sess-1")

        assert registry.get_by_session_and_agent("sess-1", "nonexistent") is None

    def test_get_by_session_and_agent_no_session(self) -> None:
        """get_by_session_and_agent() returns None if agent has no session."""
        registry = AgentRegistry()
        registry.register("a1", client_id="c1")  # no session

        assert registry.get_by_session_and_agent("sess-1", "a1") is None


# ---------------------------------------------------------------------------
# structlog migration
# ---------------------------------------------------------------------------

def test_agent_registry_has_structlog_logger():
    """AgentRegistry module should have a structlog logger."""
    import logging as _logging
    from breqy.engine import agent_registry
    assert hasattr(agent_registry, "logger")
    assert not isinstance(agent_registry.logger, _logging.Logger)
