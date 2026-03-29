# State: Breqy

**Milestone:** M2 — v1.1 Provider/Model Runtime Switching
**Created:** 2026-03-29
**Last updated:** 2026-03-29 (M2 Complete — all 6 phases done)

---

## Project Reference

**Core Value:** A reliable, always-on engine that accepts connections from a TUI, maintains persistent sessions across restarts, and lets the default agent perform approved Linux admin and filesystem tasks with full user visibility and control.

**Current Focus:** M2 Complete

---

## Current Position

**Current Phase:** 6 (Integration Polish) — COMPLETE
**Status:** Milestone complete

### Progress Bar

```
Phase:  [ 1 ][ 2 ][ 3 ][ 4 ][ 5 ][ 6 ]
         ●    ●    ●    ●    ●    ●
         DOM  Prov  Agt  Eng  TUI  Int
```

**Legend:** ○ Not started · ◑ In progress · ● Complete

---

## Phase Status

| Phase | Name | Requirements | Status | Tests | Commit |
|-------|------|--------------|--------|-------|--------|
| 1 | Domain Events & Models | MAE-01 (1) | **Complete** | 32 | `c3e18bd` |
| 2 | Provider list_models() | MDL-03–05 (3) | **Complete** | 16 | `d01b6d6` |
| 3 | Agent Runtime | MDL-02, MSW-03–05, MAI-01–02 (6) | **Complete** | 12 | `6be63fb` |
| 4 | Engine Routing | MAE-02–03 (2) | **Complete** | 8 | `5bf6ba1` |
| 5 | TUI Wiring | MDL-01, MSW-01–02, MAI-03 (4) | **Complete** | 25 | `f06e6cc` |
| 6 | Integration Polish | Cross-cutting E2E | **Complete** | 20 | `6c18aa2` |

---

## Phase 6 Summary

Phase 6 completed in 4 sub-tasks (6a–6d), all following TDD Red→Green:

| Sub-task | Scope | Tests |
|----------|-------|-------|
| 6a | Deadlock prevention: `_model_list_pending` cleared on disconnect, 15s timeout, late-response guard | 7 |
| 6b | Runtime error handling: `_NullProvider.list_models()`, try/except in list/switch handlers | 6 |
| 6c | `credential_store` extraction: `_create_credential_store()`, pass through `_build_provider()` and `main()` | 2 |
| 6d | Switching UX: `AgentStatusBar.set_switching()`, yellow "switching..." display, triggered from model select | 5 |

Sub-task 6e (`is_authenticated` in `ModelOption`) was cancelled — not required by success criteria.

**Files changed:**
- `breqy/agents/runtime.py` — `_NullProvider.list_models()`, try/except in `_handle_model_list()` and `_handle_model_switch()`, `_create_credential_store()`, `_build_provider()` accepts `credential_store` kwarg, `main()` extracts and passes credential_store
- `breqy/tui/app.py` — `_model_list_pending` cleared on disconnect, 15s timeout timer, late-response guard, loading notification on `ctrl+m`, `_handle_agent_disconnected()`
- `breqy/tui/widgets/agent_status.py` — `_switching` flag, `set_switching()`, yellow "switching..." in `_refresh_display()`

**Test files changed:**
- `tests/tui/test_app.py` — 8 new tests (deadlock prevention + switching trigger)
- `tests/tui/test_agent_status.py` — 4 new tests (switching state)
- `tests/unit/agents/test_runtime_model_switch.py` — 8 new tests (null provider, error handling, credential store)
- `tests/unit/agents/test_runtime.py` — 1 test updated (signature change)

**Total test count:** 1483 (up from 1463)

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Requirements defined | 16 |
| Requirements mapped | 16 |
| Phases planned | 6 |
| Phases complete | 6 |
| Tests written (M2) | 113 |
| Tests passing | 1483 total |

---

## Accumulated Context

### Key Decisions Made

| Decision | Context |
|----------|---------|
| 4 new A2A event types | `model.info`, `model.list.requested`, `model.list.response`, `model.switch.requested` — extend existing typed event system |
| No explicit busy guard | Serial `run()` listen loop naturally queues switch events until `handle_work()` completes |
| `list_models()` is concrete, not abstract | Existing providers work without override; only CopilotProvider overrides with HTTP query |
| Hardcoded fallback model lists | Subprocess providers (claude, codex, gemini, qwen) can't query models dynamically; fallback dicts provided |
| `CredentialStore` extraction | Created in `main()` and injected into both provider builder and AgentRuntime |
| Ephemeral switching | Runtime switch is session-only; `agent.yaml` is not mutated |
| `asyncio.to_thread()` for sync `list_models()` | Copilot HTTP calls are synchronous; wrap in thread from async runtime |
| `ModelEntry` → `ModelOption` conversion in TUI | Domain uses `ModelEntry`; existing TUI `ModelSelectScreen` uses `ModelOption` dataclass |
| Same-model guard | Skip provider rebuild when same provider/model selected |
| Switch failure preserves old provider | Assignment only on success; error sent as system message + old model `ModelInfoEvent` |
| Auth on demand | Provider object created immediately on switch; auth happens on first `stream()` via existing notice pattern |
| `ctrl+m` request flow | Changed from direct push to request→response: sends `ModelListRequestedEvent`, waits for `ModelListResponseEvent`, then pushes `ModelSelectScreen` |
| Debounce via `_model_list_pending` flag | Prevents duplicate `ctrl+m` requests while one is in flight; cleared on response, disconnect, and timeout |
| 15s timeout on model list request | Prevents UI hanging if agent doesn't respond; clears pending flag and shows notification |
| Late response guard | Ignores `ModelListResponseEvent` that arrives after timeout |
| `_NullProvider.list_models()` returns empty | Consistent with null pattern; no models available when no real provider |
| Switch error preserves old provider | try/except wraps `_build_provider()`; old provider stays, error message sent, old model info re-announced |

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

None — M2 complete.

### Active Blockers

None.

### Open Questions

None.

---

## Prior Milestones

**M1 — Slice 1 Full Build**: 10/10 phases complete, 1370+ tests, all passing.
See `.planning/MILESTONES.md` for summary.

---

## Session Continuity

**M2 is complete.** To start the next milestone:
1. Read `.planning/MILESTONES.md` for milestone history
2. Read `.planning/ROADMAP.md` for phase structure
3. Decide scope of M3 with the user

---
*State updated: 2026-03-29 — M2 complete, Phase 6 committed (`6c18aa2`), 1483 tests passing*
