"""Tests for one-click report re-synthesis after a fallback summary."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import SessionRepository
from app.services.report_generator import MAX_SYNTHESIS_RETRIES, synthesis_lock

API_HEADERS = {"X-API-Key": "dev_api_key_jev_ikf_2026"}

FALLBACK_REPORT = {
    "executive_summary": "rule-based fallback summary",
    "key_findings": ["a claim"],
    "unknowns": ["an unknown"],
    "metadata": {"synthesis": "fallback", "retry_count": 0},
}

SYNTHESIS_JSON = (
    '{"executive_summary": "Model summary",'
    ' "key_findings": ["finding"],'
    ' "unknowns": ["unknown"]}'
)


async def make_session(
    db: AsyncSession, *, retry_count: int = 0, status: str = "completed"
) -> str:
    """Create a finished session that already holds a fallback report."""
    repo = SessionRepository(db)
    session = await repo.create(question="Is green hydrogen viable at scale?")
    await repo.save_report(
        session.id,
        {
            **FALLBACK_REPORT,
            "session_id": session.id,
            "metadata": {"synthesis": "fallback", "retry_count": retry_count},
        },
    )
    if status != "completed":
        await repo.update_status(session.id, status=status)
    await db.commit()
    return session.id


@pytest.mark.asyncio
async def test_retry_replaces_a_fallback_report(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A successful retry upgrades the report and counts the attempt."""
    session_id = await make_session(db_session)

    with patch(
        "app.services.report_generator.llm_router.generate", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = SYNTHESIS_JSON
        res = await client.post(
            f"/api/research/{session_id}/retry-synthesis", headers=API_HEADERS
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "regenerated"
    assert body["synthesis"] == "llm"
    assert body["retry_count"] == 1
    assert body["max_retries"] == MAX_SYNTHESIS_RETRIES
    assert body["report_data"]["executive_summary"] == "Model summary"
    assert body["report_data"]["metadata"]["retry_count"] == 1


@pytest.mark.asyncio
async def test_retry_that_fails_again_still_records_the_attempt(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A provider that is still down leaves the fallback badge but bills one retry."""
    session_id = await make_session(db_session)

    with patch(
        "app.services.report_generator.llm_router.generate", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.side_effect = RuntimeError("provider unavailable")
        res = await client.post(
            f"/api/research/{session_id}/retry-synthesis", headers=API_HEADERS
        )

    assert res.status_code == 200
    body = res.json()
    assert body["synthesis"] == "fallback"
    assert body["report_data"]["metadata"]["retry_count"] == 1
    # The fallback rewrite must not present deterministic text as model output.
    assert body["report_data"]["executive_summary"] != "rule-based fallback summary"


@pytest.mark.asyncio
async def test_retry_does_not_relabel_a_stopped_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Re-synthesising a halted run rewrites its report without claiming completion."""
    session_id = await make_session(db_session, status="stopped")

    with patch(
        "app.services.report_generator.llm_router.generate", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = SYNTHESIS_JSON
        res = await client.post(
            f"/api/research/{session_id}/retry-synthesis", headers=API_HEADERS
        )

    assert res.status_code == 200
    session = await SessionRepository(db_session).get_by_id(session_id)
    assert session is not None
    assert session.status == "stopped"


@pytest.mark.asyncio
async def test_retry_is_refused_while_the_run_is_in_progress(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    session_id = await make_session(db_session, status="running")

    res = await client.post(
        f"/api/research/{session_id}/retry-synthesis", headers=API_HEADERS
    )

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "SynthesisNotRetryableError"


@pytest.mark.asyncio
async def test_retry_is_refused_once_the_limit_is_reached(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    session_id = await make_session(db_session, retry_count=MAX_SYNTHESIS_RETRIES)

    res = await client.post(
        f"/api/research/{session_id}/retry-synthesis", headers=API_HEADERS
    )

    assert res.status_code == 409
    assert res.json()["error"]["details"]["reason"].startswith("the retry limit")


@pytest.mark.asyncio
async def test_retry_on_an_unknown_session_is_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    res = await client.post(
        "/api/research/does-not-exist/retry-synthesis", headers=API_HEADERS
    )

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_synthesis_lock_serialises_one_session() -> None:
    """Concurrent retries must not interleave their read-modify-write.

    Reproduced live before this existed: three parallel retries all reported
    attempt 2, so three model calls were paid for and one was counted, and the
    retry cap was validated against a stale count.
    """
    assert synthesis_lock("session-a") is synthesis_lock("session-a")
    assert synthesis_lock("session-a") is not synthesis_lock("session-b")

    order: list[str] = []

    async def worker(tag: str) -> None:
        async with synthesis_lock("shared"):
            order.append(f"{tag}-in")
            await asyncio.sleep(0.01)
            order.append(f"{tag}-out")

    await asyncio.gather(worker("one"), worker("two"))

    assert order == ["one-in", "one-out", "two-in", "two-out"]
