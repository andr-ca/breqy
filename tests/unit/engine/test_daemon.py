"""Tests for EngineDaemon lifecycle."""
from __future__ import annotations

import pytest
from pathlib import Path

from breqy.engine.daemon import EngineDaemon
from breqy.config.models import EngineConfig


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
