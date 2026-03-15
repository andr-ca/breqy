import textwrap

import pytest
import yaml

from system.orchestrator.agent_adapters.checker import CheckerAdapter
from system.orchestrator.agent_adapters.doer import DoerAdapter
from system.orchestrator.config import OrchestratorConfig
from system.orchestrator.router import Router
from system.orchestrator.runners.claude_runner import ClaudeRunner
from system.orchestrator.runners.codex_runner import CodexRunner
from system.orchestrator.runners.gemini_runner import GeminiRunner
from system.orchestrator.runners.qwen_runner import QwenRunner

CONFIG_YAML = textwrap.dedent("""\
    github:
      repo: owner/repo
    agent_defaults:
      planner: claude
      doer: claude
      checker: codex
      tester: gemini
      qa_automation: claude
      lessons: claude
    routing_rules:
      feature:
        backend:
          doer: qwen
          checker: codex
      refactor:
        service:
          doer: claude
""")


@pytest.fixture
def router():
    cfg = OrchestratorConfig.model_validate(yaml.safe_load(CONFIG_YAML))
    return Router(config=cfg)


def test_router_feature_backend_doer_is_qwen(router):
    runner, adapter = router.resolve("feature", "backend", "doer")
    assert isinstance(runner, QwenRunner)
    assert isinstance(adapter, DoerAdapter)


def test_router_feature_backend_checker_is_codex(router):
    runner, adapter = router.resolve("feature", "backend", "checker")
    assert isinstance(runner, CodexRunner)
    assert isinstance(adapter, CheckerAdapter)


def test_router_falls_back_to_defaults(router):
    # "bug" not in routing_rules → falls back to agent_defaults
    runner, adapter = router.resolve("bug", "frontend", "doer")
    assert isinstance(runner, ClaudeRunner)   # agent_defaults.doer = claude


def test_router_tester_from_defaults(router):
    runner, _ = router.resolve("feature", "unknown-component", "tester")
    assert isinstance(runner, GeminiRunner)   # agent_defaults.tester = gemini


def test_router_unknown_role_raises(router):
    with pytest.raises(ValueError, match="Unknown role"):
        router.resolve("feature", "backend", "unknown_role")
