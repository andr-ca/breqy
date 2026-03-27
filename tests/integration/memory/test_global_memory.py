from __future__ import annotations

from pathlib import Path

import pytest

from breqy.config.models import EngineConfig
from breqy.engine.daemon import EngineDaemon


@pytest.mark.asyncio
async def test_global_memory_written_in_one_session_is_visible_in_another(tmp_dir: Path) -> None:
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )

    daemon = EngineDaemon(config)
    await daemon.start()
    try:
        assert daemon.server is not None
        source_session = await daemon.server.session_manager.create_session("breqy")
        other_session = await daemon.server.session_manager.create_session("breqy")

        write_result = await daemon.server.execute_tool(
            session_id=source_session.id,
            agent_id="breqy",
            tool_name="mcp.memory.n--write",
            arguments={
                "scope": "session",
                "kind": "lesson",
                "content": "Global lessons should be visible from a different session.",
                "tags": ["global", "lesson"],
            },
        )
        assert write_result.success is True
        record_id = write_result.output["record"]["id"]

        promote_result = await daemon.server.execute_tool(
            session_id=source_session.id,
            agent_id="breqy",
            tool_name="mcp.memory.n--promote",
            arguments={
                "record_id": record_id,
                "autonomy_level": "autonomous",
            },
        )
        assert promote_result.success is True

        search_result = await daemon.server.execute_tool(
            session_id=other_session.id,
            agent_id="breqy",
            tool_name="mcp.memory.n--search",
            arguments={
                "scope": "global",
                "query": "different session",
                "tags": ["global"],
            },
        )
    finally:
        await daemon.stop()

    assert search_result.success is True
    assert [record["content"] for record in search_result.output["records"]] == [
        "Global lessons should be visible from a different session.",
    ]
