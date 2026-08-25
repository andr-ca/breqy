"""
Orchestrator entry point.

Usage:
    python -m system.orchestrator.main --config system/orchestrator/orchestrator.yaml
    python -m system.orchestrator.main --config system/orchestrator/orchestrator.yaml --no-tui
    python -m system.orchestrator.main auth
    python -m system.orchestrator.main auth claude
    python -m system.orchestrator.main run --config system/orchestrator/orchestrator.yaml
"""
from __future__ import annotations

import argparse
import queue
import signal
import sys
import threading
from pathlib import Path

from system.orchestrator.artifact_store import ArtifactStore
from system.orchestrator.branch_manager import BranchManager
from system.orchestrator.ci_adapter import CIAdapter
from system.orchestrator.config import OrchestratorConfig, load_config
from system.orchestrator.event_log import EventLog
from system.orchestrator.github_adapter import GitHubAdapter
from system.orchestrator.github_task_loader import GitHubTaskLoader
from system.orchestrator.local_task_loader import LocalYamlTaskLoader
from system.orchestrator.orchestrator import OrchestratorLoop
from system.orchestrator.state_machine import ConcreteStateMachine
from system.orchestrator.task_loader import CompositeTaskLoader

_PROVIDER_CHOICES = ["claude", "codex", "gemini", "copilot", "qwen"]


def _build_loop(cfg_path: Path) -> tuple[OrchestratorLoop, queue.Queue, OrchestratorConfig]:
    cfg = load_config(cfg_path)
    sm = ConcreteStateMachine(
        max_rework_loops=cfg.orchestrator.max_rework_loops,
        max_retries=cfg.orchestrator.max_retries,
    )
    store = ArtifactStore(base=Path(cfg.orchestrator.artifact_base))
    log = EventLog(path=Path(cfg.orchestrator.event_log))
    eq: queue.Queue = queue.Queue(maxsize=1000)
    loop = OrchestratorLoop(
        config=cfg,
        state_machine=sm,
        artifact_store=store,
        event_log=log,
        event_queue=eq,
    )
    return loop, eq, cfg


def _run_orchestrator(cfg_path: str, no_tui: bool) -> None:
    loop, eq, cfg = _build_loop(Path(cfg_path))

    # Build loaders and reconstruct loop with constructor-injected dependencies
    github_loader = GitHubTaskLoader(
        repo=cfg.github.repo, managed_label=cfg.github.managed_label
    )
    local_loader = LocalYamlTaskLoader(tasks_dir=Path(cfg.orchestrator.task_fallback_dir))
    composite = CompositeTaskLoader(github=github_loader, local=local_loader)
    loop = OrchestratorLoop(
        config=cfg,
        state_machine=loop._sm,
        artifact_store=loop._artifact_store,
        event_log=loop._log,
        event_queue=eq,
        loader=composite,
        branch_manager=BranchManager(repo_root=Path.cwd()),
        ci_adapter=CIAdapter(repo=cfg.github.repo),
        github_adapter=GitHubAdapter(repo=cfg.github.repo),
    )

    # Start orchestrator loop in background thread
    loop_thread = threading.Thread(
        target=loop.run, args=(), daemon=True, name="orchestrator-loop"
    )
    loop_thread.start()

    signal.signal(signal.SIGINT, lambda s, f: None)
    signal.signal(signal.SIGTERM, lambda s, f: None)

    def _shutdown(signum, frame):
        print("\n[orchestrator] Shutdown requested — waiting for current step...")
        loop.stop()
        loop_thread.join(timeout=30)
        if loop_thread.is_alive():
            loop.force_kill_current()
        loop.flush(cfg)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if no_tui:
        loop_thread.join()
        return

    # Launch TUI (blocks main thread)
    from system.orchestrator.tui.app import OrchestratorApp
    app = OrchestratorApp(event_queue=eq, tasks=[])
    app.run()
    loop.stop()
    loop_thread.join(timeout=30)


def _run_auth(provider_filter: str | None = None) -> None:
    from system.orchestrator.auth import ALL_PROVIDER_CLASSES
    from system.orchestrator.auth.credential_store import CredentialStore
    from system.orchestrator.tui.auth_app import AuthApp

    store = CredentialStore()
    if provider_filter:
        cls = ALL_PROVIDER_CLASSES.get(provider_filter)
        if cls is None:
            print(f"Unknown provider: {provider_filter}")
            return
        providers = {provider_filter: cls(credential_store=store)}
    else:
        providers = {name: cls(credential_store=store)
                     for name, cls in ALL_PROVIDER_CLASSES.items()}

    app = AuthApp(providers=providers)
    app.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Breqy Orchestrator")
    # Top-level flags for backward compatibility (breqy-orchestrator --config X)
    parser.add_argument("--config", default="system/orchestrator/orchestrator.yaml",
                        help="Path to orchestrator.yaml")
    parser.add_argument("--no-tui", action="store_true", help="Run without TUI")

    subparsers = parser.add_subparsers(dest="command")

    # 'run' subcommand — mirrors top-level flags for symmetry
    run_parser = subparsers.add_parser("run", help="Run the orchestrator loop")
    run_parser.add_argument("--config", default="system/orchestrator/orchestrator.yaml",
                            help="Path to orchestrator.yaml")
    run_parser.add_argument("--no-tui", action="store_true", help="Run without TUI")

    # 'auth' subcommand
    auth_parser = subparsers.add_parser("auth", help="Manage provider authentication")
    auth_parser.add_argument(
        "provider", nargs="?", choices=_PROVIDER_CHOICES,
        help="Specific provider to authenticate (omit to show all)"
    )

    args = parser.parse_args()

    if args.command == "auth":
        _run_auth(getattr(args, "provider", None))
    elif args.command == "run":
        _run_orchestrator(args.config, args.no_tui)
    else:
        # No subcommand — use top-level flags (backward compat)
        _run_orchestrator(args.config, args.no_tui)


if __name__ == "__main__":
    main()
