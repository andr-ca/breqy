"""Contract tests for private memory and retrieval boundaries."""

from breqy.memory.contracts import InMemoryAgentPrivateMemoryStore, PrivateMemoryRecord
from breqy.memory.index import InMemoryVectorIndex, VectorIndexDocument


async def test_vector_index_preserves_filtered_candidate_order_and_limit() -> None:
    index = InMemoryVectorIndex()
    candidates = [
        VectorIndexDocument(id="mem_1", content="approval guidance"),
        VectorIndexDocument(id="mem_2", content="artifact reference"),
        VectorIndexDocument(id="mem_3", content="background note"),
    ]

    results = await index.rank(
        query="approval artifact",
        candidates=candidates,
        limit=2,
    )

    assert [result.document_id for result in results] == ["mem_1", "mem_2"]
    assert results[0].score > results[1].score


async def test_vector_index_sorts_by_score_before_applying_limit() -> None:
    index = InMemoryVectorIndex()
    candidates = [
        VectorIndexDocument(id="mem_1", content="artifact only"),
        VectorIndexDocument(id="mem_2", content="approval only"),
        VectorIndexDocument(id="mem_3", content="approval artifact"),
    ]

    results = await index.rank(
        query="approval artifact",
        candidates=candidates,
        limit=2,
    )

    assert [result.document_id for result in results] == ["mem_3", "mem_2"]
    assert results[0].score > results[1].score


async def test_vector_index_returns_no_results_for_non_positive_limit() -> None:
    index = InMemoryVectorIndex()
    candidates = [
        VectorIndexDocument(id="mem_1", content="approval artifact"),
    ]

    zero_limit_results = await index.rank(
        query="approval",
        candidates=candidates,
        limit=0,
    )
    negative_limit_results = await index.rank(
        query="approval",
        candidates=candidates,
        limit=-1,
    )

    assert zero_limit_results == []
    assert negative_limit_results == []


async def test_private_memory_store_isolates_records_by_agent_id() -> None:
    store = InMemoryAgentPrivateMemoryStore()
    agent_a_record = PrivateMemoryRecord(
        id="priv_1",
        owner_agent_id="agent_a",
        content="remember the user's shell preferences",
        tags=("preferences",),
    )
    agent_b_record = PrivateMemoryRecord(
        id="priv_2",
        owner_agent_id="agent_b",
        content="remember the user's review checklist",
        tags=("workflow",),
    )

    await store.write(agent_id="agent_a", record=agent_a_record)
    await store.write(agent_id="agent_b", record=agent_b_record)

    agent_a_results = await store.search(agent_id="agent_a", query="remember")
    agent_b_results = await store.search(agent_id="agent_b", query="remember")

    assert [record.id for record in agent_a_results] == ["priv_1"]
    assert [record.id for record in agent_b_results] == ["priv_2"]


async def test_private_memory_store_returns_no_results_for_non_positive_limit() -> None:
    store = InMemoryAgentPrivateMemoryStore()
    record = PrivateMemoryRecord(
        id="priv_4",
        owner_agent_id="agent_a",
        content="remember this if limits allow it",
    )

    await store.write(agent_id="agent_a", record=record)

    zero_limit_results = await store.search(agent_id="agent_a", query="remember", limit=0)
    negative_limit_results = await store.search(agent_id="agent_a", query="remember", limit=-1)

    assert zero_limit_results == []
    assert negative_limit_results == []


async def test_private_memory_store_rejects_owner_mismatch_on_write() -> None:
    store = InMemoryAgentPrivateMemoryStore()

    record = PrivateMemoryRecord(
        id="priv_3",
        owner_agent_id="agent_a",
        content="owner mismatch should be rejected",
    )

    try:
        await store.write(agent_id="agent_b", record=record)
    except ValueError as error:
        assert str(error) == "private memory record owner must match agent_id"
    else:
        raise AssertionError("expected private memory owner mismatch to raise")


async def test_private_memory_store_returns_all_records_for_blank_query_until_limit() -> None:
    store = InMemoryAgentPrivateMemoryStore()
    first = PrivateMemoryRecord(
        id="priv_a",
        owner_agent_id="agent_a",
        content="first record",
    )
    second = PrivateMemoryRecord(
        id="priv_b",
        owner_agent_id="agent_a",
        content="second record",
    )

    await store.write(agent_id="agent_a", record=first)
    await store.write(agent_id="agent_a", record=second)

    results = await store.search(agent_id="agent_a", query="   ", limit=1)

    assert [record.id for record in results] == ["priv_a"]


async def test_private_memory_store_filters_out_non_matching_query_results() -> None:
    store = InMemoryAgentPrivateMemoryStore()
    record = PrivateMemoryRecord(
        id="priv_query",
        owner_agent_id="agent_a",
        content="deployment checklist",
    )

    await store.write(agent_id="agent_a", record=record)

    results = await store.search(agent_id="agent_a", query="approval")

    assert results == []
