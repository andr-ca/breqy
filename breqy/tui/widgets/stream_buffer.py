"""Stream buffer for accumulating message chunks.

Pure logic — no Textual dependency.
"""
from __future__ import annotations


class StreamBuffer:
    """Accumulates ``MessageChunkEvent`` chunks keyed by message_id.

    Chunks are stored by their ``chunk_index`` so they can be
    reassembled in the correct order even if they arrive out of order.
    """

    def __init__(self) -> None:
        self._buffers: dict[str, dict[int, str]] = {}

    def add_chunk(self, message_id: str, chunk: str, chunk_index: int) -> str:
        """Add a chunk and return the full accumulated text so far."""
        buf = self._buffers.setdefault(message_id, {})
        buf[chunk_index] = chunk
        return self._assemble(buf)

    def complete(self, message_id: str) -> str:
        """Finalize a message and return the complete text.

        Removes the buffer for *message_id*.
        """
        buf = self._buffers.pop(message_id, None)
        if buf is None:
            return ""
        return self._assemble(buf)

    def has_message(self, message_id: str) -> bool:
        """Return True if there is an active buffer for *message_id*."""
        return message_id in self._buffers

    def get_text(self, message_id: str) -> str:
        """Return current accumulated text without completing."""
        buf = self._buffers.get(message_id)
        if buf is None:
            return ""
        return self._assemble(buf)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _assemble(buf: dict[int, str]) -> str:
        """Concatenate chunks in index order."""
        return "".join(buf[i] for i in sorted(buf))
