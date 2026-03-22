# Design: Human Review Browser Interface

**Date:** 2026-03-21
**Scope:** Slice 1
**Status:** Approved

---

## Overview

When a task reaches `READY_FOR_HUMAN_REVIEW`, the orchestrator generates a full-context HTML review page, starts a local HTTP server to capture the human's decision, and opens the system browser. The orchestrator loop remains non-blocking — it polls for the decision on each tick and processes the result when it arrives.

Decisions:
- **Approve** → merge PR, transition to `DONE`
- **Reject** (with optional correction text) → write correction artifact, transition to `READY_FOR_DOER` (rework)

---

## State Machine Changes

**New transition added to `_ALLOWED`:**

```python
TaskState.READY_FOR_HUMAN_REVIEW: {TaskState.DONE, TaskState.READY_FOR_DOER},
```

**Guard clause in `ConcreteStateMachine.can_transition`:**

A new rework-rule block is inserted immediately after the `QA_FAILED` rework block (before the structural `_ALLOWED` lookup), following the same pattern as `CHECK_FAILED`/`TEST_FAILED`:

```python
if task.state == TaskState.READY_FOR_HUMAN_REVIEW:
    if to == TaskState.READY_FOR_DOER:
        return task.rework_count < self.max_rework_loops
    return False
```

This means `can_transition(task, READY_FOR_DOER)` returns `True` only when under the rework limit, and returns `False` for any other target (which then falls through to the `_ALLOWED` structural table).

**`rework_count` increment** is handled automatically by `sm.transition()` — the same rule added there for `CHECK_FAILED`/`TEST_FAILED` is extended to cover `READY_FOR_HUMAN_REVIEW`:

```python
if task.state in (
    TaskState.CHECK_FAILED,
    TaskState.TEST_FAILED,
    TaskState.READY_FOR_HUMAN_REVIEW,
) and to == TaskState.READY_FOR_DOER:
    updates["rework_count"] = task.rework_count + 1
```

The handler does **not** manually increment `rework_count` — it calls `sm.transition()` and the model does it.

**`_BLOCKED_UNCONDITIONAL` / `_BLOCKED_ON_LIMIT` membership:**

`READY_FOR_HUMAN_REVIEW` moves from `_BLOCKED_UNCONDITIONAL` to `_BLOCKED_ON_LIMIT` because it now has a guard-gated rework path. `_force_block` bypasses `can_transition` and still works unconditionally; this change only affects what `can_transition(task, BLOCKED)` returns from this state.

```python
_BLOCKED_ON_LIMIT = {
    TaskState.DOER_IN_PROGRESS,
    TaskState.CHECK_FAILED,
    TaskState.TEST_FAILED,
    TaskState.QA_FAILED,
    TaskState.RETRY_PENDING,
    TaskState.READY_FOR_HUMAN_REVIEW,   # ← added
}
```

**Correction artifact:** correction text is written as `human-review-correction.md` via `ArtifactStore.write(task_id, "human-review-correction", correction_text)` (plain `str` → `.md`). Retrieved later with `ArtifactStore.read_text(task_id, "human-review-correction")`.

---

## Components

### `HumanReviewDecision`

```python
# system/orchestrator/human_review_server.py
from dataclasses import dataclass
from typing import Literal

@dataclass
class HumanReviewDecision:
    decision: Literal["approve", "reject"]
    correction: str  # always str; empty string ("") when approved or no correction given
```

`correction` is `str`, never `None`. The truthiness check `if result.correction:` is intentional — empty string is falsy and means no correction artifact is written.

---

### `HumanReviewServer`

**File:** `system/orchestrator/human_review_server.py`

Wraps Python stdlib `http.server.HTTPServer` in a daemon thread. The HTML is set after the server starts (see Phase 1 ordering below) — no knowledge of artifacts or orchestration state.

```python
class HumanReviewServer:
    def __init__(self, task_id: str, port: int = 0) -> None: ...
    def start(self) -> str: ...          # binds port, starts thread, returns "http://localhost:<port>"
    def set_html(self, html: str) -> None: ...   # called after start(), before browser open
    def get_result(self) -> HumanReviewDecision | None: ...  # non-blocking
    def shutdown(self) -> None: ...      # idempotent
```

- `port=0` → OS assigns a free port (avoids conflicts)
- Serves the HTML on `GET /`
- Accepts `POST /submit` with `application/x-www-form-urlencoded`: `decision=approve|reject&correction=<text>`
- Stores the **first** POST in a `threading.Event` + result slot; ignores subsequent POSTs
- Shuts itself down after the first POST; `shutdown()` is idempotent

---

### `build_review_html`

**File:** `system/orchestrator/human_review_html.py`

Pure function — no I/O, no side effects. Returns a self-contained HTML string (no external assets). All imports are from `system/orchestrator/schemas/artifacts.py` and `system/orchestrator/schemas/task_envelope.py`.

```python
from system.orchestrator.schemas.artifacts import (
    LessonsArtifact, MergeReadinessArtifact, ParsedOutput,
)
from system.orchestrator.schemas.task_envelope import TaskEnvelope

def build_review_html(
    task_id: str,
    env: TaskEnvelope,
    submit_url: str,           # "http://localhost:<port>/submit"
    doer_out: ParsedOutput | None,
    checker_out: ParsedOutput | None,
    test_out: ParsedOutput | None,
    qa_out: ParsedOutput | None,
    merge_readiness: MergeReadinessArtifact | None,
    lessons: LessonsArtifact | None,
) -> str: ...
```

Page layout:

```
┌─────────────────────────────────────────────┐
│ Breqy · Human Review                        │
│ BRQ-42: <title>          [PR link] [branch] │
├─────────────────────────────────────────────┤
│ Acceptance criteria (from envelope)         │
├─────────────────────────────────────────────┤
│ Doer summary | Checker findings             │
│ Tests: 42 run / 0 failed                    │
│ QA: pass   CI: success                      │
├─────────────────────────────────────────────┤
│ Lessons learned (bullet list)              │
├─────────────────────────────────────────────┤
│ ○ Approve    ○ Reject                       │
│ Correction: [_____________________________] │
│             [Submit]                        │
└─────────────────────────────────────────────┘
```

- Correction textarea enabled only when "Reject" is selected (inline JS)
- On submit, POSTs `application/x-www-form-urlencoded` to `submit_url`
- After submit, page replaces body with "Response recorded — you can close this tab."
- `None` artifacts render as "—" or are omitted with a "not available" note

---

### Orchestrator Changes

**File:** `system/orchestrator/orchestrator.py`

#### New field in `__init__`:

```python
self._pending_reviews: dict[str, HumanReviewServer] = {}
```

`_pending_reviews` is **ephemeral in-process state only** — it is not persisted to `StateStore`. This is intentional: if the orchestrator restarts mid-review, the dict is empty and Phase 1 re-runs on the next tick, starting a new server and reopening the browser. No persistence of review state is needed.

#### New `event_type` values (add to schema comment in `events.py`):

- `"human_review_requested"` — emitted when browser is opened, `notes` contains the URL
- `"human_review_browser_failed"` — emitted when `webbrowser.open()` raises, `notes` contains URL + exception

#### `_handle_ready_for_human_review` — two-phase handler:

```python
def _handle_ready_for_human_review(self, task: Task, env: TaskEnvelope) -> Task:
    # Phase 2: check for pending result
    server = self._pending_reviews.get(task.task_id)
    if server is not None:
        result = server.get_result()
        if result is None:
            return task  # still waiting
        # Decision received — clean up
        server.shutdown()
        del self._pending_reviews[task.task_id]
        return self._process_human_review_decision(task, env, result)

    # Phase 1: first tick — start server and open browser
    if self._github_adapter is None:
        return self._force_block(task, notes="github_adapter not configured")
    if task.pr_url is None:
        return self._force_block(task, notes="pr_url not set — cannot merge")

    try:
        review_server = HumanReviewServer(task_id=task.task_id, port=0)
        url = review_server.start()          # port bound here — URL now known
        submit_url = url + "/submit"
    except Exception as exc:
        return self._force_block(task, notes=f"human review server failed to start: {exc}")

    # Build HTML with the known submit_url, then give it to the server
    html = build_review_html(
        task_id=task.task_id, env=env, submit_url=submit_url,
        doer_out=self._artifact_store.read(task.task_id, "doer", ParsedOutput),
        checker_out=self._artifact_store.read(task.task_id, "checker", ParsedOutput),
        test_out=self._artifact_store.read(task.task_id, "tester", ParsedOutput),
        qa_out=self._artifact_store.read(task.task_id, "qa_automation", ParsedOutput),
        merge_readiness=self._artifact_store.read(task.task_id, "merge-readiness", MergeReadinessArtifact),
        lessons=self._artifact_store.read(task.task_id, "lessons", LessonsArtifact),
    )
    review_server.set_html(html)
    self._pending_reviews[task.task_id] = review_server

    try:
        webbrowser.open(url)
    except Exception as exc:
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="human_review_browser_failed",
            notes=f"browser open failed ({exc}); navigate to {url}",
        ))
    else:
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="human_review_requested",
            notes=url,
        ))

    return task  # stay in READY_FOR_HUMAN_REVIEW
```

#### `_process_human_review_decision` (private helper):

```python
def _process_human_review_decision(
    self, task: Task, env: TaskEnvelope, result: HumanReviewDecision,
) -> Task:
    if result.decision == "approve":
        self._github_adapter.merge_pr(task.pr_url)      # type: ignore[union-attr]
        task = self._sm.transition(task, TaskState.DONE)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_HUMAN_REVIEW", to_state="DONE",
        ))
        return task

    # Reject path
    if result.correction:
        self._artifact_store.write(task.task_id, "human-review-correction", result.correction)

    if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
        task = self._sm.transition(task, TaskState.READY_FOR_DOER)
        # rework_count is incremented inside sm.transition() — not manually here
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_HUMAN_REVIEW", to_state="READY_FOR_DOER",
            notes=f"human rejected: {result.correction[:120]}",
        ))
    else:
        task = self._force_block(task, notes="human rejected but rework limit reached")
    return task
```

#### `_handle_ready_for_doer` — correction-artifact injection:

The existing handler starts with a transition to `DOER_IN_PROGRESS` and then calls `_run_agent`. The correction-artifact lookup is inserted **before** `_run_agent`, replacing the plain call with one that includes `prior_artifacts`:

```python
def _handle_ready_for_doer(self, task: Task, env: TaskEnvelope) -> Task:
    task = self._sm.transition(task, TaskState.DOER_IN_PROGRESS)
    self._emit(OrchestratorEvent(
        task_id=task.task_id, event_type="state_transition",
        from_state="READY_FOR_DOER", to_state="DOER_IN_PROGRESS",
    ))
    # --- NEW: include human correction if present ---
    prior_artifacts: dict[str, str] = {}
    correction = self._artifact_store.read_text(task.task_id, "human-review-correction")
    if correction:
        prior_artifacts["human_correction"] = correction
    # ------------------------------------------------
    try:
        output = self._run_agent(task, env, "doer", prior_artifacts=prior_artifacts or None)
    except Exception:
        task = self._sm.transition(task, TaskState.RETRY_PENDING)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="DOER_IN_PROGRESS", to_state="RETRY_PENDING",
            notes="runner exception",
        ))
        return task
    # ... rest of handler unchanged
```

#### `_cancel_task` — server cleanup:

```python
def _cancel_task(self, task: Task, env: TaskEnvelope) -> None:
    # --- NEW ---
    server = self._pending_reviews.pop(task.task_id, None)
    if server is not None:
        server.shutdown()
    # --- existing code follows ---
    ...
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `github_adapter` is None | `_force_block("github_adapter not configured")` — checked in Phase 1 before server start |
| `pr_url` is None | `_force_block("pr_url not set — cannot merge")` — checked in Phase 1 before server start |
| Server fails to bind port | `_force_block("human review server failed to start: <exc>")` |
| Browser fails to open | Emit `human_review_browser_failed` with URL; keep waiting (user navigates manually) |
| Task cancelled while review pending | `_cancel_task` calls `server.shutdown()` and removes from `_pending_reviews` |
| Orchestrator restarted mid-review | `_pending_reviews` is ephemeral — not persisted. Phase 1 re-runs on next tick: new server, browser reopens. This is the intentional recovery mechanism. |
| Reject at rework limit | `_force_block("human rejected but rework limit reached")` |

---

## Testing Strategy

| Test file | Coverage |
|---|---|
| `tests/unit/orchestrator/test_human_review_server.py` | `start()` returns valid `http://localhost:<port>` URL; `get_result()` returns `None` before POST; POST stores decision + correction; second POST ignored; `shutdown()` idempotent; `set_html()` reflected in GET response. Tests POST from the test thread while server runs in daemon thread — use `threading.Event.wait(timeout=2)` rather than `time.sleep` to avoid flakiness. |
| `tests/unit/orchestrator/test_human_review_html.py` | Renders task title, PR link, lessons, acceptance criteria, `submit_url` in form action; `None` artifacts handled gracefully (no KeyError, no crash) |
| `tests/unit/orchestrator/test_orchestrator_loop.py` | Phase 1: server started + `human_review_requested` emitted + task state unchanged; Phase 2 (result=None): task unchanged; Phase 2 approve: `merge_pr` called + task → DONE; Phase 2 reject with correction: artifact written + task → READY\_FOR\_DOER (rework\_count incremented via sm.transition); Phase 2 reject at limit: task → BLOCKED; cancel while pending: server shutdown called; `_handle_ready_for_doer` with correction artifact present: `prior_artifacts["human_correction"]` passed to `_run_agent` |
| `tests/unit/orchestrator/test_state_machine.py` | `READY_FOR_HUMAN_REVIEW → READY_FOR_DOER` allowed when `rework_count < max`; returns `False` when at limit; `rework_count` incremented by `sm.transition()`; `READY_FOR_HUMAN_REVIEW → DONE` still allowed |

---

## Files Created / Modified

| Action | File |
|---|---|
| Create | `system/orchestrator/human_review_server.py` |
| Create | `system/orchestrator/human_review_html.py` |
| Create | `tests/unit/orchestrator/test_human_review_server.py` |
| Create | `tests/unit/orchestrator/test_human_review_html.py` |
| Modify | `system/orchestrator/state_machine.py` — new transition, guard, rework rule, `_BLOCKED_ON_LIMIT` |
| Modify | `system/orchestrator/schemas/events.py` — add `human_review_requested` and `human_review_browser_failed` to schema comment |
| Modify | `system/orchestrator/orchestrator.py` — two-phase handler, `_pending_reviews`, `_cancel_task` cleanup, `_handle_ready_for_doer` injection |
| Modify | `tests/unit/orchestrator/test_state_machine.py` |
| Modify | `tests/unit/orchestrator/test_orchestrator_loop.py` |
