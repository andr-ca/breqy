from __future__ import annotations

from pathlib import Path

import pytest

from breqy.config.models import EngineConfig
from breqy.domain.enums import PolicyAction, PolicyScope
from breqy.domain.models import PolicyRule
from breqy.engine.daemon import EngineDaemon


@pytest.mark.asyncio
async def test_default_runtime_rejects_private_memory_write_until_phase8_wiring(tmp_dir: Path) -> None:
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

        result = await daemon.server.execute_tool(
            session_id=session.id,
            agent_id="breqy",
            tool_name="mcp.memory.n--write",
            arguments={
                "scope": "private",
                "content": "Private runtime wiring is deferred.",
            },
        )
    finally:
        await daemon.stop()

    assert result.success is False
    assert "phase 8" in result.error.lower()


@pytest.mark.asyncio
async def test_mediated_tool_path_rejects_direct_global_write(tmp_dir: Path) -> None:
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

        result = await daemon.server.execute_tool(
            session_id=session.id,
            agent_id="breqy",
            tool_name="mcp.memory.n--write",
            arguments={
                "scope": "global",
                "content": "Direct global writes stay rejected.",
            },
        )
    finally:
        await daemon.stop()

    assert result.success is False
    assert result.error == "global memory must be created only through promotion"


@pytest.mark.asyncio
async def test_promotion_is_blocked_when_inner_memory_policy_denies_it(tmp_dir: Path) -> None:
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
        policy_rules=[
            PolicyRule(
                scope=PolicyScope.GLOBAL,
                action=PolicyAction.DENY,
                resource="memory:session:promote",
            )
        ],
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
                "kind": "lesson",
                "content": "Promotion should be denied by inner memory policy.",
            },
        )
        assert write_result.success is True

        promote_result = await daemon.server.execute_tool(
            session_id=session.id,
            agent_id="breqy",
            tool_name="mcp.memory.n--promote",
            arguments={
                "record_id": write_result.output["record"]["id"],
                "autonomy_level": "autonomous",
            },
        )
    finally:
        await daemon.stop()

    assert promote_result.success is False
    assert "policy denied memory access" in promote_result.error.lower()
