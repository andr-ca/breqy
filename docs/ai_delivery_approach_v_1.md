# AI-Assisted Delivery Approach v1

## Purpose

This document defines the end-to-end delivery model for turning a PRD or project intent into a fully implemented, reviewed, tested, and learned-from feature using a structured multi-agent workflow.

The goal is not to let multiple AI agents freely collaborate in an uncontrolled way. The goal is to establish a disciplined engineering system where:

- work is explicitly shaped before implementation
- one role owns implementation at a time
- independent roles review and validate the result
- automated test cases prove the feature works
- failures are captured as lessons
- instructions, skills, and checklists improve over time

This document is intended to be detailed enough to implement the workflow in a real repository, orchestration layer, and CI/CD environment.

---

# 1. Core Principles

## 1.1 One writer, many validators

Only one role at a time should own production-code changes for a task. Multiple agents may analyze, review, test, and propose changes, but they should not all edit the same feature branch concurrently.

## 1.2 Evidence-based completion

A task is not complete because an AI says it is complete.

A task is complete only when the required evidence exists:

- implementation exists in a branch / PR
- review findings are resolved
- deterministic CI passes
- required test automation passes
- acceptance criteria are demonstrably met
- lessons learned are captured
- a human approves merge

## 1.3 Repo-anchored intent

The system of intent must live in versioned repository files, not only in prompts or chat history.

This includes:

- PRD / feature intent
- architecture intent
- acceptance criteria
- delivery standards
- testing standards
- branch and merge policy
- agent role instructions
- reusable skills
- lessons learned

## 1.4 Separation of responsibilities

The delivery system works only if responsibilities are clear and enforceable.

At minimum, the workflow separates:

- planning / shaping
- implementation
- review
- testing
- QA automation
- lessons learned
- final approval

## 1.5 Continuous instruction improvement

Every meaningful failure or recurring correction is a candidate input for updating:

- agent instructions
- review checklists
- test templates
- reusable skills
- architectural constraints
- branching or release standards

---

# 2. Delivery Lifecycle Overview

The target lifecycle for each feature or task is:

1. PRD / Intent Definition
2. Planning / Shaping
3. Branch Preparation
4. Test Case Design
5. Implementation (Doer)
6. Review (Checker)
7. Developer Test Validation
8. QA Automation / Business Test Automation
9. API / TUI / Flow Regression
10. Rework Loop (if needed)
11. Merge Readiness Review
12. Lessons Learned
13. Instruction / Skill Update Proposal
14. Human Approval and Merge
15. Promotion Through Environments

This is not a purely linear flow. Failed review or failed tests send the task back into a bounded rework loop.

---

# 3. Roles and Ownership

## 3.1 Human Sponsor / Owner

Owns:

- prioritization
- PRD or business intent
- acceptance of scope
- ambiguity resolution when needed
- final merge approval
- approval of instruction promotion
- approval of release into higher environments when applicable

## 3.2 Orchestrator

Owns workflow state and routing.

Responsibilities:

- read the backlog / issues
- determine next eligible tasks
- assign role execution
- generate task envelopes
- invoke agents or automation steps
- collect outputs and artifacts
- advance or roll back task state
- enforce completion gates
- escalate blocked or looping tasks
- create branches according to policy
- ensure merges only happen through approved paths

The orchestrator is the control plane. It is the only role allowed to declare that a task is ready for the next stage.

## 3.3 Planner / Shaper

The Planner / Shaper is the highest-leverage control point in the workflow. A weak shape causes downstream drift even if the Doer, Checker, and Tester are strong.

Responsibilities:

- read the PRD and related architecture docs
- identify feature slices or refactor slices
- identify dependencies and sequencing
- identify required test levels
- identify risks and unknowns
- define acceptance criteria for each slice
- produce a task backlog or TODO list
- identify what can be parallelized and what cannot
- flag ambiguities for human resolution
- produce a machine-readable shaped-task package

The Planner / Shaper does not implement production code.

## 3.4 Doer

Owns implementation.

Responsibilities:

- implement the task within approved scope
- follow TDD where required
- deliver unit tests
- satisfy business-logic coverage expectations
- document assumptions and known risks
- avoid scope creep

The Doer should be the only role writing production code on the main task branch.

## 3.5 Checker

Owns independent review.

Responsibilities:

- review the diff against requirements and architecture
- assess correctness, maintainability, and boundary adherence
- review adequacy of developer tests
- identify missing edge cases
- produce structured findings

The Checker should not silently rewrite the feature. The Checker’s primary output is a review artifact.

## 3.6 Tester

Owns validation of implementation quality and required developer-level test coverage.

Responsibilities:

- verify required unit / integration / contract tests exist
- run deterministic validation
- assess whether test expectations are fulfilled
- report failures in a structured way

## 3.7 QA Automation Role

Owns executable business/regression testing.

Responsibilities:

- convert business requirements into formal test cases
- implement automated API test scenarios
- implement TUI / flow automation where required
- run regression suites
- report business-level pass/fail evidence

This role is distinct from the Doer. Code-level coverage is not enough.

## 3.8 Lessons Learned Role

Owns improvement capture.

Responsibilities:

- analyze what failed or required rework
- identify repeated correction patterns
- propose instruction updates
- propose new or improved skills
- classify improvements as local or reusable
- emit machine-readable lessons

---

# 4. Task Object Model

Every feature or task should exist as a structured work item, for example a GitHub Issue.

## 4.1 Required fields

Each task should include at least:

- `task_id`
- `title`
- `problem_statement`
- `desired_outcome`
- `acceptance_criteria`
- `in_scope`
- `out_of_scope`
- `component`
- `task_type` (`feature`, `bug`, `refactor`, `test-only`, `infra`)
- `risk_level`
- `priority`
- `required_test_levels`
- `human_owner`

## 4.2 Acceptance criteria quality standard

Acceptance criteria must be specific enough to support:

- implementation
- review
- deterministic validation
- business test case design

## 4.3 Task envelope

The orchestrator should transform the task into a normalized task envelope used by all roles.

Example:

```yaml
task_id: BRQ-144
title: Add TUI session selection flow
goal: Allow users to select an existing session and continue the same thread
component: tui
risk_level: medium
task_type: feature
scope:
  include:
    - tui/session_list/*
    - tui/app/*
  exclude:
    - unrelated agent runtime changes
acceptance_criteria:
  - session list shows prior sessions on startup
  - selecting a prior session opens the same thread
  - sending a message appends to existing session
  - no duplicate sessions created on reconnect
required_test_levels:
  - unit
  - integration
  - tui
constraints:
  - preserve existing session ID format
  - do not change storage schema without ADR
```

---

# 5. Delivery States

Recommended workflow states:

1. `NEW`
2. `READY_FOR_SHAPING`
3. `READY_FOR_BRANCH_PREP`
4. `READY_FOR_TEST_CASE_DESIGN`
5. `READY_FOR_DOER`
6. `DOER_IN_PROGRESS`
7. `READY_FOR_CHECKER`
8. `CHECK_FAILED`
9. `READY_FOR_TESTER`
10. `READY_FOR_QA_AUTOMATION`
11. `TEST_FAILED`
12. `READY_FOR_MERGE_REVIEW`
13. `READY_FOR_LESSONS`
14. `READY_FOR_HUMAN_REVIEW`
15. `DONE`
16. `BLOCKED`

Not every task requires all lanes, but the orchestrator must explicitly decide which states apply.

---

# 6. From PRD to Plan to Shaped Tasks

## 6.1 Why planning / shaping exists

A PRD usually contains intent, outcomes, assumptions, constraints, and incomplete edge cases. A Doer should not receive the raw PRD and improvise the task breakdown.

Without shaping, common failure modes are:

- tasks are too large
- acceptance criteria are vague
- testing is an afterthought
- implementation starts before dependencies are visible
- multiple agents interpret the same requirement differently

## 6.2 Planner / Shaper outputs

The outputs of planning should be concrete artifacts such as:

- a feature implementation plan
- a dependency map
- a sequenced TODO list
- a set of shaped tasks
- initial test obligations
- an open questions list
- an initial risks register

## 6.3 Minimum shaped-task schema

Every executable shaped task should conform to a minimum schema. This is the contract between Shaper and downstream roles.

```yaml
task_id: BRQ-144
title: Add TUI session selection flow
source_plan: PLAN-2026-03-001
source_prd: docs/intent/prd.md
task_type: feature
component: tui
risk_level: medium
objective: Let the user select an existing session from the TUI and continue the same thread
business_value: Preserve continuity and avoid duplicate session creation
in_scope:
  - add session list screen or panel in TUI
  - load selected session into active thread view
  - append new messages to existing session
out_of_scope:
  - archived session management
  - cross-device synchronization
files_expected_to_change:
  - tui/session_list.py
  - tui/app.py
  - tui/state/session_store.py
files_allowed_to_create:
  - tests/tui/test_session_resume.py
files_explicitly_do_not_touch:
  - engine/storage/schema.py
  - engine/auth/*
interfaces_impacted:
  - engine.sessions.list
  - engine.sessions.resume
dependencies:
  - BRQ-142
  - BRQ-143
acceptance_criteria:
  - session list shows prior sessions ordered by last updated time
  - selecting a session loads the same underlying thread
  - a follow-up message appends to the existing session
  - no duplicate session is created during reconnect
required_test_levels:
  - unit
  - integration
  - tui
required_done_evidence:
  - unit coverage threshold met
  - deterministic CI green
  - TUI regression suite passes
open_questions:
  - should archived sessions be hidden by default
```

## 6.4 Shaping template

Every shaped task should be generated from a standard shaping template.

Minimum sections:

- objective
- business value
- in scope
- out of scope
- dependencies
- acceptance criteria
- required test levels
- likely files/components touched
- files that must not be touched
- interfaces or contracts impacted
- open questions
- done evidence

## 6.5 Guidance on file specificity

The Shaper should guide likely change boundaries, but should not create false precision.

Use three levels:

- `files_expected_to_change`
- `files_allowed_to_change`
- `files_explicitly_do_not_touch`

This is better than pretending the Planner can always predict an exact file list.

## 6.6 Example: PRD to shaped slices

Raw PRD statement:

> Users should be able to continue prior work in the TUI after a disconnect or restart, without losing context or accidentally creating duplicate sessions.

Planner / Shaper should convert this into:

### Business intent

- preserve conversational continuity
- reduce friction after restart
- avoid accidental duplicate threads

### Deliverable slices

1. retrieve existing session list
2. expose resume-session engine command
3. support TUI session selection and load
4. append to existing thread on send
5. prevent duplicate session creation on reconnect
6. automate TUI regression coverage

### Required tests

- unit tests for session selection logic
- integration tests for engine session-resume behavior
- TUI regression test for restart → select → send

### Open questions

- should old sessions be sorted by last updated or created date
- should archived sessions be hidden by default

---

# 7. Orchestration Model

## 7.1 What the orchestrator is

The orchestrator is the workflow control plane.

It is responsible for:

- deciding what task is eligible to run
- deciding which role should act next
- generating task envelopes
- invoking agents and tools
- collecting outputs
- enforcing workflow state
- preventing agents from self-certifying full completion
- escalating blocked or looping tasks
- creating branches according to branch policy
- advancing work through merge paths

The orchestrator is not a free-form brainstorming agent. It is a bounded execution manager.

## 7.2 The orchestrator brain

The orchestrator should be split into two layers.

### Layer A — deterministic control logic

Implemented as code.

Responsibilities:

- state machine
- task status transitions
- routing rules
- retry counts
- escalation thresholds
- artifact path conventions
- CI status checks
- merge-readiness checks
- dependency enforcement
- branch creation
- merge path enforcement

### Layer B — bounded LLM decision assistance

Optional but useful.

Responsibilities:

- PRD breakdown
- dependency identification
- test obligation identification
- summarizing failures
- proposing instruction updates
- proposing next-best action when a task is blocked

The orchestrator does not need an LLM for basic workflow control. It does benefit from one for planning, classification, and interpretation.

## 7.3 V1 recommendation

For the first implementation, the orchestrator should be primarily a deterministic Python program that:

- reads structured task definitions
- calls the right agent with the right prompt / instructions
- writes artifacts
- tracks state
- enforces gates

## 7.4 Suggested modules

```text
system/orchestrator/
  __init__.py
  main.py
  config.py
  state_machine.py
  router.py
  task_loader.py
  artifact_store.py
  branch_manager.py
  github_adapter.py
  ci_adapter.py
  session_manager.py
  event_log.py
  runners/
    base.py
    claude_runner.py
    codex_runner.py
    gemini_runner.py
    copilot_runner.py
    qwen_runner.py
  agent_adapters/
    base.py
    planner.py
    doer.py
    checker.py
    tester.py
    qa_automation.py
    lessons.py
  prompts/
  schemas/
  tui/
    app.py
    panels/
```

See `docs/superpowers/specs/2026-03-14-orchestrator-design.md` for the full design.

## 7.5 Example routing logic

```yaml
routing_rules:
  feature:
    backend:
      doer: claude
      checker: codex
      tester: gemini
      qa: api
    tui:
      doer: claude
      checker: codex
      tester: gemini
      qa: tui
    frontend:
      doer: codex
      checker: claude
      tester: gemini
      qa: ui
  bug:
    low_risk:
      doer: copilot
      checker: codex
      tester: ci
      qa: none
  refactor:
    service:
      doer: claude
      checker: codex
      tester: gemini
      qa: no_regression
```

## 7.6 Qwen as an Orchestrator Agent Option

Qwen Code is available as a first-class agent option within the orchestrator's routing system. The orchestrator can route tasks to Qwen for any role in the delivery workflow.

### 7.6.1 Available Qwen Roles

| Role | Description | When to Use |
|---|---|---|
| `qwen-orchestrator` | Workflow state management, task routing | Primary orchestration |
| `qwen-planner` | PRD breakdown, task shaping | Feature planning |
| `qwen-doer` | TDD implementation | Feature/bug/fix implementation |
| `qwen-checker` | Independent review | Code/design review |
| `qwen-tester` | Validation execution | Test execution, coverage |
| `qwen-lessons` | Lessons capture | Post-completion learning |

### 7.6.2 Routing Qwen Tasks

Configure Qwen in routing rules alongside other providers:

```yaml
routing_rules:
  feature:
    backend:
      # Option 1: Qwen as primary doer
      doer: qwen
      checker: claude        # Different model for independence
      tester: qwen
      qa: api
    tui:
      doer: qwen
      checker: claude
      tester: qwen
      qa: tui
  bug:
    low_risk:
      doer: qwen
      checker: claude
      tester: ci
  refactor:
    service:
      doer: qwen
      checker: claude
      tester: qwen
      qa: no_regression
```

### 7.6.3 Qwen Strengths for Routing Decisions

**Use Qwen as Doer when:**
- Deep repository context is needed (reads all instruction files)
- TDD discipline is critical (enforces Red-Green-Refactor)
- Branch safety is important (always checks branch first)
- Documentation completeness matters

**Use Qwen as Checker when:**
- Independent review from different model perspective
- Structured findings with severity classification
- Architecture and TDD compliance validation

**Use Qwen as Tester when:**
- Coverage threshold enforcement needed
- Evidence capture (outputs, screenshots) required
- CLI and UI validation workflows

**Use Qwen as Planner when:**
- PRD needs breakdown into executable slices
- Acceptance criteria must be testable
- Dependencies and risks need identification

### 7.6.4 Multi-Provider Routing (Recommended)

For best independence, route different roles to different providers:

```yaml
# Recommended: Different providers for Doer/Checker independence
routing_rules:
  feature:
    backend:
      doer: qwen          # Qwen implements with TDD
      checker: claude     # Claude reviews independently
      tester: gemini      # Gemini validates
  bug:
    medium_risk:
      doer: qwen
      checker: codex
      tester: qwen
```

### 7.6.5 Qwen Configuration in agents.yaml

```yaml
# scripts/agents.yaml
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
```

### 7.6.6 Qwen Runner Module

The Qwen runner is implemented at `system/orchestrator/runners/qwen_runner.py`:

```python
from system.orchestrator.runners.qwen_runner import QwenRunner, QwenRunnerConfig

# Create Qwen runner for Doer role
config = QwenRunnerConfig(
    name="qwen-doer",
    project_dir=Path("."),
    prompt="Implement feature X with TDD",
    instructions=[
        "agents/my-instructions.md",
        "agents/core.instructions.md",
    ],
    role="doer",
)
runner = QwenRunner(config)
result = await runner.run()
```

### 7.6.7 Qwen Artifact Output

Qwen produces artifacts following repository conventions:

| Artifact Type | Location | Format |
|---|---|---|
| Plan files | `agents/docs/feat-<name>.jsonl` | JSONL |
| Review files | `docs/operational/reviews/<task-name>.<timestamp>.md` | Markdown |
| Test reports | `docs/operational/tests/<task-name>.<timestamp>.md` | Markdown |
| Test artifacts | `docs/operational/tests/artifacts/<task-name>.<timestamp>/` | Screenshots, logs |
| Lessons | `.breqy/lessons/<task-id>.yaml` | YAML |

### 7.6.8 Integration Checklist

- [x] Qwen instructions documented (`agents/my-instructions.md`)
- [x] Qwen runner implemented (`system/orchestrator/runners/qwen_runner.py`)
- [x] Routing configuration added (`scripts/agents.yaml`)
- [x] AI delivery approach updated (`docs/ai_delivery_approach_v_1.md`)
- [x] Integration guide created (`docs/qwen_integration.md`)

---

# 8. Branching and Merge Strategy

## 8.1 Branching philosophy

Branching exists to support controlled progression, not to create complexity for its own sake.

The branch strategy should support:

- safe parallel work
- clear promotion paths
- deterministic CI
- QA validation
- controlled production release
- easy rollback

## 8.2 Recommended branch structure

Default recommendation:

- `main` — production-ready branch, source of truth for released code
- `dev` — integration branch for ongoing development
- `release/<version>` — optional stabilization branch for release candidates
- task branches — short-lived branches per shaped task

Do not add a permanent `qa` branch unless you truly need environment-specific code promotion by branch. In most teams, a dedicated `qa` branch creates unnecessary drift. Prefer environment promotion through deployments and release branches, not a long-lived branch per environment.

### Recommended standard

For most projects:

- `main`
- `dev`
- `feature/<task-id>-<slug>`
- `bugfix/<task-id>-<slug>`
- `refactor/<task-id>-<slug>`
- `hotfix/<task-id>-<slug>`
- `release/<version>` when needed

## 8.3 When branches are created

### PRD / planning stage

No implementation branch yet. Planning artifacts may live in docs or issue comments.

### Shaped task becomes executable

The orchestrator creates a short-lived task branch when:

- dependencies are satisfied
- the task is shaped
- test obligations are defined
- the task is assigned to a Doer

Examples:

- `feature/BRQ-144-session-resume-flow`
- `bugfix/BRQ-201-reconnect-duplication`
- `refactor/BRQ-233-session-service-cleanup`

## 8.4 Branch source rules

Recommended defaults:

- features branch from `dev`
- normal bugfixes branch from `dev`
- refactors branch from `dev`
- hotfixes branch from `main`
- release branches branch from `main` or a stable `dev` cutoff, depending on release process

## 8.5 Merge path rules

Recommended path:

### For normal features, bugs, refactors

`task branch -> PR into dev -> optional release branch -> main`

### For hotfixes

`hotfix branch -> PR into main -> back-merge or cherry-pick into dev`

This avoids bypassing integration.

## 8.6 Why not merge task branches directly to main

Direct-to-main merges should be reserved for urgent hotfixes or very mature trunk-based teams with strong safeguards.

In this model, the safer default is:

- `dev` is where shaped tasks integrate
- `main` is where approved release content lands

## 8.7 When release branches are needed

Use a release branch when:

- multiple completed tasks need stabilization together
- QA/UAT needs a frozen candidate
- you need selective inclusion/exclusion before production
- production releases are scheduled, not continuous

Example:

- `release/2026.03.15`

## 8.8 Merge requirements

A branch may only be merged when all applicable gates pass:

- shaped task exists and matches the branch
- required reports exist
- checker findings resolved
- deterministic CI green
- required API/TUI/QA automation green
- lessons artifact created for non-trivial work
- human approval present

## 8.9 Branch ownership

- Orchestrator creates and tracks task branches
- Doer writes to task branch
- Checker comments or proposes patches, but should not directly own the branch by default
- QA automation may contribute test-only commits through orchestrated flow if allowed
- Human approves merges

## 8.10 Merge conflict policy

If a task branch drifts significantly from `dev`:

- orchestrator detects stale branch age or merge conflict risk
- Doer rebases or merges from `dev`
- deterministic tests rerun
- if behavior risk changed materially, Checker reruns review

## 8.11 Example branch flow

Example feature flow:

1. Shaper creates task `BRQ-144`
2. Orchestrator creates `feature/BRQ-144-session-resume-flow` from `dev`
3. Doer implements on that branch
4. PR opens from task branch into `dev`
5. Checker reviews PR
6. CI and QA pass
7. PR merges into `dev`
8. During release cut, `release/2026.03.15` branches from `dev`
9. final validation occurs
10. release merges into `main`

---

# 9. Test Strategy in the Delivery Cycle

Testing is a first-class part of the delivery model.

## 9.1 Developer-owned tests

Owned by Doer:

- unit tests
- service/component tests
- focused integration tests
- TDD scaffolding
- coverage targets

Baseline policy:

- 100% business logic coverage
- 80% overall coverage minimum
- all new critical branches tested
- tests written as part of implementation

## 9.2 Business / QA automation tests

Owned by QA Automation:

- business scenario test cases
- API automation suites
- TUI / CLI automation
- regression packs
- acceptance scenario execution

These prove the feature works in actual usage flows, not just at code-unit level.

## 9.3 Test case design before implementation

Before implementation begins, required business test cases should be identified.

Each test case should include:

- ID
- linked acceptance criterion
- preconditions
- steps
- expected result
- automation target
- owner
- status

Example:

```yaml
id: TC-TUI-017
criterion: Existing session resumes after reconnect
preconditions:
  - engine is running
  - at least one prior session exists
steps:
  - launch TUI
  - view session list
  - select prior session
  - send follow-up message
expected:
  - same session thread opens
  - message is appended to same session
automation_tool: pexpect
status: automated
```

## 9.4 API automation

API features should have explicit automation coverage.

Recommended layers:

- curated business/API regression suites
- schema-driven API validation
- auth / validation / error scenario coverage
- contract regression

## 9.5 TUI automation

If the project includes a TUI or CLI-driven workflow, required user flows should be automated.

Examples:

- startup / reconnect flows
- navigation flows
- session selection
- command execution flows
- error / retry handling

## 9.6 Test gate philosophy

A task cannot be marked done based only on developer tests.

Required evidence may include:

- unit tests passed
- coverage thresholds met
- API automation passed
- TUI automation passed
- critical regression suite passed
- acceptance criteria mapped to tests

---

# 10. Feature Path vs Refactor Path

## 10.1 Why this distinction matters

The workflow must not assume all meaningful work is feature delivery. Refactors often change architecture, boundaries, responsibilities, or internal structure while preserving behavior.

A feature-oriented evidence model alone is not enough.

## 10.2 Feature path evidence

For features, evidence usually includes:

- new or changed acceptance criteria
- unit and integration test additions
- business scenario automation
- API or TUI validation where relevant
- coverage expectations

## 10.3 Refactor path evidence

For refactors, evidence should focus on no-regression and structural soundness.

Required evidence may include:

- existing relevant tests still pass
- no-regression suite passes
- public contract compatibility maintained, or change explicitly approved
- Checker performs structural validation
- performance or reliability does not regress beyond accepted threshold
- architecture intent is better aligned after the change

## 10.4 Structural validation responsibilities

For refactors, the Checker should explicitly evaluate:

- boundary clarity
- dependency direction
- duplication reduction
- removal of dead code
- preservation of public behavior
- whether the refactor actually improved the target structure

## 10.5 Coverage policy for refactors

Existing coverage may already be sufficient. The goal is not to force artificial test churn.

For refactors:

- preserve or improve relevant coverage
- add tests only where structure changes reveal untested critical behavior
- require no-regression evidence
- require structural validation

---

# 11. Checker Independence Policy

## 11.1 Why independence matters

If the Checker uses the same reasoning path and tools as the Doer, there is a real risk of consensus hallucination: both roles agree on a flawed implementation.

## 11.2 Minimum independence requirement

The Checker must be independent in at least one meaningful dimension, and preferably more than one for higher-risk work.

Possible dimensions:

- different LLM provider or model family
- different role instructions
- different toolchain
- deterministic scanners
- independent test execution
- separate prompt context

## 11.3 High-risk tasks

For medium/high-risk tasks, require both:

- a different model/provider or genuinely separate review context
- objective tooling such as linter, static analysis, security scanning, contract validation, or deterministic test evidence

## 11.4 Checker output requirements

Checker output should not be only prose. It should include:

- status (`pass` / `fail`)
- severity-ranked findings
- impacted files or components
- missing test concerns
- recommended next action

Example:

```yaml
status: fail
severity_summary:
  high: 1
  medium: 2
findings:
  - severity: high
    file: tui/session_list.py
    issue: empty-state path not handled
  - severity: medium
    file: tests/tui/test_session_resume.py
    issue: duplicate-thread assertion is too weak
recommended_next_action: return_to_doer
```

---

# 12. Stage-by-Stage Execution

## 12.1 Stage 1 — PRD Intake

Inputs:

- PRD / intent docs
- architecture constraints
- backlog priorities
- prior lessons learned
- relevant standards

Outputs:

- PRD record
- planning request
- source-of-truth links

## 12.2 Stage 2 — Planning / Shaping

Activities:

- break PRD into executable slices
- identify workstreams
- identify dependencies
- identify required test levels
- identify open questions
- produce plan and TODO list

Outputs:

- implementation plan
- shaped tasks
- dependency order
- initial test obligations
- open question list

## 12.3 Stage 3 — Branch Preparation

Activities:

- verify task is shaped and ready
- verify dependencies complete
- create task branch
- attach branch metadata to task record

Outputs:

- branch name
- branch source
- task-to-branch linkage

## 12.4 Stage 4 — Test Case Design

Activities:

- create business test cases
- map criteria to tests
- decide API/TUI/UI automation needs
- identify regression packs to update

Outputs:

- test case definitions
- automation targets
- test suite mapping

## 12.5 Stage 5 — Doer Implementation

Activities:

- implement the slice
- follow TDD policy
- add or update unit tests
- document assumptions
- produce implementation notes

Required outputs:

- code diff
- unit tests
- implementation notes
- known risks / follow-ups

## 12.6 Stage 6 — Checker Review

Activities:

- review correctness
- review architectural fit
- review scope adherence
- review adequacy of unit tests
- identify missed edge cases and weak assertions

Required outputs:

- structured review artifact
- severity-classified findings
- explicit pass/fail recommendation

## 12.7 Stage 7 — Deterministic Test Validation

Activities:

- run lint
- run typecheck
- run unit/integration tests
- measure coverage
- run contract/static checks

Required outputs:

- machine-readable test report
- coverage report
- pass/fail result

## 12.8 Stage 8 — QA Automation / Business Validation

Activities:

- execute automated business scenarios
- run API regression packs
- run TUI / workflow regression where required
- compare results to acceptance criteria

Required outputs:

- test execution report
- failed scenario summaries
- criterion-to-evidence mapping

## 12.9 Stage 9 — Merge Readiness Review

Activities:

- confirm all required artifacts exist
- confirm merge target is correct
- confirm branch is current enough
- confirm release path

Required outputs:

- merge-readiness summary
- target branch decision

## 12.10 Stage 10 — Rework Loop

Possible return paths:

- Checker findings → Doer
- failed developer tests → Doer
- missing or broken automation → QA Automation
- ambiguous acceptance criteria → human sponsor / Shaper

Rework should be bounded:

- max loop count should be tracked
- repeated failures should trigger escalation
- root-cause patterns should be captured

## 12.11 Stage 11 — Lessons Learned

Activities:

- identify first avoidable miss
- identify repeated correction patterns
- identify missing instruction or missing tests
- propose reusable improvements

Outputs:

- what went wrong
- what went well
- missed assumptions
- proposed instruction changes
- proposed test / checklist / skill updates
- machine-readable lesson artifact

## 12.12 Stage 12 — Human Review and Merge

Final authority reviews:

- PR quality
- evidence completeness
- residual risk
- lessons output
- instruction-promotion proposals

Only after approval should the task be merged and marked done.

---

# 13. Artifact Requirements

Each task should produce a consistent artifact set.

Recommended structure:

```text
/ai-artifacts/<task_id>/
  task-envelope.yaml
  branch-info.yaml
  test-cases.yaml
  doer-report.json
  checker-report.yaml
  deterministic-test-report.json
  qa-automation-report.json
  merge-readiness.yaml
  lessons.yaml
  lessons-learned.md
  instruction-update-proposal.md
```

Artifacts make the workflow auditable, repeatable, measurable, and improvable.

---

# 14. Machine-Readable Lessons

## 14.1 Why structured lessons are required

Lessons learned should not exist only as prose. If lessons are structured, future agents can ingest them automatically before starting new work.

## 14.2 Storage recommendation

Use one file per task, for example:

```text
.breqy/lessons/<task-id>.yaml
```

or, if co-located with run artifacts:

```text
/ai-artifacts/<task-id>/lessons.yaml
```

## 14.3 Minimum lessons schema

```yaml
task_id: BRQ-144
task_type: feature
discovered_in_stage: qa_automation
first_avoidable_miss: reconnect flow was not included in doer test design
root_cause_class:
  - missing_test_obligation
  - weak_checker_focus
symptoms:
  - duplicate thread created after restart
impact:
  severity: medium
  user_visible: true
reusable_fix:
  - add restart-plus-resume regression template
  - require reconnect path in session-related tasks
instruction_update_proposal:
  target: doer.md
  change: For session lifecycle work, always include reconnect and resume path tests
promotion_scope: project
status: proposed
```

## 14.4 How lessons are used

Before starting a new task, the orchestrator should be able to load relevant lessons by:

- component
- task type
- failure class
- impacted interface
- prior repeated misses

---

# 15. Repository Structure Recommendation

```text
/docs/
  /intent/
    prd.md
    architecture-intent.md
    acceptance-criteria.md
  /delivery/
    delivery-approach.md
    definition-of-done.md
    review-checklist.md
    test-strategy.md
    branch-policy.md
  /lessons/
    lessons-log.md
    instruction-change-proposals.md

/.agents/
  planner.md
  doer.md
  checker.md
  tester.md
  qa-automation.md
  lessons-learned.md

/.skills/
  shape-prd/
    SKILL.md
  implement-feature/
    SKILL.md
  review-pr/
    SKILL.md
  generate-tests/
    SKILL.md
  qa-api-regression/
    SKILL.md
  qa-tui-regression/
    SKILL.md
  update-instructions/
    SKILL.md

/.breqy/
  /lessons/

/ai-artifacts/

/tests/
  unit/
  integration/
  api/
  tui/
  e2e/
```

---

# 16. Definition of Done

A feature or refactor is done only when all applicable conditions are satisfied.

Mandatory done conditions:

- implementation exists and is reviewable
- acceptance criteria or refactor objectives are addressed
- required unit tests exist
- coverage thresholds are met where applicable
- checker findings are resolved
- deterministic CI passes
- required API / TUI / QA automation passes
- merge target and path are correct
- lessons learned artifact exists
- human owner approves merge

Not sufficient on their own:

- code compiles
- AI says feature is complete
- unit tests pass
- one reviewer says “looks fine”
- demo worked once manually

---

# 17. Implementation Roadmap

## Phase 1 — Manual-but-disciplined baseline

Implement:

- issue template
- PRD intake template
- shaping output format
- task envelope format
- branch policy
- agent role markdown files
- artifact folder structure
- basic CI gates
- lessons-learned template

## Phase 2 — Structured orchestration

Implement:

- orchestrator script/service
- explicit state machine
- role routing logic
- artifact generation
- automated report collection
- branch creation logic
- test-case mapping enforcement
- GitHub integration
- CI result ingestion

## Phase 3 — Bounded LLM-assisted orchestration

Add LLM assistance to the orchestrator for:

- PRD-to-plan decomposition
- task classification
- failure summarization
- lessons extraction
- instruction update proposals

Deterministic gating remains outside the LLM.

## Phase 4 — Continuous orchestration

Implement:

- daemon/service mode
- backlog watching
- automatic low-risk transitions
- dashboards
- historical trend analysis
- selective automation of instruction promotion

---

# 18. Anti-Patterns to Avoid

Avoid the following:

1. Letting all agents write to the same feature branch
2. Treating coverage as proof of business correctness
3. Skipping shaping because “the doer will figure it out”
4. Allowing agents to self-certify completion
5. Auto-promoting instruction changes without review
6. Using unstructured prompts instead of repo-anchored instructions
7. Running only developer tests and calling it fully tested
8. Treating lessons learned as optional documentation overhead
9. Creating too many long-lived branches and letting them drift
10. Using the same reasoning stack for Doer and Checker on meaningful work

---

# 19. Summary

This delivery approach is designed to turn AI assistance into a governed engineering system rather than an ad hoc coding experience.

The essential model is:

- shape the work
- define testable outcomes
- create the correct task branch
- let one role implement
- let independent roles review and validate
- require executable evidence
- merge only through approved paths
- capture lessons
- improve the instructions

That is how a PRD becomes a fully tested feature and how each task contributes to making the next task better.
