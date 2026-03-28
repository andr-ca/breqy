# AGENTS.md

This file is the mandatory starting point for all AI agents and coding assistants working in this repository.

## REQUIRED: Read All Instructions Before Any Work

Read these files in order before writing any code, creating any file, or making any decision:

| Priority | File | Purpose |
|---|---|---|
| 1 | [agents/core.instructions.md](agents/core.instructions.md) | Branch safety, TDD enforcement, documentation, git workflow, coverage thresholds, commit rules |
| 2 | [agents/project.instructions.md](agents/project.instructions.md) | Project architecture, domain model, tech stack, Slice 1 scope, hard constraints |
| 3 | [agents/python.instructions.md](agents/python.instructions.md) | Python 3.12 modular design, DI patterns, SOLID, import rules, testing patterns |
| 4 | [agents/tdd.instructions.md](agents/tdd.instructions.md) | Red-Green-Refactor cycle, TDD workflow steps, test quality standards |
| 5 | [agents/troubleshooting.instructions.md](agents/troubleshooting.instructions.md) | Runtime debugging: ID mismatches, event handler gaps, subprocess issues, message flow tracing |

These instructions are authoritative. If there is a conflict between a general coding convention and a project instruction, project instructions win. If there is a conflict between project instructions and core instructions, core instructions win (they encode safety and process rules).

---

## Start of Every Session

Before any file operation or code change:

1. Read all four instruction files above
2. Check current branch: `git status -sb && git branch -a`
3. Confirm branch with the user before proceeding
4. Never commit directly to `main`, `master`, `develop`, or `sandbox*`

---

## Project Folder Structure

```
./
├─ AGENTS.md                         # This file — mandatory entrypoint
├─ README.md
├─ pyproject.toml
│
├─ agents/                           # Agent instruction files
│  ├─ core.instructions.md           # Branch, TDD, docs, git, coverage
│  ├─ project.instructions.md        # Project architecture and constraints
│  ├─ python.instructions.md         # Python 3.12 modular dev and DI
│  ├─ tdd.instructions.md            # Red-Green-Refactor workflow
│  ├─ troubleshooting.instructions.md # Runtime debugging knowledge
│  └─ config-code-user-prompts/      # Role-specific agent prompts
│     ├─ developer.agent.md
│     ├─ dev-manager.agent.md
│     ├─ reviewer.agent.md
│     └─ tester.agent.md
│
├─ docs/
│  ├─ intent.md                      # Why Breqy exists, guiding principles
│  ├─ prd.md                         # Full product requirements
│  ├─ architecture.md                # Runtime topology and design decisions
│  ├─ decisions.md                   # Architecture decision records
│  ├─ delivery_model.md
│  ├─ shaped_task_schema.md
│  ├─ lessons_learned_schema.md
│  ├─ branching_strategy.md
│  ├─ roadmap.md
│  ├─ ai_delivery_approach_v_1.md    # AI-assisted delivery lifecycle
│  └─ plans/
│     └─ 2026-03-13-breqy-slice-1.md  # Active implementation plan
│
├─ breqy/                            # Main Python package
│  ├─ domain/                        # Models, enums, events, errors, IDs
│  ├─ storage/                       # Repository interfaces + SQLite impls
│  ├─ a2a/                           # A2A envelope, transport, server, client
│  ├─ engine/                        # Engine daemon: event bus, writer, router
│  ├─ agents/                        # Agent runtime
│  ├─ tui/                           # Textual TUI application
│  ├─ tools/                         # Tool implementations (shell, fs, etc.)
│  ├─ policy/                        # PolicyEvaluator, ApprovalService
│  ├─ config/                        # Config loader and settings models
│  ├─ secrets/                       # SecretProvider interface + keyring impl
│  └─ utils/
│
├─ system/                           # Orchestration agents and templates
│  ├─ agents/
│  │  ├─ planner/
│  │  ├─ doer/
│  │  ├─ checker/
│  │  ├─ tester/
│  │  └─ lessons/
│  ├─ skills/
│  ├─ prompts/
│  └─ templates/
│
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  └─ tui/
│
├─ scripts/
└─ .breqy/
   └─ guardian_logs/
```
