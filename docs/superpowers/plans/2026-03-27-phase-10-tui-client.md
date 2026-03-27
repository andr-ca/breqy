# Phase 10: TUI Client — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-03-27-phase-10-tui-client-design.md`
**Phase goal:** Full Textual TUI with all 13 TUI requirements
**Baseline tests:** 915 passing
**Created:** 2026-03-27

---

## Task Breakdown

### Task 1: Foundation — Package structure, state, stream buffer, event dispatcher, constants

**Requirements:** TUI-03 (partial), infrastructure for all others
**Files:**
- `breqy/tui/__init__.py`
- `breqy/tui/constants.py`
- `breqy/tui/state.py` — `SessionState` dataclass
- `breqy/tui/events.py` — `EventDispatcher` class
- `breqy/tui/widgets/__init__.py`
- `breqy/tui/widgets/stream_buffer.py` — `StreamBuffer`
- `breqy/tui/screens/__init__.py`
- `breqy/tui/commands.py` — `CommandRegistry`
- `tests/tui/__init__.py`
- `tests/tui/conftest.py`
- `tests/tui/test_stream_buffer.py`
- `tests/tui/test_event_dispatcher.py`
- `tests/tui/test_state.py`
- `tests/tui/test_commands.py`

**Tests (~30):**
- StreamBuffer: add chunk, ordering, complete, empty, duplicate index, multi-message
- EventDispatcher: register handler, dispatch known event, unknown event type, multiple handlers
- SessionState: create, update from session event, update from task event, update from agent event, participants
- CommandRegistry: register command, dispatch known, unrecognized returns error, parse args

**TDD:** Write all test files first (RED), then implement.

---

### Task 2: CSS stylesheet + BreqyApp shell

**Requirements:** Infrastructure
**Files:**
- `breqy/tui/styles/breqy.tcss` — Textual CSS
- `breqy/tui/app.py` — `BreqyApp(App)` with mock screens (placeholders)
- `tests/tui/test_app.py`

**Tests (~8):**
- App mounts without error
- App has expected key bindings (ctrl+q, ctrl+l, ctrl+a, ctrl+m)
- App loads CSS without error
- Default screen is SessionListScreen (placeholder)

**TDD:** Write app tests first, then implement BreqyApp shell.

---

### Task 3: MessageInput widget + slash command integration

**Requirements:** TUI-11
**Files:**
- `breqy/tui/widgets/message_input.py` — `MessageInput` widget
- `tests/tui/test_message_input.py`

**Tests (~10):**
- Regular text submit posts message event
- Slash command `/help` dispatches to command registry
- Slash command `/stop` dispatches to command registry
- Unknown `/foo` shows error notification
- Empty submit does nothing
- Multi-line input supported
- Focus behavior (auto-focus on mount)

**TDD:** Write tests, implement widget.

---

### Task 4: ChatView widget + streaming

**Requirements:** TUI-02, TUI-03
**Files:**
- `breqy/tui/widgets/chat_view.py` — `ChatView` widget
- `tests/tui/test_chat_view.py`

**Tests (~12):**
- Display user message with USER style
- Display assistant message with ASSISTANT style
- Display system message with SYSTEM style
- Display tool message with TOOL style
- Stream chunks incrementally (add_chunk updates display)
- Complete streaming message (finalize on MessageSentEvent)
- Auto-scroll to bottom on new content
- Scroll-up pauses auto-scroll
- Empty message handling
- Multiple concurrent streams (different message_ids)

**TDD:** Write tests, implement widget.

---

### Task 5: TaskPanel widget

**Requirements:** TUI-04
**Files:**
- `breqy/tui/widgets/task_panel.py` — `TaskPanel` widget
- `tests/tui/test_task_panel.py`

**Tests (~8):**
- Add new task (PENDING with ○ icon)
- Update task to RUNNING (◆ icon)
- Complete task (✓ icon)
- Failed task (✗ icon)
- Cancelled task (— icon)
- Nested tasks (parent_id)
- Empty state display
- Multiple tasks in order

**TDD:** Write tests, implement widget.

---

### Task 6: ToolPanel widget

**Requirements:** TUI-08
**Files:**
- `breqy/tui/widgets/tool_panel.py` — `ToolPanel` widget
- `tests/tui/test_tool_panel.py`

**Tests (~8):**
- Tool started event adds entry with RUNNING status
- Tool output chunk appends to display
- Tool completed event marks with summary
- Tool failed event shows error
- Multiple concurrent tools
- Old completed tools scroll off (max display limit)
- Empty state

**TDD:** Write tests, implement widget.

---

### Task 7: ApprovalPrompt widget

**Requirements:** TUI-05
**Files:**
- `breqy/tui/widgets/approval_prompt.py` — `ApprovalPrompt` widget
- `tests/tui/test_approval_prompt.py`

**Tests (~8):**
- Shows approval request details (tool name, description)
- Approve button sends ApprovalDecidedEvent with GRANTED
- Deny button sends ApprovalDecidedEvent with DENIED
- Approve-for-session sends with extend_to_session=True
- Prompt dismissed after decision
- Multiple pending approvals queued
- Key bindings (A/D/S)

**TDD:** Write tests, implement widget.

---

### Task 8: ControlBar widget

**Requirements:** TUI-06
**Files:**
- `breqy/tui/widgets/control_bar.py` — `ControlBar` widget
- `tests/tui/test_control_bar.py`

**Tests (~10):**
- Stop button sends ControlEvent(control.stop)
- Stop+Steer button sends ControlEvent(control.stop_and_steer) with direction input
- Steer button sends ControlEvent(control.steer) with direction input
- Circuit Break sends ControlEvent(control.circuit_break)
- Buttons disabled when no active session
- Buttons enabled when session ACTIVE + agent connected
- Circuit Break always enabled (emergency)
- Direction input overlay appears for steer actions
- Key bindings (ctrl+s, ctrl+d, ctrl+e, ctrl+b)

**TDD:** Write tests, implement widget.

---

### Task 9: AgentStatusBar widget

**Requirements:** TUI-07
**Files:**
- `breqy/tui/widgets/agent_status.py` — `AgentStatusBar` widget
- `tests/tui/test_agent_status.py`

**Tests (~6):**
- Shows agent as connected (● icon) on AgentLifecycleEvent CONNECTED
- Shows agent as disconnected (○ icon) on AgentLifecycleEvent DISCONNECTED
- Multiple agents displayed
- No agents state
- Agent name formatting

**TDD:** Write tests, implement widget.

---

### Task 10: SessionListScreen

**Requirements:** TUI-01
**Files:**
- `breqy/tui/screens/session_list.py` — `SessionListScreen`
- `tests/tui/test_session_list.py`

**Tests (~10):**
- Screen mounts with session list
- Sessions displayed with status and timestamp
- Select session and press Enter navigates to ChatScreen
- Press N creates new session
- Session status colors (ACTIVE=green, CLOSED=dim, CIRCUIT_BROKEN=red)
- Empty session list shows "No sessions" message
- Refresh (R) re-fetches sessions
- Quit (Q) exits app

**TDD:** Write tests, implement screen.

---

### Task 11: ChatScreen — assembly of all chat widgets

**Requirements:** TUI-02/03/04/05/06/07/08 (composition)
**Files:**
- `breqy/tui/screens/chat.py` — `ChatScreen`
- `tests/tui/test_chat_screen.py`

**Tests (~12):**
- Screen composes ChatView, MessageInput, TaskPanel, ToolPanel, ControlBar, AgentStatusBar
- Incoming MessageSentEvent routed to ChatView
- Incoming MessageChunkEvent routed to ChatView streaming
- Incoming TaskUpdatedEvent routed to TaskPanel
- Incoming ToolInvocationStartedEvent routed to ToolPanel
- Incoming ApprovalRequestedEvent shows ApprovalPrompt
- User types message → sends MessageSentEvent to engine
- User sends approval decision → sends ApprovalDecidedEvent
- User sends control → sends ControlEvent
- Escape goes back to SessionListScreen

**TDD:** Write tests, implement screen.

---

### Task 12: AuthScreen

**Requirements:** TUI-09
**Files:**
- `breqy/tui/screens/auth.py` — `AuthScreen`
- `tests/tui/test_auth_screen.py`

**Tests (~10):**
- Lists all configured providers with auth status
- Select provider shows appropriate auth flow widget
- Device flow: shows code + OSC8 URL
- PKCE flow: shows URL + paste input
- API key flow: shows masked input
- Successful auth updates status to "Authenticated"
- Failed auth shows error
- Escape returns to previous screen

**TDD:** Write tests, implement screen.

---

### Task 13: LogsScreen

**Requirements:** TUI-10
**Files:**
- `breqy/tui/screens/logs.py` — `LogsScreen`
- `tests/tui/test_logs_screen.py`

**Tests (~8):**
- Displays events with timestamp, source, type, summary
- New events append to log
- Filter by event type prefix
- Clear filter shows all events
- Empty state
- Escape returns to previous screen
- Max log buffer size (ring buffer)

**TDD:** Write tests, implement screen.

---

### Task 14: ModelSelectScreen

**Requirements:** TUI-12
**Files:**
- `breqy/tui/screens/model_select.py` — `ModelSelectScreen`
- `tests/tui/test_model_select.py`

**Tests (~6):**
- Lists available providers and models
- Current model highlighted
- Select model updates preference
- Escape cancels and returns
- Empty model list handling

**TDD:** Write tests, implement screen.

---

### Task 15: App event loop wiring + A2A Worker

**Requirements:** TUI-03, TUI-13 (partial — originator verified here)
**Files:**
- `breqy/tui/app.py` — Complete A2A Worker integration
- `tests/tui/test_app.py` — Extended with event routing tests

**Tests (~8):**
- Worker connects to engine socket
- Worker receives events and posts to active screen
- Connection failure shows error notification
- Disconnect triggers reconnect with backoff
- App distributes events via EventDispatcher
- Send message round-trip (mock engine)

**TDD:** Write tests, implement worker wiring.

---

### Task 16: Integration tests

**Requirements:** All TUI requirements (end-to-end verification)
**Files:**
- `tests/tui/test_integration.py`

**Tests (~6):**
- Full startup → session list → create session → chat → send message → receive response flow
- Approval flow: send tool call → approval prompt → approve → tool completes
- Control flow: send message → stop → verify agent stopped
- Session resume: engine restart → TUI reconnects → session history preserved
- Auth screen accessible and shows provider list

**TDD:** Write tests with mock engine, implement any remaining wiring.

---

### Task 17: Documentation + CHANGES.md

**Requirements:** All (documentation checkpoint)
**Files:**
- `docs/architecture.md` — Update with TUI architecture section
- `CHANGES.md` — Phase 10 entry
- `.planning/phases/10-tui-client/README.md` — Task tracking
- `.planning/STATE.md` — Update progress
- `.planning/ROADMAP.md` — Update Phase 10 status

**No tests.** Documentation-only task.

---

## Task Dependencies

```
Task 1 (Foundation) ──────────────────────┐
    │                                      │
    ├── Task 2 (App shell) ────────────┐   │
    │       │                           │   │
    ├── Task 3 (MessageInput)           │   │
    │       │                           │   │
    ├── Task 4 (ChatView)              │   │
    │       │                           │   │
    ├── Task 5 (TaskPanel)             │   │
    │       │                           │   │
    ├── Task 6 (ToolPanel)             │   │
    │       │                           │   │
    ├── Task 7 (ApprovalPrompt)        │   │
    │       │                           │   │
    ├── Task 8 (ControlBar)            │   │
    │       │                           │   │
    ├── Task 9 (AgentStatusBar)        │   │
    │       │                           │   │
    ├── Task 10 (SessionListScreen) ───┤   │
    │                                   │   │
    └── Task 11 (ChatScreen) ──────────┤   │
            │                           │   │
            ├── Task 12 (AuthScreen)   │   │
            │                           │   │
            ├── Task 13 (LogsScreen)   │   │
            │                           │   │
            └── Task 14 (ModelSelect)  │   │
                                        │   │
    Task 15 (App wiring) ──────────────┘   │
            │                               │
    Task 16 (Integration tests) ───────────┘
            │
    Task 17 (Documentation)
```

**Parallelizable groups:**
- Tasks 3–9 can all be developed in parallel (independent widgets)
- Tasks 12–14 can be developed in parallel (independent screens)
- Task 10 + Task 11 need Tasks 3–9 complete
- Task 15 needs Task 11 complete
- Task 16 needs Task 15 complete

---

## Execution Strategy

Use subagent-driven development for the parallelizable widget tasks (3–9). Execute sequentially for screens (10–14) and integration (15–17).

**Estimated test count:** ~150 new tests
**Target total:** ~1065 tests

---

*Plan created: 2026-03-27*
