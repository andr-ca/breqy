# Design: Search/Filter for `AgentLogsScreen`

**Date:** 2026-04-04
**Status:** Approved
**Scope:** TUI only — `breqy/tui/screens/agent_logs.py` only; no engine, agent runtime, or other screen changes required

---

## Problem

`AgentLogsScreen` (opened via `/logs`) currently displays a live-tailing view of the agent log file but provides no way to find specific entries. A large log file makes it hard to locate relevant lines without scrolling manually.

## Goal

Add a live-filtering search bar to `AgentLogsScreen` that lets the user type a substring and instantly see only the matching log lines — while still live-tailing the file. Matches apply case-insensitively to the full raw text of each line.

---

## Approach: In-Memory Ring Buffer + Live Filter

Keep all loaded lines in a bounded ring buffer (`deque[str]`, `maxlen=1000`). On each poll, new lines are appended to the buffer. When the filter changes, the `RichLog` is cleared and re-rendered from the buffer showing only matching lines. New lines arriving during an active filter are checked on the fly.

This mirrors the pattern used in `LogsScreen` (the existing `ctrl+l` overlay).

---

## Layout

```
┌─────────────────────────────────────────────────────┐
│ Agent Logs  ~/.breqy/data/logs/agent-breqy.log      │  ← Static header
├─────────────────────────────────────────────────────┤
│ Filter: [________________________]                  │  ← Input (NEW)
├─────────────────────────────────────────────────────┤
│                                                     │
│  SelectableRichLog (filtered or full view)          │
│                                                     │
└─── q/Esc close  F focus filter  C clear filter ────┘
```

---

## Architecture

### New state in `AgentLogsScreen`

| Field | Type | Purpose |
|---|---|---|
| `_lines` | `collections.deque[str]` maxlen=1000 | Ring buffer of raw log lines loaded since screen opened |
| `_filter` | `str` | Current lowercase substring filter; empty = show all |

Existing `_offset: int` is unchanged.

### New pure helper

```python
def filter_lines(lines: Iterable[str], filter_str: str) -> list[str]:
    """Return lines where filter_str appears (case-insensitive). Empty filter returns all."""
```

Extracted as a module-level pure function — testable without Textual.

---

## Data Flow

### On open (`on_mount`)

The existing `_load_initial_lines()` private method is updated (not replaced) to:
1. `read_tail(path, 200)` → split by newlines → extend `_lines` (new step)
2. `_refresh_display()` replaces the current direct `RichLog.write` call
3. `_offset` set to file size (unchanged)

`on_mount` then calls `set_interval(0.5, _poll_log)` as before.

### On filter change (`Input.Changed` on `#agent-logs-filter`)

1. `_filter = event.value.strip().lower()`
2. `_refresh_display()`

### On poll (`_poll_log`)

1. `read_new_lines(path, _offset)` → new text, `_offset` updated
2. Split into lines, **extend `_lines` first** (always, regardless of filter)
3. **Fast path** (no filter): `RichLog.write(new_text)` directly — avoids full re-render
4. **Filter active**: `_refresh_display()` — full re-render to include new matches

### `_refresh_display()`

```
clear RichLog
for line in filter_lines(_lines, _filter):
    RichLog.write(line)
```

---

## Key Bindings

| Key | Action |
|---|---|
| `f` | Focus the filter `Input` |
| `c` | Clear filter, reset `Input` value; focus stays on the `Input` |
| `q` / `Escape` | Close overlay (unchanged) |

---

## Changes to Existing Files

| File | Change |
|---|---|
| `breqy/tui/screens/agent_logs.py` | Add `Input` widget; add `_lines` deque and `_filter` str; add `filter_lines()` pure helper; update `compose`, `on_mount`, `_poll_log`, `_refresh_display`; add `action_clear_filter`, `action_focus_filter`, `_on_filter_changed` |

No other files require changes. `/logs` registration, app routing, and path resolution are all unaffected.

---

## Error Handling

All existing error-handling behaviour is unchanged:
- Missing file: "Waiting for log file…" placeholder shown; filter applied to empty buffer
- `OSError` on poll: silently skipped, offset unchanged
- File disappear/reappear: handled by `read_new_lines`

When the filter is active and the file is missing, the display shows nothing (no lines match the placeholder, but the placeholder text itself is stored in `_lines` — it is treated as a log line and matches normally).

---

## Testing

All new tests go in `tests/unit/tui/test_agent_logs_screen.py`. They target the new `filter_lines` pure helper — no Textual pilot required.

| Test | Description |
|---|---|
| `test_filter_lines_hides_non_matching` | Buffer with mixed lines; filter returns only matches |
| `test_filter_lines_empty_returns_all` | Empty filter string returns all lines |
| `test_filter_lines_is_case_insensitive` | Lowercase filter matches uppercase content |
| `test_filter_lines_partial_match` | Substring match (not full-line equality) |
| `test_filter_lines_no_matches_returns_empty` | Filter with no matches returns empty list |

---

## Out of Scope

- Field-specific filters (e.g. `level:info`, `initiator:user`)
- Regex search
- Jump-to-match / `n`/`N` navigation
- Highlighting matched text within lines
- Persisting the filter across screen opens
