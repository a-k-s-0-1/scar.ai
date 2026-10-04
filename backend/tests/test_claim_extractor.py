"""Tests for ClaimExtractor JSON parsing, persistence, and confidence mapping."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import ClaimRepository, SessionRepository, SourceRepository
from app.services.claim_extractor import ClaimExtractor


@pytest.mark.asyncio
async def test_claim_extraction_success(db_session: AsyncSession) -> None:
    """Verify structured claims are successfully parsed and saved."""
    s_repo = SessionRepository(db_session)
    src_repo = SourceRepository(db_session)
    claim_repo = ClaimRepository(db_session)

    session = await s_repo.create(question="How efficient are perovskite solar cells?")
    source = await src_repo.create(
        session_id=session.id,
        url="https://nature.com/solar-paper",
        title="Perovskite Cells",
        content="Perovskite solar cells achieved 26.1% certified laboratory efficiency in recent testing.",
    )
    await db_session.commit()

    extractor = ClaimExtractor(session_id=session.id)

    mock_llm_json = """{
      "claims": [
        {
          "claim": "Perovskite solar cells achieved 26.1% certified laboratory efficiency.",
          "subject": "Perovskite solar cells",
          "predicate": "achieved",
          "object": "26.1% certified laboratory efficiency",
          "confidence": "high"
        }
      ]
    }"""

    with patch(
        "app.services.claim_extractor.llm_router.generate", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = mock_llm_json

        extracted = await extractor.extract_from_sources(
            [source], session.question, db=db_session
        )
        await db_session.commit()

        assert len(extracted) == 1
        claim = extracted[0]
        assert claim.subject == "Perovskite solar cells"
        assert claim.confidence == "high"

        # Check DB persistence
        db_claims = await claim_repo.get_by_session(session.id)
        assert len(db_claims) == 1
        assert len(db_claims[0].source_links) == 1
        assert db_claims[0].source_links[0].source_id == source.id
