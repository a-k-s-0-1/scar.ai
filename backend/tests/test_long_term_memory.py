"""Tests for long-term memory: the keep/forget policy, retrieval, embeddings and the service."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory import (
    GeminiEmbeddings,
    LongTermMemory,
    MemoryKind,
    MemoryRecord,
    MemoryWrite,
    NullEmbeddings,
    cosine_similarity,
    decay_weight,
    get_embedding_provider,
    importance_for,
    lexical_score,
    normalize_key,
    rank_records,
    reuse_boost,
    should_forget,
    tokenize,
)

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def _record(
    text: str,
    *,
    kind: str = MemoryKind.CLAIM.value,
    importance: float = 0.5,
    hits: int = 0,
    idle_days: float = 0,
    embedding: list[float] | None = None,
) -> MemoryRecord:
    touched = NOW - timedelta(days=idle_days)
    return MemoryRecord(
        id=f"id-{text[:12]}",
        kind=kind,
        key=normalize_key(kind, text),
        text=text,
        importance=importance,
        hits=hits,
        embedding=embedding,
        created_at=touched,
        updated_at=touched,
        last_used_at=touched if hits else None,
    )


# ─── store policy ────────────────────────────────────────────────────────────


def test_normalize_key_dedupes_wording_not_meaning() -> None:
    """Re-learning the same fact must update one row, not add another."""
    assert normalize_key("entity", "OpenAI, Inc.") == normalize_key("entity", "openai inc")
    assert normalize_key("claim", "Share  was 4%") == "share was 4"
    assert normalize_key("claim", "Share rose to 9%") != normalize_key("claim", "Share was 4%")


def test_decay_weight_falls_with_idleness() -> None:
    fresh = decay_weight(_record("a", idle_days=0), now=NOW, half_life_days=180)
    old = decay_weight(_record("a", idle_days=180), now=NOW, half_life_days=180)
    ancient = decay_weight(_record("a", idle_days=900), now=NOW, half_life_days=180)

    assert fresh > old > ancient
    assert pytest.approx(old, rel=0.01) == fresh / 2


def test_reuse_resists_decay_and_stays_bounded() -> None:
    """A fact recalled repeatedly should outlive one written yesterday and ignored."""
    forgotten = _record("quiet", importance=0.5, idle_days=400)
    reused = _record("useful", importance=0.5, hits=6, idle_days=400)

    quiet_weight = decay_weight(forgotten, now=NOW)
    used_weight = decay_weight(reused, now=NOW)

    assert used_weight > quiet_weight
    assert used_weight <= 1.0
    assert reuse_boost(1000) <= 0.35


def test_should_forget_uses_the_threshold() -> None:
    assert should_forget(0.01, 0.05) is True
    assert should_forget(0.5, 0.05) is False


def test_importance_ranks_kinds_and_uses_confidence() -> None:
    assert importance_for(MemoryKind.CONSTRAINT.value) > importance_for(MemoryKind.SOURCE.value)
    low = importance_for(MemoryKind.CLAIM.value, confidence=0.1)
    high = importance_for(MemoryKind.CLAIM.value, confidence=1.0)
    assert high > low
    assert 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0


# ─── retrieval ───────────────────────────────────────────────────────────────


def test_lexical_score_rewards_overlap_and_ignores_stopwords() -> None:
    tokens = tokenize("What is the solid-state battery outlook?")
    assert "the" not in tokens and "is" not in tokens

    assert lexical_score(tokens, "solid-state battery outlook") > 0.5
    assert lexical_score(tokens, "unrelated topic entirely") == 0.0
    assert lexical_score(set(), "anything") == 0.0


def test_rank_prefers_relevant_items_and_drops_unrelated_ones() -> None:
    records = [
        _record("Solid-state battery share was 4% in 2024"),
        _record("Coffee prices rose in Brazil"),
        _record("Solid-state battery share is 9% in 2026", hits=2),
    ]

    ranked = rank_records(records, "solid-state battery share", limit=5, now=NOW)

    assert len(ranked) == 2
    assert all("battery" in item.record.text for item in ranked)
    assert ranked[0].score >= ranked[1].score
    # Every recalled item reports why it was recalled.
    assert ranked[0].to_dict()["recall"]["score"] > 0


def test_rank_uses_semantic_similarity_when_vectors_exist() -> None:
    """A paraphrase with no shared words is still recalled if embeddings say so."""
    records = [
        _record("Power density improved markedly", embedding=[1.0, 0.0, 0.0]),
        _record("Coffee prices rose", embedding=[0.0, 1.0, 0.0]),
    ]

    ranked = rank_records(
        records,
        "energy per kilogram",  # shares no token with either record
        query_vector=[0.95, 0.05, 0.0],
        limit=5,
        now=NOW,
    )

    assert [item.record.text for item in ranked] == ["Power density improved markedly"]
    assert ranked[0].semantic > 0.9


def test_without_vectors_a_query_with_no_overlap_recalls_nothing() -> None:
    records = [_record("Power density improved markedly")]
    assert rank_records(records, "energy per kilogram", now=NOW) == []


def test_cosine_similarity_handles_degenerate_inputs() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    # A model change between runs yields different dimensions; that is not a crash.
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0
    assert cosine_similarity(None, [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ─── embeddings ──────────────────────────────────────────────────────────────


class _FailingClient:
    async def embed(self, text: str) -> list[float]:
        raise RuntimeError("API key not valid")


class _WorkingClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.1, 0.2, 0.3]


class _Settings:
    def __init__(self, enabled: bool, key: str) -> None:
        self.MEMORY_EMBEDDINGS_ENABLED = enabled
        self.GEMINI_API_KEY = key
        self.MEMORY_ENABLED = True
        self.MEMORY_RECALL_LIMIT = 8
        self.MEMORY_HALF_LIFE_DAYS = 180
        self.MEMORY_MIN_WEIGHT = 0.05
        self.MEMORY_MAX_ITEMS = 2000


@pytest.mark.asyncio
async def test_embeddings_never_raise_when_the_provider_fails() -> None:
    """A revoked key must downgrade recall, not break the run that is writing memory."""
    provider = GeminiEmbeddings(client=_FailingClient())  # type: ignore[arg-type]
    assert await provider.embed("some text") is None
    assert await provider.embed("some text") is None  # second failure stays quiet
    assert await provider.embed("") is None


@pytest.mark.asyncio
async def test_embeddings_return_vectors_when_the_provider_works() -> None:
    client = _WorkingClient()
    provider = GeminiEmbeddings(client=client)  # type: ignore[arg-type]
    assert await provider.embed("some text") == [0.1, 0.2, 0.3]
    assert client.calls == ["some text"]


def test_provider_selection_follows_configuration() -> None:
    assert isinstance(get_embedding_provider(_Settings(enabled=False, key="k")), NullEmbeddings)
    assert isinstance(get_embedding_provider(_Settings(enabled=True, key="")), NullEmbeddings)
    assert isinstance(get_embedding_provider(_Settings(enabled=True, key="k")), GeminiEmbeddings)


# ─── service ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remember_dedupes_and_only_strengthens(
    memory_bound_to_test_db: None,
) -> None:
    """Learning the same thing twice updates it; it never duplicates or weakens it."""
    memory = LongTermMemory(provider=NullEmbeddings())

    first = await memory.remember(MemoryKind.CONSTRAINT.value, "Minimum 10 sources per run")
    again = await memory.remember(
        MemoryKind.CONSTRAINT.value, "minimum 10 sources per run", importance=0.1
    )

    assert first is not None and again is not None
    assert first.id == again.id
    items = await memory.list_items(kind=MemoryKind.CONSTRAINT.value)
    assert len(items) == 1
    # The lower importance offered on the second write must not win.
    assert items[0]["importance"] >= first.importance


@pytest.mark.asyncio
async def test_recall_finds_relevant_items_and_records_the_reuse(
    memory_bound_to_test_db: None,
) -> None:
    memory = LongTermMemory(provider=NullEmbeddings())
    await memory.remember_many(
        [
            MemoryWrite(MemoryKind.CONCLUSION.value, "Solid-state share reached 4% in 2024"),
            MemoryWrite(MemoryKind.CONCLUSION.value, "Coffee futures fell in Brazil"),
        ]
    )

    recalled = await memory.recall("solid-state market share")
    assert [item.record.text for item in recalled] == [
        "Solid-state share reached 4% in 2024"
    ]

    # Recalling it must count as use, or it decays like something nobody needed.
    items = await memory.list_items(kind=MemoryKind.CONCLUSION.value)
    used = next(item for item in items if "Solid-state" in item["text"])
    assert used["hits"] == 1
    assert used["last_used_at"] is not None


@pytest.mark.asyncio
async def test_alias_table_and_avoided_queries_round_trip(
    memory_bound_to_test_db: None,
) -> None:
    """These two are the carry-over hooks: entity acronyms and dead-end queries."""
    memory = LongTermMemory(provider=NullEmbeddings())

    await memory.remember(
        MemoryKind.ENTITY.value,
        "IBM",
        payload={"aliases": ["Big Blue", "International Business Machines"]},
    )
    await memory.remember(MemoryKind.FAILED_QUERY.value, "unobtainium cost curve")

    assert await memory.aliases() == {
        "IBM": ["Big Blue", "International Business Machines"]
    }
    assert await memory.avoided_queries() == {"unobtainium cost curve"}


@pytest.mark.asyncio
async def test_recall_keys_are_normalized_for_query_avoidance(
    memory_bound_to_test_db: None,
) -> None:
    memory = LongTermMemory(provider=NullEmbeddings())
    await memory.remember(MemoryKind.FAILED_QUERY.value, "Unobtainium  cost, curve?")

    assert await memory.avoided_queries() == {"unobtainium cost curve"}


@pytest.mark.asyncio
async def test_remember_session_stores_the_research_history(
    memory_bound_to_test_db: None,
) -> None:
    memory = LongTermMemory(provider=NullEmbeddings())
    await memory.remember_session(
        session_id="s-1",
        question="Is solid-state manufacturing viable by 2030?",
        summary="Share is rising but yield is the constraint.",
        stop_reason="Coverage target reached",
        stats={"claims": 42, "sources": 18},
    )

    items = await memory.list_items(kind=MemoryKind.RESEARCH_HISTORY.value)
    assert len(items) == 1
    assert items[0]["payload"]["stats"]["claims"] == 42
    assert items[0]["source_session_id"] == "s-1"


@pytest.mark.asyncio
async def test_decay_and_prune_forgets_the_stale_and_keeps_the_useful(
    memory_bound_to_test_db: None,
) -> None:
    memory = LongTermMemory(provider=NullEmbeddings())

    await memory.remember(MemoryKind.SOURCE.value, "https://stale.example.com/old")
    fresh = await memory.remember(MemoryKind.CONSTRAINT.value, "Prefer primary sources")
    for _ in range(5):
        await memory.recall("prefer primary sources")

    removed = await memory.decay_and_prune(now=NOW + timedelta(days=1500))

    assert removed["removed_decayed"] >= 1
    remaining = {item["text"] for item in await memory.list_items()}
    assert "Prefer primary sources" in remaining
    assert "https://stale.example.com/old" not in remaining
    assert fresh is not None


@pytest.mark.asyncio
async def test_decay_and_prune_enforces_the_size_cap(
    memory_bound_to_test_db: None,
) -> None:
    memory = LongTermMemory(provider=NullEmbeddings())
    memory.settings.MEMORY_MAX_ITEMS = 3

    for index in range(6):
        await memory.remember(
            MemoryKind.CLAIM.value,
            f"Claim number {index}",
            importance=0.2 + index * 0.1,
        )

    removed = await memory.decay_and_prune(now=NOW)

    assert removed["removed_overflow"] == 3
    assert await memory.stats() and (await memory.stats())["total"] == 3


@pytest.mark.asyncio
async def test_stats_report_the_kinds_and_embedding_coverage(
    memory_bound_to_test_db: None,
) -> None:
    memory = LongTermMemory(provider=NullEmbeddings())
    await memory.remember(MemoryKind.CONCLUSION.value, "One conclusion")
    await memory.remember(MemoryKind.FAILED_QUERY.value, "one dead end query")

    stats = await memory.stats(now=NOW)

    assert stats["total"] == 2
    assert stats["kinds"][MemoryKind.CONCLUSION.value] == 1
    assert stats["provider"] == "none"
    assert stats["embedded"] == 0
    assert stats["max_items"] == 2000


@pytest.mark.asyncio
async def test_write_failure_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch, memory_bound_to_test_db: None
) -> None:
    """A memory bug must not cost the user a finished investigation."""
    memory = LongTermMemory(provider=NullEmbeddings())

    class _Broken:
        def __call__(self) -> object:
            raise RuntimeError("database is on fire")

    monkeypatch.setattr(
        "app.services.memory.service.get_session_factory", lambda: _Broken()
    )
    assert await memory.remember(MemoryKind.CLAIM.value, "anything") is None


@pytest.mark.asyncio
async def test_disabled_memory_writes_nothing(
    memory_bound_to_test_db: None,
) -> None:
    memory = LongTermMemory(provider=NullEmbeddings())
    memory.settings.MEMORY_ENABLED = False

    assert await memory.remember(MemoryKind.CLAIM.value, "ignored") is None
    assert await memory.recall("ignored") == []
    assert await memory.aliases() == {}
    assert await memory.avoided_queries() == set()


@pytest.mark.asyncio
async def test_forget_removes_one_item(memory_bound_to_test_db: None) -> None:
    memory = LongTermMemory(provider=NullEmbeddings())
    stored = await memory.remember(MemoryKind.CLAIM.value, "Disposable")
    assert stored is not None

    assert await memory.forget(stored.id) is True
    assert await memory.forget(stored.id) is False
    assert await memory.list_items(kind=MemoryKind.CLAIM.value) == []


@pytest.mark.asyncio
async def test_embeddings_are_stored_and_used_for_recall(
    memory_bound_to_test_db: None,
) -> None:
    """A working provider stores vectors, which is what enables paraphrase recall."""
    client = _WorkingClient()
    memory = LongTermMemory(provider=GeminiEmbeddings(client=client))  # type: ignore[arg-type]

    await memory.remember(MemoryKind.CONCLUSION.value, "Power density improved markedly")

    items = await memory.list_items(kind=MemoryKind.CONCLUSION.value)
    assert items and items[0]["id"]

    stats = await memory.stats()
    assert stats["embedded"] == 1
    assert client.calls  # the vector came from the provider, not from nowhere


@pytest.mark.asyncio
async def test_database_session_is_required_for_writes(
    memory_bound_to_test_db: None,
) -> None:
    """Sanity check that the fixture really binds memory to the test database."""
    from app.services.memory import get_session_factory

    assert get_session_factory() is not None
    memory = LongTermMemory(provider=NullEmbeddings())
    stored = await memory.remember(MemoryKind.CLAIM.value, "bound to test db")
    assert stored is not None
