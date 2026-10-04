"""Tests for Contradiction Detector conflict verification."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import (
    ClaimRepository,
    ContradictionRepository,
    SessionRepository,
)
from app.services.contradiction_detector import ContradictionDetector


@pytest.mark.asyncio
async def test_contradiction_detection(db_session: AsyncSession) -> None:
    """Verify contradicting claims are identified and persisted."""
    s_repo = SessionRepository(db_session)
    claim_repo = ClaimRepository(db_session)
    contra_repo = ContradictionRepository(db_session)

    session = await s_repo.create(
        question="What is the commercial release date of quantum batteries?"
    )

    c1 = await claim_repo.create(
        session_id=session.id,
        claim_text="Quantum batteries will enter consumer markets in 2026.",
        subject="Quantum batteries",
        predicate="market_entry",
        obj="2026",
    )
    c2 = await claim_repo.create(
        session_id=session.id,
        claim_text="Quantum batteries will not be commercially viable before 2035.",
        subject="Quantum batteries",
        predicate="market_entry",
        obj="2035",
    )
    await db_session.commit()

    detector = ContradictionDetector(session_id=session.id)

    mock_response = """{
      "contradicts": true,
      "severity": "high",
      "explanation": "Claim A predicts commercial entry in 2026 whereas Claim B states viability not before 2035."
    }"""

    with patch(
        "app.services.contradiction_detector.llm_router.generate",
        new_callable=AsyncMock,
    ) as mock_gen:
        mock_gen.return_value = mock_response

        contradictions = await detector.detect_contradictions(db=db_session)
        await db_session.commit()

        assert len(contradictions) == 1
        assert contradictions[0].severity == "high"

        db_items = await contra_repo.get_by_session(session.id)
        assert len(db_items) == 1
        assert db_items[0].claim_1_id == c1.id
        assert db_items[0].claim_2_id == c2.id
