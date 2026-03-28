"""Breqy CLI — entry point for engine, TUI, and auth commands.

Usage:
    breqy engine start    Start the engine daemon (auto-spawns default agent)
    breqy engine stop     Stop a running engine daemon
    breqy tui             Launch the Textual TUI
    breqy auth <provider> Run standalone auth flow for a provider
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import click

# ---------------------------------------------------------------------------
# .env auto-loading — must happen before any config model reads os.getenv()
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Load .env from CWD or project root (if detectable)."""
    from dotenv import load_dotenv

    # Try CWD first, then walk up to find .env
    candidates = [Path.cwd() / ".env"]
    # Also check if we're inside a git repo
    try:
        import subprocess
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        candidates.append(Path(root) / ".env")
    except Exception:
        pass

    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return


_load_dotenv()


# ---------------------------------------------------------------------------
# PID file helpers
# ---------------------------------------------------------------------------

def _pid_file_path() -> Path:
    data_dir = os.getenv("BREQY_DATA_DIR", str(Path.home() / ".breqy" / "data"))
    return Path(os.path.expandvars(os.path.expanduser(data_dir))).resolve() / "engine.pid"


def _write_pid(pid: int) -> None:
    path = _pid_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid))


def _read_pid() -> int | None:
    path = _pid_file_path()
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


def _remove_pid() -> None:
    path = _pid_file_path()
    path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CLI structure
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(version="0.1.0", prog_name="breqy")
def main() -> None:
    """Breqy — always-on AI assistant with engine, agents, and TUI."""


# ---------------------------------------------------------------------------
# Engine commands
# ---------------------------------------------------------------------------

@main.group()
def engine() -> None:
    """Manage the Breqy engine daemon."""


@engine.command("start")
@click.option("--socket", "socket_path", default=None, help="Unix socket path (overrides BREQY_ENGINE_SOCKET)")
@click.option("--data-dir", default=None, help="Data directory (overrides BREQY_DATA_DIR)")
@click.option("--log-level", default=None, type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False), help="Log level")
@click.option("--no-agent", is_flag=True, default=False, help="Don't auto-spawn the default agent")
@click.option("--agent-dir", default="agents/breqy", show_default=True, help="Path to default agent directory")
def engine_start(
    socket_path: str | None,
    data_dir: str | None,
    log_level: str | None,
    no_agent: bool,
    agent_dir: str,
) -> None:
    """Start the Breqy engine daemon.

    Initializes storage, starts the A2A server, and (by default) auto-spawns
    the default agent. Blocks until interrupted with Ctrl+C or SIGTERM.
    """
    # Apply CLI overrides to env (so EngineConfig picks them up)
    if socket_path:
        os.environ["BREQY_ENGINE_SOCKET"] = socket_path
    if data_dir:
        os.environ["BREQY_DATA_DIR"] = data_dir
    if log_level:
        os.environ["BREQY_LOG_LEVEL"] = log_level.upper()

    from breqy.config.loader import load_engine_config
    from breqy.engine.daemon import EngineDaemon

    config = load_engine_config()

    click.echo(f"Starting Breqy engine...")
    click.echo(f"  Socket:    {config.socket_path}")
    click.echo(f"  Data dir:  {config.data_dir}")
    click.echo(f"  Database:  {config.db_path}")
    click.echo(f"  Log level: {config.log_level}")

    async def run() -> None:
        daemon = EngineDaemon(config)
        loop = asyncio.get_running_loop()

        stop_task: asyncio.Task[None] | None = None

        def handle_signal() -> None:
            nonlocal stop_task
            if stop_task is None:
                click.echo("\nShutting down engine...")
                stop_task = loop.create_task(daemon.stop())

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_signal)

        await daemon.start()
        _write_pid(os.getpid())

        # Auto-spawn default agent
        if not no_agent:
            agent_path = Path(agent_dir)
            if agent_path.exists() and (agent_path / "agent.yaml").exists():
                try:
                    pid = await daemon.start_default_agent()
                    click.echo(f"  Default agent spawned (PID {pid})")
                except Exception as exc:
                    click.echo(f"  Warning: failed to spawn default agent: {exc}", err=True)
            else:
                click.echo(f"  Warning: agent dir '{agent_dir}' not found, skipping agent spawn", err=True)

        click.echo("Engine ready. Press Ctrl+C to stop.")

        await daemon.wait_until_stopped()

        _remove_pid()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        _remove_pid()
        click.echo("Engine stopped.")


@engine.command("stop")
def engine_stop() -> None:
    """Stop a running Breqy engine daemon.

    Sends SIGTERM to the engine process using its PID file.
    """
    pid = _read_pid()
    if pid is None:
        click.echo("No running engine found (no PID file).", err=True)
        sys.exit(1)

    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(f"Sent SIGTERM to engine (PID {pid}).")
        _remove_pid()
    except ProcessLookupError:
        click.echo(f"Engine process {pid} not found (stale PID file). Cleaning up.", err=True)
        _remove_pid()
    except PermissionError:
        click.echo(f"Permission denied sending signal to PID {pid}.", err=True)
        sys.exit(1)


@engine.command("status")
def engine_status() -> None:
    """Check if the engine is running."""
    pid = _read_pid()
    if pid is None:
        click.echo("Engine is not running (no PID file).")
        return

    try:
        os.kill(pid, 0)  # signal 0 = check if process exists
        click.echo(f"Engine is running (PID {pid}).")
    except ProcessLookupError:
        click.echo(f"Engine is not running (stale PID file for PID {pid}). Cleaning up.")
        _remove_pid()
    except PermissionError:
        click.echo(f"Engine process {pid} exists but access denied.")


# ---------------------------------------------------------------------------
# TUI command
# ---------------------------------------------------------------------------

@main.command("tui")
@click.option("--socket", "socket_path", default=None, help="Engine socket path (overrides BREQY_ENGINE_SOCKET)")
def tui(socket_path: str | None) -> None:
    """Launch the Breqy TUI.

    Connects to a running engine via the A2A Unix socket and provides
    the full terminal UI for session management, chat, approvals, and more.
    """
    if socket_path:
        os.environ["BREQY_ENGINE_SOCKET"] = socket_path

    resolved = socket_path or os.getenv("BREQY_ENGINE_SOCKET", "/tmp/breqy-engine.sock")

    # Set up structured logging for the TUI process
    from breqy.utils.logging import default_log_file, setup_logging

    data_dir = os.getenv("BREQY_DATA_DIR", str(Path.home() / ".breqy" / "data"))
    log_dir = Path(os.path.expandvars(os.path.expanduser(data_dir))).resolve() / "logs"
    log_level = os.getenv("BREQY_LOG_LEVEL", "INFO").upper()

    setup_logging(
        level=log_level,
        log_file=default_log_file(log_dir, process="tui"),
        console=False,
        context={"process": "tui"},
    )

    from breqy.tui.app import BreqyApp

    app = BreqyApp(socket_path=resolved)
    app.run()


# ---------------------------------------------------------------------------
# Auth command
# ---------------------------------------------------------------------------

@main.command("auth")
@click.argument("provider", type=click.Choice(["copilot", "codex", "claude", "gemini", "qwen"], case_sensitive=False))
def auth(provider: str) -> None:
    """Run standalone authentication for a model provider.

    Triggers the appropriate auth flow (device flow, PKCE, or API key entry)
    and stores credentials in the OS keyring under breqy/<provider>.
    """
    from breqy.agents.auth.adapters import build_provider_auth_backends
    from breqy.agents.auth.service import AuthService
    from breqy.agents.credentials import CredentialStore
    from breqy.secrets.provider import KeyringSecretProvider

    secret_provider = KeyringSecretProvider()
    credential_store = CredentialStore(secret_provider)
    backends = build_provider_auth_backends(secret_provider=secret_provider)
    service = AuthService(credential_store=credential_store, backends=backends)

    # Check current status
    status = service.get_status(provider)
    click.echo(f"Current status for {provider}: {status.status.value}")

    if status.status.value == "authenticated":
        if not click.confirm("Already authenticated. Re-authenticate?"):
            return

    # Start auth flow
    session = service.start(provider)
    click.echo(f"Auth flow: {session.flow_kind.value}")

    if session.verification_url:
        click.echo(f"  Open: {session.verification_url}")
    if session.user_code:
        click.echo(f"  Code: {session.user_code}")
    if session.display_message:
        click.echo(f"  {session.display_message}")

    # For API key / PKCE flows, prompt for input
    if session.flow_kind.value in ("api_key",):
        secret = click.prompt("Enter API key", hide_input=True)
        result = service.submit_secret(provider, secret)
        if result.status.value == "authenticated":
            click.echo(f"Authenticated with {provider} successfully.")
        else:
            click.echo(f"Failed: {result.last_error}", err=True)
            sys.exit(1)
    elif session.flow_kind.value in ("pkce",):
        code = click.prompt("Paste authorization code")
        result = service.submit_code(provider, code)
        if result.status.value == "authenticated":
            click.echo(f"Authenticated with {provider} successfully.")
        else:
            click.echo(f"Failed: {result.last_error}", err=True)
            sys.exit(1)
    elif session.flow_kind.value in ("device_code",):
        click.echo("Waiting for device authorization (check your browser)...")
        code = click.prompt("Press Enter when authorized, or paste code if prompted", default="", show_default=False)
        if code:
            result = service.submit_code(provider, code)
        else:
            # For device flow, the backend polls — check status
            result = service.get_status(provider)
        if result.status.value == "authenticated":
            click.echo(f"Authenticated with {provider} successfully.")
        else:
            click.echo(f"Status: {result.status.value}", err=True)
            if result.last_error:
                click.echo(f"Error: {result.last_error}", err=True)


if __name__ == "__main__":
    main()
