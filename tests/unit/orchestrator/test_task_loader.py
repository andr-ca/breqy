
import json
from unittest.mock import MagicMock, patch

import pytest
import yaml

from system.orchestrator.github_task_loader import GitHubTaskLoader
from system.orchestrator.local_task_loader import LocalYamlTaskLoader
from system.orchestrator.task_loader import CompositeTaskLoader, TaskLoader

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
    assert len(tasks) == 1   # bad file skipped


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


ISSUE_BODY = """
Some intro text.

```yaml
task_id: BRQ-144
title: Session resume flow
task_type: feature
component: backend
```

More text.
"""

ISSUE_JSON = json.dumps([{
    "number": 144,
    "title": "Session resume flow",
    "body": ISSUE_BODY,
    "labels": [{"name": "orchestrator:managed"}],
}])


def test_github_loader_parses_issue_body():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=ISSUE_JSON, stderr="")
        loader = GitHubTaskLoader(repo="owner/repo", managed_label="orchestrator:managed")
        tasks = loader.load_pending()
    assert len(tasks) == 1
    assert tasks[0].task_id == "BRQ-144"
    assert tasks[0].github_issue_number == 144


def test_github_loader_skips_issues_without_yaml_block():
    no_yaml = json.dumps([{
        "number": 1,
        "title": "No YAML",
        "body": "Just plain text",
        "labels": [{"name": "orchestrator:managed"}],
    }])
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=no_yaml, stderr="")
        loader = GitHubTaskLoader(repo="owner/repo", managed_label="orchestrator:managed")
        assert loader.load_pending() == []


def test_composite_github_primary(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    # Same task_id in both — GitHub takes priority
    (tasks_dir / "BRQ-144.yaml").write_text(yaml.dump({
        **SAMPLE_TASK, "task_id": "BRQ-144", "title": "Local version"
    }))
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=ISSUE_JSON, stderr="")
        composite = CompositeTaskLoader(
            github=GitHubTaskLoader(repo="owner/repo", managed_label="orchestrator:managed"),
            local=LocalYamlTaskLoader(tasks_dir=tasks_dir),
        )
        tasks = composite.load_pending()
    # Only one BRQ-144 — GitHub version wins
    brq_144 = [t for t in tasks if t.task_id == "BRQ-144"]
    assert len(brq_144) == 1
    assert brq_144[0].github_issue_number == 144
