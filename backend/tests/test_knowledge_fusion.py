"""Tests for Knowledge Fusion (IKF) entity and edge construction."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import (
    ClaimRepository,
    KnowledgeRepository,
    SessionRepository,
)
from app.services.knowledge_fusion import KnowledgeFusion


@pytest.mark.asyncio
async def test_knowledge_fusion_nodes_and_edges(db_session: AsyncSession) -> None:
    """Verify entity nodes and relational edges are created and deduplicated."""
    s_repo = SessionRepository(db_session)
    claim_repo = ClaimRepository(db_session)
    know_repo = KnowledgeRepository(db_session)

    session = await s_repo.create(
        question="How do solid state batteries compare to lithium ion?"
    )

    c1 = await claim_repo.create(
        session_id=session.id,
        claim_text="Solid-state batteries offer higher energy density than lithium-ion.",
        subject="Solid-state batteries",
        predicate="surpasses",
        obj="Lithium-ion",
        confidence="high",
    )
    c2 = await claim_repo.create(
        session_id=session.id,
        claim_text="Solid-state batteries use ceramic electrolytes.",
        subject="Solid-state batteries",
        predicate="contains",
        obj="Ceramic electrolytes",
        confidence="medium",
    )
    await db_session.commit()

    fusion = KnowledgeFusion(session_id=session.id)
    new_nodes, new_edges = await fusion.fuse_claims([c1, c2], db=db_session)
    await db_session.commit()

    nodes, edges = await know_repo.get_graph(session.id)

    # "Solid-state batteries" should be deduped into a single node
    entities = [n.entity.lower() for n in nodes]
    assert "solid-state batteries" in entities
    assert "lithium-ion" in entities
    assert "ceramic electrolytes" in entities
    assert len(nodes) == 3
    assert len(edges) == 2
