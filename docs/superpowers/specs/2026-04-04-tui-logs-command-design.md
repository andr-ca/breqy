# Design: `/logs` Slash Command — Agent Log File Viewer

**Date:** 2026-04-04  
**Status:** Approved  
**Scope:** TUI only — no engine or agent runtime changes required

---

## Problem

The agent subprocess logs (including the `initiator=user/agent` field on each LLM call) are written to `~/.breqy/data/logs/agent-breqy.log` with `console=False`. They are invisible from the engine console and from the existing TUI log overlay (`ctrl+l`), which only shows domain events.

## Goal

Add a `/logs` slash command in the TUI chat input that opens a live-tailing view of the agent log file, making agent subprocess logs — including `initiator` — discoverable without leaving the TUI.

---

## Approach: New `AgentLogsScreen` Overlay (Option A)

A dedicated `AgentLogsScreen` pushed as a Textual overlay screen. Follows the same pattern as the existing `LogsScreen` and `ModelSelectScreen`.

---

## Architecture

### Components

| Component | Location | Responsibility |
|---|---|---|
| `AgentLogsScreen` | `breqy/tui/screens/agent_logs.py` | New overlay; reads and tails the agent log file |
| `/logs` registration | `breqy/tui/screens/chat.py` | Adds command to `CommandRegistry` in `_build_command_registry()` |
| Command routing | `breqy/tui/app.py` | Handles `cmd == "logs"` in `on_command_executed`, resolves path, pushes screen |

### `AgentLogsScreen` Layout

```
┌─────────────────────────────────────────────────────┐
│ Agent Logs  ~/.breqy/data/logs/agent-breqy.log      │
├─────────────────────────────────────────────────────┤
│                                                     │
│  SelectableRichLog (scrollable, text-selectable)    │
│  — last 200 lines pre-loaded on open               │
│  — new lines appended every 0.5 s via set_interval │
│                                                     │
└─── q / Escape to close ────────────────────────────┘
```

### Slash Command Flow

```
User types /logs
  → CommandRegistry.dispatch("/logs")
  → CommandResult(success=True, message="logs")
  → BreqyApp.on_command_executed
  → resolves log_file path
  → self.push_screen(AgentLogsScreen(log_file=path))
```

---

## File Tailing Mechanism

- `set_interval(0.5, self._poll_log)` — Textual timer, no external dependencies
- On open: open file, seek to end minus last 200 lines, read initial content
- On each poll: read from last known offset to current EOF, append new text
- Pure stdlib `open()` — no `watchdog`, `inotify`, or threads

---

## Log File Path Resolution

Mirrors the logic in `breqy/agents/runtime.py:main()` and `breqy/utils/logging.py:default_log_file()`:

```python
data_dir = Path(os.environ.get("BREQY_DATA_DIR", "~/.breqy/data")).expanduser()
log_file = data_dir / "logs" / f"agent-{agent_id}.log"
```

`agent_id` is obtained from the connected agent's `AgentLifecycleEvent`, already tracked in `AgentStatusBar`. The `BreqyApp` passes it when constructing the screen. If no agent has connected yet, falls back to `"agent.log"` (the no-ID convention from `default_log_file`).

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Log file does not exist yet | Shows "Waiting for log file…" placeholder; poll continues until file appears |
| Log file exists but is empty | Shows empty log; tails normally |
| File disappears mid-session (agent restart) | Poll silently catches `OSError`; resumes reading when file reappears |
| Agent ID unknown (no lifecycle event yet) | Falls back to `agent.log` |
| File read error (permissions) | Shows error message in log view; does not crash |

---

## Testing

### `tests/unit/tui/test_agent_logs_screen.py` (new)

| Test | Description |
|---|---|
| `test_reads_last_n_lines_on_open` | Seed temp file with 300 lines; confirm only last 200 displayed on open |
| `test_polls_new_lines` | Write initial lines, open screen, write more, confirm new lines appended after poll |
| `test_file_not_found_shows_placeholder` | Non-existent path shows waiting message; no crash |
| `test_resolves_log_path_from_env_var` | `BREQY_DATA_DIR` env var produces correct resolved path |
| `test_file_disappears_and_reappears` | File deleted mid-session; poll handles `OSError` silently; resumes on reappearance |

### `tests/unit/tui/test_slash_commands.py` (extend or new)

| Test | Description |
|---|---|
| `test_logs_command_registered` | `CommandRegistry` recognises `/logs` without error |
| `test_logs_command_returns_logs_token` | `dispatch("/logs")` returns `CommandResult(success=True, message="logs")` |

---

## Out of Scope

- Engine log tailing (separate concern)
- Merging agent file logs with domain events
- Log filtering / search within the viewer (can be added later)
- Watching multiple agent log files simultaneously
