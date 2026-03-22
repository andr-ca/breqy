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
