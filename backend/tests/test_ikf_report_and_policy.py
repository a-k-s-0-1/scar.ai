"""Tests for the IKF 2.0 surfaces: report evidence/versioning and JEV target selection.

The orchestrator helpers decide whether an iteration gets spent, so they are pinned
here rather than left to the offline suite's integration tests alone.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Contradiction
from app.database.repository import ClaimRepository, SessionRepository, SourceRepository
from app.services.ikf import (
    ClaimVersion,
    EvidenceScore,
    KnowledgeIndex,
    build_version_groups,
    extract_validity_window,
)
from app.services.report_generator import ReportGenerator
from app.services.research_orchestrator import ResearchOrchestrator

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def _version(claim_id: str, value: str, year: int, predicate: str = "share_of") -> ClaimVersion:
    return ClaimVersion(
        claim_id=claim_id,
        text=f"share was {value} in {year}",
        subject="solid-state battery market",
        predicate=predicate,
        value=value,
        window=extract_validity_window(str(year)),
        strength=0.5,
    )


def _score(claim_id: str, strength: float) -> EvidenceScore:
    return EvidenceScore(
        claim_id=claim_id,
        strength=strength,
        band="high" if strength >= 0.6 else "medium" if strength >= 0.3 else "low",
    )


# ─── JEV target selection ────────────────────────────────────────────────────


def _pair(first: str, second: str, severity: str = "medium") -> Contradiction:
    return Contradiction(
        session_id="s",
        claim_1_id=first,
        claim_2_id=second,
        severity=severity,
    )


def test_verify_target_picks_the_weaker_evidenced_claim() -> None:
    """A claim already backed by strong evidence will not move; the thin one can."""
    index = KnowledgeIndex(session_id="s", evidence={"strong": _score("strong", 0.9)})
    contradictions = [_pair("strong", "thin")]

    assert ResearchOrchestrator._verify_target_id(contradictions, index) == "thin"

    index.evidence["thin"] = _score("thin", 0.95)
    assert ResearchOrchestrator._verify_target_id(contradictions, index) == "strong"


def test_verify_target_falls_back_to_v1_behaviour_without_an_index() -> None:
    contradictions = [_pair("first", "second")]
    assert ResearchOrchestrator._verify_target_id(contradictions, None) == "first"


def test_temporal_versions_are_dropped_but_real_conflicts_are_kept() -> None:
    """A fact moving over time is not a disagreement worth a verification search."""
    versioned = build_version_groups([_version("a", "65%", 2024), _version("b", "71%", 2026)])
    conflicted = build_version_groups([_version("c", "40%", 2026), _version("d", "80%", 2026)])
    index = KnowledgeIndex(session_id="s", groups=[*versioned, *conflicted])

    contradictions = [_pair("a", "b"), _pair("c", "d")]

    kept, suppressed = ResearchOrchestrator._drop_temporal_versions(contradictions, index)

    assert suppressed == 1
    assert [(c.claim_1_id, c.claim_2_id) for c in kept] == [("c", "d")]


def test_without_an_index_nothing_is_suppressed() -> None:
    contradictions = [_pair("a", "b")]
    kept, suppressed = ResearchOrchestrator._drop_temporal_versions(contradictions, None)
    assert kept == contradictions and suppressed == 0


# ─── report surfaces ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_report_exposes_evidence_bands_and_a_version_timeline(
    db_session: AsyncSession,
) -> None:
    """The report must carry the scored evidence and the facts that moved."""
    sessions = SessionRepository(db_session)
    sources = SourceRepository(db_session)
    claims = ClaimRepository(db_session)

    session = await sessions.create(question="How big is the solid-state market?")
    strong = await sources.create(
        session_id=session.id,
        url="https://energy.gov/review",
        title="Review",
        content="...",
        source_type="government",
        credibility_score=0.95,
        published_at=NOW,
    )
    weak = await sources.create(
        session_id=session.id,
        url="https://forum.example.com/x",
        title="Thread",
        content="...",
        source_type="forum",
        credibility_score=0.25,
        published_at=NOW.replace(year=2024),
    )

    early = await claims.create(
        session_id=session.id,
        claim_text="Solid-state share was 4% in 2024.",
        subject="Solid-state market",
        predicate="share_of",
        obj="4%",
        confidence="high",
    )
    latest = await claims.create(
        session_id=session.id,
        claim_text="Solid-state share is 9% in 2026.",
        subject="Solid-State Market Inc.",
        predicate="share_of",
        obj="9%",
        confidence="high",
    )
    await claims.link_source(early.id, strong.id)
    await claims.link_source(latest.id, weak.id)
    await db_session.commit()

    generator = ReportGenerator(session_id=session.id)
    with patch(
        "app.services.report_generator.llm_router.generate", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = '{"executive_summary": "Share is rising.", "key_findings": ["x"]}'
        report = await generator.generate_report(db=db_session)

    table = report["evidence_table"]
    assert len(table) == 2
    for item in table:
        assert item["evidence_band"] in {"high", "medium", "low"}
        assert item["evidence_strength"] is not None
        # The component breakdown is what makes the score explainable.
        assert set(item["evidence_components"]) == {
            "source_quality",
            "independent_support",
            "recency",
            "agreement",
            "extraction_confidence",
        }

    best = next(item for item in table if item["claim_id"] == early.id)
    worst = next(item for item in table if item["claim_id"] == latest.id)
    assert best["evidence_strength"] > worst["evidence_strength"]
    assert best["independent_sources"] == 1

    # Both spellings of the subject resolve together, so the two readings are one
    # fact moving rather than two unrelated claims.
    versions = report["versions"]
    assert len(versions) == 1
    assert versions[0]["status"] == "versioned"
    assert versions[0]["span"] == {"from": 2024, "to": 2026}
    assert versions[0]["conflicts"] == []

    assert report["contradictions"] == []
    assert report["metadata"]["versions"]["versioned"] == 1
    assert report["metadata"]["evidence"]["claims"] == 2


@pytest.mark.asyncio
async def test_fallback_summary_leads_with_the_best_evidenced_claim(
    db_session: AsyncSession,
) -> None:
    """With no model available, the report still ranks by evidence, not by tone."""
    sessions = SessionRepository(db_session)
    sources = SourceRepository(db_session)
    claims = ClaimRepository(db_session)

    session = await sessions.create(question="Which approach wins?")
    good = await sources.create(
        session_id=session.id,
        url="https://gov.example.com/a",
        title="A",
        content="...",
        source_type="government",
        credibility_score=1.0,
        published_at=NOW,
    )
    weak_claim = await claims.create(
        session_id=session.id,
        claim_text="An unsourced assertion.",
        subject="Thing",
        predicate="is",
        obj="fine",
        confidence="high",
    )
    strong_claim = await claims.create(
        session_id=session.id,
        claim_text="A well-evidenced finding.",
        subject="Other",
        predicate="is",
        obj="real",
        confidence="low",
    )
    await claims.link_source(strong_claim.id, good.id)
    await db_session.commit()

    generator = ReportGenerator(session_id=session.id)
    with patch(
        "app.services.report_generator.llm_router.generate", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.side_effect = RuntimeError("no provider available")
        report = await generator.generate_report(db=db_session)

    assert report["metadata"]["synthesis"] == "fallback"
    assert "evidence strength" in report["executive_summary"]
    # The low-confidence-but-evidenced claim outranks the confident unsourced one,
    # which is the whole point of scoring evidence instead of trusting the extractor.
    # Both fit in the five-slot findings list, so it is the order that carries this.
    assert report["key_findings"][0] == strong_claim.claim
    assert report["key_findings"][-1] == weak_claim.claim
