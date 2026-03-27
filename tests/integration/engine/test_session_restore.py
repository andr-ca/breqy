"""Integration tests for session restore across engine restarts.

Tests that active sessions survive an engine stop/start cycle and that
agents are respawned correctly.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from breqy.config.models import EngineConfig
from breqy.domain.enums import SessionStatus
from breqy.engine.daemon import EngineDaemon


@pytest.mark.asyncio
async def test_active_session_survives_engine_restart(tmp_dir: Path) -> None:
    """An ACTIVE session created before restart is still listed after restart."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )

    # First lifecycle: create a session
    daemon1 = EngineDaemon(config)
    await daemon1.start()
    try:
        assert daemon1.server is not None
        session = await daemon1.server.session_manager.create_session("agt_breqy")
        session_id = session.id
    finally:
        await daemon1.stop()

    # Second lifecycle: session should be restorable
    daemon2 = EngineDaemon(config)
    await daemon2.start()
    try:
        assert daemon2.server is not None
        restored = await daemon2.server.session_manager.restore_active_sessions()
        assert len(restored) == 1
        assert restored[0].id == session_id
        assert restored[0].status == SessionStatus.ACTIVE
    finally:
        await daemon2.stop()


@pytest.mark.asyncio
async def test_closed_session_not_restored(tmp_dir: Path) -> None:
    """CLOSED sessions are NOT returned by restore_active_sessions."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )

    daemon1 = EngineDaemon(config)
    await daemon1.start()
    try:
        assert daemon1.server is not None
        session = await daemon1.server.session_manager.create_session("agt_breqy")
        await daemon1.server.session_manager.close_session(session.id)
    finally:
        await daemon1.stop()

    daemon2 = EngineDaemon(config)
    await daemon2.start()
    try:
        assert daemon2.server is not None
        restored = await daemon2.server.session_manager.restore_active_sessions()
        assert len(restored) == 0
    finally:
        await daemon2.stop()


@pytest.mark.asyncio
async def test_circuit_broken_session_not_restored(tmp_dir: Path) -> None:
    """CIRCUIT_BROKEN sessions are NOT returned by restore_active_sessions."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )

    daemon1 = EngineDaemon(config)
    await daemon1.start()
    try:
        assert daemon1.server is not None
        session = await daemon1.server.session_manager.create_session("agt_breqy")
        await daemon1.server.session_manager.circuit_break_session(session.id)
    finally:
        await daemon1.stop()

    daemon2 = EngineDaemon(config)
    await daemon2.start()
    try:
        assert daemon2.server is not None
        restored = await daemon2.server.session_manager.restore_active_sessions()
        assert len(restored) == 0
    finally:
        await daemon2.stop()


@pytest.mark.asyncio
async def test_restore_sessions_spawns_agents_for_each_active_session(
    tmp_dir: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """restore_sessions() spawns an agent for each active session."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )

    # Create two active sessions
    daemon1 = EngineDaemon(config)
    await daemon1.start()
    try:
        assert daemon1.server is not None
        s1 = await daemon1.server.session_manager.create_session("agt_breqy")
        s2 = await daemon1.server.session_manager.create_session("agt_checker")
    finally:
        await daemon1.stop()

    # Restart and restore
    daemon2 = EngineDaemon(config)
    await daemon2.start()
    try:
        assert daemon2.server is not None
        spawned: list[tuple[str, str]] = []

        def tracking_spawn(agent_dir: str, *, session_id: str = "") -> int:
            spawned.append((agent_dir, session_id))
            return 12345

        monkeypatch.setattr(daemon2.server.agent_spawner, "spawn", tracking_spawn)
        await daemon2.restore_sessions()

        # Two agents spawned (one per active session)
        assert len(spawned) == 2
        session_ids = {s[1] for s in spawned}
        assert s1.id in session_ids
        assert s2.id in session_ids
    finally:
        await daemon2.stop()
