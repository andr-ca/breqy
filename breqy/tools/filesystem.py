from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from breqy.domain.enums import FilesystemOperation
from breqy.tools.executor import ToolExecutor, ToolResult

logger = structlog.get_logger(__name__)

_OPERATION_MAP: dict[str, list[FilesystemOperation]] = {
    "read": [FilesystemOperation.READ],
    "write": [FilesystemOperation.WRITE],
    "edit": [FilesystemOperation.READ, FilesystemOperation.WRITE],
    "delete": [FilesystemOperation.DELETE],
}


def derive_operations(arguments: dict[str, Any]) -> list[FilesystemOperation]:
    operation = arguments.get("operation")
    if not isinstance(operation, str):
        return []
    return list(_OPERATION_MAP.get(operation, []))


class FilesystemTool(ToolExecutor):
    name = "filesystem"
    description = "Read, write, edit, and delete files"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["read", "write", "edit", "delete"],
                "description": "The filesystem operation to perform",
            },
            "path": {"type": "string", "description": "Target file path"},
            "content": {
                "type": "string",
                "description": "File content for write operation",
            },
            "old_string": {
                "type": "string",
                "description": "Text to find for edit operation",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text for edit operation",
            },
        },
        "required": ["operation", "path"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        operation = arguments.get("operation")
        raw_path = arguments.get("path")

        if not operation:
            return ToolResult(success=False, error="Missing required argument: operation")
        if not raw_path:
            return ToolResult(success=False, error="Missing required argument: path")

        path = Path(str(raw_path))
        logger.info("Executing filesystem operation", operation=operation, path=str(path))

        try:
            if operation == "read":
                content = path.read_text(encoding="utf-8")
                return ToolResult(
                    success=True,
                    output={"content": content, "path": str(path)},
                    summary=f"Read file {path}",
                )

            if operation == "write":
                content_value = arguments.get("content")
                if content_value is None:
                    return ToolResult(success=False, error="Missing required argument: content")

                content = str(content_value)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                return ToolResult(
                    success=True,
                    output={"path": str(path), "bytes_written": len(content.encode("utf-8"))},
                    summary=f"Wrote file {path}",
                )

            if operation == "edit":
                old_string = arguments.get("old_string")
                new_string = arguments.get("new_string")
                if old_string is None:
                    return ToolResult(success=False, error="Missing required argument: old_string")
                if new_string is None:
                    return ToolResult(success=False, error="Missing required argument: new_string")

                content = path.read_text(encoding="utf-8")
                if str(old_string) not in content:
                    return ToolResult(
                        success=False,
                        error=f"Old text not found in file: {path}",
                        summary=f"Failed to edit file {path}",
                    )

                updated_content = content.replace(str(old_string), str(new_string), 1)
                path.write_text(updated_content, encoding="utf-8")
                return ToolResult(
                    success=True,
                    output={"path": str(path)},
                    summary=f"Edited file {path}",
                )

            if operation == "delete":
                path.unlink()
                return ToolResult(
                    success=True,
                    output={"path": str(path)},
                    summary=f"Deleted file {path}",
                )

            return ToolResult(
                success=False,
                error=f"Invalid filesystem operation: {operation}",
                summary="Filesystem operation failed",
            )
        except OSError as exc:
            logger.warning(
                "Filesystem operation failed",
                operation=operation,
                path=str(path),
                error=str(exc),
            )
            return ToolResult(
                success=False,
                error=str(exc),
                summary=f"Filesystem operation {operation} failed for {path}",
            )
