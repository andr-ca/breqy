"""Engine-side A2A server.

Accepts agent and TUI connections over Unix socket.
Routes incoming envelopes to a callback.
Supports broadcasting events to all connected clients.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

import structlog

from breqy.a2a.envelope import Envelope
from breqy.a2a.transport import FrameReader, FrameWriter, start_unix_server
from breqy.domain.ids import generate_prefixed_id

logger = structlog.get_logger(__name__)

OnEnvelopeCallback = Callable[[Envelope, str], Coroutine[Any, Any, None]]
OnDisconnectCallback = Callable[[str], Coroutine[Any, Any, None]]


class A2AServer:
    """Engine-side server that accepts A2A connections."""

    def __init__(
        self,
        socket_path: str,
        on_envelope: OnEnvelopeCallback,
        on_disconnect: OnDisconnectCallback | None = None,
    ) -> None:
        self._socket_path = socket_path
        self._on_envelope = on_envelope
        self._on_disconnect = on_disconnect
        self._server: asyncio.AbstractServer | None = None
        self._clients: dict[str, FrameWriter] = {}
        self._client_writers: dict[str, asyncio.StreamWriter] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Bind and start listening for connections."""
        self._server = await start_unix_server(
            self._handle_client, self._socket_path
        )
        logger.info("A2A server started", socket_path=self._socket_path)

    async def stop(self) -> None:
        """Close server and disconnect all clients."""
        # Close all connected client sockets so _handle_client loops exit
        for client_id, writer in list(self._client_writers.items()):
            try:
                writer.close()
            except Exception:
                pass
        self._client_writers.clear()
        self._clients.clear()

        # Cancel any tracked tasks
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()

        # Now close the server listener
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        logger.info("A2A server stopped", socket_path=self._socket_path)

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
        self._client_writers[client_id] = writer
        logger.info("Client connected", client_id=client_id)

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
                        "Error reading from client",
                        client_id=client_id,
                        error=str(exc),
                    )
                    break
        finally:
            self._clients.pop(client_id, None)
            self._client_writers.pop(client_id, None)
            if self._on_disconnect is not None:
                await self._on_disconnect(client_id)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("Client disconnected", client_id=client_id)
