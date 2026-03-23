import pytest

from breqy.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_shell_echo() -> None:
    result = await ShellTool(timeout=5).execute({"command": "echo hello"})

    assert result.success is True
    assert "hello" in result.output["stdout"]
    assert result.output["return_code"] == 0


@pytest.mark.asyncio
async def test_shell_non_zero_exit() -> None:
    result = await ShellTool(timeout=5).execute({"command": "false"})

    assert result.success is False
    assert result.output["return_code"] != 0


@pytest.mark.asyncio
async def test_shell_timeout() -> None:
    result = await ShellTool(timeout=1).execute({"command": "sleep 5"})

    assert result.success is False
    assert "timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_shell_requires_command() -> None:
    result = await ShellTool().execute({})

    assert result.success is False
    assert "command" in result.error.lower()


@pytest.mark.asyncio
async def test_shell_invalid_timeout_seconds_returns_failure() -> None:
    result = await ShellTool(timeout=5).execute({"command": "echo hello", "timeout_seconds": "abc"})

    assert result.success is False
    assert "timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_shell_invalid_cwd_returns_failure() -> None:
    result = await ShellTool(timeout=5).execute(
        {"command": "echo hello", "cwd": "/path/that/does/not/exist"}
    )

    assert result.success is False
    assert "cwd" in result.error.lower() or "directory" in result.error.lower()
