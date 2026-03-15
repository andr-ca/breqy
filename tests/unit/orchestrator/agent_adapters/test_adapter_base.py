
import pytest

from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext
from system.orchestrator.schemas.task_envelope import TaskEnvelope


def test_agent_adapter_is_abstract():
    with pytest.raises(TypeError):
        AgentAdapter()


def test_task_context():
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    ctx = TaskContext(task=env, prior_artifacts={}, rework_count=0)
    assert ctx.task.task_id == "BRQ-1"
    assert ctx.prior_artifacts == {}


def test_adapter_loads_prompt_template(tmp_path):
    prompt_file = tmp_path / "doer.md"
    prompt_file.write_text("# Doer Prompt\nDo the work.")

    class ConcreteAdapter(AgentAdapter):
        role = "doer"
        prompts_dir = tmp_path

        def build_prompt(self, task, context):
            return self._load_template() + f"\n## Task\n{task.title}"

        def parse_output(self, result):
            from system.orchestrator.schemas.artifacts import ParsedOutput
            return ParsedOutput(status="pass", artifact_paths=[])

    adapter = ConcreteAdapter()
    env = TaskEnvelope(task_id="BRQ-1", title="My task", task_type="feature", component="backend")
    ctx = TaskContext(task=env, prior_artifacts={}, rework_count=0)
    prompt = adapter.build_prompt(env, ctx)
    assert "Doer Prompt" in prompt
    assert "My task" in prompt
