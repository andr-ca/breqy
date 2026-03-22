# State: Breqy

**Milestone:** M1 — Slice 1 Full Build
**Created:** 2026-03-22
**Last updated:** 2026-03-22 (Phase 04 complete)

---

## Project Reference

**Core Value:** A reliable, always-on engine that accepts connections from a TUI, maintains persistent sessions across restarts, and lets the default agent perform approved Linux admin and filesystem tasks with full user visibility and control.

**Current Focus:** Phase 04 (Policy & Approvals) complete — ready to implement Phase 5 (Engine Runtime)

---

## Current Position

**Current Phase:** 5 (Engine Runtime — next)
**Current Plan:** None
**Status:** Phase 04 complete; Phase 05 not yet planned

### Progress Bar

```
Phase:  [ 1 ][ 2 ][ 3 ][ 4 ][ 5 ][ 6 ][ 7 ][ 8 ][ 9 ][10]
         ●    ●    ●    ●    ○    ○    ○    ○    ○    ○
         Domain Storage A2A  Pol  Eng  Tool Mem  Agt  Ses  TUI
```

**Legend:** ○ Not started · ◑ In progress · ● Complete

---

## Phase Status

| Phase | Name | Requirements | Status |
|-------|------|--------------|--------|
| 1 | Domain Foundation | DOM-01–05 (5) | **Complete** |
| 2 | Storage Layer | STR-01–05 (5) | **Complete** |
| 3 | Config, Secrets & A2A Protocol | CFG-01–04, A2A-01–05 (9) | **Complete** |
| 4 | Policy & Approvals | POL-01–06 (6) | **Complete** |
| 5 | Engine Runtime | ENG-01–06 (6) | Not started |
| 6 | Tools | TOOL-01–06 (6) | Not started |
| 7 | Memory | MEM-01–05 (5) | Not started |
| 8 | Agent Runtime & Auth | AGT-01–11 (11) | Not started |
| 9 | Sessions & Control | SES-01–08 (8) | Not started |
| 10 | TUI Client | TUI-01–13 (13) | Not started |

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Requirements defined | 57 |
| Requirements mapped | 57 |
| Phases planned | 10 |
| Plans written | 12 (Phase 1: 4, Phase 2: 4, Phase 3: 2, Phase 4: 2) |
| Plans complete | 12 |
| Tests written | 442 total |
| Tests passing | 442 |

---

## Accumulated Context

### Key Decisions Made

| Decision | Context |
|----------|---------|
| Fine granularity (10 phases) | 57 requirements across 11 natural category groups; fine granularity preserves clean delivery boundaries per category cluster |
| CFG + A2A combined into Phase 3 | Both are infrastructure/transport prerequisites for ENG; batching them avoids a one-req phase for CFG alone |
| Memory after Tools (Phase 7 after Phase 6) | MEM depends on both STR (persistence) and the MCP memory tool (TOOL-06); must follow tools layer |
| SES before TUI (Phase 9 before Phase 10) | TUI depends on all session/control capabilities being live; session layer is the final backend phase |
| Session.workspace → workspace_paths: list[str] | DB schema uses TEXT column with JSON; aligned domain model in Phase 2 |
| Task.agent_id: str \| None = None | DB schema has nullable agent_id column; added to domain model in Phase 2 |
| Event.agent_id/correlation_id default "" | DB schema has NOT NULL DEFAULT ''; changed from Optional to required-defaulted str |
| ToolInvocation.created_at → started_at | DB schema column name is started_at |
| Participant.left_at: datetime \| None = None | DB schema has nullable left_at column; added to domain model |
| ApprovalDecision fields aligned to DB | granted: bool, extend_to_session: bool, reason: str, decided_at: datetime |
| MessageRole.ASSISTANT (not AGENT) | Phase 1 enum uses ASSISTANT; plan spec said AGENT — ASSISTANT is correct |
| AgentConfig.engine_socket reads BREQY_ENGINE_SOCKET | Aligned with EngineConfig so both track the same socket path |
| AgentConfig.log_path: str \| None = None | Optional is more explicit than empty-string sentinel |
| A2A uses length-prefixed JSON frames | 4-byte big-endian uint32 prefix + UTF-8 JSON body; no other framing scheme |
| Integration tests use asyncio.sleep(0.1) | Stability buffer for Unix socket connection establishment in test environments |
| PolicyAction enum: ALLOW, DENY, REQUIRE_APPROVAL | NOT "APPROVE" — confirmed from domain enums |
| FilesystemPolicyChecker sorts by path depth | Uses len(PurePosixPath(r.path_pattern).parts) not len(str) to be robust against trailing slashes |
| ApprovalService prunes _pending in decide() | Prevents memory leak when decide() is called without a corresponding wait_for_decision() |
| ApprovalService double-decide: raises ValueError | After _pending prune in decide(), second call raises "No pending approval" (semantically correct) |
| structlog used throughout policy modules | structlog.get_logger(__name__) — not stdlib logging |

### Architectural Dependencies Encoded in Phases

```
Phase 1 (DOM)
  └─► Phase 2 (STR)
  └─► Phase 3 (CFG + A2A)
        └─► Phase 4 (POL)
              └─► Phase 5 (ENG)
                    └─► Phase 6 (TOOL)
                          └─► Phase 7 (MEM)
                    └─► Phase 8 (AGT)
                          └─► Phase 9 (SES)
                                └─► Phase 10 (TUI)
```

### Active Todos

- [ ] Run `/gsd-plan-phase 5` to decompose Phase 5 (Engine Runtime) into executable plans

### Active Blockers

None.

### Open Questions

None.

---

## Session Continuity

**To resume from this state:**
1. Read `.planning/ROADMAP.md` to understand current phase and progress
2. Read `.planning/REQUIREMENTS.md` for requirement traceability
3. Check which phases are complete in the Progress Table
4. Run `/gsd-plan-phase N` for the next incomplete phase

**Files to check first:**
- `.planning/ROADMAP.md` — phase structure and success criteria
- `.planning/REQUIREMENTS.md` — requirement traceability
- `.planning/STATE.md` — this file, project memory

---
*State initialized: 2026-03-22 after roadmap creation*
