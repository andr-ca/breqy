"""Session lifecycle management for the Breqy engine."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog

from breqy.domain.enums import MessageRole, SessionStatus
from breqy.domain.errors import SessionNotFoundError
from breqy.domain.models import Message, Participant, Session
from breqy.storage.interfaces import (
    MessageRepository,
    ParticipantRepository,
    SessionRepository,
)

logger = structlog.get_logger(__name__)


class SessionManager:
    """Creates, resumes, lists, and closes sessions."""

    def __init__(
        self,
        session_repo: SessionRepository,
        message_repo: MessageRepository,
        *,
        participant_repo: ParticipantRepository | None = None,
    ) -> None:
        self._sessions = session_repo
        self._messages = message_repo
        self._participants = participant_repo

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    async def create_session(self, agent_id: str) -> Session:
        """Create and persist a new ACTIVE session."""
        session = Session(primary_agent_id=agent_id)
        await self._sessions.create(session)
        logger.info("Session created", session_id=session.id, agent_id=agent_id)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        """Return session by ID, or None if not found."""
        return await self._sessions.get(session_id)

    async def list_sessions(self) -> list[Session]:
        """Return all active sessions."""
        return await self._sessions.list_active()

    async def close_session(self, session_id: str) -> None:
        """Mark session as CLOSED."""
        await self._sessions.update_status(session_id, SessionStatus.CLOSED)
        logger.info("Session closed", session_id=session_id)

    async def circuit_break_session(self, session_id: str) -> None:
        """Mark session as CIRCUIT_BROKEN (terminal)."""
        await self._sessions.update_status(
            session_id, SessionStatus.CIRCUIT_BROKEN
        )
        logger.info("Session circuit-broken", session_id=session_id)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        agent_id: str | None = None,
    ) -> Message:
        """Persist a new message and update the session timestamp."""
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            agent_id=agent_id,
        )
        await self._messages.create(message)
        await self._sessions.update_timestamp(session_id)
        return message

    async def get_messages(
        self, session_id: str, limit: int = 100
    ) -> list[Message]:
        """Return messages for a session."""
        return await self._messages.list_by_session(session_id, limit=limit)

    # ------------------------------------------------------------------
    # Session restore (5b)
    # ------------------------------------------------------------------

    async def restore_active_sessions(self) -> list[Session]:
        """Return all active sessions (for engine/daemon agent respawn)."""
        sessions = await self._sessions.list_active()
        logger.info("Restored active sessions", count=len(sessions))
        return sessions

    # ------------------------------------------------------------------
    # Workspace path management (5c)
    # ------------------------------------------------------------------

    async def set_workspace_paths(
        self, session_id: str, paths: list[str]
    ) -> None:
        """Validate and persist workspace paths for a session."""
        for p in paths:
            if not Path(p).exists():
                raise ValueError(f"Workspace path does not exist: {p}")
        await self._sessions.update_workspace_paths(session_id, paths)
        logger.info(
            "Workspace paths updated",
            session_id=session_id,
            path_count=len(paths),
        )

    async def get_workspace_paths(self, session_id: str) -> list[str]:
        """Return workspace paths for a session."""
        session = await self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session.workspace_paths

    # ------------------------------------------------------------------
    # Participant lifecycle (5d)
    # ------------------------------------------------------------------

    def _require_participant_repo(self) -> ParticipantRepository:
        if self._participants is None:
            raise RuntimeError("ParticipantRepository not configured")
        return self._participants

    async def add_participant(
        self, session_id: str, agent_id: str
    ) -> Participant:
        """Create and persist a participant for a session."""
        repo = self._require_participant_repo()
        participant = Participant(session_id=session_id, agent_id=agent_id)
        await repo.create(participant)
        logger.info(
            "Participant added",
            session_id=session_id,
            agent_id=agent_id,
            participant_id=participant.id,
        )
        return participant

    async def remove_participant(
        self, session_id: str, agent_id: str
    ) -> None:
        """Mark a participant as left. Warns if not found."""
        repo = self._require_participant_repo()
        participant = await repo.get_by_agent_and_session(agent_id, session_id)
        if participant is None:
            logger.warning(
                "Participant not found for removal",
                session_id=session_id,
                agent_id=agent_id,
            )
            return
        if participant.left_at is None:
            await repo.set_left_at(participant.id, datetime.now(UTC))
            logger.info(
                "Participant removed",
                session_id=session_id,
                agent_id=agent_id,
                participant_id=participant.id,
            )

    async def get_session_participants(
        self, session_id: str
    ) -> list[Participant]:
        """Return active participants for a session."""
        repo = self._require_participant_repo()
        return await repo.get_active_by_session(session_id)
