from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import pytest

from breqy.domain.enums import (
    ApprovalStatus,
    AutonomyLevel,
    MemoryPromotionStatus,
    MemoryRecordKind,
    MemoryScope,
    PolicyAction,
)
from breqy.domain.events import (
    ApprovalDecidedEvent,
    ApprovalRequestedEvent,
    MemoryPromotionApprovedEvent,
    MemoryPromotionDeniedEvent,
    MemoryPromotionRequestedEvent,
    MemoryRecordCreatedEvent,
)
from breqy.domain.models import MemoryPromotion, MemoryRecord
from breqy.memory.index import VectorIndexDocument, VectorIndexMatch
from breqy.memory.service import MemoryService
from breqy.policy.models import PolicyDecision


class RecordingMemoryRepository:
    def __init__(self, records: Sequence[MemoryRecord] | None = None) -> None:
        self.records: dict[str, MemoryRecord] = {record.id: record for record in (records or [])}
        self.promotions: dict[str, MemoryPromotion] = {}
        self.create_record_calls: list[MemoryRecord] = []
        self.list_calls: list[dict[str, Any]] = []
        self.update_record_promotion_calls: list[tuple[str, str | None]] = []
        self.create_promotion_calls: list[MemoryPromotion] = []
        self.update_promotion_state_calls: list[tuple[str, MemoryPromotionStatus, str | None]] = []

    async def create_record(self, record: MemoryRecord) -> None:
        self.create_record_calls.append(record)
        self.records[record.id] = record

    async def get_record(self, record_id: str) -> MemoryRecord | None:
        return self.records.get(record_id)

    async def list_records(
        self,
        scope: MemoryScope,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        tags: list[str] | None = None,
        task_id: str | None = None,
        approval_id: str | None = None,
        artifact_id: str | None = None,
        linked_event_id: str | None = None,
        promotion_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        self.list_calls.append(
            {
                "scope": scope,
                "session_id": session_id,
                "agent_id": agent_id,
                "tags": tags,
                "task_id": task_id,
                "approval_id": approval_id,
                "artifact_id": artifact_id,
                "linked_event_id": linked_event_id,
                "promotion_id": promotion_id,
                "limit": limit,
            }
        )

        results: list[MemoryRecord] = []
        for record in self.records.values():
            if record.scope != scope:
                continue
            if session_id is not None and record.session_id != session_id:
                continue
            if agent_id is not None and record.agent_id != agent_id:
                continue
            if task_id is not None and record.task_id != task_id:
                continue
            if approval_id is not None and record.approval_id != approval_id:
                continue
            if artifact_id is not None and record.artifact_id != artifact_id:
                continue
            if linked_event_id is not None and record.linked_event_id != linked_event_id:
                continue
            if promotion_id is not None and record.promotion_id != promotion_id:
                continue
            if tags and not all(tag in record.tags for tag in tags):
                continue
            results.append(record)

        results.sort(key=lambda record: record.created_at)
        return results[:limit]

    async def update_record_promotion(
        self,
        record_id: str,
        promotion_id: str | None,
    ) -> None:
        self.update_record_promotion_calls.append((record_id, promotion_id))
        record = self.records[record_id]
        self.records[record_id] = record.model_copy(update={"promotion_id": promotion_id})

    async def create_promotion(self, promotion: MemoryPromotion) -> None:
        self.create_promotion_calls.append(promotion)
        self.promotions[promotion.id] = promotion

    async def get_promotion(self, promotion_id: str) -> MemoryPromotion | None:
        return self.promotions.get(promotion_id)

    async def update_promotion_state(
        self,
        promotion_id: str,
        status: MemoryPromotionStatus,
        target_record_id: str | None = None,
    ) -> None:
        self.update_promotion_state_calls.append((promotion_id, status, target_record_id))
        promotion = self.promotions[promotion_id]
        self.promotions[promotion_id] = promotion.model_copy(
            update={
                "status": status,
                "target_record_id": target_record_id or promotion.target_record_id,
            }
        )


class StubPolicyEvaluator:
    def __init__(self, actions: dict[str, PolicyAction] | None = None) -> None:
        self._actions = actions or {}
        self.calls: list[tuple[str, str, str]] = []

    def evaluate(self, resource: str, agent_id: str = "", session_id: str = "") -> PolicyDecision:
        self.calls.append((resource, agent_id, session_id))
        return PolicyDecision(
            action=self._actions.get(resource, PolicyAction.ALLOW),
            reason=f"decision:{resource}",
        )


class RecordingApprovalService:
    def __init__(
        self,
        *,
        decision: ApprovalStatus = ApprovalStatus.GRANTED,
        request_id: str = "apr_memory",
    ) -> None:
        self.decision = decision
        self.request_id = request_id
        self.request_calls: list[tuple[str, str, str, str]] = []
        self.wait_calls: list[tuple[str, float]] = []
        self.session_grants: set[tuple[str, str]] = set()

    async def request_approval(
        self,
        session_id: str,
        agent_id: str,
        tool_invocation_id: str,
        description: str,
    ) -> str:
        self.request_calls.append((session_id, agent_id, tool_invocation_id, description))
        return self.request_id

    async def wait_for_decision(self, request_id: str, timeout: float = 300.0) -> ApprovalStatus:
        self.wait_calls.append((request_id, timeout))
        return self.decision

    def has_session_grant(self, session_id: str, description: str) -> bool:
        return (session_id, description) in self.session_grants


class MissingApprovalIdApprovalService(RecordingApprovalService):
    async def request_approval(
        self,
        session_id: str,
        agent_id: str,
        tool_invocation_id: str,
        description: str,
    ) -> str:
        self.request_calls.append((session_id, agent_id, tool_invocation_id, description))
        return cast(str, None)


class RecordingVectorIndex:
    def __init__(self, matches: Sequence[VectorIndexMatch] | None = None) -> None:
        self._matches = list(matches or [])
        self.calls: list[dict[str, Any]] = []

    async def rank(
        self,
        *,
        query: str,
        candidates: Sequence[VectorIndexDocument],
        limit: int = 10,
    ) -> list[VectorIndexMatch]:
        self.calls.append(
            {
                "query": query,
                "candidate_ids": [candidate.id for candidate in candidates],
                "limit": limit,
            }
        )
        return list(self._matches)[:limit]


class RecordingEventBus:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def publish(self, event: object) -> None:
        self.events.append(event)


def build_service(
    *,
    records: Sequence[MemoryRecord] | None = None,
    policy_actions: dict[str, PolicyAction] | None = None,
    approval_decision: ApprovalStatus = ApprovalStatus.GRANTED,
    vector_matches: Sequence[VectorIndexMatch] | None = None,
) -> tuple[
    MemoryService,
    RecordingMemoryRepository,
    StubPolicyEvaluator,
    RecordingApprovalService,
    RecordingVectorIndex,
    RecordingEventBus,
]:
    repository = RecordingMemoryRepository(records=records)
    policy_evaluator = StubPolicyEvaluator(actions=policy_actions)
    approval_service = RecordingApprovalService(decision=approval_decision)
    vector_index = RecordingVectorIndex(matches=vector_matches)
    event_bus = RecordingEventBus()
    service = MemoryService(
        repository=cast(Any, repository),
        vector_index=cast(Any, vector_index),
        policy_evaluator=cast(Any, policy_evaluator),
        approval_service=cast(Any, approval_service),
        event_bus=cast(Any, event_bus),
        approval_timeout=9.5,
    )
    return service, repository, policy_evaluator, approval_service, vector_index, event_bus


@pytest.mark.asyncio
async def test_write_record_persists_session_memory_with_link_metadata() -> None:
    service, repository, policy_evaluator, _, _, event_bus = build_service()

    record = await service.write_record(
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        kind=MemoryRecordKind.NOTE,
        source="tool:memory.write",
        content="Remember the selected deployment path.",
        tags=["deployment", "decision"],
        task_id="tsk_123",
        approval_id="apr_123",
        artifact_id="art_123",
        linked_event_id="evt_123",
    )

    assert repository.create_record_calls == [record]
    assert record.scope == MemoryScope.SESSION
    assert record.session_id == "ses_123"
    assert record.task_id == "tsk_123"
    assert record.approval_id == "apr_123"
    assert record.artifact_id == "art_123"
    assert record.linked_event_id == "evt_123"
    assert policy_evaluator.calls == [("memory:session:write", "agt_123", "ses_123")]
    assert len(event_bus.events) == 1
    assert isinstance(event_bus.events[0], MemoryRecordCreatedEvent)


@pytest.mark.asyncio
async def test_search_records_reads_with_explicit_scope_filters() -> None:
    session_match = MemoryRecord(
        id="mem_session_match",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        kind=MemoryRecordKind.FACT,
        source="conversation",
        content="Deployment target is the staging cluster.",
        tags=["deployment", "staging"],
        artifact_id="art_123",
    )
    other_session = MemoryRecord(
        id="mem_other_session",
        scope=MemoryScope.SESSION,
        session_id="ses_other",
        agent_id="agt_123",
        kind=MemoryRecordKind.FACT,
        source="conversation",
        content="This should be filtered by session.",
        tags=["deployment", "staging"],
        artifact_id="art_123",
    )
    global_record = MemoryRecord(
        id="mem_global",
        scope=MemoryScope.GLOBAL,
        agent_id="agt_123",
        kind=MemoryRecordKind.FACT,
        source="promotion",
        content="This should be filtered by scope.",
        tags=["deployment", "staging"],
        artifact_id="art_123",
    )
    service, repository, policy_evaluator, _, vector_index, _ = build_service(
        records=[session_match, other_session, global_record],
    )

    records = await service.search_records(
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        query="",
        tags=["deployment"],
        artifact_id="art_123",
        limit=5,
    )

    assert [record.id for record in records] == ["mem_session_match"]
    assert repository.list_calls == [
        {
            "scope": MemoryScope.SESSION,
            "session_id": "ses_123",
            "agent_id": None,
            "tags": ["deployment"],
            "task_id": None,
            "approval_id": None,
            "artifact_id": "art_123",
            "linked_event_id": None,
            "promotion_id": None,
            "limit": 5,
        }
    ]
    assert policy_evaluator.calls == [("memory:session:read", "agt_123", "ses_123")]
    assert vector_index.calls == []


@pytest.mark.asyncio
async def test_search_records_keeps_shared_session_visibility_across_agents() -> None:
    own_record = MemoryRecord(
        id="mem_own",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_reader",
        kind=MemoryRecordKind.FACT,
        source="conversation",
        content="Own session memory.",
        tags=["shared"],
    )
    other_agent_record = MemoryRecord(
        id="mem_other_agent",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_writer",
        kind=MemoryRecordKind.FACT,
        source="conversation",
        content="Other agent session memory stays shared.",
        tags=["shared"],
    )
    service, repository, _, _, _, _ = build_service(records=[own_record, other_agent_record])

    records = await service.search_records(
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_reader",
        tags=["shared"],
    )

    assert [record.id for record in records] == ["mem_own", "mem_other_agent"]
    assert repository.list_calls[0]["agent_id"] is None


@pytest.mark.asyncio
async def test_search_records_keeps_shared_global_visibility_across_agents() -> None:
    own_global_record = MemoryRecord(
        id="mem_global_own",
        scope=MemoryScope.GLOBAL,
        agent_id="agt_reader",
        kind=MemoryRecordKind.FACT,
        source="promotion",
        content="Reader-owned global fact.",
        tags=["global"],
    )
    other_global_record = MemoryRecord(
        id="mem_global_other",
        scope=MemoryScope.GLOBAL,
        agent_id="agt_writer",
        kind=MemoryRecordKind.FACT,
        source="promotion",
        content="Other agent global fact remains visible.",
        tags=["global"],
    )
    service, repository, _, _, _, _ = build_service(records=[own_global_record, other_global_record])

    records = await service.search_records(
        scope=MemoryScope.GLOBAL,
        agent_id="agt_reader",
        tags=["global"],
    )

    assert [record.id for record in records] == ["mem_global_own", "mem_global_other"]
    assert repository.list_calls[0]["agent_id"] is None


@pytest.mark.asyncio
async def test_search_records_authorizes_with_session_context_without_filtering_global_records() -> None:
    global_record = MemoryRecord(
        id="mem_global",
        scope=MemoryScope.GLOBAL,
        agent_id="agt_writer",
        kind=MemoryRecordKind.FACT,
        source="promotion",
        content="Global fact remains visible during session-bound reads.",
        tags=["shared"],
    )
    service, repository, policy_evaluator, _, _, _ = build_service(records=[global_record])

    records = await service.search_records(
        scope=MemoryScope.GLOBAL,
        session_id="ses_123",
        agent_id="agt_reader",
        tags=["shared"],
    )

    assert [record.id for record in records] == ["mem_global"]
    assert policy_evaluator.calls == [("memory:global:read", "agt_reader", "ses_123")]
    assert repository.list_calls == [
        {
            "scope": MemoryScope.GLOBAL,
            "session_id": None,
            "agent_id": None,
            "tags": ["shared"],
            "task_id": None,
            "approval_id": None,
            "artifact_id": None,
            "linked_event_id": None,
            "promotion_id": None,
            "limit": 10,
        }
    ]


@pytest.mark.asyncio
async def test_search_records_requires_session_id_for_session_scope() -> None:
    service, repository, policy_evaluator, approval_service, _, event_bus = build_service()

    with pytest.raises(ValueError, match="session scope reads require session_id"):
        await service.search_records(
            scope=MemoryScope.SESSION,
            session_id=None,
            agent_id="agt_reader",
        )

    assert repository.list_calls == []
    assert policy_evaluator.calls == []
    assert approval_service.request_calls == []
    assert event_bus.events == []


@pytest.mark.asyncio
async def test_create_checkpoint_writes_summary_record_for_session_continuity() -> None:
    service, repository, _, _, _, event_bus = build_service()

    record = await service.create_checkpoint(
        session_id="ses_123",
        agent_id="agt_123",
        content="User chose the safer migration plan and approved shell access.",
        task_id="tsk_123",
    )

    assert record.kind == MemoryRecordKind.SUMMARY
    assert record.scope == MemoryScope.SESSION
    assert record.session_id == "ses_123"
    assert "checkpoint" in record.tags
    assert repository.create_record_calls == [record]
    assert len(event_bus.events) == 1
    assert isinstance(event_bus.events[0], MemoryRecordCreatedEvent)


@pytest.mark.asyncio
async def test_write_record_rejects_direct_global_writes() -> None:
    service, repository, policy_evaluator, _, _, event_bus = build_service()

    with pytest.raises(ValueError, match="global memory must be created only through promotion"):
        await service.write_record(
            scope=MemoryScope.GLOBAL,
            agent_id="agt_123",
            kind=MemoryRecordKind.FACT,
            source="tool:memory.write",
            content="Global memory should not be directly writable.",
        )

    assert repository.create_record_calls == []
    assert policy_evaluator.calls == []
    assert event_bus.events == []


@pytest.mark.asyncio
async def test_write_record_requires_session_id_for_session_scope() -> None:
    service, repository, policy_evaluator, approval_service, _, event_bus = build_service()

    with pytest.raises(ValueError, match="session scope writes require session_id"):
        await service.write_record(
            scope=MemoryScope.SESSION,
            session_id=None,
            agent_id="agt_123",
            kind=MemoryRecordKind.NOTE,
            source="tool:memory.write",
            content="Session writes need a session id.",
        )

    assert repository.create_record_calls == []
    assert policy_evaluator.calls == []
    assert approval_service.request_calls == []
    assert event_bus.events == []


@pytest.mark.asyncio
async def test_write_record_requests_inner_approval_when_policy_requires_it() -> None:
    service, repository, policy_evaluator, approval_service, _, event_bus = build_service(
        policy_actions={"memory:session:write": PolicyAction.REQUIRE_APPROVAL},
    )

    record = await service.write_record(
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        kind=MemoryRecordKind.NOTE,
        source="tool:memory.write",
        content="Approval-gated session note.",
    )

    assert repository.create_record_calls == [record]
    assert policy_evaluator.calls == [("memory:session:write", "agt_123", "ses_123")]
    assert len(approval_service.request_calls) == 1
    request_call = approval_service.request_calls[0]
    assert request_call[0] == "ses_123"
    assert request_call[1] == "agt_123"
    assert request_call[2].startswith("inv_")
    assert request_call[3] == "Access memory resource 'memory:session:write' for session 'ses_123'"
    assert approval_service.wait_calls == [("apr_memory", 9.5)]
    assert len(event_bus.events) == 3
    assert isinstance(event_bus.events[0], ApprovalRequestedEvent)
    assert isinstance(event_bus.events[1], ApprovalDecidedEvent)
    assert isinstance(event_bus.events[2], MemoryRecordCreatedEvent)


@pytest.mark.asyncio
async def test_search_records_requests_inner_approval_when_policy_requires_it() -> None:
    shared_record = MemoryRecord(
        id="mem_shared",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_writer",
        kind=MemoryRecordKind.NOTE,
        source="conversation",
        content="Approval-gated shared session memory.",
        tags=["shared"],
    )
    service, repository, policy_evaluator, approval_service, _, _ = build_service(
        records=[shared_record],
        policy_actions={"memory:session:read": PolicyAction.REQUIRE_APPROVAL},
    )

    records = await service.search_records(
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_reader",
        tags=["shared"],
    )

    assert [record.id for record in records] == ["mem_shared"]
    assert policy_evaluator.calls == [("memory:session:read", "agt_reader", "ses_123")]
    assert repository.list_calls[0]["agent_id"] is None
    assert len(approval_service.request_calls) == 1
    request_call = approval_service.request_calls[0]
    assert request_call[0] == "ses_123"
    assert request_call[1] == "agt_reader"
    assert request_call[2].startswith("inv_")
    assert request_call[3] == "Access memory resource 'memory:session:read' for session 'ses_123'"
    assert approval_service.wait_calls == [("apr_memory", 9.5)]


@pytest.mark.asyncio
async def test_write_record_denied_by_policy_raises_before_persistence() -> None:
    service, repository, policy_evaluator, approval_service, _, event_bus = build_service(
        policy_actions={"memory:session:write": PolicyAction.DENY},
    )

    with pytest.raises(PermissionError, match="policy denied memory access"):
        await service.write_record(
            scope=MemoryScope.SESSION,
            session_id="ses_123",
            agent_id="agt_123",
            kind=MemoryRecordKind.NOTE,
            source="tool:memory.write",
            content="Denied by policy.",
        )

    assert policy_evaluator.calls == [("memory:session:write", "agt_123", "ses_123")]
    assert repository.create_record_calls == []
    assert approval_service.request_calls == []
    assert event_bus.events == []


@pytest.mark.asyncio
async def test_search_records_denied_approval_raises_and_emits_request_and_decision_events() -> None:
    shared_record = MemoryRecord(
        id="mem_shared",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_writer",
        kind=MemoryRecordKind.NOTE,
        source="conversation",
        content="Approval-denied shared session memory.",
        tags=["shared"],
    )
    service, repository, policy_evaluator, approval_service, _, event_bus = build_service(
        records=[shared_record],
        policy_actions={"memory:session:read": PolicyAction.REQUIRE_APPROVAL},
        approval_decision=ApprovalStatus.DENIED,
    )

    with pytest.raises(PermissionError, match="approval denied for memory access"):
        await service.search_records(
            scope=MemoryScope.SESSION,
            session_id="ses_123",
            agent_id="agt_reader",
            tags=["shared"],
        )

    assert policy_evaluator.calls == [("memory:session:read", "agt_reader", "ses_123")]
    assert repository.list_calls == []
    assert len(approval_service.request_calls) == 1
    assert approval_service.wait_calls == [("apr_memory", 9.5)]
    assert len(event_bus.events) == 2
    assert isinstance(event_bus.events[0], ApprovalRequestedEvent)
    assert isinstance(event_bus.events[1], ApprovalDecidedEvent)


@pytest.mark.asyncio
async def test_write_record_expired_approval_raises_and_emits_request_event_only() -> None:
    service, repository, policy_evaluator, approval_service, _, event_bus = build_service(
        policy_actions={"memory:session:write": PolicyAction.REQUIRE_APPROVAL},
        approval_decision=ApprovalStatus.EXPIRED,
    )

    with pytest.raises(PermissionError, match="approval expired for memory access"):
        await service.write_record(
            scope=MemoryScope.SESSION,
            session_id="ses_123",
            agent_id="agt_123",
            kind=MemoryRecordKind.NOTE,
            source="tool:memory.write",
            content="Approval expires before write.",
        )

    assert policy_evaluator.calls == [("memory:session:write", "agt_123", "ses_123")]
    assert repository.create_record_calls == []
    assert len(approval_service.request_calls) == 1
    assert approval_service.wait_calls == [("apr_memory", 9.5)]
    assert len(event_bus.events) == 1
    assert isinstance(event_bus.events[0], ApprovalRequestedEvent)


@pytest.mark.asyncio
async def test_promote_record_supports_approval_and_autonomous_flows() -> None:
    supervised_source = MemoryRecord(
        id="mem_supervised",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        kind=MemoryRecordKind.LESSON,
        source="tool:memory.write",
        content="Prefer the migration path with a rollback window.",
        tags=["deployment", "lesson"],
        task_id="tsk_123",
        linked_event_id="evt_123",
    )
    autonomous_source = MemoryRecord(
        id="mem_autonomous",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        kind=MemoryRecordKind.FACT,
        source="tool:memory.write",
        content="The default workspace lives under /srv/breqy.",
        tags=["workspace"],
    )
    service, repository, policy_evaluator, approval_service, _, event_bus = build_service(
        records=[supervised_source, autonomous_source],
    )

    supervised_promotion = await service.promote_record(
        record_id="mem_supervised",
        session_id="ses_123",
        agent_id="agt_123",
        autonomy_level=AutonomyLevel.SUPERVISED,
    )
    autonomous_promotion = await service.promote_record(
        record_id="mem_autonomous",
        session_id="ses_123",
        agent_id="agt_123",
        autonomy_level=AutonomyLevel.AUTONOMOUS,
    )

    assert supervised_promotion.status == MemoryPromotionStatus.APPROVED
    assert autonomous_promotion.status == MemoryPromotionStatus.APPROVED
    assert supervised_promotion.approval_id == "apr_memory"
    assert autonomous_promotion.approval_id is None
    assert len(approval_service.request_calls) == 1
    assert approval_service.wait_calls == [("apr_memory", 9.5)]
    assert policy_evaluator.calls == [
        ("memory:session:promote", "agt_123", "ses_123"),
        ("memory:session:promote", "agt_123", "ses_123"),
    ]
    global_records = [record for record in repository.records.values() if record.scope == MemoryScope.GLOBAL]
    assert len(global_records) == 2
    assert {record.promotion_id for record in global_records} == {
        supervised_promotion.id,
        autonomous_promotion.id,
    }
    assert repository.records["mem_supervised"].promotion_id == supervised_promotion.id
    assert repository.records["mem_autonomous"].promotion_id == autonomous_promotion.id
    assert isinstance(event_bus.events[0], ApprovalRequestedEvent)
    assert isinstance(event_bus.events[1], MemoryPromotionRequestedEvent)
    assert isinstance(event_bus.events[2], ApprovalDecidedEvent)


@pytest.mark.asyncio
async def test_promote_record_uses_description_based_session_grant_when_no_grant_key() -> None:
    source = MemoryRecord(
        id="mem_source",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        kind=MemoryRecordKind.LESSON,
        source="tool:memory.write",
        content="Keep this promoted.",
    )
    service, repository, _policy_evaluator, approval_service, _, event_bus = build_service(
        records=[source],
    )
    approval_service.session_grants.add(("ses_123", "Promote memory record 'mem_source' to global scope"))

    promotion = await service.promote_record(
        record_id="mem_source",
        session_id="ses_123",
        agent_id="agt_123",
        autonomy_level=AutonomyLevel.SUPERVISED,
    )

    assert promotion.approval_id is None
    assert approval_service.request_calls == []
    global_records = [
        record for record in repository.records.values() if record.scope == MemoryScope.GLOBAL
    ]
    assert len(global_records) == 1
    assert isinstance(event_bus.events[0], MemoryPromotionRequestedEvent)
    assert isinstance(event_bus.events[1], MemoryRecordCreatedEvent)
    assert isinstance(event_bus.events[2], MemoryPromotionApprovedEvent)


@pytest.mark.asyncio
async def test_promote_record_denial_keeps_session_record_and_blocks_global_write() -> None:
    source_record = MemoryRecord(
        id="mem_source",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        kind=MemoryRecordKind.LESSON,
        source="tool:memory.write",
        content="Denied promotions should not create global records.",
        tags=["lesson"],
    )
    service, repository, _, approval_service, _, event_bus = build_service(
        records=[source_record],
        approval_decision=ApprovalStatus.DENIED,
    )

    promotion = await service.promote_record(
        record_id="mem_source",
        session_id="ses_123",
        agent_id="agt_123",
        autonomy_level=AutonomyLevel.SUPERVISED,
    )

    assert promotion.status == MemoryPromotionStatus.DENIED
    assert promotion.target_record_id is None
    assert repository.records["mem_source"].promotion_id == promotion.id
    assert [record.id for record in repository.records.values() if record.scope == MemoryScope.GLOBAL] == []
    assert len(approval_service.request_calls) == 1
    assert len(event_bus.events) == 4
    assert isinstance(event_bus.events[0], ApprovalRequestedEvent)
    assert isinstance(event_bus.events[1], MemoryPromotionRequestedEvent)
    assert isinstance(event_bus.events[2], ApprovalDecidedEvent)
    assert isinstance(event_bus.events[3], MemoryPromotionDeniedEvent)


@pytest.mark.asyncio
async def test_promote_record_policy_required_approval_blocks_global_write_when_expired() -> None:
    source_record = MemoryRecord(
        id="mem_source",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_writer",
        kind=MemoryRecordKind.LESSON,
        source="tool:memory.write",
        content="Expired promotion approval keeps promotion pending.",
        tags=["lesson"],
    )
    service, repository, policy_evaluator, approval_service, _, event_bus = build_service(
        records=[source_record],
        policy_actions={"memory:session:promote": PolicyAction.REQUIRE_APPROVAL},
        approval_decision=ApprovalStatus.EXPIRED,
    )

    promotion = await service.promote_record(
        record_id="mem_source",
        session_id="ses_123",
        agent_id="agt_reader",
        autonomy_level=AutonomyLevel.AUTONOMOUS,
    )

    assert promotion.status == MemoryPromotionStatus.PENDING
    assert promotion.target_record_id is None
    assert policy_evaluator.calls == [("memory:session:promote", "agt_reader", "ses_123")]
    assert approval_service.request_calls == [
        (
            "ses_123",
            "agt_reader",
            "mem_source",
            "Promote memory record 'mem_source' to global scope",
        )
    ]
    assert approval_service.wait_calls == [("apr_memory", 9.5)]
    assert repository.records["mem_source"].promotion_id == promotion.id
    assert repository.update_promotion_state_calls == []
    assert [record.id for record in repository.records.values() if record.scope == MemoryScope.GLOBAL] == []
    assert len(event_bus.events) == 2
    assert isinstance(event_bus.events[0], ApprovalRequestedEvent)
    assert isinstance(event_bus.events[1], MemoryPromotionRequestedEvent)


@pytest.mark.asyncio
async def test_promote_record_rejects_unknown_record_id() -> None:
    service, _, policy_evaluator, approval_service, _, event_bus = build_service()

    with pytest.raises(ValueError, match="unknown memory record: mem_missing"):
        await service.promote_record(
            record_id="mem_missing",
            session_id="ses_123",
            agent_id="agt_123",
            autonomy_level=AutonomyLevel.AUTONOMOUS,
        )

    assert policy_evaluator.calls == [("memory:session:promote", "agt_123", "ses_123")]
    assert approval_service.request_calls == []
    assert event_bus.events == []


@pytest.mark.asyncio
async def test_promote_record_rejects_non_session_source_record() -> None:
    global_record = MemoryRecord(
        id="mem_global",
        scope=MemoryScope.GLOBAL,
        agent_id="agt_123",
        kind=MemoryRecordKind.FACT,
        source="tool:memory.write",
        content="Global memory cannot be promoted again.",
    )
    service, _, _, approval_service, _, event_bus = build_service(records=[global_record])

    with pytest.raises(ValueError, match="only session memory can be promoted"):
        await service.promote_record(
            record_id="mem_global",
            session_id="ses_123",
            agent_id="agt_123",
            autonomy_level=AutonomyLevel.AUTONOMOUS,
        )

    assert approval_service.request_calls == []
    assert event_bus.events == []


@pytest.mark.asyncio
async def test_promote_record_rejects_record_from_another_session() -> None:
    source_record = MemoryRecord(
        id="mem_other_session",
        scope=MemoryScope.SESSION,
        session_id="ses_other",
        agent_id="agt_123",
        kind=MemoryRecordKind.FACT,
        source="tool:memory.write",
        content="Session mismatches should be rejected.",
    )
    service, _, _, approval_service, _, event_bus = build_service(records=[source_record])

    with pytest.raises(ValueError, match="memory record does not belong to the requested session"):
        await service.promote_record(
            record_id="mem_other_session",
            session_id="ses_123",
            agent_id="agt_123",
            autonomy_level=AutonomyLevel.AUTONOMOUS,
        )

    assert approval_service.request_calls == []
    assert event_bus.events == []


@pytest.mark.asyncio
async def test_promote_record_raises_when_approval_id_is_missing_after_request() -> None:
    source_record = MemoryRecord(
        id="mem_source",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        kind=MemoryRecordKind.LESSON,
        source="tool:memory.write",
        content="Approval ids must be present for promotion approval flows.",
    )
    repository = RecordingMemoryRepository(records=[source_record])
    policy_evaluator = StubPolicyEvaluator()
    approval_service = MissingApprovalIdApprovalService()
    vector_index = RecordingVectorIndex()
    event_bus = RecordingEventBus()
    service = MemoryService(
        repository=cast(Any, repository),
        vector_index=cast(Any, vector_index),
        policy_evaluator=cast(Any, policy_evaluator),
        approval_service=cast(Any, approval_service),
        event_bus=cast(Any, event_bus),
        approval_timeout=9.5,
    )

    with pytest.raises(RuntimeError, match="promotion approval id missing"):
        await service.promote_record(
            record_id="mem_source",
            session_id="ses_123",
            agent_id="agt_123",
            autonomy_level=AutonomyLevel.SUPERVISED,
        )


@pytest.mark.asyncio
async def test_search_records_filters_before_vector_ranking() -> None:
    matching = MemoryRecord(
        id="mem_match",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        kind=MemoryRecordKind.NOTE,
        source="conversation",
        content="Approval guidance for deployment rollout.",
        tags=["deployment", "approval"],
    )
    also_matching = MemoryRecord(
        id="mem_match_2",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        kind=MemoryRecordKind.NOTE,
        source="conversation",
        content="Deployment artifact references.",
        tags=["deployment"],
    )
    filtered_out_by_tag = MemoryRecord(
        id="mem_filtered_tag",
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        kind=MemoryRecordKind.NOTE,
        source="conversation",
        content="Approval guidance without deployment tag.",
        tags=["approval"],
    )
    filtered_out_by_scope = MemoryRecord(
        id="mem_filtered_scope",
        scope=MemoryScope.GLOBAL,
        agent_id="agt_123",
        kind=MemoryRecordKind.NOTE,
        source="promotion",
        content="Global approval guidance.",
        tags=["deployment", "approval"],
    )
    service, _, _, _, vector_index, _ = build_service(
        records=[matching, also_matching, filtered_out_by_tag, filtered_out_by_scope],
        vector_matches=[
            VectorIndexMatch(document_id="mem_match_2", score=9.0),
            VectorIndexMatch(document_id="mem_match", score=7.0),
        ],
    )

    records = await service.search_records(
        scope=MemoryScope.SESSION,
        session_id="ses_123",
        agent_id="agt_123",
        query="approval deployment",
        tags=["deployment"],
        limit=2,
    )

    assert [record.id for record in records] == ["mem_match_2", "mem_match"]
    assert vector_index.calls == [
        {
            "query": "approval deployment",
            "candidate_ids": ["mem_match", "mem_match_2"],
            "limit": 2,
        }
    ]
