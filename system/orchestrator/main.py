"""
Orchestrator entry point.

Usage:
    python -m system.orchestrator.main --config system/orchestrator/orchestrator.yaml
    python -m system.orchestrator.main --config system/orchestrator/orchestrator.yaml --no-tui
"""
from __future__ import annotations
import argparse
import queue
import signal
import sys
import threading
from pathlib import Path
from system.orchestrator.artifact_store import ArtifactStore
from system.orchestrator.config import load_config, OrchestratorConfig
from system.orchestrator.event_log import EventLog
from system.orchestrator.orchestrator import OrchestratorLoop
from system.orchestrator.state_machine import ConcreteStateMachine, Task, TaskState
from system.orchestrator.task_loader import CompositeTaskLoader
from system.orchestrator.github_task_loader import GitHubTaskLoader
from system.orchestrator.local_task_loader import LocalYamlTaskLoader


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Breqy Orchestrator")
    parser.add_argument("--config", default="system/orchestrator/orchestrator.yaml",
                        help="Path to orchestrator.yaml")
    parser.add_argument("--no-tui", action="store_true", help="Run without TUI")
    args = parser.parse_args()

    loop, eq, cfg = _build_loop(Path(args.config))

    # Load tasks
    github_loader = GitHubTaskLoader(
        repo=cfg.github.repo, managed_label=cfg.github.managed_label
    )
    local_loader = LocalYamlTaskLoader(tasks_dir=Path(cfg.orchestrator.task_fallback_dir))
    composite = CompositeTaskLoader(github=github_loader, local=local_loader)
    envelopes = composite.load_pending()
    tasks = [(Task(task_id=env.task_id, state=TaskState.NEW), env) for env in envelopes]

    # Start orchestrator loop in background thread
    loop_thread = threading.Thread(
        target=loop.run, args=(tasks,), daemon=True, name="orchestrator-loop"
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

    if args.no_tui:
        loop_thread.join()
        return

    # Launch TUI (blocks main thread)
    from system.orchestrator.tui.app import OrchestratorApp
    app = OrchestratorApp(event_queue=eq, tasks=tasks)
    app.run()
    loop.stop()
    loop_thread.join(timeout=30)


if __name__ == "__main__":
    main()
