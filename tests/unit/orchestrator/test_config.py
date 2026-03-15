import textwrap
from pathlib import Path
import pytest
from system.orchestrator.config import OrchestratorConfig, load_config


MINIMAL_YAML = textwrap.dedent("""\
    github:
      repo: owner/repo

    orchestrator:
      poll_interval_seconds: 30
      max_rework_loops: 3
      max_retries: 3

    agent_defaults:
      doer: claude
      checker: codex
      tester: gemini
      lessons: claude
""")

ROUTING_YAML = textwrap.dedent("""\
    github:
      repo: owner/repo

    orchestrator:
      max_rework_loops: 3
      max_retries: 3

    agent_defaults:
      doer: claude

    routing_rules:
      feature:
        backend:
          doer: qwen
          checker: codex
""")


def test_load_config_minimal(tmp_path):
    cfg_file = tmp_path / "orchestrator.yaml"
    cfg_file.write_text(MINIMAL_YAML)
    cfg = load_config(cfg_file)
    assert cfg.github.repo == "owner/repo"
    assert cfg.orchestrator.max_rework_loops == 3
    assert cfg.agent_defaults["doer"] == "claude"


def test_config_github_defaults(tmp_path):
    cfg_file = tmp_path / "orchestrator.yaml"
    cfg_file.write_text(MINIMAL_YAML)
    cfg = load_config(cfg_file)
    assert cfg.github.ci_timeout_minutes == 30
    assert cfg.github.ci_poll_interval_seconds == 60
    assert cfg.github.managed_label == "orchestrator:managed"


def test_config_orchestrator_defaults(tmp_path):
    cfg_file = tmp_path / "orchestrator.yaml"
    cfg_file.write_text(MINIMAL_YAML)
    cfg = load_config(cfg_file)
    assert cfg.orchestrator.branch_stale_days == 3
    assert cfg.orchestrator.artifact_base == "ai-artifacts"


def test_config_routing_rules(tmp_path):
    cfg_file = tmp_path / "orchestrator.yaml"
    cfg_file.write_text(ROUTING_YAML)
    cfg = load_config(cfg_file)
    assert cfg.routing_rules["feature"]["backend"]["doer"] == "qwen"
    assert cfg.routing_rules["feature"]["backend"]["checker"] == "codex"


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/orchestrator.yaml"))
