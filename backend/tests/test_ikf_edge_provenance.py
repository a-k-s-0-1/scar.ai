"""Tests for IKF 2.0 wiring into knowledge fusion: canonical entities, edge strength, provenance."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import (
    ClaimRepository,
    KnowledgeRepository,
    SessionRepository,
    SourceRepository,
)
from app.services.ikf import (
    EntityResolver,
    EvidenceInput,
    SourceRef,
    edge_provenance,
    merge_provenance,
    score_claim,
)
from app.services.knowledge_fusion import KnowledgeFusion


def _ref(source_id: str, url: str, support_type: str = "supports") -> SourceRef:
    return SourceRef(source_id=source_id, url=url, support_type=support_type)


# ─── provenance payloads ─────────────────────────────────────────────────────


def test_merge_unions_sources_and_recomputes_independence() -> None:
    """A second assertion of the same edge must widen the evidence, not replace it."""
    first = edge_provenance(
        [_ref("s1", "https://wire.example.com/a")], ["claim-1"]
    )
    second = edge_provenance(
        [
            _ref("s2", "https://second.example.com/b"),
            _ref("s3", "https://third.example.com/c"),
        ],
        ["claim-2"],
    )

    merged = merge_provenance(first, second)

    assert merged["source_ids"] == ["s1", "s2", "s3"]
    assert merged["claim_ids"] == ["claim-1", "claim-2"]
    # Two of the three domains are distinct publishers.
    assert merged["independent_sources"] == 3
    assert merged["supports"] == 3


def test_merge_counts_one_source_once_even_if_it_repeats() -> None:
    payload = edge_provenance([_ref("s1", "https://a.example.com/x")], ["c1"])
    merged = merge_provenance(payload, payload)

    assert merged["source_ids"] == ["s1"]
    assert merged["total_sources"] == 1
    assert merged["supports"] == 1


def test_merge_lets_a_refutation_win_over_support() -> None:
    """A source that refutes anywhere must not also be counted as supporting."""
    supporting = edge_provenance([_ref("s1", "https://a.example.com/x")], ["c1"])
    refuting = edge_provenance(
        [_ref("s1", "https://a.example.com/x", support_type="refutes")], ["c2"]
    )

    merged = merge_provenance(supporting, refuting)

    assert merged["supports"] == 0
    assert merged["refutes"] == 1
    assert merged["support_weight"] == 0.0


def test_merge_from_nothing_keeps_the_single_payload() -> None:
    payload = edge_provenance([_ref("s1", "https://a.example.com/x")], ["c1"])
    assert merge_provenance(None, payload) == payload


# ─── fusion wiring ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fusion_resolves_entities_and_records_provenance(
    db_session: AsyncSession,
) -> None:
    """One canonical node per entity, with edge strength and provenance from evidence."""
    sessions = SessionRepository(db_session)
    sources = SourceRepository(db_session)
    claims = ClaimRepository(db_session)
    graph = KnowledgeRepository(db_session)

    session = await sessions.create(question="Who leads enterprise AI adoption?")

    primary = await sources.create(
        session_id=session.id,
        url="https://analyst.example.com/report",
        title="Adoption report",
        content="...",
        source_type="report",
        credibility_score=0.9,
    )

    first = await claims.create(
        session_id=session.id,
        claim_text="OpenAI leads enterprise AI adoption.",
        subject="OpenAI Inc.",
        predicate="leads",
        obj="enterprise AI adoption",
        confidence="high",
    )
    second = await claims.create(
        session_id=session.id,
        claim_text="OpenAI, Inc. leads enterprise AI adoption.",
        subject="OpenAI, Inc.",
        predicate="leads",
        obj="enterprise AI adoption",
        confidence="high",
    )
    await claims.link_source(first.id, primary.id)
    await claims.link_source(second.id, primary.id)
    await db_session.commit()

    # Explicitly loaded links, because the loop hands fusion detached claims.
    links = await claims.get_links_for_claims([first.id, second.id])
    evidence = {
        claim.id: score_claim(
            EvidenceInput(
                claim_id=claim.id,
                refs=[_ref(primary.id, primary.url, "supports")],
                extraction_confidence="high",
            )
        )
        for claim in (first, second)
    }

    fusion = KnowledgeFusion(session_id=session.id)
    new_nodes, new_edges = await fusion.fuse_claims(
        [first, second],
        db=db_session,
        resolver=EntityResolver(),
        evidence=evidence,
    )
    await db_session.commit()

    nodes, edges = await graph.get_graph(session.id)

    # "OpenAI Inc." and "OpenAI, Inc." are the same organisation: one node, one edge.
    assert new_nodes == 2
    assert new_edges == 1
    assert [node.entity for node in nodes] == ["OpenAI Inc.", "enterprise AI adoption"]

    assert len(edges) == 1
    edge = edges[0]
    assert edge.strength == pytest.approx(evidence[first.id].strength, abs=1e-6)

    provenance = await graph.get_edge_provenance(session.id)
    assert edge.id in provenance
    payload = provenance[edge.id]
    assert payload["claim_ids"] == [first.id, second.id]
    assert payload["independent_sources"] == 1
    assert payload["supports"] == 1

    assert links[first.id][0].source_id == primary.id


@pytest.mark.asyncio
async def test_fusion_skips_provenance_for_unsourced_claims(
    db_session: AsyncSession,
) -> None:
    """An edge with no evidence must look unsupported, not 'recorded but empty'."""
    sessions = SessionRepository(db_session)
    claims = ClaimRepository(db_session)
    graph = KnowledgeRepository(db_session)

    session = await sessions.create(question="Uncited question?")
    claim = await claims.create(
        session_id=session.id,
        claim_text="A claim nobody sourced.",
        subject="Subject",
        predicate="relates_to",
        obj="Object",
        confidence="low",
    )
    await db_session.commit()

    fusion = KnowledgeFusion(session_id=session.id)
    new_nodes, new_edges = await fusion.fuse_claims([claim], db=db_session)
    await db_session.commit()

    _, edges = await graph.get_graph(session.id)
    assert new_nodes == 2 and new_edges == 1
    assert edges[0].strength == 0.5  # the confidence fallback, no evidence supplied
    assert await graph.get_edge_provenance(session.id) == {}
