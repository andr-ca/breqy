import pytest
import yaml
from pathlib import Path
from system.orchestrator.task_loader import TaskLoader
from system.orchestrator.local_task_loader import LocalYamlTaskLoader


SAMPLE_TASK = {
    "task_id": "BRQ-1",
    "title": "Test task",
    "task_type": "feature",
    "component": "backend",
}


def test_local_loader_loads_yaml_files(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "BRQ-1.yaml").write_text(yaml.dump(SAMPLE_TASK))
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    tasks = loader.load_pending()
    assert len(tasks) == 1
    assert tasks[0].task_id == "BRQ-1"


def test_local_loader_empty_dir(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    assert loader.load_pending() == []


def test_local_loader_skips_invalid_yaml(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "bad.yaml").write_text("not: valid: yaml: {{{")
    (tasks_dir / "good.yaml").write_text(yaml.dump(SAMPLE_TASK))
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    tasks = loader.load_pending()
    assert len(tasks) == 1


def test_local_loader_multiple_files(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    for i in range(3):
        t = {**SAMPLE_TASK, "task_id": f"BRQ-{i}"}
        (tasks_dir / f"BRQ-{i}.yaml").write_text(yaml.dump(t))
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    assert len(loader.load_pending()) == 3


def test_task_loader_is_abstract():
    with pytest.raises(TypeError):
        TaskLoader()
