#!/usr/bin/env python3
"""
Claude Session Guardian

Monitors Claude Code usage via `ccusage blocks` and automatically respawns
agent processes when 5-hour session limits are hit. Waits for the next
billing window before restarting.

Usage:
    python scripts/claude_guardian.py [--config scripts/agents.yaml] [--dry-run]

Requires: PyYAML (pip install pyyaml), ccusage (npm i -g ccusage), claude CLI
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

LOG_FMT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE = "%H:%M:%S"
log = logging.getLogger("guardian")

# ANSI colors for agent output prefixes (cycles for multiple agents)
AGENT_COLORS = [
    "\033[36m",   # cyan
    "\033[33m",   # yellow
    "\033[35m",   # magenta
    "\033[32m",   # green
    "\033[34m",   # blue
    "\033[91m",   # bright red
]
COLOR_RESET = "\033[0m"
COLOR_DIM = "\033[2m"

# Strings that indicate Claude hit a rate/session limit
RATE_LIMIT_SIGNALS = [
    "rate limit",
    "rate_limit",
    "too many requests",
    "quota exceeded",
    "session limit",
    "usage limit",
    "429",
    "throttl",
    "capacity",
    "overloaded",
]


@dataclass
class AgentConfig:
    name: str
    project_dir: str
    prompt: str
    resume_prompt: str = "You were interrupted by a rate limit. Continue where you left off."
    model: Optional[str] = None
    permission_mode: str = "acceptEdits"


@dataclass
class AgentState:
    config: AgentConfig
    process: Optional[subprocess.Popen] = None
    session_id: Optional[str] = None
    status: str = "idle"  # idle | running | rate_limited | completed | failed
    last_exit_code: Optional[int] = None
    spawn_count: int = 0
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    color: str = ""           # ANSI color for this agent's output
    reader_threads: list = field(default_factory=list)
    stderr_lines: list = field(default_factory=list)  # captured for rate-limit detection


def load_config(path: str) -> tuple[dict, list[AgentConfig]]:
    """Load agent configuration from YAML."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    permission_mode = raw.get("permission_mode", "acceptEdits")

    settings = {
        "poll_interval": raw.get("poll_interval", 30),
        "cooldown_buffer": raw.get("cooldown_buffer", 120),
        "max_respawns": raw.get("max_respawns", 50),
    }

    agents = []
    for entry in raw.get("agents", []):
        agents.append(
            AgentConfig(
                name=entry["name"],
                project_dir=entry["project_dir"],
                prompt=entry.get("prompt", ""),
                resume_prompt=entry.get(
                    "resume_prompt",
                    "You were interrupted by a rate limit. Continue where you left off.",
                ),
                model=entry.get("model"),
                permission_mode=entry.get("permission_mode", permission_mode),
            )
        )

    return settings, agents


def get_active_block() -> Optional[dict]:
    """Query ccusage for the current active billing block."""
    try:
        result = subprocess.run(
            ["ccusage", "blocks", "--json", "--active", "--offline"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.debug("ccusage returned %d: %s", result.returncode, result.stderr.strip())
            return None

        data = json.loads(result.stdout)
        for block in data.get("blocks", []):
            if block.get("isActive") and not block.get("isGap"):
                return block
        return None
    except FileNotFoundError:
        log.error("ccusage not found. Install with: npm i -g ccusage")
        return None
    except Exception as e:
        log.warning("Failed to query ccusage: %s", e)
        return None


def block_time_remaining(block: dict) -> float:
    """Seconds remaining in a billing block."""
    end = datetime.fromisoformat(block["endTime"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return max(0.0, (end - now).total_seconds())


def detect_rate_limit(exit_code: int, stderr_text: str) -> bool:
    """Check if an agent exit looks like a rate limit."""
    lower = stderr_text.lower()
    return any(sig in lower for sig in RATE_LIMIT_SIGNALS)


def make_log_dir(base_dir: str) -> str:
    """Create a directory for agent logs."""
    log_dir = os.path.join(base_dir, ".breqy", "guardian_logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


# ---------------------------------------------------------------------------
# Live output streaming
# ---------------------------------------------------------------------------

# Lock to serialize print output across agent threads
_print_lock = threading.Lock()


def _extract_text(value) -> str:
    """Recursively extract text from various Claude event shapes."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Try common keys
        for key in ("text", "content", "message"):
            if key in value:
                return _extract_text(value[key])
        return ""
    if isinstance(value, list):
        parts = []
        for item in value:
            t = _extract_text(item)
            if t:
                parts.append(t)
        return "\n".join(parts)
    return str(value) if value else ""


def _format_stream_event(event: dict) -> Optional[str]:
    """Extract a human-readable summary from a stream-json event."""
    etype = event.get("type", "")

    # Assistant text message
    if etype == "assistant":
        # "message" can be str, dict, or list of content blocks
        if "message" in event:
            text = _extract_text(event["message"])
            if text:
                return text
        content = event.get("content_block", {})
        if isinstance(content, dict):
            text = content.get("text", "")
            if text:
                return text
        return None

    # Content block delta (streaming text chunks)
    if etype == "content_block_delta":
        delta = event.get("delta", {})
        text = delta.get("text", "")
        if text:
            return text
        return None

    # Tool use
    if etype == "tool_use":
        tool_name = event.get("name") or event.get("tool", {}).get("name", "")
        if tool_name:
            return f"[tool] {tool_name}"
        return None

    # Result / completion
    if etype == "result":
        cost = event.get("cost_usd")
        session_id = event.get("session_id", "")
        duration = event.get("duration_seconds")
        parts = []
        if session_id:
            parts.append(f"session={session_id}")
        if cost is not None:
            parts.append(f"cost=${cost:.4f}")
        if duration is not None:
            parts.append(f"duration={duration:.0f}s")
        return f"[result] {' '.join(parts)}" if parts else None

    # System messages — only show if there's actual content
    if etype == "system":
        text = _extract_text(event.get("message") or event.get("text") or "")
        if text.strip():
            return f"[system] {text}"
        # Also check for a "subtype" or other useful fields
        subtype = event.get("subtype", "")
        if subtype:
            return f"[system] {subtype}"
        return None

    # Error
    if etype == "error":
        text = _extract_text(event.get("message") or event.get("error") or "")
        return f"[error] {text}" if text else None

    return None


def _agent_stdout_reader(
    state: AgentState, pipe, log_file_path: str
) -> None:
    """Thread: reads stream-json stdout, displays live, writes to log file."""
    prefix = f"{state.color}[{state.config.name}]{COLOR_RESET}"
    try:
        with open(log_file_path, "w") as lf:
            for raw_line in iter(pipe.readline, ""):
                raw_line = raw_line.rstrip("\n")
                if not raw_line:
                    continue

                # Write raw line to log
                lf.write(raw_line + "\n")
                lf.flush()

                # Try to parse and pretty-print
                try:
                    event = json.loads(raw_line)
                    # Capture session_id early
                    sid = event.get("session_id")
                    if sid:
                        state.session_id = sid

                    summary = _format_stream_event(event)
                    if summary:
                        # Ensure summary is always a string
                        summary = str(summary)
                        with _print_lock:
                            # Wrap long lines
                            for line in summary.splitlines():
                                wrapped = textwrap.shorten(line, width=120, placeholder="...")
                                print(f"  {prefix} {wrapped}")
                            sys.stdout.flush()
                except json.JSONDecodeError:
                    # Not JSON — print raw
                    with _print_lock:
                        print(f"  {prefix} {raw_line[:120]}")
                        sys.stdout.flush()
    except (ValueError, OSError):
        pass  # pipe closed


def _agent_stderr_reader(
    state: AgentState, pipe, log_file_path: str
) -> None:
    """Thread: reads stderr, displays warnings, writes to log file."""
    prefix = f"{state.color}[{state.config.name}]{COLOR_RESET} {COLOR_DIM}stderr:{COLOR_RESET}"
    try:
        with open(log_file_path, "w") as lf:
            for raw_line in iter(pipe.readline, ""):
                raw_line = raw_line.rstrip("\n")
                if not raw_line:
                    continue

                lf.write(raw_line + "\n")
                lf.flush()

                state.stderr_lines.append(raw_line)

                with _print_lock:
                    print(f"  {prefix} {raw_line[:160]}")
                    sys.stdout.flush()
    except (ValueError, OSError):
        pass  # pipe closed


def spawn_agent(state: AgentState, log_dir: str, dry_run: bool = False) -> None:
    """Spawn a Claude Code agent subprocess with live output streaming."""
    cfg = state.config
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    cmd = ["claude"]

    # If we have a session from a previous run, resume it with continuation prompt
    if state.session_id:
        cmd.extend(["--resume", state.session_id, "-p", cfg.resume_prompt])
    else:
        # First run: non-interactive print mode with the task prompt
        cmd.extend(["-p", cfg.prompt])

    if cfg.model:
        cmd.extend(["--model", cfg.model])

    # Auto-handle permission prompts so agent runs unattended
    cmd.extend(["--permission-mode", cfg.permission_mode])

    # Use stream-json for real-time output visibility
    cmd.extend(["--output-format", "stream-json", "--verbose"])

    state.stdout_path = os.path.join(log_dir, f"{cfg.name}_{ts}_stdout.jsonl")
    state.stderr_path = os.path.join(log_dir, f"{cfg.name}_{ts}_stderr.log")
    state.stderr_lines = []

    log.info(
        "Spawning agent '%s' (#%d) in %s",
        cfg.name,
        state.spawn_count + 1,
        cfg.project_dir,
    )
    log.info("  cmd: %s", " ".join(cmd))
    log.info("  logs: %s", state.stdout_path)

    if dry_run:
        log.info("  [DRY RUN] Would spawn: %s", " ".join(cmd))
        state.status = "completed"
        return

    proc = subprocess.Popen(
        cmd,
        cwd=cfg.project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )

    state.process = proc
    state.status = "running"
    state.spawn_count += 1

    # Start reader threads for live output
    t_out = threading.Thread(
        target=_agent_stdout_reader,
        args=(state, proc.stdout, state.stdout_path),
        daemon=True,
        name=f"reader-{cfg.name}-stdout",
    )
    t_err = threading.Thread(
        target=_agent_stderr_reader,
        args=(state, proc.stderr, state.stderr_path),
        daemon=True,
        name=f"reader-{cfg.name}-stderr",
    )
    t_out.start()
    t_err.start()
    state.reader_threads = [t_out, t_err]


def collect_agent_output(state: AgentState) -> tuple[str, str]:
    """Read stdout/stderr from agent log files, with in-memory stderr as fallback."""
    stdout_text = ""
    stderr_text = ""
    try:
        if state.stdout_path and os.path.exists(state.stdout_path):
            stdout_text = Path(state.stdout_path).read_text()
    except Exception:
        pass
    try:
        if state.stderr_path and os.path.exists(state.stderr_path):
            stderr_text = Path(state.stderr_path).read_text()
    except Exception:
        pass
    # Use in-memory stderr captured by reader thread only if file content is unavailable
    if not stderr_text and state.stderr_lines:
        stderr_text = "\n".join(state.stderr_lines)
    return stdout_text, stderr_text


def extract_session_id(stdout_text: str) -> Optional[str]:
    """Try to extract session_id from Claude's JSON output."""
    # Already captured by the reader thread in state.session_id, but
    # also scan log file as fallback.
    try:
        data = json.loads(stdout_text)
        return data.get("session_id")
    except (json.JSONDecodeError, TypeError):
        pass
    # Try line-by-line for stream-json
    for line in stdout_text.strip().splitlines():
        try:
            data = json.loads(line)
            if "session_id" in data:
                return data["session_id"]
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def wait_for_next_window(cooldown_buffer: int, shutdown_event: threading.Event) -> None:
    """Wait for the current billing block to expire, then add buffer time."""
    block = get_active_block()

    if block:
        remaining = block_time_remaining(block)
        total_wait = remaining + cooldown_buffer
        end_str = block["endTime"][:19].replace("T", " ")
        log.info(
            "Active block ends at %s UTC (%.0f min remaining)",
            end_str,
            remaining / 60,
        )
    else:
        # No active block found — might already be in a gap.
        # Wait a short period and recheck.
        total_wait = cooldown_buffer
        log.info("No active block found. Waiting buffer period.")

    resume_at = datetime.now() + timedelta(seconds=total_wait)
    log.info(
        "Waiting %.1f minutes before respawning (resume ~%s)",
        total_wait / 60,
        resume_at.strftime("%H:%M:%S"),
    )

    waited = 0.0
    while waited < total_wait and not shutdown_event.is_set():
        chunk = min(60.0, total_wait - waited)
        # Event.wait returns True if set (shutdown), False on timeout
        if shutdown_event.wait(timeout=chunk):
            break
        waited += chunk
        remaining_min = (total_wait - waited) / 60
        if remaining_min > 1:
            log.info("  %.0f min remaining...", remaining_min)


def check_agents(states: list[AgentState]) -> tuple[bool, bool]:
    """
    Check all agent processes. Returns (all_done, any_rate_limited).
    Updates agent states in place.
    """
    all_done = True
    any_rate_limited = False

    for state in states:
        if state.status in ("completed", "failed"):
            continue

        all_done = False

        if state.process is None:
            continue

        ret = state.process.poll()
        if ret is None:
            # Still running
            continue

        # Process exited — wait for reader threads to finish draining
        for t in state.reader_threads:
            t.join(timeout=5)
        state.reader_threads = []

        state.last_exit_code = ret
        state.process = None

        stdout_text, stderr_text = collect_agent_output(state)

        # Try to capture session ID for resume (reader thread may have it already)
        if not state.session_id:
            sid = extract_session_id(stdout_text)
            if sid:
                state.session_id = sid
        if state.session_id:
            log.info("Agent '%s' session_id: %s", state.config.name, state.session_id)

        if ret == 0 and not detect_rate_limit(ret, stderr_text):
            log.info("Agent '%s' completed (exit 0)", state.config.name)
            state.status = "completed"
        elif detect_rate_limit(ret, stderr_text):
            log.warning(
                "Agent '%s' hit rate limit (exit %d)", state.config.name, ret
            )
            state.status = "rate_limited"
            any_rate_limited = True
        else:
            # Non-zero exit that doesn't look like rate limit.
            # Treat as rate limit anyway — Claude often exits 1 on throttle.
            log.warning(
                "Agent '%s' exited with code %d (assuming rate limit)",
                state.config.name,
                ret,
            )
            state.status = "rate_limited"
            any_rate_limited = True

    return all_done, any_rate_limited


def print_status(states: list[AgentState]) -> None:
    """Print a summary of all agents."""
    log.info("--- Agent Status ---")
    for s in states:
        extra = ""
        if s.process:
            extra = f" pid={s.process.pid}"
        elif s.last_exit_code is not None:
            extra = f" last_exit={s.last_exit_code}"
        log.info(
            "  %-15s  status=%-14s  spawns=%d%s",
            s.config.name,
            s.status,
            s.spawn_count,
            extra,
        )
    log.info("--------------------")


def run(config_path: str, dry_run: bool = False) -> None:
    """Main guardian loop."""
    settings, agent_configs = load_config(config_path)

    if not agent_configs:
        log.error("No agents defined in %s", config_path)
        sys.exit(1)

    poll_interval = settings["poll_interval"]
    cooldown_buffer = settings["cooldown_buffer"]
    max_respawns = settings["max_respawns"]

    log.info("Claude Session Guardian starting")
    log.info("  Agents: %d", len(agent_configs))
    log.info("  Poll interval: %ds", poll_interval)
    log.info("  Cooldown buffer: %ds", cooldown_buffer)
    log.info("  Max respawns: %s", max_respawns or "unlimited")
    if dry_run:
        log.info("  *** DRY RUN MODE ***")

    # Determine log dir from first agent's project dir
    base_dir = agent_configs[0].project_dir
    log_dir = make_log_dir(base_dir)
    log.info("  Log dir: %s", log_dir)

    states = []
    for i, cfg in enumerate(agent_configs):
        s = AgentState(config=cfg)
        s.color = AGENT_COLORS[i % len(AGENT_COLORS)]
        states.append(s)

    # Initial spawn
    for state in states:
        spawn_agent(state, log_dir, dry_run=dry_run)
        # Stagger spawns slightly to avoid thundering herd
        if len(states) > 1:
            time.sleep(2)

    print_status(states)

    # Signal handling for clean shutdown using threading.Event
    # so all waits can be interrupted immediately.
    shutdown_event = threading.Event()

    def terminate_all():
        """Send SIGTERM to all running agent processes."""
        for st in states:
            if st.process and st.process.poll() is None:
                try:
                    st.process.terminate()
                except OSError:
                    pass

    def handle_signal(signum, frame):
        log.info("Signal %d received, shutting down...", signum)
        shutdown_event.set()
        # Immediately terminate children so they don't linger
        terminate_all()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Main loop
    while not shutdown_event.is_set():
        # Use event.wait instead of time.sleep so Ctrl+C wakes us immediately
        if shutdown_event.wait(timeout=poll_interval):
            break

        all_done, any_rate_limited = check_agents(states)

        if all_done:
            log.info("All agents completed. Guardian exiting.")
            break

        if any_rate_limited:
            print_status(states)

            # Check if any agents are still running — wait for them too
            running = [s for s in states if s.status == "running"]
            if running:
                log.info(
                    "%d agent(s) still running. Waiting for them to finish before cooldown...",
                    len(running),
                )
                # Keep polling until all running agents also finish
                while running and not shutdown_event.is_set():
                    if shutdown_event.wait(timeout=poll_interval):
                        break
                    check_agents(states)
                    running = [s for s in states if s.status == "running"]

            if shutdown_event.is_set():
                break

            # Now all agents are stopped — wait for next billing window
            wait_for_next_window(cooldown_buffer, shutdown_event)

            if shutdown_event.is_set():
                break

            # Respawn all rate-limited agents
            respawned = 0
            for state in states:
                if state.status != "rate_limited":
                    continue
                if max_respawns and state.spawn_count >= max_respawns:
                    log.warning(
                        "Agent '%s' hit max respawns (%d). Marking failed.",
                        state.config.name,
                        max_respawns,
                    )
                    state.status = "failed"
                    continue

                spawn_agent(state, log_dir, dry_run=dry_run)
                respawned += 1
                if respawned < len(states):
                    shutdown_event.wait(timeout=2)

            if respawned:
                log.info("Respawned %d agent(s)", respawned)
                print_status(states)

    # Cleanup — terminate any processes still alive
    log.info("Shutting down...")
    for state in states:
        if state.process and state.process.poll() is None:
            log.info("Terminating agent '%s' (pid %d)", state.config.name, state.process.pid)
            state.process.terminate()
            try:
                state.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                log.warning("Force-killing agent '%s'", state.config.name)
                state.process.kill()
                state.process.wait()
        # Wait for reader threads to drain
        for t in state.reader_threads:
            t.join(timeout=3)

    print_status(states)
    log.info("Guardian stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Claude Session Guardian — auto-respawn agents on session limits"
    )
    parser.add_argument(
        "-c",
        "--config",
        default="scripts/agents.yaml",
        help="Path to agent config YAML (default: scripts/agents.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without spawning agents",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=LOG_FMT,
        datefmt=LOG_DATE,
    )

    run(args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
