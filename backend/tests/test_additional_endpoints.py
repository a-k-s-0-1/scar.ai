"""Tests for knowledge, evidence, contradictions, and report endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import (
    ClaimRepository,
    ContradictionRepository,
    KnowledgeRepository,
    SessionRepository,
    SourceRepository,
)


@pytest.mark.asyncio
async def test_knowledge_graph_endpoint(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s_repo = SessionRepository(db_session)
    k_repo = KnowledgeRepository(db_session)

    session = await s_repo.create(question="How do solid state electrolytes function?")
    n1 = await k_repo.get_or_create_node(
        session.id, "Solid-state electrolyte", "concept"
    )
    n2 = await k_repo.get_or_create_node(session.id, "Ion conductivity", "property")
    await k_repo.add_edge(session.id, n1.id, n2.id, "exhibits", strength=0.85)
    await db_session.commit()

    headers = {"X-API-Key": "dev_api_key_jev_ikf_2026"}
    res = await client.get(f"/api/research/{session.id}/knowledge", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_nodes"] == 2
    assert data["total_edges"] == 1
    assert data["nodes"][0]["label"] in ("Solid-state electrolyte", "Ion conductivity")


@pytest.mark.asyncio
async def test_evidence_and_contradiction_endpoints(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s_repo = SessionRepository(db_session)
    src_repo = SourceRepository(db_session)
    claim_repo = ClaimRepository(db_session)
    contra_repo = ContradictionRepository(db_session)

    session = await s_repo.create(
        question="Evaluation of sodium-ion battery cycling stability."
    )
    src = await src_repo.create(
        session_id=session.id,
        url="https://nature.com/sodium-ion",
        title="Sodium Battery Paper",
        content="Sodium cells demonstrated 3000 cycles.",
        credibility_score=0.9,
    )
    c1 = await claim_repo.create(
        session_id=session.id,
        claim_text="Sodium cells demonstrated 3000 cycles.",
        subject="Sodium cells",
        predicate="demonstrated",
        obj="3000 cycles",
        confidence="high",
    )
    c2 = await claim_repo.create(
        session_id=session.id,
        claim_text="Sodium cells degrade rapidly under 500 cycles.",
        subject="Sodium cells",
        predicate="degrade",
        obj="under 500 cycles",
        confidence="medium",
    )
    await claim_repo.link_source(c1.id, src.id)
    await contra_repo.create(
        session.id, c1.id, c2.id, severity="high", resolution_note="Cycle disparity"
    )
    await db_session.commit()

    headers = {"X-API-Key": "dev_api_key_jev_ikf_2026"}

    # Evidence
    ev_res = await client.get(f"/api/research/{session.id}/evidence", headers=headers)
    assert ev_res.status_code == 200
    ev_data = ev_res.json()
    assert ev_data["total_claims"] == 2

    # Contradictions
    contra_res = await client.get(
        f"/api/research/{session.id}/contradictions", headers=headers
    )
    assert contra_res.status_code == 200
    contra_data = contra_res.json()
    assert len(contra_data) == 1
    assert contra_data[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_session_response_exposes_depth_profile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Iteration caps and duration estimates come from the shared depth profile."""
    s_repo = SessionRepository(db_session)
    session = await s_repo.create(
        question="Deep dive on grid-scale storage economics.", depth="deep"
    )
    await db_session.commit()

    res = await client.get(
        f"/api/research/{session.id}",
        headers={"X-API-Key": "dev_api_key_jev_ikf_2026"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["max_iterations"] == 8
    assert body["estimated_time_seconds"] == 480


@pytest.mark.asyncio
async def test_report_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    s_repo = SessionRepository(db_session)
    session = await s_repo.create(
        question="Commercial status of synthetic aviation fuels."
    )
    await s_repo.save_report(
        session.id,
        {
            "session_id": session.id,
            "executive_summary": "Synthetic aviation fuel demonstrates decarbonization pathway.",
            "key_findings": ["Drop-in replacement verified."],
            "evidence_table": [],
            "contradictions": [],
            "unknowns": ["Feedstock scaling limitations."],
            "citations": [],
        },
    )
    await db_session.commit()

    headers = {"X-API-Key": "dev_api_key_jev_ikf_2026"}
    res = await client.get(f"/api/research/{session.id}/report", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "Synthetic aviation fuel" in data["executive_summary"]
