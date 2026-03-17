import json
import pytest
from pathlib import Path
from system.orchestrator.event_log import EventLog
from system.orchestrator.schemas.events import OrchestratorEvent


def test_append_creates_file(tmp_path):
    log = EventLog(path=tmp_path / "events.jsonl")
    event = OrchestratorEvent(task_id="BRQ-1", event_type="state_transition")
    log.append(event)
    assert (tmp_path / "events.jsonl").exists()


def test_append_writes_valid_json_line(tmp_path):
    log = EventLog(path=tmp_path / "events.jsonl")
    event = OrchestratorEvent(task_id="BRQ-1", event_type="agent_spawn", role="doer")
    log.append(event)
    lines = (tmp_path / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["task_id"] == "BRQ-1"
    assert data["event_type"] == "agent_spawn"
    assert data["role"] == "doer"


def test_append_multiple_events(tmp_path):
    log = EventLog(path=tmp_path / "events.jsonl")
    for i in range(5):
        log.append(OrchestratorEvent(task_id=f"BRQ-{i}", event_type="test"))
    lines = (tmp_path / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 5


def test_tail_returns_last_n(tmp_path):
    log = EventLog(path=tmp_path / "events.jsonl")
    for i in range(10):
        log.append(OrchestratorEvent(task_id=f"BRQ-{i}", event_type="test"))
    events = log.tail(3)
    assert len(events) == 3
    assert events[-1].task_id == "BRQ-9"


def test_tail_on_empty_file(tmp_path):
    log = EventLog(path=tmp_path / "events.jsonl")
    assert log.tail(5) == []


def test_creates_parent_directory(tmp_path):
    log = EventLog(path=tmp_path / "nested" / "dir" / "events.jsonl")
    log.append(OrchestratorEvent(task_id="BRQ-1", event_type="test"))
    assert log._path.exists()
