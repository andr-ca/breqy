from __future__ import annotations

from pathlib import Path

import pytest

from breqy.config.models import EngineConfig
from breqy.engine.daemon import EngineDaemon


@pytest.mark.asyncio
async def test_session_memory_survives_engine_restart(tmp_dir: Path) -> None:
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )

    daemon = EngineDaemon(config)
    await daemon.start()
    try:
        assert daemon.server is not None
        session = await daemon.server.session_manager.create_session("breqy")

        write_result = await daemon.server.execute_tool(
            session_id=session.id,
            agent_id="breqy",
            tool_name="mcp.memory.n--write",
            arguments={
                "scope": "session",
                "kind": "fact",
                "content": "Session continuity survives restart.",
                "tags": ["continuity", "restart"],
            },
        )
    finally:
        await daemon.stop()

    assert write_result.success is True

    restarted_daemon = EngineDaemon(config)
    await restarted_daemon.start()
    try:
        assert restarted_daemon.server is not None

        search_result = await restarted_daemon.server.execute_tool(
            session_id=session.id,
            agent_id="breqy",
            tool_name="mcp.memory.n--search",
            arguments={
                "scope": "session",
                "query": "continuity restart",
                "tags": ["continuity"],
            },
        )
    finally:
        await restarted_daemon.stop()

    assert search_result.success is True
    assert [record["content"] for record in search_result.output["records"]] == [
        "Session continuity survives restart.",
    ]
