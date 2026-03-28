"""Tests for EngineDaemon lifecycle."""
from __future__ import annotations

import asyncio
import runpy
import pytest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from breqy.domain.enums import PolicyAction, PolicyScope
from breqy.domain.models import PolicyRule
from breqy.engine.daemon import EngineDaemon
from breqy.config.models import EngineConfig
from breqy.memory.service import MemoryService


@pytest.mark.asyncio
async def test_daemon_starts_and_stops(tmp_dir: Path):
    """Daemon starts (is_running=True) and stops (is_running=False) cleanly."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()
    assert daemon.is_running

    await daemon.stop()
    assert not daemon.is_running


@pytest.mark.asyncio
async def test_daemon_creates_data_dir(tmp_dir: Path):
    """Daemon creates data_dir on startup if it doesn't exist."""
    data_dir = tmp_dir / "breqy_data"
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(data_dir / "test.db"),
        data_dir=str(data_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()

    assert data_dir.exists()

    await daemon.stop()


@pytest.mark.asyncio
async def test_daemon_creates_socket_parent_dir(tmp_dir: Path):
    """Daemon creates the socket parent directory on startup if it doesn't exist."""
    nested_socket = tmp_dir / "deep" / "nested" / "engine.sock"
    config = EngineConfig(
        socket_path=str(nested_socket),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()

    assert nested_socket.parent.exists()

    await daemon.stop()


@pytest.mark.asyncio
async def test_daemon_wires_tool_service_into_engine_server(tmp_dir: Path):
    """Daemon startup composes a tool service for the engine server."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)

    await daemon.start()
    try:
        assert daemon.server is not None
        assert daemon.server.tool_service is not None
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_daemon_default_tool_service_registers_native_tools(tmp_dir: Path):
    """Daemon startup builds the default native tool registry."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)

    await daemon.start()
    try:
        assert daemon.server is not None
        assert daemon.server.tool_service is not None
        assert daemon.server.tool_service._registry.get("shell") is not None
        assert daemon.server.tool_service._registry.get("filesystem") is not None
        assert daemon.server.tool_service._registry.get("mcp.memory.n--search") is not None
        assert daemon.server.tool_service._registry.get("mcp.memory.n--write") is not None
        assert daemon.server.tool_service._registry.get("mcp.memory.n--promote") is not None
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_daemon_wires_memory_service_into_engine_server(tmp_dir: Path):
    """Daemon startup composes the engine-owned memory service."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)

    await daemon.start()
    try:
        assert daemon.server is not None
        assert isinstance(daemon.server.memory_service, MemoryService)
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_daemon_spawns_default_agent_runtime_from_agents_directory(tmp_dir: Path, monkeypatch: pytest.MonkeyPatch):
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    spawned: list[str] = []

    await daemon.start()
    try:
        assert daemon.server is not None

        def fake_spawn(agent_dir: str, *, session_id: str = "") -> int:
            spawned.append(agent_dir)
            return 12345

        monkeypatch.setattr(daemon.server.agent_spawner, "spawn", fake_spawn)

        await daemon.start_default_agent()
    finally:
        await daemon.stop()

    assert spawned == ["agents/breqy"]


@pytest.mark.asyncio
async def test_start_default_agent_creates_session_and_passes_session_id(tmp_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """start_default_agent creates a session before spawning so the agent has a valid session_id."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    spawned: list[tuple[str, str]] = []

    await daemon.start()
    try:
        assert daemon.server is not None

        def tracking_spawn(agent_dir: str, *, session_id: str = "") -> int:
            spawned.append((agent_dir, session_id))
            return 12345

        monkeypatch.setattr(daemon.server.agent_spawner, "spawn", tracking_spawn)

        await daemon.start_default_agent()

        # Should have spawned with a real session_id (not empty)
        assert len(spawned) == 1
        agent_dir, session_id = spawned[0]
        assert agent_dir == "agents/breqy"
        assert session_id != "", "start_default_agent must create a session and pass its id"
        assert session_id.startswith("ses_"), f"Expected session ID prefix 'ses_', got: {session_id}"
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_daemon_tool_service_honors_configured_policy_rules(tmp_dir: Path):
    """Daemon-composed tool service uses EngineConfig policy rules."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
        policy_rules=[
            PolicyRule(
                scope=PolicyScope.GLOBAL,
                action=PolicyAction.DENY,
                resource="tool:shell",
            )
        ],
    )
    daemon = EngineDaemon(config)

    await daemon.start()
    try:
        assert daemon.server is not None
        session = await daemon.server.session_manager.create_session("breqy")

        result = await daemon.server.execute_tool(
            session_id=session.id,
            agent_id="breqy",
            tool_name="shell",
            arguments={"command": "printf blocked"},
        )
    finally:
        await daemon.stop()

    assert result.success is False
    assert "policy denied" in result.error.lower()


@pytest.mark.asyncio
async def test_wait_until_stopped_returns_immediately_after_stop(tmp_dir: Path):
    """wait_until_stopped() unblocks as soon as stop() is called — no polling delay."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()

    # Schedule stop() to fire shortly after we start waiting
    async def delayed_stop() -> None:
        await asyncio.sleep(0.01)  # 10 ms
        await daemon.stop()

    asyncio.create_task(delayed_stop())

    # wait_until_stopped should return almost instantly (well under 1 s)
    await asyncio.wait_for(daemon.wait_until_stopped(), timeout=1.0)
    assert not daemon.is_running


@pytest.mark.asyncio
async def test_wait_until_stopped_returns_if_already_stopped(tmp_dir: Path):
    """wait_until_stopped() returns immediately when stop() was already called."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()
    await daemon.stop()

    # Should return immediately since event is already set
    await asyncio.wait_for(daemon.wait_until_stopped(), timeout=0.1)
    assert not daemon.is_running


def test_main_loads_config_registers_signal_handlers_and_stops_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    config = EngineConfig(
        socket_path="/tmp/breqy-engine.sock",
        db_path="/tmp/breqy.db",
        data_dir="/tmp",
    )

    stopped_event = asyncio.Event()
    daemon = SimpleNamespace(is_running=True)
    daemon.start = AsyncMock()

    async def stop() -> None:
        daemon.is_running = False
        stopped_event.set()

    daemon.stop = AsyncMock(side_effect=stop)

    async def wait_until_stopped() -> None:
        await stopped_event.wait()

    daemon.wait_until_stopped = wait_until_stopped

    created_tasks: list[asyncio.Task[None]] = []
    registered_signals: list[object] = []

    class FakeLoop:
        def add_signal_handler(self, sig: object, handler: Any) -> None:
            registered_signals.append(sig)
            if len(registered_signals) == 2:
                handler()

        def create_task(self, coro: Any) -> asyncio.Task[None]:
            task = asyncio.create_task(coro)
            created_tasks.append(task)
            return task

    fake_loop = FakeLoop()

    monkeypatch.setattr("breqy.config.loader.load_engine_config", lambda: config)
    monkeypatch.setattr("breqy.engine.daemon.EngineDaemon", lambda loaded_config: daemon)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: fake_loop)

    from breqy.engine import daemon as daemon_module

    daemon_module.main()

    daemon.start.assert_awaited_once()
    daemon.stop.assert_awaited_once()
    assert len(registered_signals) == 2


# --------------------------------------------------------------------------- #
# Phase 9, Task 11: EngineDaemon startup restore + agent respawn
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_daemon_wires_participant_repo_into_engine_server(tmp_dir: Path):
    """Daemon creates ParticipantRepository and passes it to EngineServer."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)

    await daemon.start()
    try:
        assert daemon.server is not None
        # EngineServer has participant_repo wired
        assert daemon.server._participant_repo is not None
        # ControlHandler is created (because participant_repo is present)
        assert daemon.server.control_handler is not None
        # SessionManager has participant_repo
        assert daemon.server.session_manager._participants is not None
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_daemon_restores_active_sessions_and_respawns_agents_on_start(tmp_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """On start, daemon restores active sessions and respawns their primary agents."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)

    await daemon.start()
    try:
        assert daemon.server is not None

        # Create a session that represents a "pre-existing" active session
        session = await daemon.server.session_manager.create_session("agt_breqy")

        # Track spawn calls
        spawned: list[tuple[str, str]] = []
        original_spawn = daemon.server.agent_spawner.spawn

        def tracking_spawn(agent_dir: str, *, session_id: str = "") -> int:
            spawned.append((agent_dir, session_id))
            return 12345

        monkeypatch.setattr(daemon.server.agent_spawner, "spawn", tracking_spawn)

        # Stop and restart to trigger restore
        await daemon.stop()

        daemon2 = EngineDaemon(config)
        await daemon2.start()
        try:
            assert daemon2.server is not None
            monkeypatch.setattr(daemon2.server.agent_spawner, "spawn", tracking_spawn)

            # Call the restore method explicitly
            await daemon2.restore_sessions()

            assert len(spawned) == 1
            assert spawned[0][0] == "agents/breqy"
            assert spawned[0][1] == session.id
        finally:
            await daemon2.stop()
    except Exception:
        await daemon.stop()
        raise


@pytest.mark.asyncio
async def test_daemon_restore_sessions_skips_when_no_active_sessions(tmp_dir: Path):
    """restore_sessions does nothing when there are no active sessions."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)

    await daemon.start()
    try:
        assert daemon.server is not None
        # No sessions exist, should complete without error
        await daemon.restore_sessions()
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_daemon_restore_sessions_raises_when_server_not_started(tmp_dir: Path):
    """restore_sessions raises RuntimeError when called before start()."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)

    with pytest.raises(RuntimeError, match="Engine server is not started"):
        await daemon.restore_sessions()


def test_daemon_module_entrypoint_invokes_main(monkeypatch: pytest.MonkeyPatch) -> None:
    config = EngineConfig(
        socket_path="/tmp/breqy-engine.sock",
        db_path="/tmp/breqy.db",
        data_dir="/tmp",
    )

    monkeypatch.setattr("breqy.config.loader.load_engine_config", lambda: config)

    def fake_run(coro: Any) -> None:
        coro.close()

    monkeypatch.setattr(asyncio, "run", fake_run)

    runpy.run_path(
        "/home/andrey/projects/breqy/.worktrees/exp-full-build/breqy/engine/daemon.py",
        run_name="__main__",
    )
