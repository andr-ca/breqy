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

Add allowed transition:

```
READY_FOR_HUMAN_REVIEW → READY_FOR_DOER
```

This is a rework transition: `rework_count` increments (same semantics as `CHECK_FAILED → READY_FOR_DOER`). No new `TaskState` values are introduced.

Guard: `can_transition(task, READY_FOR_DOER)` returns `False` when `rework_count >= max_rework_loops`. In that case the orchestrator calls `_force_block`.

The correction text is written as `human-review-correction.md` via `ArtifactStore`. `_handle_ready_for_doer` checks for its existence and passes it as `"human_correction"` in `prior_artifacts` when calling `_run_agent`.

---

## Components

### `HumanReviewServer`

**File:** `system/orchestrator/human_review_server.py`

Wraps Python stdlib `http.server.HTTPServer` in a daemon thread. Receives the HTML at construction time — no knowledge of artifacts or orchestration state.

```python
@dataclass
class HumanReviewDecision:
    decision: Literal["approve", "reject"]
    correction: str  # empty string if approved

class HumanReviewServer:
    def __init__(self, task_id: str, html: str, port: int = 0) -> None: ...
    def start(self) -> str: ...          # returns "http://localhost:<port>"
    def get_result(self) -> HumanReviewDecision | None: ...  # non-blocking
    def shutdown(self) -> None: ...
```

- `port=0` lets the OS assign a free port — avoids conflicts between tasks
- Serves the HTML on `GET /`
- Accepts `POST /submit` with `application/x-www-form-urlencoded`: `decision=approve|reject&correction=<text>`
- Stores the first POST result in a `threading.Event` + result slot; ignores subsequent POSTs
- Shuts itself down after the first POST
- `shutdown()` is idempotent

---

### `build_review_html`

**File:** `system/orchestrator/human_review_html.py`

Pure function — no I/O, no side effects. Takes artifacts and returns a self-contained HTML string (no external assets).

```python
def build_review_html(
    task_id: str,
    env: TaskEnvelope,
    submit_url: str,
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

- Correction textarea is enabled only when "Reject" is selected (inline JS)
- On submit, form POSTs `application/x-www-form-urlencoded` to `submit_url`
- After submit, page replaces body with "Response recorded — you can close this tab."
- All `None` artifacts render gracefully as "—" or are omitted

---

### Orchestrator Changes

**File:** `system/orchestrator/orchestrator.py`

`OrchestratorLoop.__init__` gains:

```python
self._pending_reviews: dict[str, HumanReviewServer] = {}
```

`_handle_ready_for_human_review` becomes a two-phase handler:

**Phase 1 — server not yet started (first tick):**
1. Read all artifacts from `_artifact_store`
2. Generate HTML via `build_review_html(...)`
3. Instantiate and start `HumanReviewServer(task_id, html, port=0)`
4. Store in `_pending_reviews[task_id]`
5. Open browser: `webbrowser.open(url)`
6. Emit `human_review_requested` event with `notes=url`
7. Return task unchanged (stay in `READY_FOR_HUMAN_REVIEW`)

**Phase 2 — server started, polling (subsequent ticks):**
1. `result = _pending_reviews[task_id].get_result()`
2. If `None`: return task unchanged
3. Decision received:
   - `server.shutdown()`, `del _pending_reviews[task_id]`
   - **Approve:** `github_adapter.merge_pr(task.pr_url)` → transition to `DONE`
   - **Reject:**
     - If `result.correction`: write `"human-review-correction"` artifact
     - If `sm.can_transition(task, READY_FOR_DOER)`: transition to `READY_FOR_DOER`, increment `rework_count`
     - Else: `_force_block(task, "human rejected but rework limit reached")`

**`_handle_ready_for_doer` addition:**

```python
correction = self._artifact_store.read_text(task.task_id, "human-review-correction")
prior_artifacts = {}
if correction:
    prior_artifacts["human_correction"] = correction
output = self._run_agent(task, env, "doer", prior_artifacts=prior_artifacts)
```

**`_cancel_task` addition:** if `task_id in self._pending_reviews`, call `shutdown()` and remove.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `github_adapter` is None on approve | `_force_block("github_adapter not configured")` |
| `pr_url` is None on approve | `_force_block("pr_url not set — cannot merge")` |
| Server fails to bind port | `_force_block("human review server failed to start: <exc>")` |
| Browser fails to open | Emit warning event with URL; keep waiting (user can navigate manually) |
| Task cancelled while review pending | `_cancel_task` shuts down server and removes from `_pending_reviews` |
| Orchestrator restarted mid-review | Server gone; Phase 1 re-runs on next tick — new server, browser reopens |
| Reject at rework limit | `_force_block("human rejected but rework limit reached")` |

---

## Testing Strategy

| Test file | Coverage |
|---|---|
| `tests/unit/orchestrator/test_human_review_server.py` | `start()` returns valid URL; `get_result()` returns `None` before POST; POST stores decision; second POST ignored; `shutdown()` idempotent |
| `tests/unit/orchestrator/test_human_review_html.py` | Renders task title, PR link, lessons, acceptance criteria, `submit_url` in form action; `None` artifacts handled gracefully |
| `tests/unit/orchestrator/test_orchestrator_loop.py` | Phase 1: server started + event emitted + task unchanged; Phase 2 approve: merge called + DONE; Phase 2 reject: correction artifact written + READY\_FOR\_DOER; Phase 2 reject at limit: BLOCKED; cancel shuts down pending server |
| `tests/unit/orchestrator/test_state_machine.py` | `READY_FOR_HUMAN_REVIEW → READY_FOR_DOER` allowed under limit; blocked at limit; `rework_count` incremented |

Server tests use real localhost HTTP (stdlib only, no external deps). Orchestrator tests mock `HumanReviewServer`.

---

## Files Created / Modified

| Action | File |
|---|---|
| Create | `system/orchestrator/human_review_server.py` |
| Create | `system/orchestrator/human_review_html.py` |
| Create | `tests/unit/orchestrator/test_human_review_server.py` |
| Create | `tests/unit/orchestrator/test_human_review_html.py` |
| Modify | `system/orchestrator/state_machine.py` |
| Modify | `system/orchestrator/orchestrator.py` |
| Modify | `tests/unit/orchestrator/test_state_machine.py` |
| Modify | `tests/unit/orchestrator/test_orchestrator_loop.py` |
