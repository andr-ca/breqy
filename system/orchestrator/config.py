from __future__ import annotations
from pathlib import Path
import yaml
from pydantic import BaseModel


class GitHubConfig(BaseModel):
    repo: str
    managed_label: str = "orchestrator:managed"
    ci_timeout_minutes: int = 30
    ci_poll_interval_seconds: int = 60


class OrchestratorSettings(BaseModel):
    poll_interval_seconds: int = 30
    max_rework_loops: int = 3
    max_retries: int = 3
    retry_backoff_seconds: int = 60
    artifact_base: str = "ai-artifacts"
    event_log: str = ".breqy/orchestrator/events.jsonl"
    runtime_state: str = ".breqy/orchestrator/runtime-state.yaml"
    task_fallback_dir: str = "system/orchestrator/tasks"
    branch_stale_days: int = 3


class OrchestratorConfig(BaseModel):
    github: GitHubConfig
    orchestrator: OrchestratorSettings = OrchestratorSettings()
    routing_rules: dict[str, dict[str, dict[str, str]]] = {}
    agent_defaults: dict[str, str] = {}


def load_config(path: Path) -> OrchestratorConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    data = yaml.safe_load(path.read_text())
    return OrchestratorConfig.model_validate(data)
