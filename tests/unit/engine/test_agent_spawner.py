"""Tests for AgentSpawner."""
from __future__ import annotations

import sys

from breqy.engine.agent_spawner import AgentSpawner


def test_spawner_builds_command():
    """_build_command() returns a valid python -m invocation."""
    spawner = AgentSpawner(engine_socket="/tmp/test.sock")
    cmd = spawner._build_command("system/agents/breqy")
    assert sys.executable == cmd[0]
    assert "-m" in cmd
    assert "breqy.agents.runtime" in cmd


def test_spawner_tracks_no_processes_initially():
    """list_running() returns empty list before any spawns."""
    spawner = AgentSpawner(engine_socket="/tmp/test.sock")
    assert spawner.list_running() == []
