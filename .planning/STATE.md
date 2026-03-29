# State: Breqy

**Milestone:** M2 — v1.1 Provider/Model Runtime Switching
**Created:** 2026-03-29
**Last updated:** 2026-03-29 (M2 initialized)

---

## Project Reference

**Core Value:** A reliable, always-on engine that accepts connections from a TUI, maintains persistent sessions across restarts, and lets the default agent perform approved Linux admin and filesystem tasks with full user visibility and control.

**Current Focus:** M2 Phase 1 — Domain Events & Models

---

## Current Position

**Current Phase:** 1 (Domain Events & Models)
**Current Plan:** Not yet planned
**Status:** Starting

### Progress Bar

```
Phase:  [ 1 ][ 2 ][ 3 ][ 4 ][ 5 ][ 6 ]
         ○    ○    ○    ○    ○    ○
         DOM  Prov  Agt  Eng  TUI  Int
```

**Legend:** ○ Not started · ◑ In progress · ● Complete

---

## Phase Status

| Phase | Name | Requirements | Status |
|-------|------|--------------|--------|
| 1 | Domain Events & Models | MAE-01 (1) | **Not started** |
| 2 | Provider list_models() | MDL-03–05 (3) | **Not started** |
| 3 | Agent Runtime | MDL-02, MSW-03–05, MAI-01–02 (6) | **Not started** |
| 4 | Engine Routing | MAE-02–03 (2) | **Not started** |
| 5 | TUI Wiring | MDL-01, MSW-01–02, MAI-03 (4) | **Not started** |
| 6 | Integration Polish | Cross-cutting E2E | **Not started** |

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Requirements defined | 16 |
| Requirements mapped | 16 |
| Phases planned | 6 |
| Plans written | 0 |
| Plans complete | 0 |
| Tests written | 0 (M2-specific) |
| Tests passing | All existing (M1) |

---

## Accumulated Context

### Key Decisions Made

| Decision | Context |
|----------|---------|
| 4 new A2A event types | `model.info`, `model.list.requested`, `model.list.response`, `model.switch.requested` — extend existing typed event system |
| No explicit busy guard | Serial `run()` listen loop naturally queues switch events until `handle_work()` completes |
| `list_models()` is concrete, not abstract | Existing providers work without override; only CopilotProvider overrides with HTTP query |
| Hardcoded fallback model lists | Subprocess providers (claude, codex, gemini, qwen) can't query models dynamically; fallback dicts provided |
| `CredentialStore` extraction | Currently created inside `_build_provider()` — extract to `main()` and inject into both provider builder and AgentRuntime |
| Ephemeral switching | Runtime switch is session-only; `agent.yaml` is not mutated |
| `asyncio.to_thread()` for sync `list_models()` | Copilot HTTP calls are synchronous; wrap in thread from async runtime |
| `ModelEntry` → `ModelOption` conversion in TUI | Domain uses `ModelEntry`; existing TUI `ModelSelectScreen` uses `ModelOption` dataclass |
| Same-model guard | Skip provider rebuild when same provider/model selected |
| Switch failure preserves old provider | Assignment only on success; error sent as system message + old model `ModelInfoEvent` |
| Auth on demand | Provider object created immediately on switch; auth happens on first `stream()` via existing notice pattern |

### Architectural Dependencies

```
Phase 1 (Domain Events & Models)
  └─► Phase 2 (Provider list_models)
  └─► Phase 4 (Engine Routing)
        └─► Phase 5 (TUI Wiring)
  Phase 2
    └─► Phase 3 (Agent Runtime)
          └─► Phase 5 (TUI Wiring)
                └─► Phase 6 (Integration Polish)
```

### Active Todos

- [ ] Plan and execute Phase 1: Domain Events & Models

### Active Blockers

None.

### Open Questions

None.

---

## Prior Milestone

**M1 — Slice 1 Full Build**: 10/10 phases complete, 1370+ tests, all passing.
See `.planning/MILESTONES.md` for summary.

---

## Session Continuity

**To resume from this state:**
1. Read `.planning/ROADMAP.md` (M2 section) for phase structure and success criteria
2. Read `.planning/REQUIREMENTS.md` (v1.1 section) for requirement traceability
3. Read `docs/superpowers/specs/2026-03-29-provider-model-display-switching-design.md` for approved design
4. Check which phases are complete in the M2 Progress Table
5. If the next incomplete phase has no plans yet, plan it; otherwise resume execution

**Files to check first:**
- `.planning/ROADMAP.md` — M2 phase structure and success criteria
- `.planning/REQUIREMENTS.md` — v1.1 requirement traceability
- `.planning/STATE.md` — this file, project memory
- `docs/superpowers/specs/2026-03-29-provider-model-display-switching-design.md` — approved design spec

---
*State initialized: 2026-03-29 for M2*
