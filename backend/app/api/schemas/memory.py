"""Pydantic schemas for the long-term memory API (V2 2.1)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MemoryItemModel(BaseModel):
    """One durable memory item, with the recall scores when it came from a search."""

    id: str
    kind: str
    key: str
    text: str
    payload: dict[str, Any] = {}
    importance: float
    confidence: float
    hits: int = 0
    embedded: bool = False
    embedding_model: str | None = None
    source_session_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_used_at: datetime | None = None
    recall: dict[str, float] | None = None


class MemoryListResponse(BaseModel):
    """A page of stored knowledge."""

    total: int
    items: list[MemoryItemModel]


class MemoryStatsResponse(BaseModel):
    """Store-level view: size, composition, decay and the forgetting policy."""

    total: int
    kinds: dict[str, int]
    embedded: int
    provider: str
    mean_weight: float
    max_items: int
    half_life_days: int


class MemoryPruneResponse(BaseModel):
    """What forgetting actually removed, so pruning is never a silent deletion."""

    removed_decayed: int
    removed_overflow: int


class MemoryProvenanceModel(BaseModel):
    """Where a remembered item came from.

    Provenance is not optional decoration: knowledge with no traceable origin cannot be
    audited, corrected or trusted in a later report.
    """

    session_id: str | None = None
    learned_in_session: str | None = None
    created_at: str | None = None
    last_verified_at: str | None = None
    status: str | None = None
    sources: list[str] = []


class MemoryVersionModel(BaseModel):
    """One observation of a remembered fact (V2 2.12)."""

    value: str = ""
    text: str = ""
    valid_from: int | None = None
    valid_to: int | None = None
    precision: str = "unknown"
    session_id: str | None = None
    claim_id: str | None = None
    sources: list[str] = []
    confidence: float = 0.6
    recorded_at: str | None = None
    status: str = "active"


class MemoryConflictItem(BaseModel):
    """A remembered fact with history: current reading, superseded readings, conflicts."""

    id: str
    key: str
    text: str
    subject: str | None = None
    predicate: str | None = None
    status: str
    conflicts: int = 0
    sources: list[str] = []
    versions: list[MemoryVersionModel] = []
    confirmation_count: int = 0
    importance: float = 0.5
    confidence: float = 0.6
    provenance: MemoryProvenanceModel = Field(default_factory=MemoryProvenanceModel)


class MemoryConflictsResponse(BaseModel):
    """Conflicting or versioned memories, plus how many of each status exist."""

    total: int
    status_counts: dict[str, int] = {}
    items: list[MemoryConflictItem]


class MemorySessionResponse(BaseModel):
    """Everything one session contributed to memory, with provenance."""

    session_id: str
    total: int
    items: list[dict[str, Any]]


class MemoryPromoteRequest(BaseModel):
    """Re-promote a finished session's durable knowledge into memory."""

    session_id: str = Field(min_length=1)
    max_claims: int = Field(default=25, ge=1, le=200)
    max_sources: int = Field(default=10, ge=1, le=100)


class MemoryPromoteResponse(BaseModel):
    """What promotion stored, so the operation is never a silent write."""

    session_id: str
    stored: dict[str, int] = {}
    updates: dict[str, int] = {}
    reason: str | None = None
