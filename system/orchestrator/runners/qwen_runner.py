"""
Qwen Code Runner for Breqy Orchestrator.

This module provides the Qwen Code integration for the multi-agent orchestration system.
Qwen Code is invoked as a role-specific agent (Orchestrator, Doer, Checker, Tester, etc.)
and produces structured artifacts following the delivery workflow.

See docs/ai_delivery_approach_v_1.md for full workflow documentation.
"""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import AgentRunner, AgentResult, RunnerConfig


@dataclass
class QwenRunnerConfig(RunnerConfig):
    """Configuration for Qwen Code runner.

    Attributes:
        instructions: List of instruction files Qwen should read before work.
        role: The delivery role (orchestrator, doer, checker, tester, planner, lessons).
        resume_prompt: Prompt used when resuming after interruption.
    """

    instructions: list[str] = field(default_factory=list)
    role: str = "doer"
    resume_prompt: str | None = None


class QwenRunner(AgentRunner):
    """Runner for Qwen Code agent.

    Qwen Code is invoked via CLI with specific prompts and instruction files.
    The runner manages execution, captures output, and produces structured results.

    Example usage:
        config = QwenRunnerConfig(
            name="qwen-doer",
            project_dir=Path("."),
            prompt="Implement feature X with TDD",
            instructions=["agents/my-instructions.md"],
            role="doer",
        )
        runner = QwenRunner(config)
        result = await runner.run()
    """

    def __init__(self, config: QwenRunnerConfig) -> None:
        """Initialize Qwen runner.

        Args:
            config: Runner configuration including prompt, instructions, and role.
        """
        super().__init__(config)
        self.config = config
        self._process: asyncio.subprocess.Process | None = None

    async def run(self) -> AgentResult:
        """Execute Qwen Code with the configured prompt.

        Returns:
            AgentResult with execution status, output, and artifact paths.
        """
        self.logger.info(f"Starting Qwen Code runner for role: {self.config.role}")
        self.logger.info(f"Project directory: {self.config.project_dir}")

        # Build Qwen command
        cmd = self._build_command()

        try:
            # Execute Qwen Code
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.config.project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await self._process.communicate()

            # Parse output
            output = stdout.decode() if stdout else ""
            errors = stderr.decode() if stderr else ""

            # Extract artifact paths from output
            artifacts = self._extract_artifacts(output)

            return AgentResult(
                success=self._process.returncode == 0,
                output=output,
                errors=errors,
                artifacts=artifacts,
                metadata={
                    "role": self.config.role,
                    "instructions": self.config.instructions,
                    "return_code": self._process.returncode,
                },
            )

        except Exception as e:
            self.logger.error(f"Qwen runner failed: {e}")
            return AgentResult(
                success=False,
                output="",
                errors=str(e),
                artifacts={},
                metadata={"role": self.config.role, "error": str(e)},
            )

    async def stop(self) -> None:
        """Stop the running Qwen process if active."""
        if self._process and self._process.returncode is None:
            self.logger.info("Stopping Qwen process...")
            self._process.terminate()
            await self._process.wait()

    def _build_command(self) -> list[str]:
        """Build the Qwen Code CLI command.

        Returns:
            List of command arguments for subprocess execution.
        """
        cmd = ["qwen-code"]

        # Add project directory
        cmd.extend(["--project-dir", str(self.config.project_dir)])

        # Add role-specific prompt
        prompt = self._build_role_prompt()
        cmd.extend(["--prompt", prompt])

        # Add instruction files
        for instruction_file in self.config.instructions:
            cmd.extend(["--instruction", instruction_file])

        # Add permission mode if configured
        if self.config.permission_mode:
            cmd.extend(["--permission-mode", self.config.permission_mode])

        return cmd

    def _build_role_prompt(self) -> str:
        """Build the prompt based on the assigned role.

        Returns:
            Role-specific prompt string.
        """
        base_prompt = self.config.prompt

        # Role-specific additions
        role_context = {
            "orchestrator": "Manage workflow state, route tasks, enforce gates.",
            "doer": "Implement with TDD: RED (test first), GREEN (minimal code), REFACTOR.",
            "checker": "Review independently, produce structured findings.",
            "tester": "Execute validation, capture evidence, produce test reports.",
            "planner": "Shape tasks, define acceptance criteria, identify dependencies.",
            "lessons": "Capture lessons learned, propose instruction updates.",
        }

        role_instruction = role_context.get(self.config.role, "")
        if role_instruction:
            base_prompt = f"{base_prompt}\n\n{role_instruction}"

        return base_prompt

    def _extract_artifacts(self, output: str) -> dict[str, Any]:
        """Extract artifact paths from Qwen output.

        Parses output for standard artifact locations:
        - Plan files: agents/docs/feat-<name>.jsonl
        - Review files: docs/operational/reviews/<task-name>.<timestamp>.md
        - Test files: docs/operational/tests/<task-name>.<timestamp>.md
        - Lessons: .breqy/lessons/<task-id>.yaml

        Args:
            output: Raw output from Qwen Code execution.

        Returns:
            Dictionary mapping artifact types to file paths.
        """
        artifacts: dict[str, Any] = {
            "plan_files": [],
            "review_files": [],
            "test_files": [],
            "lessons_files": [],
            "changed_files": [],
        }

        # Parse output for artifact paths
        # This is a simplified parser - production implementation should be more robust
        lines = output.split("\n")
        for line in lines:
            line = line.strip()

            if "agents/docs/feat-" in line and line.endswith(".jsonl"):
                artifacts["plan_files"].append(line)
            elif "docs/operational/reviews/" in line and line.endswith(".md"):
                artifacts["review_files"].append(line)
            elif "docs/operational/tests/" in line and line.endswith(".md"):
                artifacts["test_files"].append(line)
            elif ".breqy/lessons/" in line and line.endswith(".yaml"):
                artifacts["lessons_files"].append(line)
            elif line.startswith("Modified:") or line.startswith("Created:"):
                artifacts["changed_files"].append(line.split(":", 1)[1].strip())

        return artifacts


def create_qwen_runner(
    name: str,
    role: str,
    project_dir: Path | str = ".",
    prompt: str = "",
    instructions: list[str] | None = None,
    permission_mode: str = "acceptEdits",
) -> QwenRunner:
    """Factory function to create a Qwen runner.

    Args:
        name: Runner name (e.g., "qwen-doer", "qwen-checker").
        role: Delivery role (orchestrator, doer, checker, tester, planner, lessons).
        project_dir: Project directory path.
        prompt: Base prompt for the agent.
        instructions: List of instruction file paths.
        permission_mode: Permission mode for Qwen Code.

    Returns:
        Configured QwenRunner instance.
    """
    config = QwenRunnerConfig(
        name=name,
        project_dir=Path(project_dir) if isinstance(project_dir, str) else project_dir,
        prompt=prompt,
        instructions=instructions or [],
        role=role,
        permission_mode=permission_mode,
    )
    return QwenRunner(config)
