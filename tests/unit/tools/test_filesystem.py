import inspect
from pathlib import Path

import pytest

from breqy.domain.enums import FilesystemOperation
from breqy.tools.filesystem import FilesystemTool, derive_operations


@pytest.mark.asyncio
async def test_read_file(tmp_dir: Path) -> None:
    path = tmp_dir / "input.txt"
    path.write_text("hello", encoding="utf-8")

    result = await FilesystemTool().execute({"operation": "read", "path": str(path)})

    assert result.success is True
    assert result.output["content"] == "hello"


@pytest.mark.asyncio
async def test_write_file(tmp_dir: Path) -> None:
    path = tmp_dir / "out.txt"

    result = await FilesystemTool().execute(
        {"operation": "write", "path": str(path), "content": "new content"}
    )

    assert result.success is True
    assert path.read_text(encoding="utf-8") == "new content"


@pytest.mark.asyncio
async def test_write_file_creates_parent_directories(tmp_dir: Path) -> None:
    path = tmp_dir / "nested" / "dir" / "out.txt"

    result = await FilesystemTool().execute(
        {"operation": "write", "path": str(path), "content": "new content"}
    )

    assert result.success is True
    assert path.read_text(encoding="utf-8") == "new content"


@pytest.mark.asyncio
async def test_edit_file(tmp_dir: Path) -> None:
    path = tmp_dir / "edit.txt"
    path.write_text("old text here", encoding="utf-8")

    result = await FilesystemTool().execute(
        {
            "operation": "edit",
            "path": str(path),
            "old_string": "old text",
            "new_string": "new text",
        }
    )

    assert result.success is True
    assert path.read_text(encoding="utf-8") == "new text here"


@pytest.mark.asyncio
async def test_edit_file_replaces_only_first_matching_occurrence(tmp_dir: Path) -> None:
    path = tmp_dir / "edit.txt"
    path.write_text("old old old", encoding="utf-8")

    result = await FilesystemTool().execute(
        {
            "operation": "edit",
            "path": str(path),
            "old_string": "old",
            "new_string": "new",
        }
    )

    assert result.success is True
    assert path.read_text(encoding="utf-8") == "new old old"


@pytest.mark.asyncio
async def test_delete_file(tmp_dir: Path) -> None:
    path = tmp_dir / "delete.txt"
    path.write_text("delete me", encoding="utf-8")

    result = await FilesystemTool().execute({"operation": "delete", "path": str(path)})

    assert result.success is True
    assert not path.exists()


@pytest.mark.asyncio
async def test_invalid_operation() -> None:
    result = await FilesystemTool().execute({"operation": "invalid", "path": "/tmp/x"})

    assert result.success is False


@pytest.mark.asyncio
async def test_edit_fails_when_old_text_missing(tmp_dir: Path) -> None:
    path = tmp_dir / "edit.txt"
    path.write_text("original", encoding="utf-8")

    result = await FilesystemTool().execute(
        {
            "operation": "edit",
            "path": str(path),
            "old_string": "missing",
            "new_string": "replacement",
        }
    )

    assert result.success is False
    assert "not found" in result.error.lower()


def test_derive_operations_returns_expected_values() -> None:
    assert derive_operations({"operation": "read"}) == [FilesystemOperation.READ]
    assert derive_operations({"operation": "write"}) == [FilesystemOperation.WRITE]
    assert derive_operations({"operation": "edit"}) == [
        FilesystemOperation.READ,
        FilesystemOperation.WRITE,
    ]
    assert derive_operations({"operation": "delete"}) == [FilesystemOperation.DELETE]
    assert derive_operations({"operation": "invalid"}) == []


def test_derive_operations_does_not_reference_nonexistent_edit_enum_member() -> None:
    assert "FilesystemOperation.EDIT" not in inspect.getsource(derive_operations)
