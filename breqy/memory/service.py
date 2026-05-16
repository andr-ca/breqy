"""Engine-owned orchestration for canonical session and global memory."""

from __future__ import annotations

from typing import Any

from breqy.domain.enums import (
    ApprovalStatus,
    AutonomyLevel,
    EventType,
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
from breqy.domain.ids import generate_prefixed_id
from breqy.domain.models import MemoryPromotion, MemoryRecord
from breqy.memory.index import VectorIndex, VectorIndexDocument
from breqy.policy.approval import ApprovalService
from breqy.policy.evaluator import PolicyEvaluator
from breqy.storage.interfaces import MemoryRepository


class MemoryService:
    def __init__(
        self,
        repository: MemoryRepository,
        vector_index: VectorIndex,
        policy_evaluator: PolicyEvaluator,
        approval_service: ApprovalService,
        event_bus: Any,
        approval_timeout: float = 300.0,
    ) -> None:
        self._repository = repository
        self._vector_index = vector_index
        self._policy_evaluator = policy_evaluator
        self._approval_service = approval_service
        self._event_bus = event_bus
        self._approval_timeout = approval_timeout

    async def write_record(
        self,
        *,
        scope: MemoryScope,
        agent_id: str,
        kind: MemoryRecordKind,
        source: str,
        content: str,
        session_id: str | None = None,
        tags: list[str] | None = None,
        task_id: str | None = None,
        approval_id: str | None = None,
        artifact_id: str | None = None,
        linked_event_id: str | None = None,
        promotion_id: str | None = None,
    ) -> MemoryRecord:
        if scope == MemoryScope.GLOBAL:
            raise ValueError("global memory must be created only through promotion")
        if scope == MemoryScope.SESSION and session_id is None:
            raise ValueError("session scope writes require session_id")

        policy_approval_id = await self._authorize(
            resource=self._resource_name(scope=scope, action="write"),
            agent_id=agent_id,
            session_id=session_id or "",
        )
        resolved_approval_id = policy_approval_id or approval_id

        record = MemoryRecord(
            scope=scope,
            session_id=session_id,
            agent_id=agent_id,
            kind=kind,
            source=source,
            content=content,
            tags=list(tags or []),
            task_id=task_id,
            approval_id=resolved_approval_id,
            artifact_id=artifact_id,
            linked_event_id=linked_event_id,
            promotion_id=promotion_id,
        )
        await self._repository.create_record(record)
        await self._event_bus.publish(
            MemoryRecordCreatedEvent(
                session_id=session_id or "",
                agent_id=agent_id,
                record_id=record.id,
                scope=record.scope,
                kind=record.kind,
                source=record.source,
                content=record.content,
                task_id=record.task_id,
                approval_id=record.approval_id,
                artifact_id=record.artifact_id,
                linked_event_id=record.linked_event_id,
                promotion_id=record.promotion_id,
            )
        )
        return record

    async def search_records(
        self,
        *,
        scope: MemoryScope,
        agent_id: str,
        query: str = "",
        session_id: str | None = None,
        tags: list[str] | None = None,
        task_id: str | None = None,
        approval_id: str | None = None,
        artifact_id: str | None = None,
        linked_event_id: str | None = None,
        promotion_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        if scope == MemoryScope.SESSION and session_id is None:
            raise ValueError("session scope reads require session_id")

        resource = self._resource_name(scope=scope, action="read")
        await self._authorize(
            resource=resource,
            agent_id=agent_id,
            session_id=session_id or "",
        )

        records = await self._repository.list_records(
            scope,
            session_id=session_id if scope == MemoryScope.SESSION else None,
            agent_id=None,
            tags=tags,
            task_id=task_id,
            approval_id=approval_id,
            artifact_id=artifact_id,
            linked_event_id=linked_event_id,
            promotion_id=promotion_id,
            limit=limit,
        )
        normalized_query = query.strip()
        if not normalized_query or not records:
            return records

        matches = await self._vector_index.rank(
            query=normalized_query,
            candidates=[VectorIndexDocument(id=record.id, content=record.content) for record in records],
            limit=limit,
        )
        records_by_id = {record.id: record for record in records}
        return [
            records_by_id[match.document_id]
            for match in matches
            if match.document_id in records_by_id
        ]

    async def create_checkpoint(
        self,
        *,
        session_id: str,
        agent_id: str,
        content: str,
        task_id: str | None = None,
        approval_id: str | None = None,
        artifact_id: str | None = None,
        linked_event_id: str | None = None,
    ) -> MemoryRecord:
        return await self.write_record(
            scope=MemoryScope.SESSION,
            session_id=session_id,
            agent_id=agent_id,
            kind=MemoryRecordKind.SUMMARY,
            source="engine:checkpoint",
            content=content,
            tags=["checkpoint", "continuity"],
            task_id=task_id,
            approval_id=approval_id,
            artifact_id=artifact_id,
            linked_event_id=linked_event_id,
        )

    async def promote_record(
        self,
        *,
        record_id: str,
        session_id: str,
        agent_id: str,
        autonomy_level: AutonomyLevel,
    ) -> MemoryPromotion:
        policy_decision = self._policy_evaluator.evaluate(
            resource="memory:session:promote",
            agent_id=agent_id,
            session_id=session_id,
        )
        if policy_decision.action == PolicyAction.DENY:
            raise PermissionError("policy denied memory access to memory:session:promote")

        source_record = await self._repository.get_record(record_id)
        if source_record is None:
            raise ValueError(f"unknown memory record: {record_id}")
        if source_record.scope != MemoryScope.SESSION:
            raise ValueError("only session memory can be promoted")
        if source_record.session_id != session_id:
            raise ValueError("memory record does not belong to the requested session")

        approval_description = self._build_promotion_approval_description(record_id)
        policy_requires_approval = policy_decision.action == PolicyAction.REQUIRE_APPROVAL
        autonomy_requires_approval = autonomy_level != AutonomyLevel.AUTONOMOUS and not self._approval_service.has_session_grant(
            session_id,
            approval_description,
        )
        approval_id: str | None = None
        if policy_requires_approval or autonomy_requires_approval:
            approval_id = await self._approval_service.request_approval(
                session_id=session_id,
                agent_id=agent_id,
                tool_invocation_id=record_id,
                description=approval_description,
            )
            if approval_id is None:
                raise RuntimeError("promotion approval id missing")
            await self._event_bus.publish(
                ApprovalRequestedEvent(
                    session_id=session_id,
                    agent_id=agent_id,
                    approval_id=approval_id,
                    invocation_id=record_id,
                    description=approval_description,
                )
            )

        promotion = MemoryPromotion(
            source_record_id=source_record.id,
            source_session_id=session_id,
            proposing_agent_id=agent_id,
            approval_id=approval_id,
        )
        await self._repository.create_promotion(promotion)
        await self._repository.update_record_promotion(source_record.id, promotion.id)
        await self._event_bus.publish(
            MemoryPromotionRequestedEvent(
                session_id=session_id,
                agent_id=agent_id,
                promotion_id=promotion.id,
                source_record_id=source_record.id,
                approval_id=approval_id,
            )
        )

        if policy_requires_approval or autonomy_requires_approval:
            request_id = approval_id
            if request_id is None:
                raise RuntimeError("promotion approval id missing")
            decision = await self._approval_service.wait_for_decision(
                request_id,
                timeout=self._approval_timeout,
            )
            if decision == ApprovalStatus.GRANTED:
                await self._event_bus.publish(
                    ApprovalDecidedEvent(
                        event_type=EventType.APPROVAL_GRANTED,
                        session_id=session_id,
                        agent_id=agent_id,
                        approval_id=request_id,
                        decision=ApprovalStatus.GRANTED,
                    )
                )
            if decision == ApprovalStatus.DENIED:
                await self._event_bus.publish(
                    ApprovalDecidedEvent(
                        event_type=EventType.APPROVAL_DENIED,
                        session_id=session_id,
                        agent_id=agent_id,
                        approval_id=request_id,
                        decision=ApprovalStatus.DENIED,
                    )
                )
                await self._repository.update_promotion_state(
                    promotion.id,
                    MemoryPromotionStatus.DENIED,
                )
                denied_promotion = promotion.model_copy(update={"status": MemoryPromotionStatus.DENIED})
                await self._event_bus.publish(
                    MemoryPromotionDeniedEvent(
                        session_id=session_id,
                        agent_id=agent_id,
                        promotion_id=promotion.id,
                        source_record_id=source_record.id,
                        approval_id=approval_id,
                        reason="Approval denied",
                    )
                )
                return denied_promotion
            if decision == ApprovalStatus.EXPIRED:
                return promotion

        global_record = MemoryRecord(
            scope=MemoryScope.GLOBAL,
            session_id=None,
            agent_id=source_record.agent_id,
            kind=source_record.kind,
            source=source_record.source,
            content=source_record.content,
            tags=list(source_record.tags),
            task_id=source_record.task_id,
            approval_id=approval_id,
            artifact_id=source_record.artifact_id,
            linked_event_id=source_record.linked_event_id,
            promotion_id=promotion.id,
        )
        await self._repository.create_record(global_record)
        await self._event_bus.publish(
            MemoryRecordCreatedEvent(
                session_id=session_id,
                agent_id=agent_id,
                record_id=global_record.id,
                scope=global_record.scope,
                kind=global_record.kind,
                source=global_record.source,
                content=global_record.content,
                task_id=global_record.task_id,
                approval_id=global_record.approval_id,
                artifact_id=global_record.artifact_id,
                linked_event_id=global_record.linked_event_id,
                promotion_id=global_record.promotion_id,
            )
        )
        await self._repository.update_promotion_state(
            promotion.id,
            MemoryPromotionStatus.APPROVED,
            target_record_id=global_record.id,
        )
        approved_promotion = promotion.model_copy(
            update={
                "status": MemoryPromotionStatus.APPROVED,
                "target_record_id": global_record.id,
            }
        )
        await self._event_bus.publish(
            MemoryPromotionApprovedEvent(
                session_id=session_id,
                agent_id=agent_id,
                promotion_id=promotion.id,
                source_record_id=source_record.id,
                target_record_id=global_record.id,
                approval_id=approval_id,
            )
        )
        return approved_promotion

    async def _authorize(
        self,
        *,
        resource: str,
        agent_id: str,
        session_id: str,
    ) -> str | None:
        decision = self._policy_evaluator.evaluate(
            resource=resource,
            agent_id=agent_id,
            session_id=session_id,
        )
        if decision.action == PolicyAction.DENY:
            raise PermissionError(f"policy denied memory access to {resource}")
        if decision.action != PolicyAction.REQUIRE_APPROVAL:
            return None

        description = self._build_resource_approval_description(resource=resource, session_id=session_id)
        invocation_id = generate_prefixed_id("inv")
        approval_id = await self._approval_service.request_approval(
            session_id=session_id,
            agent_id=agent_id,
            tool_invocation_id=invocation_id,
            description=description,
        )
        await self._event_bus.publish(
            ApprovalRequestedEvent(
                session_id=session_id,
                agent_id=agent_id,
                approval_id=approval_id,
                invocation_id=invocation_id,
                description=description,
            )
        )
        approval_status = await self._approval_service.wait_for_decision(
            approval_id,
            timeout=self._approval_timeout,
        )
        if approval_status == ApprovalStatus.GRANTED:
            await self._event_bus.publish(
                ApprovalDecidedEvent(
                    event_type=EventType.APPROVAL_GRANTED,
                    session_id=session_id,
                    agent_id=agent_id,
                    approval_id=approval_id,
                    decision=ApprovalStatus.GRANTED,
                )
            )
            return approval_id
        if approval_status == ApprovalStatus.DENIED:
            await self._event_bus.publish(
                ApprovalDecidedEvent(
                    event_type=EventType.APPROVAL_DENIED,
                    session_id=session_id,
                    agent_id=agent_id,
                    approval_id=approval_id,
                    decision=ApprovalStatus.DENIED,
                )
            )
            raise PermissionError(f"approval denied for memory access to {resource}")
        raise PermissionError(f"approval expired for memory access to {resource}")

    @staticmethod
    def _resource_name(*, scope: MemoryScope, action: str) -> str:
        return f"memory:{scope.value}:{action}"

    @staticmethod
    def _build_promotion_approval_description(record_id: str) -> str:
        return f"Promote memory record '{record_id}' to global scope"

    @staticmethod
    def _build_resource_approval_description(*, resource: str, session_id: str) -> str:
        return f"Access memory resource '{resource}' for session '{session_id}'"
