"""Tests for SearchAgent credibility scoring, deduplication, and rate limit handling."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import RateLimitExceededError
from app.database.repository import SessionRepository
from app.services.search_agent import SearchAgent, estimate_source_credibility


def test_credibility_heuristics() -> None:
    """Verify authority domains receive higher credibility scores."""
    assert estimate_source_credibility("https://arxiv.org/abs/2301.00000") >= 0.90
    assert estimate_source_credibility("https://nature.com/articles/s41586") >= 0.90
    assert estimate_source_credibility("https://stanford.edu/research") >= 0.85
    assert estimate_source_credibility("https://www.reuters.com/business") >= 0.80
    assert estimate_source_credibility("https://reddit.com/r/technology") <= 0.40


@pytest.mark.asyncio
async def test_search_agent_deduplication(db_session: AsyncSession) -> None:
    """Ensure identical URLs are deduplicated across searches."""
    s_repo = SessionRepository(db_session)
    session = await s_repo.create(question="What is solid state battery tech?")
    await db_session.commit()

    agent = SearchAgent(session_id=session.id, max_queries=5)

    mock_results = [
        {
            "url": "https://nature.com/1",
            "title": "Paper 1",
            "content": "Content A",
            "score": 0.9,
        },
        {
            "url": "https://nature.com/2",
            "title": "Paper 2",
            "content": "Content B",
            "score": 0.8,
        },
    ]

    with patch.object(agent.client, "search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_results

        # First run: both sources added
        sources_1 = await agent.search("solid state battery", db=db_session)
        await db_session.commit()
        assert len(sources_1) == 2

        # Second run with same URLs: 0 new sources added
        sources_2 = await agent.search("solid state battery", db=db_session)
        await db_session.commit()
        assert len(sources_2) == 0


@pytest.mark.asyncio
async def test_search_agent_rate_limit(db_session: AsyncSession) -> None:
    """Verify rate limit exception is raised when max_queries is exceeded."""
    s_repo = SessionRepository(db_session)
    session = await s_repo.create(question="Quantum computing algorithms")
    await db_session.commit()

    agent = SearchAgent(session_id=session.id, max_queries=1)

    with patch.object(agent.client, "search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        await agent.search("q1", db=db_session)

        with pytest.raises(RateLimitExceededError):
            await agent.search("q2", db=db_session)
