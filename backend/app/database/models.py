"""SQLAlchemy 2.0 ORM Models for Research Agent."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    """Generate string UUID."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Base declarative class for all models."""


# Use JSON type that falls back to standard JSON on SQLite and JSONB on PostgreSQL
JsonType = JSON().with_variant(JSONB, "postgresql")


class User(Base):
    """User entity for API key tracking."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    api_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    sessions: Mapped[list["ResearchSession"]] = relationship(
        "ResearchSession", back_populates="user", cascade="all, delete-orphan"
    )


class ResearchSession(Base):
    """Core research session tracking state, loop progression and report output."""

    __tablename__ = "research_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[str] = mapped_column(String(20), default="standard", nullable=False)
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    geographic_scope: Mapped[str] = mapped_column(
        String(100), default="global", nullable=False
    )
    time_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    max_research_time_minutes: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False
    )
    min_sources_required: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False
    )
    output_format: Mapped[str] = mapped_column(
        String(50), default="report", nullable=False
    )

    # State tracking: initializing, running, completed, error, stopped
    status: Mapped[str] = mapped_column(
        String(50), default="initializing", nullable=False, index=True
    )
    current_iteration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Final compiled report data (JSONB)
    report_data: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="sessions")
    sources: Mapped[list["Source"]] = relationship(
        "Source", back_populates="session", cascade="all, delete-orphan"
    )
    claims: Mapped[list["Claim"]] = relationship(
        "Claim", back_populates="session", cascade="all, delete-orphan"
    )
    nodes: Mapped[list["KnowledgeNode"]] = relationship(
        "KnowledgeNode", back_populates="session", cascade="all, delete-orphan"
    )
    edges: Mapped[list["KnowledgeEdge"]] = relationship(
        "KnowledgeEdge", back_populates="session", cascade="all, delete-orphan"
    )
    actions: Mapped[list["ResearchAction"]] = relationship(
        "ResearchAction", back_populates="session", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["Decision"]] = relationship(
        "Decision", back_populates="session", cascade="all, delete-orphan"
    )
    contradictions: Mapped[list["Contradiction"]] = relationship(
        "Contradiction", back_populates="session", cascade="all, delete-orphan"
    )
    events: Mapped[list["SessionEvent"]] = relationship(
        "SessionEvent", back_populates="session", cascade="all, delete-orphan"
    )
    transitions: Mapped[list["ResearchTransition"]] = relationship(
        "ResearchTransition", back_populates="session", cascade="all, delete-orphan"
    )
    rl_predictions: Mapped[list["RLPrediction"]] = relationship(
        "RLPrediction", back_populates="session", cascade="all, delete-orphan"
    )


class SessionEvent(Base):
    """Durable progress event log for a session.

    Live updates only exist on the WebSocket, so a finished investigation used to
    replay as an empty activity feed. Every broadcast is appended here first, which
    gives the UI the same timeline whether the run is live or long over.
    """

    __tablename__ = "session_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Per-session ascending sequence: the replay cursor for clients.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    iteration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped["ResearchSession"] = relationship(
        "ResearchSession", back_populates="events"
    )


class Source(Base):
    """External source material fetched via search."""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(50), default="article", nullable=False
    )
    credibility_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped["ResearchSession"] = relationship(
        "ResearchSession", back_populates="sources"
    )
    claim_links: Mapped[list["ClaimSource"]] = relationship(
        "ClaimSource", back_populates="source", cascade="all, delete-orphan"
    )


class Claim(Base):
    """Factual atomic claim extracted from sources."""

    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    predicate: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    object: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(
        String(50), default="medium", nullable=False
    )  # high, medium, low
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped["ResearchSession"] = relationship(
        "ResearchSession", back_populates="claims"
    )
    source_links: Mapped[list["ClaimSource"]] = relationship(
        "ClaimSource", back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimSource(Base):
    """Many-to-many relationship linking claims to their supporting/refuting sources."""

    __tablename__ = "claim_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    claim_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    support_type: Mapped[str] = mapped_column(
        String(50), default="supports", nullable=False
    )  # supports, refutes, neutral
    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)

    claim: Mapped["Claim"] = relationship("Claim", back_populates="source_links")
    source: Mapped["Source"] = relationship("Source", back_populates="claim_links")


class KnowledgeNode(Base):
    """Entity node in the session knowledge graph (IKF)."""

    __tablename__ = "knowledge_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(
        String(100), default="concept", nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped["ResearchSession"] = relationship(
        "ResearchSession", back_populates="nodes"
    )


class KnowledgeEdge(Base):
    """Relationship edge connecting two entities in the knowledge graph."""

    __tablename__ = "knowledge_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    strength: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped["ResearchSession"] = relationship(
        "ResearchSession", back_populates="edges"
    )
    source_node: Mapped["KnowledgeNode"] = relationship(
        "KnowledgeNode", foreign_keys=[source_node_id]
    )
    target_node: Mapped["KnowledgeNode"] = relationship(
        "KnowledgeNode", foreign_keys=[target_node_id]
    )


class MemoryItem(Base):
    """One durable fact carried between research sessions (V2 2.1).

    Everything a run learns that outlives the run lives here: questions asked, claims
    and entities it established, conclusions it reached, the strategies that worked,
    the queries that failed, and the constraints the user stated. Retrieval scores on
    lexical overlap plus an optional embedding, weighted by importance and decayed by
    idleness, so knowledge that keeps proving useful stays and dead weight is forgotten.

    The vector is stored inline as JSON rather than in a vector index: this project
    deliberately dropped pgvector, and at this scale scoring in Python over a capped
    candidate set is both fast enough and dependency-free.
    """

    __tablename__ = "memory_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    #: Stable dedupe key derived from the content, so re-learning updates instead of
    #: duplicating. Indexed because every write looks the item up first.
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JsonType, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    #: Times this item was recalled. Reuse is the signal that it deserves to stay.
    hits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


Index("idx_memory_kind_key", MemoryItem.kind, MemoryItem.key)


class EdgeProvenance(Base):
    """Where a knowledge edge came from: sources, claims, independence, evidence.

    Kept as its own table rather than columns on ``knowledge_edges`` so an existing
    database picks it up through ``create_all`` with no ALTER — the live development
    DB is a plain SQLite file, not a migration-managed cluster.
    """

    __tablename__ = "edge_provenances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edge_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_edges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Source ids, per-source domains, support breakdown and contributing claim ids.
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    session: Mapped["ResearchSession"] = relationship("ResearchSession")


Index("idx_edge_provenance_session_edge", EdgeProvenance.session_id, EdgeProvenance.edge_id)


class ResearchAction(Base):
    """History of search/scrape/verify actions taken during a research session."""

    __tablename__ = "research_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_claims_extracted: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    information_gain: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped["ResearchSession"] = relationship(
        "ResearchSession", back_populates="actions"
    )


class Decision(Base):
    """JEV Decision logging for analysis and future RL training."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_state_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JsonType, nullable=True
    )
    available_actions: Mapped[list[str] | None] = mapped_column(JsonType, nullable=True)
    selected_action: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    reward_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped["ResearchSession"] = relationship(
        "ResearchSession", back_populates="decisions"
    )


class Contradiction(Base):
    """Contradiction pair flagged between two claims."""

    __tablename__ = "contradictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_1_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_2_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        String(50), default="medium", nullable=False
    )  # low, medium, high
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped["ResearchSession"] = relationship(
        "ResearchSession", back_populates="contradictions"
    )
    claim_1: Mapped["Claim"] = relationship("Claim", foreign_keys=[claim_1_id])
    claim_2: Mapped["Claim"] = relationship("Claim", foreign_keys=[claim_2_id])


class ResearchTransition(Base):
    """One learnable research step: state -> action -> observation -> reward -> next state.

    V1 recorded decisions (a state snapshot, the chosen action, a reward signal) but
    never joined a decision to what the action actually produced, so nothing in the
    database was a training transition. This table is that join. The reward is stored
    both as a scalar (for learning) and component-by-component (so the evaluation page
    can explain it), and the states are compact aggregates — never raw source text.
    """

    __tablename__ = "research_transitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    state_before: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    state_after: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    #: sha256 of the canonical state JSON, so duplicates and repeat contexts are
    #: visible without parsing the payload.
    state_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    state_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action_parameters: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    observation: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    reward: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    #: Named reward components (V2 2.4); the scalar above is their signed sum.
    reward_components: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    information_gain: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    coverage_before: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    coverage_after: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    contradictions_before: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contradictions_after: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sources_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    claims_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    execution_time: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    #: JEV for every production run in V2; RL_SHADOW only if a shadow policy ever
    #: drives a run, OTHER for imported data.
    policy_source: Mapped[str] = mapped_column(
        String(20), default="JEV", nullable=False, index=True
    )
    done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped["ResearchSession"] = relationship(
        "ResearchSession", back_populates="transitions"
    )


Index(
    "idx_transition_session_iteration",
    ResearchTransition.session_id,
    ResearchTransition.iteration,
)


class RLPolicy(Base):
    """A learned offline policy, stored as its full JSON payload.

    The payload *is* the model (a tabular estimate), which is deliberate: it can be
    inspected, diffed and rolled back without a binary artifact, and replacing the
    algorithm later only changes what goes in this column.
    """

    __tablename__ = "rl_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), default="1.0", nullable=False)
    algorithm: Mapped[str] = mapped_column(String(60), nullable=False)
    #: Identity of the data this was trained on; a policy must never be applied to a
    #: dataset it did not see, so both are recorded and compared.
    dataset_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dataset_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    baseline: Mapped[str] = mapped_column(String(20), default="JEV", nullable=False)
    samples: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    predictions: Mapped[list["RLPrediction"]] = relationship("RLPrediction")


class RLPrediction(Base):
    """What the learned policy would have done, next to what JEV actually did.

    Written during a live run but never executed: this table is the comparison record
    that makes a future policy swap defensible instead of a leap of faith.
    """

    __tablename__ = "rl_predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("rl_policies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    state_key: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    jev_action: Mapped[str] = mapped_column(String(50), nullable=False)
    jev_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    jev_expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    rl_action: Mapped[str] = mapped_column(String(50), nullable=False)
    rl_expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    rl_scores: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    rl_support: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Reward the JEV action actually earned on the following iteration, once known.
    actual_reward: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_rl_reward: Mapped[float | None] = mapped_column(Float, nullable=True)
    disagreement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped["ResearchSession"] = relationship(
        "ResearchSession", back_populates="rl_predictions"
    )


Index("idx_prediction_session_iteration", RLPrediction.session_id, RLPrediction.iteration)


class EvaluationRun(Base):
    """One offline JEV-vs-RL evaluation over a stored dataset."""

    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    policy: Mapped[str] = mapped_column(String(40), nullable=False)
    baseline: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dataset_version: Mapped[str] = mapped_column(String(40), nullable=False)
    dataset_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    aggregate: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    comparison: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    notes: Mapped[list[str] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    results: Mapped[list["EvaluationResult"]] = relationship(
        "EvaluationResult", back_populates="run", cascade="all, delete-orphan"
    )


class EvaluationResult(Base):
    """A per-scope slice of an evaluation run: overall, per session, per action.

    Kept relational rather than buried in one JSON blob so the dashboard can query
    "how does RL do on VERIFY?" without loading every run ever recorded.
    """

    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    run: Mapped["EvaluationRun"] = relationship(
        "EvaluationRun", back_populates="results"
    )


# Index declarations
Index("idx_sessions_status", ResearchSession.status)
Index(
    "idx_sessions_user_created",
    ResearchSession.user_id,
    ResearchSession.created_at.desc(),
)
Index("idx_claims_subject_predicate", Claim.subject, Claim.predicate)
Index("idx_session_events_session_seq", SessionEvent.session_id, SessionEvent.seq)
