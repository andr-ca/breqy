from __future__ import annotations

import asyncio
from typing import Any

import structlog

from breqy.tools.executor import ToolExecutor, ToolResult

logger = structlog.get_logger(__name__)


class ShellTool(ToolExecutor):
    name = "shell"
    description = "Execute a shell command and return its output"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"},
            "timeout_seconds": {
                "type": "integer",
                "description": "Maximum seconds to wait for the command to complete",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for command execution",
            },
        },
        "required": ["command"],
    }

    def __init__(self, timeout: int = 120) -> None:
        self._timeout = timeout

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        command = arguments.get("command")
        if not command:
            return ToolResult(success=False, error="Missing required argument: command")

        raw_timeout_seconds = arguments.get("timeout_seconds", self._timeout)
        try:
            timeout_seconds = int(raw_timeout_seconds)
        except (TypeError, ValueError):
            return ToolResult(
                success=False,
                error=f"Invalid timeout_seconds value: {raw_timeout_seconds}",
            )

        cwd = arguments.get("cwd")

        logger.info("Executing shell command", command=command, cwd=cwd, timeout=timeout_seconds)

        try:
            process = await asyncio.create_subprocess_shell(
                str(command),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd) if cwd is not None else None,
            )
        except OSError as exc:
            return ToolResult(
                success=False, error=f"Failed to start shell command for cwd {cwd}: {exc}"
            )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning(
                "Shell command timed out", command=command, cwd=cwd, timeout=timeout_seconds
            )
            process.kill()
            stdout, stderr = await process.communicate()
            return ToolResult(
                success=False,
                output={
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "return_code": process.returncode,
                },
                error=f"Command timeout after {timeout_seconds}s",
                summary=f"Shell command timed out after {timeout_seconds}s",
            )

        return_code = process.returncode or 0
        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        if return_code == 0:
            logger.info("Shell command completed", command=command, return_code=return_code)
        else:
            logger.warning("Shell command failed", command=command, return_code=return_code)

        return ToolResult(
            success=return_code == 0,
            output={
                "stdout": stdout_text,
                "stderr": stderr_text,
                "return_code": return_code,
            },
            error=stderr_text if return_code != 0 else "",
            summary=f"Shell command exited with code {return_code}",
        )
