"""Tests for ReportGenerator final synthesis and citation structure."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import ClaimRepository, SessionRepository, SourceRepository
from app.services.report_generator import ReportGenerator


@pytest.mark.asyncio
async def test_report_generation(db_session: AsyncSession) -> None:
    """Verify report includes executive summary, evidence table, citations and metadata."""
    s_repo = SessionRepository(db_session)
    src_repo = SourceRepository(db_session)
    claim_repo = ClaimRepository(db_session)

    session = await s_repo.create(
        question="What are the main breakthroughs in fusion energy?"
    )
    source = await src_repo.create(
        session_id=session.id,
        url="https://nature.com/fusion-ignition",
        title="National Ignition Facility",
        content="NIF achieved net energy gain Q > 1.",
        credibility_score=0.95,
    )
    claim = await claim_repo.create(
        session_id=session.id,
        claim_text="NIF achieved net energy gain Q > 1.",
        confidence="high",
    )
    await claim_repo.link_source(claim.id, source.id)
    await db_session.commit()

    generator = ReportGenerator(session_id=session.id)

    mock_llm_json = """{
      "executive_summary": "Fusion energy achieved historical net energy gain at NIF.",
      "key_findings": ["Net energy gain demonstrated under laser inertial confinement."],
      "unknowns": ["Engineering scalability for continuous grid supply."]
    }"""

    with patch(
        "app.services.report_generator.llm_router.generate", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = mock_llm_json

        report = await generator.generate_report(db=db_session)
        await db_session.commit()

        assert "executive_summary" in report
        assert "Fusion energy" in report["executive_summary"]
        assert len(report["citations"]) == 1
        assert report["citations"][0]["url"] == "https://nature.com/fusion-ignition"
        assert len(report["evidence_table"]) == 1
        assert report["metadata"]["total_sources"] == 1
