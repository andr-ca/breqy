import pytest
from pathlib import Path
from pydantic import BaseModel
from system.orchestrator.artifact_store import ArtifactStore


class _SampleModel(BaseModel):
    value: str
    count: int = 0


def test_write_and_read_model(tmp_path):
    store = ArtifactStore(base=tmp_path)
    obj = _SampleModel(value="hello", count=42)
    path = store.write("BRQ-1", "doer-report", obj)
    assert path.exists()
    result = store.read("BRQ-1", "doer-report", _SampleModel)
    assert result is not None
    assert result.value == "hello"
    assert result.count == 42


def test_write_and_read_text(tmp_path):
    store = ArtifactStore(base=tmp_path)
    store.write("BRQ-1", "lessons-learned", "# Lessons\n- Use mocks carefully")
    text = store.read_text("BRQ-1", "lessons-learned")
    assert text is not None
    assert "Use mocks carefully" in text


def test_exists(tmp_path):
    store = ArtifactStore(base=tmp_path)
    assert not store.exists("BRQ-1", "doer-report")
    store.write("BRQ-1", "doer-report", _SampleModel(value="x"))
    assert store.exists("BRQ-1", "doer-report")


def test_read_missing_returns_none(tmp_path):
    store = ArtifactStore(base=tmp_path)
    assert store.read("BRQ-1", "doer-report", _SampleModel) is None
    assert store.read_text("BRQ-1", "lessons-learned") is None


def test_write_creates_task_directory(tmp_path):
    store = ArtifactStore(base=tmp_path)
    store.write("BRQ-99", "test-artifact", _SampleModel(value="y"))
    assert (tmp_path / "BRQ-99").is_dir()


def test_model_stored_as_json(tmp_path):
    store = ArtifactStore(base=tmp_path)
    obj = _SampleModel(value="test")
    path = store.write("BRQ-1", "doer-report", obj)
    assert path.suffix == ".json"
