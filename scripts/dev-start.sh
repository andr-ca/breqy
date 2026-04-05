#!/usr/bin/env bash
# dev-start.sh — Worktree-aware engine + TUI launcher
# Usage: scripts/dev-start.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve repo root (works from any directory)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PYTHON="$REPO_ROOT/.venv/bin/python"

# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
if ! command -v tmux &>/dev/null; then
    echo "error: tmux is not installed or not in PATH" >&2
    exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "error: venv python not found at $PYTHON" >&2
    echo "       Run: python -m venv .venv && pip install -e ." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Discover worktrees
# ---------------------------------------------------------------------------
declare -a WT_PATHS=()
declare -a WT_BRANCHES=()
declare -a MENU_ITEMS=()

_current_path=""
_current_branch=""

while IFS= read -r line; do
    case "$line" in
        "worktree "*)
            _current_path="${line#worktree }"
            _current_branch=""
            ;;
        "branch "*)
            _current_branch="${line#branch refs/heads/}"
            ;;
        "")
            if [[ -n "$_current_path" && -n "$_current_branch" ]]; then
                WT_PATHS+=("$_current_path")
                WT_BRANCHES+=("$_current_branch")
                if [[ "$_current_path" == "$REPO_ROOT" ]]; then
                    MENU_ITEMS+=("main  [main]")
                else
                    rel="${_current_path#"$REPO_ROOT"/}"
                    MENU_ITEMS+=("$_current_branch  [$rel]")
                fi
            fi
            _current_path=""
            _current_branch=""
            ;;
    esac
done < <(git -C "$REPO_ROOT" worktree list --porcelain; echo "")

if [[ ${#MENU_ITEMS[@]} -eq 0 ]]; then
    echo "error: no worktrees found" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Pick a worktree
# ---------------------------------------------------------------------------
selected_idx=""

_pick_with_select() {
    local PS3="Pick a worktree (number): "
    select item in "${MENU_ITEMS[@]}"; do
        local i
        for i in "${!MENU_ITEMS[@]}"; do
            if [[ "${MENU_ITEMS[$i]}" == "$item" ]]; then
                selected_idx=$i
                return 0
            fi
        done
        echo "Invalid selection, try again."
    done
}

if command -v fzf &>/dev/null; then
    selected_label=$(printf '%s\n' "${MENU_ITEMS[@]}" \
        | fzf --height=40% --reverse --prompt="Pick a worktree: ") || true
    if [[ -z "$selected_label" ]]; then
        # User cancelled (Ctrl-C or Esc)
        exit 0
    fi
    for i in "${!MENU_ITEMS[@]}"; do
        if [[ "${MENU_ITEMS[$i]}" == "$selected_label" ]]; then
            selected_idx=$i
            break
        fi
    done
else
    echo "Note: fzf not found, falling back to numbered list." >&2
    _pick_with_select
fi

if [[ -z "$selected_idx" ]]; then
    exit 0
fi

SELECTED_PATH="${WT_PATHS[$selected_idx]}"
SELECTED_BRANCH="${WT_BRANCHES[$selected_idx]}"

# ---------------------------------------------------------------------------
# Debug mode?
# ---------------------------------------------------------------------------
DEBUG=false
read -r -p "Debug mode? [y/N]: " _dbg </dev/tty
_dbg="${_dbg,,}"
if [[ "$_dbg" == "y" || "$_dbg" == "yes" ]]; then
    DEBUG=true
fi

# ---------------------------------------------------------------------------
# Build environment prefix and commands
# ---------------------------------------------------------------------------
declare -a _env=()
if [[ "$SELECTED_PATH" != "$REPO_ROOT" ]]; then
    _env+=("PYTHONPATH=$SELECTED_PATH${PYTHONPATH:+:$PYTHONPATH}")
fi
if [[ "$DEBUG" == true ]]; then
    _env+=("BREQY_LOG_LEVEL=DEBUG")
fi

if [[ ${#_env[@]} -gt 0 ]]; then
    _env_str="${_env[*]} "
else
    _env_str=""
fi

ENGINE_CMD="${_env_str}${PYTHON} -m breqy.cli engine start"
TUI_CMD="${_env_str}${PYTHON} -m breqy.cli tui"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
if [[ "$SELECTED_PATH" == "$REPO_ROOT" ]]; then
    echo "  Worktree : main (no PYTHONPATH override)"
else
    echo "  Worktree : $SELECTED_PATH"
    echo "  Branch   : $SELECTED_BRANCH"
    echo "  PYTHONPATH set"
fi
[[ "$DEBUG" == true ]] && echo "  Log level: DEBUG"
echo ""

# ---------------------------------------------------------------------------
# Launch in tmux
# ---------------------------------------------------------------------------
_setup_panes() {
    # $1 = window target (e.g. "mysession:breqy-dev" or "breqy-dev:0")
    local target="$1"

    # Capture engine pane ID before splitting (pane that already exists)
    local engine_pane
    engine_pane=$(tmux display-message -t "$target" -p '#{pane_id}')

    # Split: top pane (30%) + new bottom pane (70%)
    # -l "70%" is the tmux 3.1+ syntax (-p was removed in 3.4)
    # -P -F '#{pane_id}' captures the new pane's ID directly — immune to pane-base-index
    local tui_pane
    tui_pane=$(tmux split-window -t "$target" -v -l "70%" -c "$REPO_ROOT" -P -F '#{pane_id}') \
        || { echo "error: tmux split-window failed" >&2; exit 1; }

    # Send commands using pane IDs (not indices — avoids pane-base-index issues)
    tmux send-keys -t "$tui_pane"    "$TUI_CMD"    Enter
    tmux send-keys -t "$engine_pane" "$ENGINE_CMD" Enter

    # Return focus to TUI pane
    tmux select-pane -t "$tui_pane"
}

set +e
if [[ -n "${TMUX:-}" ]]; then
    # Already inside tmux — create a new window in the current session
    echo "Creating window 'breqy-dev' in current tmux session..."
    _session=$(tmux display-message -p '#S')
    if tmux list-windows -t "$_session" -F '#W' 2>/dev/null | grep -q "^breqy-dev$"; then
        tmux kill-window -t "${_session}:breqy-dev"
    fi
    tmux new-window -n breqy-dev -c "$REPO_ROOT"
    _setup_panes "${_session}:breqy-dev"
else
    # Not inside tmux
    if tmux has-session -t breqy-dev 2>/dev/null; then
        echo "Session 'breqy-dev' already exists — attaching..."
        tmux attach-session -t breqy-dev
        exit 0
    fi
    echo "Creating tmux session 'breqy-dev'..."
    tmux new-session -d -s breqy-dev -c "$REPO_ROOT"
    _setup_panes "breqy-dev:0"
    tmux attach-session -t breqy-dev
fi
set -e
