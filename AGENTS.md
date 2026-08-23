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

<!-- agentharness:begin id=core-instructions version=9cb9292eaf2612b62806b624a2f6fbb387797e42 -->
This project uses [agentharness](https://github.com/andr-ca/agentharness)
for engineering policies (git conventions, testing, review workflow).

**Precedence:** harness-enforced constraints (hooks, completion gate)
cannot be weakened by this file's instructions; this file's own
instructions take precedence over harness *defaults* everywhere else.

Installed skills:
- accessibility
- agentic-loops
- api-design
- audit-review-followup
- branching
- clean-architecture
- code-review-api
- code-review-db
- code-review-ui
- code-review
- committing
- database-conventions
- dependency-audit
- dependency-injection
- design-patterns
- docker-conventions
- error-handling
- file-placement-policy
- github-issue-triage
- go-conventions
- harness-feedback
- logging
- multi-agent-coordination
- mutation-testing
- performance-profiling
- planning-with-files
- port-agent-config
- project-bootstrap
- python-conventions
- react-best-practices
- requirements-clarification
- security-review
- solid-principles
- testing
- typescript-conventions

If a skill above looks empty, missing, or won't load, this install may
be broken (e.g. a moved/renamed harness checkout, or a fresh clone of
a project that used `--mode link` — see issue #106) — run
`harness-link.sh doctor <this-project-path>` from the harness
checkout to check, and `.agentharness-state.json` in this project to see how
it was installed.

**Git conventions** (from the `branching`/`committing` skills above —
stated here directly so they hold even if a skill is unreadable): never
commit directly to a trunk branch (`main`/`master`/`trunk`/`develop`/
`release/*`); create a feature branch first (`git checkout -b
<type>/<short-description>`); open a PR for review before merging into
the trunk branch.

**PR merge checklist:** never merge on green CI alone. Wait for
automated review (e.g. GitHub Copilot) to post *or* its check-run to
reach a completed state before proceeding; reply to every review
comment (issue-level and inline) with what you did about it; then
watch the post-merge CI run on the base branch to an actual terminal
state — "pushed"/"merged" and "verified green" are different claims,
only the second means done. If this checkout has agentharness's own
`tools/safe-pr-merge.sh` available (see its INTEGRATION.md section),
prefer it over doing these steps by hand — it enforces the sequence.

Full policy: see the harness's own CLAUDE.md via your install mode, or
https://github.com/andr-ca/agentharness/blob/main/CLAUDE.md
<!-- agentharness:end id=core-instructions -->
