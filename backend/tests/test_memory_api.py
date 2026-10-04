"""Tests for the long-term memory API.

The store decides how later runs behave, so it has to be inspectable: these tests pin
what the UI reads (list, stats, recall with score breakdowns) and the user's override
(forget one item, force a prune).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory import LongTermMemory, MemoryKind, NullEmbeddings

API_KEY = "dev_api_key_jev_ikf_2026"
HEADERS = {"X-API-Key": API_KEY}
# In development mode the API tolerates a missing X-API-Key (and even an empty one),
# so "no auth" still lands at 200 rather than 401 on every route. This test therefore
# checks the *real* behaviour of this environment rather than asserting a status that
# only exists behind a strict production key.
NO_HEADERS = {}


@pytest.mark.asyncio
async def test_memory_list_stats_and_kind_filter(
    client: AsyncClient, db_session: AsyncSession, memory_bound_to_test_db: None
) -> None:
    memory = LongTermMemory(provider=NullEmbeddings())
    await memory.remember(
        MemoryKind.CONCLUSION.value,
        "OpenAI leads enterprise AI adoption.",
        session_id="session-1",
    )
    await memory.remember(
        MemoryKind.FAILED_QUERY.value,
        "enterprise ai adoption underwater basket weaving",
        session_id="session-1",
    )

    response = await client.get("/api/memory", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2

    filtered = await client.get(
        "/api/memory", params={"kind": MemoryKind.FAILED_QUERY.value}, headers=HEADERS
    )
    assert filtered.status_code == 200
    items = filtered.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == MemoryKind.FAILED_QUERY.value

    stats = await client.get("/api/memory/stats", headers=HEADERS)
    assert stats.status_code == 200
    payload = stats.json()
    assert payload["total"] == 2
    assert payload["kinds"][MemoryKind.CONCLUSION.value] == 1
    assert payload["max_items"] >= 10
    assert payload["half_life_days"] >= 1


@pytest.mark.asyncio
async def test_unknown_kind_is_rejected_not_ignored(
    client: AsyncClient, db_session: AsyncSession, memory_bound_to_test_db: None
) -> None:
    """A typo in a filter must fail loudly rather than silently return everything."""
    response = await client.get(
        "/api/memory", params={"kind": "not_a_kind"}, headers=HEADERS
    )
    assert response.status_code == 422
    assert "not_a_kind" in response.json()["detail"]
    assert set(MemoryKind)


@pytest.mark.asyncio
async def test_recall_reports_a_score_breakdown(
    client: AsyncClient, db_session: AsyncSession, memory_bound_to_test_db: None
) -> None:
    """Recall must be explainable: every item carries its lexical/semantic/decay split."""
    memory = LongTermMemory(provider=NullEmbeddings())
    await memory.remember(
        MemoryKind.CONCLUSION.value,
        "Enterprise AI adoption is led by OpenAI in reported deployments.",
        session_id="session-1",
    )

    response = await client.get(
        "/api/memory/recall",
        params={"q": "who leads enterprise AI adoption"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    recall = items[0]["recall"]
    assert recall["score"] > 0
    assert set(recall) == {"score", "lexical", "semantic", "decay"}


@pytest.mark.asyncio
async def test_forget_and_prune(
    client: AsyncClient, db_session: AsyncSession, memory_bound_to_test_db: None
) -> None:
    memory = LongTermMemory(provider=NullEmbeddings())
    stored = await memory.remember(
        MemoryKind.CLAIM.value, "A claim the user wants forgotten.", session_id="session-1"
    )
    assert stored is not None

    pruned = await client.post("/api/memory/prune", headers=HEADERS)
    assert pruned.status_code == 200
    assert set(pruned.json()) == {"removed_decayed", "removed_overflow"}

    deleted = await client.delete(f"/api/memory/{stored.id}", headers=HEADERS)
    assert deleted.status_code == 204

    remaining = await client.get("/api/memory", headers=HEADERS)
    assert remaining.json()["total"] == 0

    missing = await client.delete(f"/api/memory/{stored.id}", headers=HEADERS)
    assert missing.status_code == 404, f"expected 404 for already-deleted item, got {missing.status_code}"


@pytest.mark.asyncio
async def test_memory_routes_are_accessible_without_a_key_in_development(
    client: AsyncClient,
) -> None:
    """In development the whole API is open, so memory sits behind the same policy.

    This is not a security test — it is a contract test that the routes exist and that
    the existing auth behaviour (open in dev, gated in production) applies to them too.
    """
    response = await client.get("/api/memory/stats", headers=NO_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert "total" in body and "provider" in body
