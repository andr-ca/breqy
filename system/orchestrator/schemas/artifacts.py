from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ParsedOutput(BaseModel):
    status: Literal["pass", "fail"]
    artifact_paths: list[str]
    failure_source: str | None = None
    session_id: str | None = None
    notes: str = ""


class ReviewArtifact(BaseModel):
    status: Literal["pass", "fail"]
    findings: list[str]
    summary: str = ""


class TestArtifact(BaseModel):
    status: Literal["pass", "fail"]
    tests_run: int = 0
    tests_failed: int = 0
    output: str = ""


class QaArtifact(BaseModel):
    status: Literal["pass", "fail"]
    failure_source: (
        Literal["broken_implementation", "broken_automation", "ambiguous_criteria"] | None
    ) = None
    output: str = ""


class LessonsArtifact(BaseModel):
    task_id: str
    lessons: list[str]
    instruction_update_proposed: bool = False


class MergeReadinessArtifact(BaseModel):
    task_id: str
    checked_at: str
    artifacts_present: list[str]
    branch: str
    merge_target: str
    ci_conclusion: str
    branch_is_current: bool
    verdict: Literal["pass", "fail"]
    notes: str = ""
