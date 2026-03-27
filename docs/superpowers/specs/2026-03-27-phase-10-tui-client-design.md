# Phase 10: TUI Client — Design Specification

**Phase:** 10 of 10
**Requirements:** TUI-01 through TUI-13 (13 total)
**Depends on:** Phase 3 (A2A client), Phase 5 (engine live), Phase 8 (agent live), Phase 9 (sessions and controls)
**Created:** 2026-03-27

---

## Phase Goal

The Textual TUI provides the full user experience — session browsing, real-time chat, live task and tool status, inline approvals, control actions, runner authentication, structured event logs, and slash commands — all driven by typed A2A events with no heuristic payload parsing.

---

## Architecture Overview

### Application Structure

```
BreqyApp(App)
├── SessionListScreen        # TUI-01: Browse/create/resume sessions
├── ChatScreen               # TUI-02/03/04/05/06/07/08: Main interaction screen
│   ├── ChatView             # Message display with streaming
│   ├── MessageInput         # User text input with slash command detection
│   ├── TaskPanel            # TUI-04: Live task list
│   ├── ToolPanel            # TUI-08: Tool execution status
│   ├── ApprovalPrompt       # TUI-05: Inline approval widget
│   ├── ControlBar           # TUI-06: Stop/steer/circuit-break buttons
│   └── AgentStatusBar       # TUI-07: Agent participation indicators
├── AuthScreen               # TUI-09: Provider auth management
├── LogsScreen               # TUI-10: Structured event log viewer
└── ModelSelectScreen        # TUI-12: Provider/model selection
```

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Screen navigation | Multi-screen with `push_screen`/`pop_screen` | Clean separation of concerns; each screen owns its widget tree |
| Event routing | `EventDispatcher` class maps `EventType → handler method` | Single place to wire events; no switch/if chains in widgets |
| A2A connection | Async `Worker` in the App | Textual Workers run in background; App distributes events to active screen |
| Streaming assembly | `StreamBuffer` keyed by `message_id` | Accumulates `MessageChunkEvent`s into contiguous text; flushes on `MessageSentEvent(role=ASSISTANT)` |
| Slash commands | `CommandRegistry` maps `/name → handler` | Extensible; unrecognized commands show error tooltip |
| CSS theming | `.tcss` file(s) in `breqy/tui/` | Textual native CSS; no inline styles |
| State management | `SessionState` dataclass held by ChatScreen | Tracks current session, messages, tasks, participants, pending approvals |

### A2A Integration Pattern

```
┌──────────────┐     Unix Socket      ┌──────────────┐
│   BreqyApp   │◄────────────────────►│ EngineServer │
│              │    A2AClient          │              │
│  Worker:     │                       │              │
│  listen()────►─── Envelope ─────────►│ _handle_     │
│              │    (send_event)       │  envelope()  │
│  on_event()◄─── Envelope ◄──────────│ broadcast()  │
│  dispatch()  │    (listen)           │              │
└──────────────┘                       └──────────────┘
```

**Outbound (TUI → Engine):**
- User message: `MessageSentEvent(role=USER, content=...)`
- Control: `ControlEvent(event_type=control.stop|steer|...)`
- Approval: `ApprovalDecidedEvent(approval_id=..., decision=GRANTED|DENIED)`
- Session create: `SessionCreatedEvent(primary_agent_id=..., workspace=...)`

**Inbound (Engine → TUI):**
- Chat: `MessageSentEvent(role=ASSISTANT)`, `MessageChunkEvent`
- Tasks: `TaskUpdatedEvent(event_type=task.created|updated|completed)`
- Tools: `ToolInvocationStartedEvent`, `ToolInvocationCompletedEvent`, `ToolOutputChunkEvent`
- Approvals: `ApprovalRequestedEvent`
- Agents: `AgentLifecycleEvent(event_type=agent.connected|disconnected)`
- Sessions: `SessionCreatedEvent`, `SessionResumedEvent`, `SessionClosedEvent`

---

## Requirement → Component Mapping

| Req | Component | Description |
|-----|-----------|-------------|
| TUI-01 | `SessionListScreen` | Lists sessions with status; create new or resume existing |
| TUI-02 | `ChatView` | Streams `MessageChunkEvent` incrementally; assembles into messages |
| TUI-03 | `EventDispatcher` | Routes all typed events to correct widget handlers — no payload guessing |
| TUI-04 | `TaskPanel` | Renders `TaskUpdatedEvent` into a live task tree |
| TUI-05 | `ApprovalPrompt` | Surfaces `ApprovalRequestedEvent`; sends `ApprovalDecidedEvent` back |
| TUI-06 | `ControlBar` | Buttons for stop, stop-and-steer, steer, circuit-break; sends `ControlEvent` |
| TUI-07 | `AgentStatusBar` | Shows agent names + connection status from `AgentLifecycleEvent` |
| TUI-08 | `ToolPanel` | Shows tool name, status, summary, output from tool invocation events |
| TUI-09 | `AuthScreen` | Lists providers with auth status; drives device flow / PKCE / API key input |
| TUI-10 | `LogsScreen` | Filterable structured event log with timestamp, source, type, level |
| TUI-11 | `CommandRegistry` + `MessageInput` | Slash command detection, dispatch, error hints |
| TUI-12 | `ModelSelectScreen` | Lists providers/models; selecting updates session model preference |
| TUI-13 | `BreqyApp` + provider adapters | Sets originator header on inference calls (GitHub Copilot requires this) |

---

## Component Specifications

### 1. BreqyApp (App subclass)

**Responsibilities:**
- Own the `A2AClient` connection lifecycle
- Run background `Worker` for `client.listen()` event stream
- Distribute incoming events to the active screen via `post_message`
- Manage screen stack (SessionList → Chat, push Auth/Logs/ModelSelect as overlays)

**Key bindings (app-level):**
- `ctrl+q` — Quit
- `ctrl+l` — Push LogsScreen
- `ctrl+a` — Push AuthScreen
- `ctrl+m` — Push ModelSelectScreen
- `escape` — Pop current overlay screen

**Configuration:**
- `socket_path`: from env `BREQY_ENGINE_SOCKET` or default `~/.breqy/engine.sock`
- Connection retry with backoff on startup

### 2. SessionListScreen (TUI-01)

**Layout:**
```
┌─────────────────────────────────────────┐
│  BREQY — Sessions                       │
├─────────────────────────────────────────┤
│  ○ ses_01HZ... │ active  │ 2m ago      │
│  ○ ses_01HY... │ closed  │ 1h ago      │
│  ○ ses_01HX... │ circuit │ 3h ago      │
├─────────────────────────────────────────┤
│  [N] New Session  [Enter] Resume        │
│  [Q] Quit         [R] Refresh           │
└─────────────────────────────────────────┘
```

**Data source:** On mount, TUI sends a request to engine to list sessions. The engine responds with session list data. For Slice 1, we use a simple request/response pattern over A2A: TUI sends a `SessionListRequestEvent`, engine responds with session data.

**Alternative (simpler for Slice 1):** TUI connects to the engine and the engine broadcasts current session state on connect. The TUI can also query sessions via a direct message/event exchange.

**Decision:** For Slice 1, the session list will be populated from a lightweight RPC-over-A2A pattern: TUI sends a custom query event, engine responds. This keeps the A2A transport as the single communication channel.

### 3. ChatView (TUI-02, TUI-03)

**Responsibilities:**
- Display messages in a scrollable container (Textual `RichLog` or custom `ScrollableContainer`)
- Handle `MessageSentEvent` (role=USER/ASSISTANT/SYSTEM/TOOL) — render complete messages
- Handle `MessageChunkEvent` — append chunks to an in-progress message assembly
- Rich formatting: different colors/styles per `MessageRole`

**Streaming assembly (`StreamBuffer`):**
```python
class StreamBuffer:
    """Accumulates MessageChunkEvent chunks into messages."""
    _buffers: dict[str, list[str]]  # message_id → ordered chunks

    def add_chunk(self, message_id: str, chunk: str, chunk_index: int) -> str:
        """Returns the full accumulated text so far."""

    def complete(self, message_id: str) -> str:
        """Flushes and returns final text when MessageSentEvent arrives."""
```

**Rendering rules:**
- USER messages: right-aligned or prefixed with `> `
- ASSISTANT messages: left-aligned, streamed character by character
- SYSTEM messages: dimmed/italic
- TOOL messages: code-block style

### 4. TaskPanel (TUI-04)

**Layout:** Side panel or collapsible section showing task tree.

```
┌─ Tasks ─────────────────────┐
│ ◆ Implement auth flow       │
│   ○ Write tests             │
│   ✓ Create interfaces       │
│   ✓ Wire dependencies       │
└─────────────────────────────┘
```

**Event handling:**
- `TaskUpdatedEvent` with `task.created` → add new task entry
- `TaskUpdatedEvent` with `task.updated` → update status icon
- `TaskUpdatedEvent` with `task.completed` → mark with ✓

**Status icons:** PENDING=○, RUNNING=◆, COMPLETED=✓, FAILED=✗, CANCELLED=—

### 5. ApprovalPrompt (TUI-05)

**Appears inline** in the chat area when `ApprovalRequestedEvent` arrives:

```
╔══════════════════════════════════════════════╗
║  APPROVAL REQUIRED                           ║
║  Tool: shell_execute                         ║
║  Command: rm -rf /tmp/build                  ║
║                                              ║
║  [A] Approve  [D] Deny  [S] Approve Session ║
╚══════════════════════════════════════════════╝
```

**Sends back:** `ApprovalDecidedEvent` with:
- `approval_id` from the request
- `decision`: GRANTED or DENIED
- `extend_to_session`: true if user chose "Approve Session"

### 6. ControlBar (TUI-06)

**Fixed footer bar** with action buttons:

```
[^S] Stop  [^D] Stop+Steer  [^E] Steer  [^B] Circuit Break
```

**State-dependent:**
- Buttons enabled only when session is ACTIVE and agent is connected
- Circuit Break always available (emergency)
- After Stop/Circuit Break, all buttons except "new message" are disabled until session is idle

**Steer flow:** When user presses Steer or Stop+Steer, a text input overlay appears for the new direction. The `ControlEvent` is sent with `new_direction` field populated.

### 7. AgentStatusBar (TUI-07)

**Shows in the header/status area:**

```
Agents: breqy ● (active)  |  sub-agent-1 ○ (disconnected)
```

**Updates from:** `AgentLifecycleEvent` (agent.connected / agent.disconnected)

### 8. ToolPanel (TUI-08)

**Collapsible panel** showing active/recent tool executions:

```
┌─ Tools ─────────────────────────────────┐
│ ◆ shell_execute: ls -la /home           │
│   ├─ Status: RUNNING                    │
│   └─ Output: (streaming...)             │
│                                         │
│ ✓ filesystem_read: /etc/hosts           │
│   └─ 14 lines read                      │
└─────────────────────────────────────────┘
```

**Events:**
- `ToolInvocationStartedEvent` → add entry with RUNNING status
- `ToolOutputChunkEvent` → append to output area
- `ToolInvocationCompletedEvent` → mark complete with summary
- `ToolInvocationFailedEvent` → mark failed with error

### 9. AuthScreen (TUI-09)

**Overlay screen** showing provider auth status:

```
┌─────────────────────────────────────────────┐
│  Provider Authentication                     │
├─────────────────────────────────────────────┤
│  GitHub Copilot  ● Authenticated             │
│  OpenAI Codex    ○ Not configured            │
│  Claude          ○ Not configured            │
│  Gemini          ○ Not configured            │
│  Qwen            ○ Not configured            │
├─────────────────────────────────────────────┤
│  Select provider to authenticate [↑↓ Enter] │
│  [Esc] Back                                 │
└─────────────────────────────────────────────┘
```

**Auth flows per provider type:**
- **Device flow** (Copilot, Codex, Gemini): Shows device code + URL (OSC8 clickable link). Polls until complete.
- **PKCE** (Claude): Shows URL (OSC8 link) + text input for paste-back code.
- **API key** (Qwen): Masked text input field.

**Integration:** Auth screen calls into `breqy.agents.auth` module's provider authenticators. On success, credential is stored via `CredentialStore` (keyring).

### 10. LogsScreen (TUI-10)

**Overlay screen** with filterable event log:

```
┌─────────────────────────────────────────────────────────────┐
│  Event Log                          Filter: [all types  ▼] │
├──────────┬────────┬──────────────────┬──────────────────────┤
│ Time     │ Source │ Type             │ Summary              │
├──────────┼────────┼──────────────────┼──────────────────────┤
│ 14:23:01 │ engine │ session.created  │ New session ses_01.. │
│ 14:23:02 │ breqy  │ agent.connected  │ Agent registered     │
│ 14:23:05 │ user   │ message.sent     │ "Help me with..."   │
│ 14:23:06 │ breqy  │ tool.invocation..│ shell_execute: ls    │
└──────────┴────────┴──────────────────┴──────────────────────┘
```

**Data source:** All events received via A2A are appended to an in-memory ring buffer. The LogsScreen renders from this buffer.

**Filtering:** Dropdown/input to filter by event type prefix (e.g., "message.", "tool.", "control.").

### 11. CommandRegistry + MessageInput (TUI-11)

**Slash commands for Slice 1:**

| Command | Action |
|---------|--------|
| `/help` | Show available commands |
| `/clear` | Clear chat display |
| `/stop` | Shortcut for Stop control |
| `/steer <direction>` | Shortcut for Steer control with direction |
| `/circuit-break` | Shortcut for Circuit Break |
| `/sessions` | Switch to SessionListScreen |
| `/auth` | Push AuthScreen |
| `/logs` | Push LogsScreen |
| `/model` | Push ModelSelectScreen |
| `/quit` | Quit app |

**Detection:** `MessageInput` checks if text starts with `/`. If recognized, dispatch to handler. If unrecognized, show inline error hint ("Unknown command: /foo — type /help for available commands").

### 12. ModelSelectScreen (TUI-12)

**Overlay screen** listing available providers and models:

```
┌─────────────────────────────────────────┐
│  Model Selection                         │
├─────────────────────────────────────────┤
│  ● github-copilot / gpt-4o             │
│  ○ anthropic / claude-sonnet-4-20250514          │
│  ○ google / gemini-2.0-flash            │
│  ○ openai / o3                          │
│  ○ qwen / qwen-max                     │
├─────────────────────────────────────────┤
│  [Enter] Select  [Esc] Cancel           │
└─────────────────────────────────────────┘
```

**Data:** Available models come from agent config / engine config. The selection is communicated to the engine as a session-level preference.

### 13. Originator Header (TUI-13)

**Scope:** Not a TUI widget, but a behavioral requirement. For providers like GitHub Copilot that require an `X-Copilot-Agent-Originator` header (or equivalent), the TUI/agent must set this header correctly.

**Implementation:** This is handled in the agent runtime's provider adapter layer (`breqy/agents/providers/`). The TUI's role is limited to ensuring the agent config carries the originator identity. Phase 8 already implemented provider adapters with auth — this requirement is about verifying the header is set correctly on inference calls and tool-use follow-up messages.

**TUI impact:** Minimal. The TUI displays auth status (TUI-09) which covers visibility. The actual header injection happens in the agent process, not the TUI.

---

## File Structure

```
breqy/tui/
├── __init__.py              # Package exports
├── app.py                   # BreqyApp(App) — main application class
├── screens/
│   ├── __init__.py
│   ├── session_list.py      # SessionListScreen
│   ├── chat.py              # ChatScreen (main interaction)
│   ├── auth.py              # AuthScreen (provider auth)
│   ├── logs.py              # LogsScreen (event log viewer)
│   └── model_select.py      # ModelSelectScreen (provider/model picker)
├── widgets/
│   ├── __init__.py
│   ├── chat_view.py         # ChatView (message display)
│   ├── message_input.py     # MessageInput (text input with slash commands)
│   ├── task_panel.py        # TaskPanel (live task list)
│   ├── tool_panel.py        # ToolPanel (tool execution status)
│   ├── approval_prompt.py   # ApprovalPrompt (inline approval widget)
│   ├── control_bar.py       # ControlBar (stop/steer/break actions)
│   ├── agent_status.py      # AgentStatusBar (agent connection indicators)
│   └── stream_buffer.py     # StreamBuffer (chunk assembly)
├── events.py                # EventDispatcher (typed event → handler routing)
├── commands.py              # CommandRegistry (slash command dispatch)
├── state.py                 # SessionState (client-side state tracking)
├── styles/
│   └── breqy.tcss           # Textual CSS stylesheet
└── constants.py             # Key bindings, status icons, colors

tests/tui/
├── __init__.py
├── conftest.py              # Shared TUI test fixtures
├── test_app.py              # App lifecycle, connection, event routing
├── test_session_list.py     # Session list screen tests
├── test_chat_view.py        # Chat rendering, streaming assembly
├── test_task_panel.py       # Task widget updates
├── test_tool_panel.py       # Tool event rendering
├── test_approval_prompt.py  # Approval widget interaction
├── test_control_bar.py      # Control button behavior
├── test_agent_status.py     # Agent status display
├── test_commands.py         # Slash command parsing/dispatch
├── test_event_dispatcher.py # Event routing correctness
├── test_stream_buffer.py    # Chunk assembly logic
├── test_auth_screen.py      # Auth flow rendering
├── test_logs_screen.py      # Event log display and filtering
└── test_model_select.py     # Model selection screen
```

---

## Testing Strategy

### Unit tests (no engine required)
- **StreamBuffer**: chunk assembly, ordering, completion, edge cases
- **CommandRegistry**: command parsing, dispatch, unrecognized commands
- **EventDispatcher**: event type → handler mapping, unknown events
- **SessionState**: state updates from events, immutability

### Widget tests (Textual pilot)
- Use `app.run_test()` with Textual's built-in testing support
- Mock the A2A client (no real socket connection)
- Post synthetic events to widgets and verify rendering
- Test keyboard interactions (key bindings, button presses)

### Screen tests (Textual pilot)
- Mount each screen with mock data
- Verify widget composition and layout
- Test screen transitions (push/pop)

### Integration tests
- Start a real engine (in-process), connect TUI via socket
- Send a message, verify it appears in chat
- Trigger an approval, verify prompt appears and response is sent back

---

## Dependencies

**Existing (no new packages):**
- `textual>=0.71.0` (installed: 8.1.1)
- `breqy.a2a.client` — A2AClient for engine connection
- `breqy.domain.events` — All typed event classes
- `breqy.domain.models` — Session, Message, Task, etc.
- `breqy.domain.enums` — SessionStatus, TaskStatus, etc.
- `breqy.agents.auth` — Provider authenticators (for AuthScreen)
- `breqy.agents.credentials` — CredentialStore (for AuthScreen)

**No new pip packages required.**

---

## Open Questions (resolved with defaults)

| Question | Default Decision |
|----------|-----------------|
| Session list data source | RPC-over-A2A: query event → response event |
| Rich text in chat (markdown) | Plain text for Slice 1; markdown rendering is a polish item |
| Chat scroll behavior | Auto-scroll to bottom on new content; user scroll-up pauses auto-scroll |
| Error display (connection lost, etc.) | Notification banner at top of screen; auto-reconnect with backoff |
| TUI-13 originator header | Verified in agent provider tests, not TUI tests |

---

*Spec created: 2026-03-27*
