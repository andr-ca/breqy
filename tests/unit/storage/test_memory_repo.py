"""Tests for SQLite memory repository."""

import pytest

from breqy.domain.enums import MemoryPromotionStatus, MemoryRecordKind, MemoryScope
from breqy.domain.models import MemoryPromotion, MemoryRecord, Session
from breqy.storage.sqlite.session_repo import SqliteSessionRepository


@pytest.mark.asyncio
async def test_create_and_get_session_memory_record(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    session = Session(primary_agent_id="agent_breqy")
    await SqliteSessionRepository(db_connection).create(session)

    repo = SqliteMemoryRepository(db_connection)
    record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.NOTE,
        source="conversation",
        content="Remember to use WAL mode.",
        tags=["infra", "sqlite"],
        task_id="tsk_123",
        approval_id="apr_123",
        artifact_id="art_123",
        linked_event_id="evt_123",
        promotion_id="mpr_123",
    )

    await repo.create_record(record)

    result = await repo.get_record(record.id)
    assert result is not None
    assert result.id == record.id
    assert result.scope == MemoryScope.SESSION
    assert result.session_id == session.id
    assert result.tags == ["infra", "sqlite"]
    assert result.task_id == "tsk_123"
    assert result.approval_id == "apr_123"
    assert result.artifact_id == "art_123"
    assert result.linked_event_id == "evt_123"
    assert result.promotion_id == "mpr_123"


@pytest.mark.asyncio
async def test_create_and_get_global_memory_record(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    repo = SqliteMemoryRepository(db_connection)
    record = MemoryRecord(
        scope=MemoryScope.GLOBAL,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.FACT,
        source="promotion",
        content="User prefers explicit approval for destructive tools.",
        tags=["preference"],
    )

    await repo.create_record(record)

    result = await repo.get_record(record.id)
    assert result is not None
    assert result.scope == MemoryScope.GLOBAL
    assert result.session_id is None
    assert result.content == record.content


@pytest.mark.asyncio
async def test_list_records_by_scope_filters_session_and_global(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    session_one = Session(primary_agent_id="agent_breqy")
    session_two = Session(primary_agent_id="agent_breqy")
    session_repo = SqliteSessionRepository(db_connection)
    await session_repo.create(session_one)
    await session_repo.create(session_two)

    repo = SqliteMemoryRepository(db_connection)
    session_record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session_one.id,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.SUMMARY,
        source="checkpoint",
        content="Session one checkpoint.",
        tags=["checkpoint"],
    )
    other_session_record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session_two.id,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.NOTE,
        source="conversation",
        content="Session two note.",
    )
    global_record = MemoryRecord(
        scope=MemoryScope.GLOBAL,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.LESSON,
        source="promotion",
        content="Always confirm branch strategy before coding.",
        tags=["process"],
    )

    await repo.create_record(session_record)
    await repo.create_record(other_session_record)
    await repo.create_record(global_record)

    session_results = await repo.list_records(
        scope=MemoryScope.SESSION,
        session_id=session_one.id,
    )
    global_results = await repo.list_records(scope=MemoryScope.GLOBAL)

    assert [record.id for record in session_results] == [session_record.id]
    assert [record.id for record in global_results] == [global_record.id]


@pytest.mark.asyncio
async def test_list_records_requires_session_id_for_session_scope(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    repo = SqliteMemoryRepository(db_connection)

    with pytest.raises(ValueError, match="session scope requires session_id"):
        await repo.list_records(scope=MemoryScope.SESSION)


@pytest.mark.asyncio
async def test_list_records_rejects_session_id_for_global_scope(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    repo = SqliteMemoryRepository(db_connection)

    with pytest.raises(ValueError, match="global scope does not accept session_id"):
        await repo.list_records(scope=MemoryScope.GLOBAL, session_id="ses_invalid")


@pytest.mark.asyncio
async def test_list_records_supports_metadata_first_filtering(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    session = Session(primary_agent_id="agent_breqy")
    await SqliteSessionRepository(db_connection).create(session)

    repo = SqliteMemoryRepository(db_connection)
    matching_record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.FACT,
        source="conversation",
        content="Selected by task metadata.",
        task_id="tsk_filter",
        approval_id="apr_filter",
        artifact_id="art_filter",
        linked_event_id="evt_filter",
        promotion_id="mpr_filter",
    )
    non_matching_record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.FACT,
        source="conversation",
        content="Should not be overfetched.",
        task_id="tsk_other",
        approval_id="apr_other",
        artifact_id="art_other",
        linked_event_id="evt_other",
        promotion_id="mpr_other",
    )

    await repo.create_record(matching_record)
    await repo.create_record(non_matching_record)

    results = await repo.list_records(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        task_id="tsk_filter",
        approval_id="apr_filter",
        artifact_id="art_filter",
        linked_event_id="evt_filter",
        promotion_id="mpr_filter",
    )

    assert [record.id for record in results] == [matching_record.id]


@pytest.mark.asyncio
async def test_list_records_supports_agent_and_tag_filtering(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    session = Session(primary_agent_id="agent_breqy")
    await SqliteSessionRepository(db_connection).create(session)

    repo = SqliteMemoryRepository(db_connection)
    matching_record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.NOTE,
        source="conversation",
        content="Owned by breqy and tagged for retrieval.",
        tags=["focus", "retrieval"],
    )
    other_owner = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        agent_id="agent_other",
        kind=MemoryRecordKind.NOTE,
        source="conversation",
        content="Wrong owner.",
        tags=["focus", "retrieval"],
    )
    other_tag = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.NOTE,
        source="conversation",
        content="Wrong tag.",
        tags=["background"],
    )

    await repo.create_record(matching_record)
    await repo.create_record(other_owner)
    await repo.create_record(other_tag)

    results = await repo.list_records(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        agent_id="agent_breqy",
        tags=["retrieval"],
    )

    assert [record.id for record in results] == [matching_record.id]


@pytest.mark.asyncio
async def test_create_and_update_promotion_state(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    session = Session(primary_agent_id="agent_breqy")
    await SqliteSessionRepository(db_connection).create(session)

    repo = SqliteMemoryRepository(db_connection)
    source_record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.FACT,
        source="conversation",
        content="User works primarily in Linux worktrees.",
    )
    target_record = MemoryRecord(
        scope=MemoryScope.GLOBAL,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.FACT,
        source="promotion",
        content="User works primarily in Linux worktrees.",
    )
    promotion = MemoryPromotion(
        source_record_id=source_record.id,
        source_session_id=session.id,
        proposing_agent_id="agent_breqy",
        approval_id="apr_promote",
    )

    await repo.create_record(source_record)
    await repo.create_promotion(promotion)
    await repo.create_record(target_record)

    pending = await repo.get_promotion(promotion.id)
    assert pending is not None
    assert pending.status == MemoryPromotionStatus.PENDING
    assert pending.target_record_id is None

    await repo.update_promotion_state(
        promotion_id=promotion.id,
        status=MemoryPromotionStatus.APPROVED,
        target_record_id=target_record.id,
    )

    updated = await repo.get_promotion(promotion.id)
    assert updated is not None
    assert updated.status == MemoryPromotionStatus.APPROVED
    assert updated.target_record_id == target_record.id


@pytest.mark.asyncio
async def test_approved_promotion_requires_target_record_id(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    session = Session(primary_agent_id="agent_breqy")
    await SqliteSessionRepository(db_connection).create(session)

    repo = SqliteMemoryRepository(db_connection)
    source_record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.FACT,
        source="conversation",
        content="Needs approval target.",
    )
    promotion = MemoryPromotion(
        source_record_id=source_record.id,
        source_session_id=session.id,
        proposing_agent_id="agent_breqy",
    )

    await repo.create_record(source_record)
    await repo.create_promotion(promotion)

    with pytest.raises(ValueError, match="approved promotions require target_record_id"):
        await repo.update_promotion_state(
            promotion_id=promotion.id,
            status=MemoryPromotionStatus.APPROVED,
        )

    result = await repo.get_promotion(promotion.id)
    assert result is not None
    assert result.status == MemoryPromotionStatus.PENDING
    assert result.target_record_id is None


@pytest.mark.asyncio
async def test_denied_promotion_updates_without_target_record_id(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    session = Session(primary_agent_id="agent_breqy")
    await SqliteSessionRepository(db_connection).create(session)

    repo = SqliteMemoryRepository(db_connection)
    source_record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.FACT,
        source="conversation",
        content="May be denied.",
    )
    promotion = MemoryPromotion(
        source_record_id=source_record.id,
        source_session_id=session.id,
        proposing_agent_id="agent_breqy",
    )

    await repo.create_record(source_record)
    await repo.create_promotion(promotion)
    await repo.update_promotion_state(
        promotion_id=promotion.id,
        status=MemoryPromotionStatus.DENIED,
    )

    result = await repo.get_promotion(promotion.id)
    assert result is not None
    assert result.status == MemoryPromotionStatus.DENIED
    assert result.target_record_id is None


@pytest.mark.asyncio
async def test_update_record_promotion_metadata(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    session = Session(primary_agent_id="agent_breqy")
    await SqliteSessionRepository(db_connection).create(session)

    repo = SqliteMemoryRepository(db_connection)
    record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id=session.id,
        agent_id="agent_breqy",
        kind=MemoryRecordKind.NOTE,
        source="conversation",
        content="Potentially promotable note.",
    )
    await repo.create_record(record)

    await repo.update_record_promotion(record.id, "mpr_promoted")

    result = await repo.get_record(record.id)
    assert result is not None
    assert result.promotion_id == "mpr_promoted"


@pytest.mark.asyncio
async def test_get_record_and_get_promotion_return_none_for_unknown_ids(db_connection) -> None:
    from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository

    repo = SqliteMemoryRepository(db_connection)

    assert await repo.get_record("mem_missing") is None
    assert await repo.get_promotion("mpr_missing") is None
