from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel


class TaskState(StrEnum):
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


class InvalidTransitionError(Exception):
    pass


# Structural transitions (no guard counters needed).
# BLOCKED is NOT in these tables — it is guard-gated per state.
_ALLOWED: dict[TaskState, set[TaskState]] = {
    TaskState.NEW: {TaskState.READY_FOR_SHAPING},
    TaskState.READY_FOR_SHAPING: {TaskState.READY_FOR_BRANCH_PREP},
    TaskState.READY_FOR_BRANCH_PREP: {TaskState.READY_FOR_TEST_CASE_DESIGN},
    TaskState.READY_FOR_TEST_CASE_DESIGN: {TaskState.READY_FOR_DOER},
    TaskState.READY_FOR_DOER: {TaskState.DOER_IN_PROGRESS},
    TaskState.DOER_IN_PROGRESS: {TaskState.READY_FOR_CHECKER, TaskState.RETRY_PENDING},
    TaskState.READY_FOR_CHECKER: {TaskState.READY_FOR_TESTER, TaskState.CHECK_FAILED},
    TaskState.READY_FOR_TESTER: {TaskState.READY_FOR_QA_AUTOMATION, TaskState.TEST_FAILED},
    TaskState.READY_FOR_QA_AUTOMATION: {TaskState.READY_FOR_MERGE_REVIEW, TaskState.QA_FAILED},
    # READY_FOR_MERGE_REVIEW → READY_FOR_LESSONS is structurally allowed here.
    # The CI green + merge-readiness artifact gates are checked by the orchestrator
    # loop BEFORE calling transition() — they are not enforced inside can_transition().
    TaskState.READY_FOR_MERGE_REVIEW: {TaskState.READY_FOR_LESSONS},
    TaskState.READY_FOR_LESSONS: {TaskState.READY_FOR_HUMAN_REVIEW},
    TaskState.READY_FOR_HUMAN_REVIEW: {TaskState.DONE},
    TaskState.BLOCKED: set(),
    TaskState.DONE: set(),
}

# States where BLOCKED is guard-gated (only when limit exceeded)
_BLOCKED_ON_LIMIT = {
    TaskState.DOER_IN_PROGRESS,   # retry_count >= max_retries
    TaskState.CHECK_FAILED,        # rework_count >= max_rework_loops
    TaskState.TEST_FAILED,         # rework_count >= max_rework_loops
    TaskState.QA_FAILED,           # rework_count >= max_rework_loops OR ambiguous_criteria
    TaskState.RETRY_PENDING,       # retry_count >= max_retries
}

# States where BLOCKED is always allowed (manual operator block, no guard required)
_BLOCKED_UNCONDITIONAL = set(TaskState) - _BLOCKED_ON_LIMIT - {TaskState.BLOCKED, TaskState.DONE}


class ConcreteStateMachine(StateMachine):
    def __init__(self, max_rework_loops: int = 3, max_retries: int = 3) -> None:
        self.max_rework_loops = max_rework_loops
        self.max_retries = max_retries

    def can_transition(self, task: Task, to: TaskState) -> bool:
        # --- BLOCKED rules (guard-gated per state) ---
        if to == TaskState.BLOCKED:
            if task.state in _BLOCKED_UNCONDITIONAL:
                return True
            if task.state == TaskState.DOER_IN_PROGRESS:
                return task.retry_count >= self.max_retries
            if task.state == TaskState.CHECK_FAILED:
                return task.rework_count >= self.max_rework_loops
            if task.state == TaskState.TEST_FAILED:
                return task.rework_count >= self.max_rework_loops
            if task.state == TaskState.QA_FAILED:
                return (
                    task.failure_source == "ambiguous_criteria"
                    or task.rework_count >= self.max_rework_loops
                )
            if task.state == TaskState.RETRY_PENDING:
                return task.retry_count >= self.max_retries
            return False

        # --- Rework loop rules ---
        if task.state in (TaskState.CHECK_FAILED, TaskState.TEST_FAILED):
            if to == TaskState.READY_FOR_DOER:
                return task.rework_count < self.max_rework_loops
            return False

        if task.state == TaskState.QA_FAILED:
            if to == TaskState.READY_FOR_DOER:
                return (
                    task.failure_source == "broken_implementation"
                    and task.rework_count < self.max_rework_loops
                )
            if to == TaskState.READY_FOR_QA_AUTOMATION:
                return (
                    task.failure_source == "broken_automation"
                    and task.rework_count < self.max_rework_loops
                )
            return False

        if task.state == TaskState.RETRY_PENDING:
            if to == TaskState.DOER_IN_PROGRESS:
                return task.retry_count < self.max_retries
            return False

        # --- Structural transitions ---
        return to in _ALLOWED.get(task.state, set())

    def transition(self, task: Task, to: TaskState) -> Task:
        if not self.can_transition(task, to):
            raise InvalidTransitionError(
                f"Cannot transition {task.task_id} from {task.state} to {to}"
            )
        updates: dict = {"state": to}
        # Increment rework_count on rework transitions
        rework_states = (TaskState.CHECK_FAILED, TaskState.TEST_FAILED)
        if task.state in rework_states and to == TaskState.READY_FOR_DOER:
            updates["rework_count"] = task.rework_count + 1
        qa_rework_targets = (TaskState.READY_FOR_DOER, TaskState.READY_FOR_QA_AUTOMATION)
        if task.state == TaskState.QA_FAILED and to in qa_rework_targets:
            updates["rework_count"] = task.rework_count + 1
        # Increment retry_count on retry transition
        if task.state == TaskState.RETRY_PENDING and to == TaskState.DOER_IN_PROGRESS:
            updates["retry_count"] = task.retry_count + 1
        return task.model_copy(update=updates)

    def force_block(self, task: Task, notes: str = "") -> Task:
        """Unconditional operator block. DONE is terminal — no-op."""
        if task.state in (TaskState.DONE, TaskState.BLOCKED):
            return task
        return task.model_copy(update={"state": TaskState.BLOCKED})
