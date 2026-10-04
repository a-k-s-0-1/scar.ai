"""Knowledge Graph API routes."""

from fastapi import APIRouter

from app.api.dependencies import ApiKeyAuth, DbSession
from app.api.errors import SessionNotFoundError
from app.api.schemas.knowledge import (
    KnowledgeEdgeModel,
    KnowledgeGraphResponse,
    KnowledgeNodeModel,
)
from app.database.repository import KnowledgeRepository, SessionRepository

router = APIRouter(prefix="/api/research", tags=["Knowledge Graph"])


@router.get(
    "/{session_id}/knowledge",
    response_model=KnowledgeGraphResponse,
    summary="Get knowledge graph nodes and edges for vis-network",
)
async def get_knowledge_graph(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> KnowledgeGraphResponse:
    """Retrieve nodes and edges representing the synthesized knowledge graph."""
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError(session_id)

    know_repo = KnowledgeRepository(db)
    nodes, edges = await know_repo.get_graph(session_id)

    node_models = [
        KnowledgeNodeModel(
            id=n.id,
            label=n.entity,
            entity_type=n.entity_type,
            description=n.description,
        )
        for n in nodes
    ]

    edge_models = [
        KnowledgeEdgeModel(
            id=e.id,
            from_node=e.source_node_id,
            to_node=e.target_node_id,
            label=e.relationship_type,
            strength=e.strength,
        )
        for e in edges
    ]

    return KnowledgeGraphResponse(
        session_id=session_id,
        nodes=node_models,
        edges=edge_models,
        total_nodes=len(node_models),
        total_edges=len(edge_models),
    )
