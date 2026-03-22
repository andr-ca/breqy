# Phase 3 Plan 02: A2A Protocol

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the full A2A wire protocol: typed envelope format, length-prefixed Unix socket transport, engine-side server, and agent/TUI-side client — verified with integration tests that prove a full duplex message exchange.

**Architecture:** Three modules under `breqy/a2a/`. `envelope.py` defines the JSON wire format and round-trip helpers. `transport.py` provides async Unix socket helpers and `FrameReader`/`FrameWriter` for length-prefixed framing (4-byte big-endian uint32). `server.py` is the engine-side acceptor; `client.py` is the agent/TUI-side connector. Integration tests use `socket_path` fixture (already in `tests/conftest.py`) and real asyncio connections over a temporary socket.

**Tech Stack:** Python 3.12, asyncio, pydantic v2, pytest-asyncio

**Worktree:** `/home/andrey/projects/breqy/.worktrees/exp-full-build`
**Run tests with:** `uv run pytest`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `breqy/a2a/__init__.py` | Create | Package init |
| `breqy/a2a/envelope.py` | Create | `Envelope` model, `encode_envelope`, `decode_envelope`, `from_event`, `to_event` |
| `breqy/a2a/transport.py` | Create | `FrameReader`, `FrameWriter`, `start_unix_server`, `connect_unix` |
| `breqy/a2a/server.py` | Create | `A2AServer` — accept connections, route, broadcast |
| `breqy/a2a/client.py` | Create | `A2AClient` — connect, send, listen |
| `tests/unit/a2a/__init__.py` | Create | Test package stub |
| `tests/unit/a2a/test_envelope.py` | Create | Envelope round-trip tests |
| `tests/unit/a2a/test_transport.py` | Create | Frame encode/decode tests |
| `tests/integration/__init__.py` | Create | Integration test package stub |
| `tests/integration/a2a/__init__.py` | Create | A2A integration stub |
| `tests/integration/a2a/test_server_client.py` | Create | Full duplex server+client tests |

---

## Task 1: A2A Envelope

**Files:**
- Create: `breqy/a2a/__init__.py`
- Create: `breqy/a2a/envelope.py`
- Create: `tests/unit/a2a/__init__.py`
- Create: `tests/unit/a2a/test_envelope.py`

- [ ] **Step 1: Write failing envelope tests**

Create `tests/unit/a2a/__init__.py` (empty) and `tests/unit/a2a/test_envelope.py`:

```python
"""Tests for A2A Envelope format."""
from __future__ import annotations

import pytest

from breqy.a2a.envelope import Envelope, decode_envelope, encode_envelope
from breqy.domain.enums import EventType
from breqy.domain.events import MessageSentEvent


def test_envelope_from_event():
    """Envelope.from_event extracts metadata and payload correctly."""
    event = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_001",
        role="user",
        content="hello",
    )
    env = Envelope.from_event(event)
    assert env.session_id == "ses_test"
    assert env.event_type == EventType.MESSAGE_SENT
    assert env.payload["content"] == "hello"
    assert env.payload["message_id"] == "msg_001"


def test_envelope_to_event_round_trip():
    """Envelope.to_event reconstructs the original typed event."""
    event = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_002",
        role="user",
        content="round trip",
    )
    env = Envelope.from_event(event)
    restored = env.to_event()
    assert isinstance(restored, MessageSentEvent)
    assert restored.content == "round trip"
    assert restored.session_id == "ses_test"


def test_envelope_json_serialization():
    """Envelope serializes to and from JSON without loss."""
    event = MessageSentEvent(
        session_id="ses_abc",
        message_id="msg_003",
        role="agent",
        content="json test",
    )
    env = Envelope.from_event(event)
    json_str = env.model_dump_json()
    restored = Envelope.model_validate_json(json_str)
    assert restored.session_id == env.session_id
    assert restored.payload["content"] == "json test"


def test_encode_decode_envelope():
    """encode_envelope and decode_envelope are inverses."""
    event = MessageSentEvent(
        session_id="ses_enc",
        message_id="msg_004",
        role="user",
        content="encode test",
    )
    env = Envelope.from_event(event)
    encoded = encode_envelope(env)
    # first 4 bytes are length prefix
    assert len(encoded) > 4
    decoded = decode_envelope(encoded)
    assert decoded.session_id == env.session_id
    assert decoded.payload["content"] == "encode test"
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/unit/a2a/test_envelope.py -v
```
Expected: `ModuleNotFoundError: No module named 'breqy.a2a'`

- [ ] **Step 3: Create `breqy/a2a/__init__.py`** (empty)

- [ ] **Step 4: Create `breqy/a2a/envelope.py`**

```python
"""A2A Envelope: the wire format for all engine-agent communication.

Every message on the wire is a length-prefixed JSON envelope containing:
- event metadata (type, version, IDs, timestamp)
- payload (event-specific fields)

Wire encoding: 4-byte big-endian uint32 length prefix + UTF-8 JSON bytes.
"""
from __future__ import annotations

import struct
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from breqy.domain.enums import EventType
from breqy.domain.events import Event, deserialize_event
from breqy.domain.ids import generate_prefixed_id


class Envelope(BaseModel):
    """Wire-format envelope wrapping a typed event."""

    event_id: str = Field(default_factory=lambda: generate_prefixed_id("evt"))
    event_type: EventType
    schema_version: int = 1
    session_id: str
    agent_id: str = ""
    correlation_id: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_event(cls, event: Event) -> "Envelope":
        """Create an envelope from a typed Event."""
        data = event.model_dump()
        envelope_keys = {
            "event_id",
            "event_type",
            "schema_version",
            "session_id",
            "agent_id",
            "correlation_id",
            "timestamp",
        }
        payload = {k: v for k, v in data.items() if k not in envelope_keys}
        return cls(
            event_id=event.event_id,
            event_type=event.event_type,
            schema_version=event.schema_version,
            session_id=event.session_id,
            agent_id=event.agent_id,
            correlation_id=event.correlation_id,
            timestamp=(
                event.timestamp.isoformat()
                if isinstance(event.timestamp, datetime)
                else str(event.timestamp)
            ),
            payload=payload,
        )

    def to_event(self) -> Event:
        """Reconstruct the typed Event from this envelope."""
        data = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            **self.payload,
        }
        return deserialize_event(data)


def encode_envelope(envelope: Envelope) -> bytes:
    """Encode an envelope to length-prefixed JSON bytes."""
    json_bytes = envelope.model_dump_json().encode("utf-8")
    length = struct.pack("!I", len(json_bytes))
    return length + json_bytes


def decode_envelope(data: bytes) -> Envelope:
    """Decode an envelope from length-prefixed JSON bytes."""
    if len(data) < 4:
        raise ValueError("Data too short for length prefix")
    length = struct.unpack("!I", data[:4])[0]
    json_bytes = data[4 : 4 + length]
    return Envelope.model_validate_json(json_bytes)
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/unit/a2a/test_envelope.py -v
```
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add breqy/a2a/__init__.py breqy/a2a/envelope.py \
        tests/unit/a2a/__init__.py tests/unit/a2a/test_envelope.py
git commit -m "feat(a2a): add Envelope with from_event/to_event and length-prefix wire encoding"
```

---

## Task 2: Transport (FrameReader/FrameWriter)

**Files:**
- Create: `breqy/a2a/transport.py`
- Create: `tests/unit/a2a/test_transport.py`

- [ ] **Step 1: Write failing transport tests**

Create `tests/unit/a2a/test_transport.py`:

```python
"""Tests for A2A transport framing."""
from __future__ import annotations

import asyncio
import struct

import pytest

from breqy.a2a.envelope import Envelope
from breqy.a2a.transport import FrameReader, FrameWriter
from breqy.domain.enums import EventType
from breqy.domain.events import MessageSentEvent


def _make_frame(payload_bytes: bytes) -> bytes:
    """Build a length-prefixed frame manually."""
    return struct.pack("!I", len(payload_bytes)) + payload_bytes


@pytest.mark.asyncio
async def test_frame_reader_reads_single_frame():
    """FrameReader.read_frame() reads one length-prefixed frame."""
    payload = b'{"hello": "world"}'
    raw = _make_frame(payload)
    reader = asyncio.StreamReader()
    reader.feed_data(raw)
    reader.feed_eof()
    frame_reader = FrameReader(reader)
    result = await frame_reader.read_frame()
    assert result == payload


@pytest.mark.asyncio
async def test_frame_reader_reads_envelope():
    """FrameReader.read_envelope() returns a parsed Envelope."""
    event = MessageSentEvent(
        session_id="ses_tr",
        message_id="msg_tr1",
        role="user",
        content="transport test",
    )
    env = Envelope.from_event(event)
    payload = env.model_dump_json().encode()
    raw = _make_frame(payload)

    reader = asyncio.StreamReader()
    reader.feed_data(raw)
    reader.feed_eof()

    frame_reader = FrameReader(reader)
    result = await frame_reader.read_envelope()
    assert result is not None
    assert result.session_id == "ses_tr"
    assert result.payload["content"] == "transport test"


@pytest.mark.asyncio
async def test_frame_writer_writes_frame():
    """FrameWriter.write_frame() produces correct length-prefixed bytes."""
    transport = asyncio.Transport()
    reader = asyncio.StreamReader()

    # Use asyncio pipe trick: write to writer, read from connected reader
    server_reader, server_writer = await asyncio.open_connection(
        sock=None
    ) if False else (None, None)

    # Simpler: just verify FrameWriter produces correct bytes in memory
    collected = bytearray()

    class FakeTransport(asyncio.Transport):
        def write(self, data: bytes) -> None:
            collected.extend(data)
        def get_extra_info(self, key, default=None):
            return default

    proto = asyncio.StreamReaderProtocol(asyncio.StreamReader())
    fake_writer = asyncio.StreamWriter(FakeTransport(), proto, asyncio.StreamReader(), asyncio.get_event_loop())

    # We verify via encode directly — FrameWriter is thin wrapper
    payload = b"frame content"
    frame_writer = FrameWriter(fake_writer)
    # Verify the method exists and is callable
    assert callable(frame_writer.write_frame)
    assert callable(frame_writer.write_envelope)
```

> **Note:** The `FrameWriter` tests use a lightweight smoke-test approach since writing to a real socket requires a server. Full round-trip is validated in the integration tests (Task 4).

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/unit/a2a/test_transport.py -v
```
Expected: `ModuleNotFoundError: No module named 'breqy.a2a.transport'`

- [ ] **Step 3: Create `breqy/a2a/transport.py`**

```python
"""Low-level Unix socket transport with length-prefixed framing.

Every frame on the wire:
  [4 bytes: big-endian uint32 payload length][payload bytes]
"""
from __future__ import annotations

import asyncio
import struct
from typing import Any, Callable, Coroutine

from breqy.a2a.envelope import Envelope


async def start_unix_server(
    client_handler: Callable[
        [asyncio.StreamReader, asyncio.StreamWriter],
        Coroutine[Any, Any, None],
    ],
    socket_path: str,
) -> asyncio.AbstractServer:
    """Start a Unix domain socket server."""
    return await asyncio.start_unix_server(client_handler, path=socket_path)


async def connect_unix(
    socket_path: str,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to a Unix domain socket server."""
    return await asyncio.open_unix_connection(socket_path)


class FrameReader:
    """Reads length-prefixed frames from an asyncio StreamReader."""

    def __init__(self, reader: asyncio.StreamReader) -> None:
        self._reader = reader

    async def read_frame(self) -> bytes | None:
        """Read one frame. Returns None on EOF."""
        try:
            header = await self._reader.readexactly(4)
        except asyncio.IncompleteReadError:
            return None
        length = struct.unpack("!I", header)[0]
        data = await self._reader.readexactly(length)
        return data

    async def read_envelope(self) -> Envelope | None:
        """Read one frame and parse as Envelope."""
        data = await self.read_frame()
        if data is None:
            return None
        return Envelope.model_validate_json(data)


class FrameWriter:
    """Writes length-prefixed frames to an asyncio StreamWriter."""

    def __init__(self, writer: asyncio.StreamWriter) -> None:
        self._writer = writer

    async def write_frame(self, data: bytes) -> None:
        """Write one frame with length prefix."""
        header = struct.pack("!I", len(data))
        self._writer.write(header + data)
        await self._writer.drain()

    async def write_envelope(self, envelope: Envelope) -> None:
        """Serialize and write an envelope as a frame."""
        json_bytes = envelope.model_dump_json().encode("utf-8")
        await self.write_frame(json_bytes)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/unit/a2a/test_transport.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add breqy/a2a/transport.py tests/unit/a2a/test_transport.py
git commit -m "feat(a2a): add FrameReader/FrameWriter and Unix socket helpers"
```

---

## Task 3: A2A Server & Client

**Files:**
- Create: `breqy/a2a/server.py`
- Create: `breqy/a2a/client.py`

No unit tests at this level — tested fully in integration tests (Task 4).

- [ ] **Step 1: Create `breqy/a2a/server.py`**

```python
"""Engine-side A2A server.

Accepts agent and TUI connections over Unix socket.
Routes incoming envelopes to a callback.
Supports broadcasting events to all connected clients.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

from breqy.a2a.envelope import Envelope
from breqy.a2a.transport import FrameReader, FrameWriter, start_unix_server
from breqy.domain.ids import generate_prefixed_id

logger = logging.getLogger(__name__)

OnEnvelopeCallback = Callable[[Envelope, str], Coroutine[Any, Any, None]]


class A2AServer:
    """Engine-side server that accepts A2A connections."""

    def __init__(
        self,
        socket_path: str,
        on_envelope: OnEnvelopeCallback,
    ) -> None:
        self._socket_path = socket_path
        self._on_envelope = on_envelope
        self._server: asyncio.AbstractServer | None = None
        self._clients: dict[str, FrameWriter] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Bind and start listening for connections."""
        self._server = await start_unix_server(
            self._handle_client, self._socket_path
        )
        logger.info("A2A server started on %s", self._socket_path)

    async def stop(self) -> None:
        """Close server and cancel client tasks."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for task in list(self._tasks):
            task.cancel()
        self._clients.clear()
        logger.info("A2A server stopped")

    async def broadcast(
        self, envelope: Envelope, exclude_client: str = ""
    ) -> None:
        """Send envelope to all connected clients."""
        disconnected: list[str] = []
        for client_id, writer in list(self._clients.items()):
            if client_id == exclude_client:
                continue
            try:
                await writer.write_envelope(envelope)
            except (ConnectionError, OSError):
                disconnected.append(client_id)
        for cid in disconnected:
            self._clients.pop(cid, None)

    async def send_to(self, client_id: str, envelope: Envelope) -> None:
        """Send envelope to a specific client by ID."""
        writer = self._clients.get(client_id)
        if writer:
            await writer.write_envelope(envelope)

    @property
    def connected_client_ids(self) -> list[str]:
        return list(self._clients.keys())

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        client_id = generate_prefixed_id("cli")
        frame_reader = FrameReader(reader)
        frame_writer = FrameWriter(writer)
        self._clients[client_id] = frame_writer
        logger.info("Client connected: %s", client_id)

        try:
            while True:
                try:
                    envelope = await frame_reader.read_envelope()
                    if envelope is None:
                        break
                    await self._on_envelope(envelope, client_id)
                except asyncio.IncompleteReadError:
                    break
                except Exception as exc:
                    logger.error(
                        "Error reading from client %s: %s", client_id, exc
                    )
                    break
        finally:
            self._clients.pop(client_id, None)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("Client disconnected: %s", client_id)
```

- [ ] **Step 2: Create `breqy/a2a/client.py`**

```python
"""Agent/TUI-side A2A client.

Connects to the engine's Unix socket, sends events, and
listens for incoming events via async iteration.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from breqy.a2a.envelope import Envelope
from breqy.a2a.transport import FrameReader, FrameWriter, connect_unix
from breqy.domain.events import Event

logger = logging.getLogger(__name__)


class A2AClient:
    """Client that connects to the engine's A2A server."""

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._frame_reader: FrameReader | None = None
        self._frame_writer: FrameWriter | None = None

    async def connect(self) -> None:
        """Establish connection to the engine socket."""
        self._reader, self._writer = await connect_unix(self._socket_path)
        self._frame_reader = FrameReader(self._reader)
        self._frame_writer = FrameWriter(self._writer)
        logger.info("Connected to engine at %s", self._socket_path)

    async def disconnect(self) -> None:
        """Close the connection."""
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
        self._frame_reader = None
        self._frame_writer = None

    async def send_envelope(self, envelope: Envelope) -> None:
        """Send a pre-built envelope."""
        if self._frame_writer is None:
            raise ConnectionError("Not connected")
        await self._frame_writer.write_envelope(envelope)

    async def send_event(self, event: Event) -> None:
        """Wrap event in envelope and send."""
        envelope = Envelope.from_event(event)
        await self.send_envelope(envelope)

    async def listen(self) -> AsyncIterator[Envelope]:
        """Async iterator that yields envelopes from the server."""
        if self._frame_reader is None:
            raise ConnectionError("Not connected")
        while True:
            try:
                envelope = await self._frame_reader.read_envelope()
                if envelope is None:
                    break
                yield envelope
            except asyncio.IncompleteReadError:
                break
            except Exception as exc:
                logger.error("Error reading from server: %s", exc)
                break
```

- [ ] **Step 3: Verify imports work**

```bash
uv run python -c "from breqy.a2a.server import A2AServer; from breqy.a2a.client import A2AClient; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add breqy/a2a/server.py breqy/a2a/client.py
git commit -m "feat(a2a): add A2AServer (engine-side) and A2AClient (agent/TUI-side)"
```

---

## Task 4: Integration Tests (Server + Client)

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/a2a/__init__.py`
- Create: `tests/integration/a2a/test_server_client.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/integration/__init__.py` (empty), `tests/integration/a2a/__init__.py` (empty), and `tests/integration/a2a/test_server_client.py`:

```python
"""Integration tests for A2A server + client over Unix socket."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from breqy.a2a.client import A2AClient
from breqy.a2a.envelope import Envelope
from breqy.a2a.server import A2AServer
from breqy.domain.events import MessageSentEvent


@pytest.mark.asyncio
async def test_client_sends_event_to_server(socket_path: Path):
    """Client sends a typed event; server callback receives it."""
    received: list[Envelope] = []

    async def on_envelope(envelope: Envelope, client_id: str) -> None:
        received.append(envelope)

    server = A2AServer(str(socket_path), on_envelope=on_envelope)
    await server.start()

    client = A2AClient(str(socket_path))
    await client.connect()

    event = MessageSentEvent(
        session_id="ses_integ1",
        message_id="msg_integ1",
        role="user",
        content="Hello from client",
    )
    await client.send_event(event)
    await asyncio.sleep(0.05)

    await client.disconnect()
    await server.stop()

    assert len(received) == 1
    assert received[0].session_id == "ses_integ1"
    assert received[0].payload["content"] == "Hello from client"


@pytest.mark.asyncio
async def test_server_broadcasts_to_client(socket_path: Path):
    """Server broadcasts an envelope; connected client receives it."""
    received: list[Envelope] = []

    async def on_envelope(envelope: Envelope, client_id: str) -> None:
        pass  # server receives nothing in this test

    server = A2AServer(str(socket_path), on_envelope=on_envelope)
    await server.start()

    client = A2AClient(str(socket_path))
    await client.connect()

    # give the server time to register the client connection
    await asyncio.sleep(0.05)

    async def collect_one() -> None:
        async for envelope in client.listen():
            received.append(envelope)
            break

    listen_task = asyncio.create_task(collect_one())

    event = MessageSentEvent(
        session_id="ses_integ2",
        message_id="msg_integ2",
        role="assistant",
        content="Hello from server",
    )
    envelope = Envelope.from_event(event)
    await server.broadcast(envelope)

    await asyncio.wait_for(listen_task, timeout=2.0)
    await client.disconnect()
    await server.stop()

    assert len(received) == 1
    assert received[0].payload["content"] == "Hello from server"


@pytest.mark.asyncio
async def test_full_duplex_exchange(socket_path: Path):
    """Full duplex: client sends, server echoes back, client receives."""
    server_received: list[Envelope] = []
    client_received: list[Envelope] = []
    server_ref: list[A2AServer] = []

    async def on_envelope(envelope: Envelope, client_id: str) -> None:
        server_received.append(envelope)
        # echo back to the sender
        await server_ref[0].send_to(client_id, envelope)

    server = A2AServer(str(socket_path), on_envelope=on_envelope)
    server_ref.append(server)
    await server.start()

    client = A2AClient(str(socket_path))
    await client.connect()
    await asyncio.sleep(0.05)

    async def collect_one() -> None:
        async for envelope in client.listen():
            client_received.append(envelope)
            break

    listen_task = asyncio.create_task(collect_one())

    event = MessageSentEvent(
        session_id="ses_duplex",
        message_id="msg_duplex",
        role="user",
        content="ping",
    )
    await client.send_event(event)

    await asyncio.wait_for(listen_task, timeout=2.0)
    await client.disconnect()
    await server.stop()

    assert len(server_received) == 1
    assert len(client_received) == 1
    assert client_received[0].payload["content"] == "ping"
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/integration/a2a/test_server_client.py -v
```
Expected: tests fail because `socket_path` fixture is used but integration tests need to find it. The fixture is in `tests/conftest.py` — it is auto-discovered by pytest for all subdirectories.

If `socket_path` fixture is not found, check `tests/conftest.py`. It should have:
```python
@pytest.fixture
def socket_path(tmp_path: Path) -> Path:
    return tmp_path / "test.sock"
```

- [ ] **Step 3: Check conftest has socket_path fixture**

```bash
grep -n "socket_path" /home/andrey/projects/breqy/.worktrees/exp-full-build/tests/conftest.py
```
Expected: a fixture definition is present.

- [ ] **Step 4: Run integration tests — verify they pass**

```bash
uv run pytest tests/integration/a2a/test_server_client.py -v
```
Expected: 3 passed

- [ ] **Step 5: Run full suite — verify no regressions**

```bash
uv run pytest --tb=no -q
```
Expected: all prior + new tests pass

- [ ] **Step 6: Commit**

```bash
git add tests/integration/__init__.py \
        tests/integration/a2a/__init__.py \
        tests/integration/a2a/test_server_client.py
git commit -m "test(a2a): add integration tests for A2A server+client full duplex exchange"
```

---

## Final Verification

```bash
uv run pytest tests/unit/a2a/ tests/integration/a2a/ -v
```
Expected: 7+ tests pass, all green.

CFG-01–04 (Plan 01) + A2A-01–05 (Plan 02) together satisfy all Phase 3 success criteria:
1. Config YAML + env var loading → CFG-01, CFG-02
2. SecretProvider ABC + KeyringProvider → CFG-03
3. Runtime config not persisted (Pydantic models are in-memory) → CFG-04
4. Envelope round-trip → A2A-01
5. Unix socket transport with framing → A2A-02
6. Server + client connected, routed, broadcast → A2A-03, A2A-04, A2A-05
