"""Low-level Unix socket transport with length-prefixed framing.

Every frame on the wire:
  [4 bytes: big-endian uint32 payload length][payload bytes]
"""
from __future__ import annotations

import asyncio
import struct
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

from breqy.a2a.envelope import Envelope

logger = structlog.get_logger(__name__)


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
        logger.debug("Frame read", length=length)
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
        logger.debug("Frame written", length=len(data))

    async def write_envelope(self, envelope: Envelope) -> None:
        """Serialize and write an envelope as a frame."""
        json_bytes = envelope.model_dump_json().encode("utf-8")
        await self.write_frame(json_bytes)
