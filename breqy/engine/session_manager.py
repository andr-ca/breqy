"""Session lifecycle management for the Breqy engine."""
from __future__ import annotations

import structlog

from breqy.domain.enums import MessageRole, SessionStatus
from breqy.domain.models import Message, Session
from breqy.storage.interfaces import MessageRepository, SessionRepository

logger = structlog.get_logger(__name__)


class SessionManager:
    """Creates, resumes, lists, and closes sessions."""

    def __init__(
        self,
        session_repo: SessionRepository,
        message_repo: MessageRepository,
    ) -> None:
        self._sessions = session_repo
        self._messages = message_repo

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
