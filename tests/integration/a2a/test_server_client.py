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
    await asyncio.sleep(0.1)

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
    await asyncio.sleep(0.1)

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
    await asyncio.sleep(0.1)

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
