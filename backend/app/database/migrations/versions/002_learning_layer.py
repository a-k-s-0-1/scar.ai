"""002_learning_layer

Adds the V2 offline-learning tables:

* ``research_transitions`` — one learnable ``state -> action -> observation -> reward
  -> next_state`` row per research iteration.
* ``rl_policies``          — stored offline policies (their full JSON payload *is* the
  model, so it can be inspected, diffed and rolled back).
* ``rl_predictions``       — what the offline policy would have done beside what JEV
  actually did. Never executed in V2.
* ``evaluation_runs`` / ``evaluation_results`` — offline JEV-vs-RL comparisons and
  their per-session / per-action slices.

These are new tables, not new columns, so ``Base.metadata.create_all`` picks them up on
an existing SQLite development file as well; this migration exists for the databases
that are migration-managed (PostgreSQL deployments, and CI that runs alembic).

Revision ID: 002_learning_layer
Revises: 001_initial_schema
Create Date: 2026-10-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_learning_layer"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── research_transitions ────────────────────────────────────────────────
    op.create_table(
        "research_transitions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("research_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("state_before", sa.JSON(), nullable=False),
        sa.Column("state_after", sa.JSON(), nullable=True),
        sa.Column("state_hash", sa.String(length=64), nullable=True),
        sa.Column("state_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("action_parameters", sa.JSON(), nullable=True),
        sa.Column("observation", sa.JSON(), nullable=True),
        sa.Column("reward", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reward_components", sa.JSON(), nullable=True),
        sa.Column("information_gain", sa.Float(), nullable=False, server_default="0"),
        sa.Column("coverage_before", sa.Float(), nullable=False, server_default="0"),
        sa.Column("coverage_after", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "contradictions_before", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "contradictions_after", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("sources_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claims_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_time", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "policy_source", sa.String(length=20), nullable=False, server_default="JEV"
        ),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_research_transitions_session_id",
        "research_transitions",
        ["session_id"],
    )
    op.create_index(
        "ix_research_transitions_state_hash",
        "research_transitions",
        ["state_hash"],
    )
    op.create_index(
        "ix_research_transitions_policy_source",
        "research_transitions",
        ["policy_source"],
    )
    op.create_index(
        "idx_transition_session_iteration",
        "research_transitions",
        ["session_id", "iteration"],
    )

    # ── rl_policies ─────────────────────────────────────────────────────────
    op.create_table(
        "rl_policies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False, server_default="1.0"),
        sa.Column("algorithm", sa.String(length=60), nullable=False),
        sa.Column("dataset_version", sa.String(length=40), nullable=True),
        sa.Column("dataset_hash", sa.String(length=64), nullable=True),
        sa.Column("baseline", sa.String(length=20), nullable=False, server_default="JEV"),
        sa.Column("samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rl_policies_name", "rl_policies", ["name"])
    op.create_index("ix_rl_policies_active", "rl_policies", ["active"])

    # ── rl_predictions ──────────────────────────────────────────────────────
    op.create_table(
        "rl_predictions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("research_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column(
            "policy_id",
            sa.String(length=36),
            sa.ForeignKey("rl_policies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("state_key", sa.String(length=255), nullable=False),
        sa.Column("state", sa.JSON(), nullable=True),
        sa.Column("jev_action", sa.String(length=50), nullable=False),
        sa.Column("jev_reasoning", sa.Text(), nullable=True),
        sa.Column("jev_expected_value", sa.Float(), nullable=True),
        sa.Column("rl_action", sa.String(length=50), nullable=False),
        sa.Column("rl_expected_value", sa.Float(), nullable=True),
        sa.Column("rl_scores", sa.JSON(), nullable=True),
        sa.Column("rl_support", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("actual_reward", sa.Float(), nullable=True),
        sa.Column("estimated_rl_reward", sa.Float(), nullable=True),
        sa.Column(
            "disagreement", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_rl_predictions_session_id", "rl_predictions", ["session_id"]
    )
    op.create_index("ix_rl_predictions_policy_id", "rl_predictions", ["policy_id"])
    op.create_index(
        "idx_prediction_session_iteration",
        "rl_predictions",
        ["session_id", "iteration"],
    )

    # ── evaluation_runs ─────────────────────────────────────────────────────
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("policy", sa.String(length=40), nullable=False),
        sa.Column("baseline", sa.String(length=40), nullable=True),
        sa.Column("dataset_version", sa.String(length=40), nullable=False),
        sa.Column("dataset_hash", sa.String(length=64), nullable=True),
        sa.Column("dataset_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_steps", sa.Integer(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="completed"
        ),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("aggregate", sa.JSON(), nullable=True),
        sa.Column("comparison", sa.JSON(), nullable=True),
        sa.Column("notes", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── evaluation_results ──────────────────────────────────────────────────
    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evaluation_results_run_id", "evaluation_results", ["run_id"])
    op.create_index("ix_evaluation_results_scope", "evaluation_results", ["scope"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_results_scope", table_name="evaluation_results")
    op.drop_index("ix_evaluation_results_run_id", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")

    op.drop_index("idx_prediction_session_iteration", table_name="rl_predictions")
    op.drop_index("ix_rl_predictions_policy_id", table_name="rl_predictions")
    op.drop_index("ix_rl_predictions_session_id", table_name="rl_predictions")
    op.drop_table("rl_predictions")

    op.drop_index("ix_rl_policies_active", table_name="rl_policies")
    op.drop_index("ix_rl_policies_name", table_name="rl_policies")
    op.drop_table("rl_policies")

    op.drop_index("idx_transition_session_iteration", table_name="research_transitions")
    op.drop_index("ix_research_transitions_policy_source", table_name="research_transitions")
    op.drop_index("ix_research_transitions_state_hash", table_name="research_transitions")
    op.drop_index("ix_research_transitions_session_id", table_name="research_transitions")
    op.drop_table("research_transitions")
