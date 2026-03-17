"""Tests for TaskState enum and StateMachine ABC."""
import pytest
from system.orchestrator.state_machine import TaskState, StateMachine, Task


def test_task_state_count():
    # Spec heading says "17 states" but enumerates 18 including RETRY_PENDING.
    # We implement all 18 as listed in the spec's transition table.
    states = list(TaskState)
    assert len(states) == 18


def test_task_state_values():
    assert TaskState.NEW == "NEW"
    assert TaskState.DONE == "DONE"
    assert TaskState.BLOCKED == "BLOCKED"
    assert TaskState.RETRY_PENDING == "RETRY_PENDING"
    assert TaskState.QA_FAILED == "QA_FAILED"
    assert TaskState.READY_FOR_MERGE_REVIEW == "READY_FOR_MERGE_REVIEW"


def test_task_model_defaults():
    t = Task(task_id="BRQ-1", state=TaskState.NEW)
    assert t.rework_count == 0
    assert t.retry_count == 0
    assert t.failure_source is None
    assert t.branch is None


def test_state_machine_is_abstract():
    with pytest.raises(TypeError):
        StateMachine()


from system.orchestrator.state_machine import ConcreteStateMachine, InvalidTransitionError


@pytest.fixture
def sm():
    return ConcreteStateMachine(max_rework_loops=3, max_retries=3)


@pytest.fixture
def new_task():
    return Task(task_id="BRQ-1", state=TaskState.NEW)


# --- Happy path transitions ---

def test_new_to_shaping_allowed(sm, new_task):
    assert sm.can_transition(new_task, TaskState.READY_FOR_SHAPING)


def test_transition_new_to_shaping(sm, new_task):
    result = sm.transition(new_task, TaskState.READY_FOR_SHAPING)
    assert result.state == TaskState.READY_FOR_SHAPING


def test_full_happy_path_transitions(sm):
    """Verify each consecutive normal-path transition is allowed."""
    happy_path = [
        TaskState.NEW,
        TaskState.READY_FOR_SHAPING,
        TaskState.READY_FOR_BRANCH_PREP,
        TaskState.READY_FOR_TEST_CASE_DESIGN,
        TaskState.READY_FOR_DOER,
        TaskState.DOER_IN_PROGRESS,
        TaskState.READY_FOR_CHECKER,
        TaskState.READY_FOR_TESTER,
        TaskState.READY_FOR_QA_AUTOMATION,
        TaskState.READY_FOR_MERGE_REVIEW,
        TaskState.READY_FOR_LESSONS,
        TaskState.READY_FOR_HUMAN_REVIEW,
        TaskState.DONE,
    ]
    task = Task(task_id="BRQ-1", state=TaskState.NEW)
    for to_state in happy_path[1:]:
        assert sm.can_transition(task, to_state), f"Expected {task.state} → {to_state} to be allowed"
        task = sm.transition(task, to_state)
    assert task.state == TaskState.DONE


# --- Invalid transition ---

def test_invalid_transition_raises(sm, new_task):
    with pytest.raises(InvalidTransitionError):
        sm.transition(new_task, TaskState.DONE)


# --- Rework: CHECK_FAILED ---

def test_check_failed_to_doer_within_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=1)
    assert sm.can_transition(task, TaskState.READY_FOR_DOER)
    result = sm.transition(task, TaskState.READY_FOR_DOER)
    assert result.state == TaskState.READY_FOR_DOER
    assert result.rework_count == 2   # incremented


def test_check_failed_to_blocked_not_allowed_within_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=1)
    assert not sm.can_transition(task, TaskState.BLOCKED)


def test_check_failed_to_blocked_at_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=3)
    assert not sm.can_transition(task, TaskState.READY_FOR_DOER)
    assert sm.can_transition(task, TaskState.BLOCKED)


# --- Rework: TEST_FAILED ---

def test_test_failed_to_doer_within_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.TEST_FAILED, rework_count=0)
    assert sm.can_transition(task, TaskState.READY_FOR_DOER)
    result = sm.transition(task, TaskState.READY_FOR_DOER)
    assert result.rework_count == 1   # incremented


def test_test_failed_to_blocked_at_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.TEST_FAILED, rework_count=3)
    assert not sm.can_transition(task, TaskState.READY_FOR_DOER)
    assert sm.can_transition(task, TaskState.BLOCKED)


# --- Rework: QA_FAILED ---

def test_qa_failed_broken_impl_routes_to_doer(sm):
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                failure_source="broken_implementation", rework_count=0)
    assert sm.can_transition(task, TaskState.READY_FOR_DOER)
    assert not sm.can_transition(task, TaskState.READY_FOR_QA_AUTOMATION)
    result = sm.transition(task, TaskState.READY_FOR_DOER)
    assert result.rework_count == 1


def test_qa_failed_broken_automation_routes_to_qa(sm):
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                failure_source="broken_automation", rework_count=0)
    assert sm.can_transition(task, TaskState.READY_FOR_QA_AUTOMATION)
    assert not sm.can_transition(task, TaskState.READY_FOR_DOER)
    result = sm.transition(task, TaskState.READY_FOR_QA_AUTOMATION)
    assert result.rework_count == 1


def test_qa_failed_ambiguous_always_blocks(sm):
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                failure_source="ambiguous_criteria", rework_count=0)
    assert not sm.can_transition(task, TaskState.READY_FOR_DOER)
    assert not sm.can_transition(task, TaskState.READY_FOR_QA_AUTOMATION)
    assert sm.can_transition(task, TaskState.BLOCKED)


def test_qa_failed_blocked_not_allowed_within_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                failure_source="broken_implementation", rework_count=1)
    assert not sm.can_transition(task, TaskState.BLOCKED)


# --- DOER_IN_PROGRESS error paths ---

def test_doer_in_progress_to_retry_pending(sm):
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    assert sm.can_transition(task, TaskState.RETRY_PENDING)
    result = sm.transition(task, TaskState.RETRY_PENDING)
    assert result.state == TaskState.RETRY_PENDING
    assert result.retry_count == 0   # not incremented here; incremented on exit from RETRY_PENDING


def test_doer_in_progress_to_blocked_only_at_retry_limit(sm):
    task_within = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS, retry_count=1)
    assert not sm.can_transition(task_within, TaskState.BLOCKED)
    task_at_limit = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS, retry_count=3)
    assert sm.can_transition(task_at_limit, TaskState.BLOCKED)


# --- Retry ---

def test_retry_pending_to_doer_within_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.RETRY_PENDING, retry_count=1)
    assert sm.can_transition(task, TaskState.DOER_IN_PROGRESS)
    result = sm.transition(task, TaskState.DOER_IN_PROGRESS)
    assert result.retry_count == 2   # incremented


def test_retry_pending_to_blocked_at_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.RETRY_PENDING, retry_count=3)
    assert not sm.can_transition(task, TaskState.DOER_IN_PROGRESS)
    assert sm.can_transition(task, TaskState.BLOCKED)


# --- Force block ---

def test_force_block_from_any_state(sm):
    for state in TaskState:
        if state in (TaskState.DONE, TaskState.BLOCKED):
            continue
        task = Task(task_id="BRQ-1", state=state)
        result = sm.force_block(task, notes="operator override")
        assert result.state == TaskState.BLOCKED


def test_force_block_no_effect_on_done(sm):
    task = Task(task_id="BRQ-1", state=TaskState.DONE)
    result = sm.force_block(task)
    assert result.state == TaskState.DONE   # DONE is terminal, no-op
