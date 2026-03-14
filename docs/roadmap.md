# Breqy Roadmap

Last updated: March 14, 2026

## 1. Purpose

This roadmap translates product intent and Slice 1 planning into an execution sequence with clear milestones and release gates.

Scope of this document:

- define the active delivery path for Slice 1
- define milestone exit criteria (what must be true to move forward)
- separate active work from future opportunities

Primary source documents:

- `docs/intent.md`
- `docs/prd.md`
- `docs/architecture.md`
- `docs/ai_delivery_approach_v_1.md`
- `docs/plans/2026-03-13-breqy-slice-1.md`

## 2. Roadmap Principles

1. Reliability before feature breadth.
2. Engine and typed contracts before channel polish.
3. One-writer, evidence-based completion per task.
4. No Slice 2 scope expansion until Slice 1 exit criteria are met.

## 3. Active Roadmap (Slice 1)

Slice 1 is the current target and includes 36 planned tasks across 9 chunks.

### Milestone M1: Foundation and Contracts

Objective:

- establish project foundation, core domain types, and canonical event schemas

Source tasks:

- Chunk 1 (Tasks 1-4)

Deliverables:

- project tooling and baseline package setup
- ID/enums and core domain models
- typed event schemas shared across engine/agents/TUI

Exit criteria:

- canonical envelope and core event model are defined
- domain model compiles and validates via tests
- core docs and contracts are stable enough for downstream implementation

### Milestone M2: Durable Core Infrastructure

Objective:

- implement persistent storage, A2A transport, and policy/approval/config foundations

Source tasks:

- Chunk 2 (Tasks 5-9)
- Chunk 3 (Tasks 10-13)
- Chunk 4 (Tasks 14-17)

Deliverables:

- repository interfaces + SQLite implementation with WAL mode
- migrations and canonical persistence boundaries
- framed A2A transport and server/client baseline
- policy evaluator, filesystem policy, approval service, config + secret provider abstractions

Exit criteria:

- engine-side centralized persistence flow works with no direct agent DB writes
- approvals and policy checks are auditable and enforceable
- A2A typed contracts are round-trippable in tests

### Milestone M3: Runtime Execution Path

Objective:

- deliver end-to-end engine and agent runtime with tool execution

Source tasks:

- Chunk 5 (Tasks 18-22)
- Chunk 6 (Tasks 23-25)
- Chunk 7 (Tasks 26-28)

Deliverables:

- event bus, centralized event writer, session manager
- agent registry/spawner and engine daemon shell
- tool executor, shell tool, filesystem tool
- default `breqy` agent config + runtime loop

Exit criteria:

- engine starts reliably and accepts agent registrations
- default agent can execute approved shell/filesystem actions via policy gates
- tool invocation and approval events are durably logged

### Milestone M4: TUI, Control, and Integration Hardening

Objective:

- ship user-facing Slice 1 experience and validate restart-safe operations

Source tasks:

- Chunk 8 (Tasks 29-32)
- Chunk 9 (Tasks 33-36)

Deliverables:

- TUI session list + chat + task/approval widgets + control bar
- control primitives: stop, stop-and-steer, steer, circuit-break
- end-to-end session flow and restart survival
- final validation and cleanup

Exit criteria:

- user can create/resume sessions from TUI and stream chat
- approvals/tasks/tool actions are visible and interactive in TUI
- restart survival is verified for session continuity
- full Slice 1 validation checklist is green

## 4. Release Gates for Slice 1

A Slice 1 release candidate is ready only when all gates below are satisfied:

- required implementation exists for all in-scope Slice 1 capabilities
- checker findings are resolved
- deterministic validation passes (lint/type/tests)
- required coverage thresholds are met
- documentation for implemented behavior is updated
- lessons artifact and merge-readiness evidence are present
- human sponsor approves release/merge

## 5. Tentative Delivery Windows

These windows are planning targets, not hard commitments.

- Window A: M1-M2
  - target: late March to April 2026
- Window B: M3
  - target: April to May 2026
- Window C: M4 + release gate
  - target: May to June 2026

If measured velocity or dependency risks change, update this roadmap before changing scope.

## 6. Deferred Roadmap (Not Active Yet)

The following are explicitly out of Slice 1 and should not be pulled forward without sponsor approval:

- memory retrieval/promotion automation expansion
- SSH tool
- agent delegation/handoff depth
- Docker inspection workflows
- artifact tracking enhancements
- additional channels beyond TUI

These are candidates for Slice 2 planning after Slice 1 completion evidence is accepted.

## 7. Risks and Watchpoints

- process sprawl from unmanaged agent lifecycles
- SQLite write contention if centralized writer rules are bypassed
- TUI responsiveness regressions during streaming/tool output
- scope creep from introducing Slice 2 features early

Mitigation approach:

- enforce policy and architecture constraints early
- keep milestones small and evidence-driven
- prefer finishing critical path work before parallel expansion

## 8. Roadmap Maintenance

Update this document when one of the following happens:

- milestone exit criteria changes
- scope boundary changes (Slice 1 vs Slice 2)
- release windows are re-baselined
- architecture or delivery gates materially change

Use pull requests for roadmap changes to keep timeline decisions auditable.
