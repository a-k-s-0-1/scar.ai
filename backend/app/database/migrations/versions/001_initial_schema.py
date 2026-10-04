"""001_initial_schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-09-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("api_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_api_key", "users", ["api_key"])

    # Research Sessions
    op.create_table(
        "research_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "depth", sa.String(length=20), nullable=False, server_default="standard"
        ),
        sa.Column("domain", sa.String(length=100), nullable=True),
        sa.Column(
            "geographic_scope",
            sa.String(length=100),
            nullable=False,
            server_default="global",
        ),
        sa.Column("time_range", sa.String(length=100), nullable=True),
        sa.Column(
            "max_research_time_minutes",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "min_sources_required", sa.Integer(), nullable=False, server_default="10"
        ),
        sa.Column(
            "output_format",
            sa.String(length=50),
            nullable=False,
            server_default="report",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="initializing",
        ),
        sa.Column(
            "current_iteration", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("report_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_sessions_status", "research_sessions", ["status"])
    op.create_index(
        "idx_sessions_user_created", "research_sessions", ["user_id", "created_at"]
    )

    # Sources
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("research_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "source_type",
            sa.String(length=50),
            nullable=False,
            server_default="article",
        ),
        sa.Column(
            "credibility_score", sa.Float(), nullable=False, server_default="0.5"
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_sources_session", "sources", ["session_id"])
    op.create_index("idx_sources_hash", "sources", ["content_hash"])

    # Claims
    op.create_table(
        "claims",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("research_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("predicate", sa.String(length=255), nullable=True),
        sa.Column("object", sa.Text(), nullable=True),
        sa.Column(
            "confidence", sa.String(length=50), nullable=False, server_default="medium"
        ),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="active"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_claims_session", "claims", ["session_id"])
    op.create_index("idx_claims_subject_predicate", "claims", ["subject", "predicate"])

    # Claim Sources
    op.create_table(
        "claim_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "claim_id",
            sa.String(length=36),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "support_type",
            sa.String(length=50),
            nullable=False,
            server_default="supports",
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.8"),
    )
    op.create_index("idx_claim_sources_claim", "claim_sources", ["claim_id"])
    op.create_index("idx_claim_sources_source", "claim_sources", ["source_id"])

    # Knowledge Nodes
    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("research_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column(
            "entity_type",
            sa.String(length=100),
            nullable=False,
            server_default="concept",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_nodes_session", "knowledge_nodes", ["session_id"])

    # Knowledge Edges
    op.create_table(
        "knowledge_edges",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("research_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_node_id",
            sa.String(length=36),
            sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_node_id",
            sa.String(length=36),
            sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(length=100), nullable=True),
        sa.Column("strength", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_edges_session", "knowledge_edges", ["session_id"])

    # Research Actions
    op.create_table(
        "research_actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("research_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("iteration_number", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("sources_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "new_claims_extracted", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("information_gain", sa.Float(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_actions_session", "research_actions", ["session_id"])

    # Decisions
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("research_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("iteration_number", sa.Integer(), nullable=False),
        sa.Column("knowledge_state_snapshot", sa.JSON(), nullable=True),
        sa.Column("available_actions", sa.JSON(), nullable=True),
        sa.Column("selected_action", sa.String(length=50), nullable=True),
        sa.Column("action_reasoning", sa.Text(), nullable=True),
        sa.Column("reward_signal", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_decisions_session", "decisions", ["session_id"])

    # Contradictions
    op.create_table(
        "contradictions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("research_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "claim_1_id",
            sa.String(length=36),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "claim_2_id",
            sa.String(length=36),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "severity", sa.String(length=50), nullable=False, server_default="medium"
        ),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_contradictions_session", "contradictions", ["session_id"])


def downgrade() -> None:
    op.drop_table("contradictions")
    op.drop_table("decisions")
    op.drop_table("research_actions")
    op.drop_table("knowledge_edges")
    op.drop_table("knowledge_nodes")
    op.drop_table("claim_sources")
    op.drop_table("claims")
    op.drop_table("sources")
    op.drop_table("research_sessions")
    op.drop_table("users")
