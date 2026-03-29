# State: Breqy

**Milestone:** M2 — v1.1 Provider/Model Runtime Switching
**Created:** 2026-03-29
**Last updated:** 2026-03-29 (Phase 5 complete)

---

## Project Reference

**Core Value:** A reliable, always-on engine that accepts connections from a TUI, maintains persistent sessions across restarts, and lets the default agent perform approved Linux admin and filesystem tasks with full user visibility and control.

**Current Focus:** M2 Phase 6 — Integration Polish

---

## Current Position

**Current Phase:** 6 (Integration Polish)
**Status:** Ready to start

### Progress Bar

```
Phase:  [ 1 ][ 2 ][ 3 ][ 4 ][ 5 ][ 6 ]
         ●    ●    ●    ●    ●    ○
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
| 6 | Integration Polish | Cross-cutting E2E | **Not started** | — | — |

---

## Phase 5 Summary

Phase 5 completed in 5 sub-tasks (5a–5e), all following TDD Red→Green:

| Sub-task | Scope | Tests |
|----------|-------|-------|
| 5a | `AgentStatusBar.update_model_info()`, `clear_model_info()`, `_refresh_display()` with model info | 6 |
| 5b | `ChatScreen.handle_model_info()`, disconnect clears model info | 4 |
| 5c | `MODEL_INFO` + `MODEL_LIST_RESPONSE` dispatcher handlers, `ModelEntry→ModelOption` conversion | 7 |
| 5d | `ctrl+m` sends `ModelListRequestedEvent`, `_model_list_pending` debounce | 5 |
| 5e | `on_model_select_screen_model_selected()` sends `ModelSwitchRequestedEvent` | 3 |

**Files changed:**
- `breqy/tui/widgets/agent_status.py` — `_model_info` state, `update_model_info()`, `clear_model_info()`, display in `_refresh_display()`
- `breqy/tui/screens/chat.py` — `handle_model_info()`, disconnect clearing in `handle_agent_lifecycle()`
- `breqy/tui/app.py` — `_model_list_pending` flag, `MODEL_INFO`/`MODEL_LIST_RESPONSE` dispatcher handlers, `_handle_model_list_response()`, `action_push_model_select()` rewritten for request flow, `on_model_select_screen_model_selected()`, imports for `ModelInfoEvent`, `ModelListRequestedEvent`, `ModelListResponseEvent`, `ModelSwitchRequestedEvent`, `ModelOption`

**Test files changed:**
- `tests/tui/test_agent_status.py` — 6 new tests in `TestAgentStatusBarModelInfo`
- `tests/tui/test_chat_screen.py` — 4 new tests (`TestChatScreenModelInfo` + disconnect clearing)
- `tests/tui/test_app.py` — 15 new tests (`TestModelInfoDispatcher`, `TestModelListResponseDispatcher`, `TestCtrlMModelList`, `TestModelSelectedHandler`), 1 test updated

**Total test count:** 1463 (up from 1438)

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Requirements defined | 16 |
| Requirements mapped | 16 |
| Phases planned | 6 |
| Phases complete | 5 |
| Tests written (M2) | 93 |
| Tests passing | 1463 total |

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
| `ctrl+m` request flow | Changed from direct push to request→response: sends `ModelListRequestedEvent`, waits for `ModelListResponseEvent`, then pushes `ModelSelectScreen` |
| Debounce via `_model_list_pending` flag | Prevents duplicate `ctrl+m` requests while one is in flight; cleared on response |

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

- [ ] Plan and execute Phase 6: Integration Polish (loading states, error handling, E2E)

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
5. Phase 5 is committed at `f06e6cc` — proceed to Phase 6

**Files to check first:**
- `.planning/ROADMAP.md` — M2 phase structure and success criteria
- `.planning/REQUIREMENTS.md` — v1.1 requirement traceability
- `.planning/STATE.md` — this file, project memory
- `docs/superpowers/specs/2026-03-29-provider-model-display-switching-design.md` — approved design spec

---
*State updated: 2026-03-29 — Phase 5 committed (`f06e6cc`), 1463 tests passing*
