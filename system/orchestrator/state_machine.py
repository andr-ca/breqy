"""TaskState enum, Task model, and StateMachine ABC."""
from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from pydantic import BaseModel


class TaskState(str, Enum):
    NEW = "NEW"
    READY_FOR_SHAPING = "READY_FOR_SHAPING"
    READY_FOR_BRANCH_PREP = "READY_FOR_BRANCH_PREP"
    READY_FOR_TEST_CASE_DESIGN = "READY_FOR_TEST_CASE_DESIGN"
    READY_FOR_DOER = "READY_FOR_DOER"
    DOER_IN_PROGRESS = "DOER_IN_PROGRESS"
    READY_FOR_CHECKER = "READY_FOR_CHECKER"
    CHECK_FAILED = "CHECK_FAILED"
    READY_FOR_TESTER = "READY_FOR_TESTER"
    TEST_FAILED = "TEST_FAILED"
    READY_FOR_QA_AUTOMATION = "READY_FOR_QA_AUTOMATION"
    QA_FAILED = "QA_FAILED"
    READY_FOR_MERGE_REVIEW = "READY_FOR_MERGE_REVIEW"
    READY_FOR_LESSONS = "READY_FOR_LESSONS"
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    RETRY_PENDING = "RETRY_PENDING"


class Task(BaseModel):
    task_id: str
    state: TaskState
    rework_count: int = 0
    retry_count: int = 0
    failure_source: str | None = None
    session_id: str | None = None
    branch: str | None = None
    github_issue_number: int | None = None
    pr_url: str | None = None


class StateMachine(ABC):
    @abstractmethod
    def can_transition(self, task: Task, to: TaskState) -> bool:
        """Return True if the guard-gated transition is allowed given task state.
        Note: READY_FOR_MERGE_REVIEW → READY_FOR_LESSONS additionally requires
        CI green + merge-readiness artifact — these external gates are checked by
        the orchestrator loop BEFORE calling transition(), not inside can_transition().
        """
        ...

    @abstractmethod
    def transition(self, task: Task, to: TaskState) -> Task:
        """Apply the transition and return a new Task. Increments rework_count or
        retry_count as appropriate for rework/retry transitions."""
        ...

    @abstractmethod
    def force_block(self, task: Task, notes: str = "") -> Task:
        """Emergency/manual block — moves any non-terminal task to BLOCKED
        unconditionally. Use for operator intervention, not guard logic."""
        ...
