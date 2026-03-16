# Qwen Integration Guide

**Version:** 1.0  
**Date:** 2026-03-14  
**Status:** Implemented

This document provides a comprehensive guide for integrating Qwen Code as an agent option in the Breqy multi-agent delivery workflow. The orchestrator can route tasks to Qwen for any role (Doer, Checker, Tester, Planner, Lessons).

---

## 1. Overview

Qwen Code is integrated as a first-class agent option in the Breqy orchestration system. The orchestrator can route tasks to Qwen for any delivery role:

- **Planner/Shaper** — PRD breakdown, task shaping, acceptance criteria definition
- **Doer** — TDD implementation, test writing, documentation
- **Checker** — independent review, structured findings
- **Tester** — validation execution, evidence capture
- **Lessons** — lesson capture, instruction improvement proposals

The orchestrator itself can be any implementation (Python service, CLI tool, or even Qwen itself in an orchestrator role).

---

## 2. Architecture

### 2.1 Integration Points

```
┌─────────────────────────────────────────────────────────────┐
│                    Breqy Orchestrator                        │
│              (Python service / CLI / Agent)                  │
├─────────────────────────────────────────────────────────────┤
│  State Machine  │  Router  │  Artifact Store  │  CI Adapter │
└─────────────────────────────────────────────────────────────┘
         │
         │ Routes tasks to agents
         ▼
┌─────────────────────────────────────────────────────────────┐
│                     Agent Runners                            │
├─────────────────┬─────────────────┬─────────────────────────┤
│  Qwen Runner    │  Claude Runner  │  Other Runners          │
│  (qwen_runner)  │  (claude_runner)│  (gemini_runner, etc.)  │
└─────────────────┴─────────────────┴─────────────────────────┘
         │
         │ Invokes
         ▼
┌─────────────────────────────────────────────────────────────┐
│                     Qwen Code CLI                            │
└─────────────────────────────────────────────────────────────┘
         │
         │ Reads
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Role-Specific Prompts + Instruction Files                   │
│  - agents/my-instructions.md                                 │
│  - agents/core.instructions.md                               │
│  - agents/project.instructions.md                            │
│  - agents/python.instructions.md                             │
│  - agents/tdd.instructions.md                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Module Structure

```
system/orchestrator/
  runners/
    base.py              # Base runner interface
    qwen_runner.py       # Qwen Code integration
    claude_runner.py     # Claude Code integration
    gemini_runner.py     # Gemini integration
    ...
  agent_adapters/
    base.py
    planner.py
    doer.py
    checker.py
    tester.py
    lessons.py
```

---

## 3. Configuration

### 3.1 Agent Configuration File

Edit `scripts/agents.yaml` to configure Qwen agents:

```yaml
# Global settings
permission_mode: acceptEdits

# Routing configuration - orchestrator routes tasks to these agents
routing:
  feature:
    backend:
      doer: qwen        # Orchestrator routes Doer tasks to Qwen
      checker: claude   # Orchestrator routes Checker tasks to Claude
      tester: qwen      # Orchestrator routes Tester tasks to Qwen
    tui:
      doer: qwen
      checker: claude
      tester: qwen
  bug:
    low_risk:
      doer: qwen
      checker: claude

# Agent definitions
agents:
  - name: qwen-doer
    project_dir: .
    prompt: |
      Act as Doer. Read agents/my-instructions.md.
      Implement with TDD: write tests first (RED), implement minimum code (GREEN), refactor.
    role: doer
    instructions:
      - agents/my-instructions.md
      - agents/core.instructions.md
      - agents/project.instructions.md
      - agents/python.instructions.md
      - agents/tdd.instructions.md

  - name: qwen-checker
    project_dir: .
    prompt: |
      Act as Checker. Read agents/my-instructions.md.
      Review independently: correctness, architecture, tests, documentation.
    role: checker
    instructions:
      - agents/my-instructions.md
      - agents/core.instructions.md
      - agents/project.instructions.md

  - name: qwen-tester
    project_dir: .
    prompt: |
      Act as Tester. Read agents/my-instructions.md.
      Execute validation: CLI commands, UI flows, unit/integration tests.
    role: tester
    instructions:
      - agents/my-instructions.md
      - agents/core.instructions.md
      - agents/tdd.instructions.md

  - name: qwen-planner
    project_dir: .
    prompt: |
      Act as Planner. Read agents/my-instructions.md and docs/ai_delivery_approach_v_1.md.
      Break PRD/features into executable slices. Define acceptance criteria.
    role: planner
    instructions:
      - agents/my-instructions.md
      - agents/project.instructions.md
      - docs/ai_delivery_approach_v_1.md
      - docs/shaped_task_schema.md

  - name: qwen-lessons
    project_dir: .
    prompt: |
      Act as Lessons. Read agents/my-instructions.md.
      Analyze what went wrong/well. Capture lessons in .breqy/lessons/<task-id>.yaml.
    role: lessons
    instructions:
      - agents/my-instructions.md
      - docs/ai_delivery_approach_v_1.md
      - docs/lessons_learned_schema.md
```

### 3.2 Routing Rules

Configure role assignment by task type and component:

```yaml
routing:
  feature:
    backend:
      doer: qwen          # Qwen implements with TDD
      checker: claude     # Claude reviews independently (recommended)
      tester: qwen        # Qwen validates
    tui:
      doer: qwen
      checker: claude
      tester: qwen
  bug:
    low_risk:
      doer: qwen
      checker: claude
  refactor:
    service:
      doer: qwen
      checker: claude
      tester: qwen
```

---

## 4. Usage

### 4.1 Programmatic Usage

```python
from system.orchestrator.runners.qwen_runner import create_qwen_runner, QwenRunnerConfig

# Create a Doer runner
doer = create_qwen_runner(
    name="qwen-doer",
    role="doer",
    project_dir="/path/to/project",
    prompt="Implement session resume feature",
    instructions=[
        "agents/my-instructions.md",
        "agents/core.instructions.md",
        "agents/project.instructions.md",
    ],
    permission_mode="acceptEdits",
)

# Execute
result = await doer.run()

# Check results
if result.success:
    print("Qwen completed the task")
    print(f"Plan files: {result.artifacts['plan_files']}")
    print(f"Review files: {result.artifacts['review_files']}")
    print(f"Test files: {result.artifacts['test_files']}")
    print(f"Changed files: {result.artifacts['changed_files']}")
else:
    print(f"Qwen failed: {result.errors}")
```

### 4.2 Orchestrator Integration

```python
from system.orchestrator.main import Orchestrator
from system.orchestrator.runners.qwen_runner import QwenRunner

# Initialize orchestrator with Qwen support
orchestrator = Orchestrator(config_path="scripts/agents.yaml")

# Register Qwen runners
orchestrator.register_runner("qwen-doer", QwenRunner)
orchestrator.register_runner("qwen-checker", QwenRunner)
orchestrator.register_runner("qwen-tester", QwenRunner)

# Route task to Qwen Doer
task = orchestrator.get_next_task()
runner = orchestrator.get_runner("qwen-doer", task)
result = await runner.run()

# Collect artifacts
orchestrator.collect_artifacts(result)
```

---

## 5. Role-Specific Behavior

### 5.1 Planner/Shaper

**Responsibilities:**
- Read PRD and architecture docs
- Break features into executable slices
- Define acceptance criteria
- Identify dependencies and test obligations
- Produce shaped task envelopes

**Artifacts Produced:**
- Implementation plans
- Shaped task YAML/JSON files
- Dependency maps
- Test obligation lists

**Output Location:** `agents/docs/feat-<name>.jsonl`

### 5.2 Doer

**Responsibilities:**
- Implement features following TDD
- Write tests first (RED phase)
- Implement minimum code to pass (GREEN phase)
- Refactor while tests stay green
- Document changes and update changelog

**Artifacts Produced:**
- Code changes
- Unit/integration tests
- JSONL plan updates
- Documentation updates

**Output Locations:**
- Plan: `agents/docs/feat-<name>.jsonl`
- Reviews: `docs/operational/reviews/<task-name>.<timestamp>.md`
- Tests: `docs/operational/tests/<task-name>.<timestamp>.md`

### 5.3 Checker

**Responsibilities:**
- Review independently
- Assess correctness and architectural fit
- Identify missing edge cases
- Classify findings by severity
- Provide clear verdict

**Artifacts Produced:**
- Structured review document
- Severity-classified findings
- Pass/fail recommendation

**Output Location:** `docs/operational/reviews/<task-name>.<timestamp>.md`

### 5.4 Tester

**Responsibilities:**
- Execute CLI and UI validation
- Run automated test suites
- Capture evidence (outputs, screenshots)
- Verify coverage thresholds
- Produce test reports

**Artifacts Produced:**
- Test report document
- Evidence artifacts (screenshots, logs)
- Coverage reports
- Pass/fail verdict

**Output Locations:**
- Report: `docs/operational/tests/<task-name>.<timestamp>.md`
- Artifacts: `docs/operational/tests/artifacts/<task-name>.<timestamp>/`

### 5.5 Lessons

**Responsibilities:**
- Analyze what went wrong/well
- Identify repeated correction patterns
- Capture lessons in machine-readable format
- Propose instruction updates

**Artifacts Produced:**
- Lessons YAML file
- Instruction update proposals
- Root cause classifications

**Output Location:** `.breqy/lessons/<task-id>.yaml`

---

## 6. Artifact Conventions

### 6.1 Plan Files (JSONL Format)

```jsonl
{"step":"pull latest changes","status":"pending","kind":"git","notes":"sync before branching"}
{"step":"inspect git status and branches","status":"pending","kind":"git","notes":"confirm safe starting point"}
{"step":"create or switch to feat/<name>","status":"pending","kind":"git","notes":"never work on trunk"}
{"step":"read instructions and analyze impacted code","status":"pending","kind":"discovery","notes":"gather constraints"}
{"step":"write failing tests","status":"pending","kind":"tdd","notes":"red phase"}
{"step":"implement minimal change","status":"pending","kind":"tdd","notes":"green phase"}
{"step":"refactor while tests stay green","status":"pending","kind":"tdd","notes":"refactor phase"}
{"step":"run lint and unit tests","status":"pending","kind":"validation","notes":"must be clean"}
{"step":"update docs and changelog","status":"pending","kind":"documentation","notes":"keep docs current"}
{"step":"commit changes and prepare PR","status":"pending","kind":"delivery","notes":"include validation summary"}
```

### 6.2 Review Document Structure

```markdown
# Review: <task-name>

## Metadata
- Timestamp: 2026-03-14T10:30:00Z
- Reviewer: qwen-checker
- Scope: Session resume feature implementation
- Artifact types: code, tests, docs

## Summary
Implementation follows TDD correctly. Tests are comprehensive.
One high-severity issue found in error handling.

## What was reviewed
- tui/session_list.py
- tests/tui/test_session_resume.py
- agents/docs/feat-session-resume.jsonl

## Findings

### Error handling in empty-state path
- Severity: high
- Artifact: tui/session_list.py:45
- Evidence: No handling for empty session list
- Why it matters: Will crash on first launch
- Recommendation: Add empty-state guard

## Clean verdict
- Status: changes required
- Rationale: High-severity issue must be fixed

## Recommended next actions
- Add empty-state handling in session list
- Add test for empty session list scenario
```

### 6.3 Test Report Structure

```markdown
# Test Report: <task-name>

## Metadata
- Timestamp: 2026-03-14T11:00:00Z
- Tester: qwen-tester
- Scope: Session resume feature
- Environment: local
- Worktree path: .worktrees/feat-session-resume

## Test targets
- CLI: pytest tests/tui/test_session_resume.py
- UI: Session selection flow

## Executed tests

### test_session_list_shows_prior_sessions
- Target: pytest tests/tui/test_session_resume.py::test_session_list_shows_prior_sessions
- Steps: Run pytest test
- Expected: Test passes, sessions displayed
- Actual: Test passed
- Status: pass
- Evidence: docs/operational/tests/artifacts/session-resume/pytest-output.txt

## Results
- Passed: 5
- Failed: 0
- Blocked: 0

## Evidence
- Report: docs/operational/tests/session-resume.20260314T110000Z.md
- Artifacts: docs/operational/tests/artifacts/session-resume.20260314T110000Z/

## Clean verdict
- Status: clean
- Rationale: All tests pass, coverage thresholds met
```

### 6.4 Lessons Learned Schema

```yaml
task_id: BRQ-144
task_type: feature
discovered_in_stage: checker_review
first_avoidable_miss: Empty-state path not handled in session list
root_cause_class:
  - missing_test_case
  - weak_edge_case_coverage
symptoms:
  - crash on first launch with no prior sessions
impact:
  severity: high
  user_visible: true
reusable_fix:
  - add empty-state test template for all list views
  - require "first launch" scenario in session-related tasks
instruction_update_proposal:
  target: agents/my-instructions.md
  change: For list/view implementations, always test empty-state scenario
promotion_scope: project
status: proposed
```

---

## 7. Multi-Agent Coordination Patterns

### 7.1 Pattern 1: Orchestrator + Qwen Specialists

```
┌─────────────────┐
│  Orchestrator   │
│  (any impl)     │
└────────┬────────┘
         │ routes to
    ┌────┴────┬────────────┬──────────┐
    ▼         ▼            ▼          ▼
┌───────┐ ┌───────┐ ┌──────────┐ ┌────────┐
│Qwen   │ │Qwen   │ │ Qwen     │ │ Qwen   │
│Doer   │ │Checker│ │ Tester   │ │Lessons │
└───────┘ └───────┘ └──────────┘ └────────┘
```

**Use case:** Complex features requiring full workflow

### 7.2 Pattern 2: Multi-Provider Review

```
┌──────────┐
│ Qwen     │
│ Doer     │
└────┬─────┘
     │ implements
     ▼
┌──────────┐     ┌──────────┐
│ Claude   │     │ Qwen     │
│ Checker  │     │ Tester   │
└────┬─────┘     └────┬─────┘
     │                │
     └────────┬───────┘
              ▼
       ┌──────────────┐
       │ Consolidated │
       │ Findings     │
       └──────────────┘
```

**Use case:** High-risk changes requiring independent validation from different providers

### 7.3 Pattern 3: Staged Delivery

```
PRD → Qwen Planner → Shaped Tasks
              ↓
     Qwen Doer → Implementation
              ↓
     Qwen/Claude Checker → Review
              ↓
     Qwen Tester → Validation
              ↓
     Qwen Lessons → Learnings
```

**Use case:** Standard feature delivery workflow

---

## 8. Best Practices

### 8.1 Instruction File Management

- Keep instruction files versioned and up-to-date
- Reference instruction files explicitly in agent configs
- Update `agents/my-instructions.md` when workflow changes
- Use instruction files as the source of truth for agent behavior

### 8.2 Artifact Hygiene

- Always produce artifacts in standard locations
- Use consistent naming: `<task-name>.<timestamp>.<ext>`
- Keep artifacts machine-readable where possible
- Link artifacts to task IDs for traceability

### 8.3 Provider Independence

- Ensure Checker uses different provider than Doer
- Tester should validate independently, not assume correctness
- Lessons role should analyze patterns, not just single tasks

### 8.4 Coverage Enforcement

- Qwen Tester must verify coverage thresholds
- 100% business logic coverage mandatory
- 80% overall coverage minimum
- Block merge if thresholds not met

---

## 9. Troubleshooting

### 9.1 Common Issues

**Issue:** Qwen not reading instructions  
**Solution:** Verify instruction file paths are absolute or repo-relative

**Issue:** Artifacts not found  
**Solution:** Check artifact path conventions in output parsing

**Issue:** Role confusion  
**Solution:** Ensure role-specific prompts are clear and distinct

**Issue:** Multi-agent conflicts  
**Solution:** Use worktrees for isolation, coordinate via orchestrator

### 9.2 Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check Qwen output:

```bash
qwen-code --verbose --project-dir . --prompt "..."
```

---

## 10. Future Enhancements

- [ ] Native Qwen API integration (beyond CLI)
- [ ] Streaming output capture
- [ ] Real-time artifact generation
- [ ] Multi-model consensus checking
- [ ] Automated instruction improvement
- [ ] Historical pattern learning
- [ ] Dashboard for multi-agent coordination

---

## 11. References

- `docs/ai_delivery_approach_v_1.md` — Full delivery workflow
- `agents/my-instructions.md` — Qwen operating instructions
- `scripts/agents.yaml` — Agent configuration
- `system/orchestrator/runners/qwen_runner.py` — Runner implementation
- `docs/shaped_task_schema.md` — Task shaping format
- `docs/lessons_learned_schema.md` — Lessons capture format
