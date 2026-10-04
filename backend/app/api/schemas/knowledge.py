"""Pydantic schemas for the Knowledge Graph (nodes and edges)."""

from pydantic import BaseModel, ConfigDict


class KnowledgeNodeModel(BaseModel):
    """Entity node in knowledge graph."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    entity_type: str = "concept"
    description: str | None = None


class KnowledgeEdgeModel(BaseModel):
    """Relationship edge between nodes in knowledge graph."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    from_node: str
    to_node: str
    label: str | None = None
    strength: float = 0.7


class KnowledgeGraphResponse(BaseModel):
    """Graph response formatted for interactive vis-network rendering."""

    session_id: str
    nodes: list[KnowledgeNodeModel]
    edges: list[KnowledgeEdgeModel]
    total_nodes: int
    total_edges: int
