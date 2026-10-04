"""Pydantic schemas for V2 trajectories, offline policies and evaluation.

The frontend has a matching TypeScript shape in ``frontend/lib/types.ts``; keep the two
in sync when either changes. Deep, policy-specific payloads (a stored research state,
reward components, per-action slices) stay as typed dictionaries on purpose: they are
already versioned and documented inside the modules that produce them, and duplicating
every field here would create a third place to update.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PolicyChoice = Literal["jev", "rl"]
BaselineChoice = Literal["jev", "none"]


# ─── trajectory ──────────────────────────────────────────────────────────────


class TransitionModel(BaseModel):
    """One ``state -> action -> observation -> reward -> next_state`` step."""

    id: str
    session_id: str
    iteration: int
    action_type: str
    action_parameters: dict[str, Any] = {}
    observation: dict[str, Any] = {}
    reward: float
    reward_components: dict[str, Any] = {}
    information_gain: float
    coverage_before: float
    coverage_after: float
    contradictions_before: int
    contradictions_after: int
    sources_added: int
    claims_added: int
    execution_time: float
    policy_source: str
    done: bool
    state_hash: str | None = None
    state_bytes: int = 0
    state_before: dict[str, Any] = {}
    state_after: dict[str, Any] | None = None
    created_at: datetime | None = None


class TrajectoryResponse(BaseModel):
    """A session's recorded trajectory, in iteration order."""

    session_id: str
    total: int
    complete: bool
    total_reward: float
    average_reward: float
    policies: dict[str, int] = {}
    transitions: list[TransitionModel]


# ─── decisions and state ─────────────────────────────────────────────────────


class DecisionModel(BaseModel):
    """One stored JEV decision."""

    id: str
    iteration: int
    selected_action: str | None = None
    available_actions: list[str] = []
    reasoning: str = ""
    reward_signal: float | None = None
    state: dict[str, Any] = {}
    created_at: datetime | None = None


class ShadowPredictionModel(BaseModel):
    """What the offline policy would have done, next to what JEV did."""

    id: str
    iteration: int
    policy_id: str | None = None
    state_key: str
    jev_action: str
    jev_reasoning: str | None = None
    jev_expected_value: float | None = None
    rl_action: str
    rl_expected_value: float | None = None
    rl_scores: dict[str, Any] = {}
    rl_support: int = 0
    fallback: bool = False
    actual_reward: float | None = None
    estimated_rl_reward: float | None = None
    disagreement: bool = False
    created_at: datetime | None = None


class DecisionInspectorEntry(BaseModel):
    """A whole decision step: state, options, JEV choice, RL choice and the reward.

    Built by joining the decision log, the transition and the shadow prediction, which
    is exactly the view a developer needs to answer "why did the run do that?".
    """

    iteration: int
    state: dict[str, Any] = {}
    state_key: str | None = None
    available_actions: list[str] = []
    jev_action: str | None = None
    jev_reasoning: str = ""
    jev_expected_value: float | None = None
    rl_action: str | None = None
    rl_expected_value: float | None = None
    rl_scores: dict[str, Any] = {}
    rl_support: int = 0
    disagreement: bool = False
    actual_action: str | None = None
    reward: float | None = None
    reward_components: dict[str, Any] = {}
    reward_explanation: list[dict[str, Any]] = []
    information_gain: float | None = None
    coverage_after: float | None = None
    policy_source: str | None = None


class StateResponse(BaseModel):
    """The formal research state for a session, plus its hash and features."""

    session_id: str
    state: dict[str, Any]
    state_hash: str
    state_bytes: int
    features: dict[str, str]
    state_key: str
    source: str = Field(
        description="'trajectory' when read from the last recorded transition, "
        "'reconstructed' when rebuilt from stored rows",
    )
    latest_prediction: ShadowPredictionModel | None = None


class PredictionsResponse(BaseModel):
    """Shadow predictions for one session, with agreement totals."""

    session_id: str
    total: int
    agreements: int
    disagreements: int
    predictions: list[ShadowPredictionModel]


class DecisionInspectorResponse(BaseModel):
    """Every decision step of a session, merged with its outcome."""

    session_id: str
    total: int
    entries: list[DecisionInspectorEntry]


class DecisionsResponse(BaseModel):
    """The raw JEV decision log for a session."""

    session_id: str
    total: int
    decisions: list[DecisionModel]


# ─── dataset ─────────────────────────────────────────────────────────────────


class DatasetSampleModel(BaseModel):
    """The learning sample exactly as it would be exported."""

    state: dict[str, Any]
    action: str
    reward: float
    next_state: dict[str, Any] | None = None
    done: bool


class DatasetIssueModel(BaseModel):
    kind: str
    session_id: str
    iteration: int
    detail: str


class DatasetResponse(BaseModel):
    """A dataset plus the validation issues found while building it."""

    version: str
    dataset_hash: str
    transitions: int
    sessions: int
    session_ids: list[str] = []
    actions: dict[str, int] = {}
    policy_sources: dict[str, int] = {}
    done_transitions: int = 0
    average_reward: float = 0.0
    total_reward: float = 0.0
    average_information_gain: float = 0.0
    average_steps_per_session: float = 0.0
    dropped: int = 0
    issues: list[DatasetIssueModel] = []
    samples: list[DatasetSampleModel] = []


class DatasetStatsResponse(BaseModel):
    """Dataset statistics without loading the samples into the response."""

    version: str
    dataset_hash: str
    transitions: int
    sessions: int
    session_ids: list[str] = []
    actions: dict[str, int] = {}
    policy_sources: dict[str, int] = {}
    done_transitions: int = 0
    average_reward: float = 0.0
    total_reward: float = 0.0
    average_information_gain: float = 0.0
    average_steps_per_session: float = 0.0
    recorded_transitions: int = 0
    sessions_with_transitions: int = 0
    complete_sessions: int = 0
    by_policy_source: dict[str, int] = {}
    issues: dict[str, int] = {}
    dropped: int = 0


class DatasetBuildRequest(BaseModel):
    """Build request: which sessions, whether to include unfinished ones, train now.

    ``backfill`` first reconstructs transitions for completed sessions that predate
    trajectory recording (from decisions + research_actions), so past investigations
    join the dataset. Idempotent: sessions that already have transitions are skipped.
    """

    session_ids: list[str] | None = None
    include_incomplete: bool = False
    train: bool = False
    activate: bool = True
    policy_name: str = "jev-baseline-shadow"
    backfill: bool = False


class PolicyModel(BaseModel):
    """One stored offline policy."""

    id: str
    name: str
    version: str
    algorithm: str
    dataset_version: str | None = None
    dataset_hash: str | None = None
    baseline: str
    samples: int
    sessions: int
    active: bool
    metrics: dict[str, Any] = {}
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DatasetBuildResponse(BaseModel):
    """Result of a build (and optionally a training) request."""

    dataset: DatasetStatsResponse
    trained: bool = False
    policy: PolicyModel | None = None
    policy_metrics: dict[str, Any] = {}
    backfill: dict[str, Any] | None = None


class PoliciesResponse(BaseModel):
    total: int
    policies: list[PolicyModel]


class PolicyActivateResponse(BaseModel):
    policy: PolicyModel
    message: str


# ─── evaluation ──────────────────────────────────────────────────────────────


class EvaluationMetricsModel(BaseModel):
    """Aggregate outcome for one policy."""

    policy: str
    steps: int = 0
    observed_steps: int = 0
    counterfactual_steps: int = 0
    unestimable_steps: int = 0
    total_reward: float = 0.0
    average_reward: float = 0.0
    average_information_gain: float = 0.0
    coverage_improvement: float = 0.0
    average_iterations: float = 0.0
    duplicate_search_rate: float = 0.0
    contradiction_resolution_rate: float = 0.0
    stop_rate: float = 0.0
    unnecessary_action_rate: float = 0.0
    research_cost_seconds: float = 0.0
    time_to_convergence: float | None = None
    action_distribution: dict[str, int] = {}
    estimated: bool = False


class EvaluationRunRequest(BaseModel):
    """Options for an offline evaluation run."""

    policy: PolicyChoice = "rl"
    baseline: BaselineChoice = "jev"
    dataset_version: str | None = None
    max_steps: int | None = Field(default=None, ge=1, le=200)
    session_ids: list[str] | None = None
    include_incomplete: bool = False
    persist: bool = True


class EvaluationActionRow(BaseModel):
    action: str
    sample_size: int
    observed_steps: int = 0
    counterfactual_steps: int = 0
    average_reward: float | None = None
    estimated: bool = False
    baseline_sample_size: int = 0
    baseline_average_reward: float | None = None
    reward_delta: float | None = None


class EvaluationSessionRow(BaseModel):
    session_id: str
    steps: int
    observed_steps: int = 0
    counterfactual_steps: int = 0
    average_reward: float | None = None
    total_reward: float = 0.0
    baseline_average_reward: float | None = None
    reward_delta: float | None = None
    final_coverage: float = 0.0
    stopped: bool = False


class EvaluationReportModel(BaseModel):
    """A full evaluation report."""

    run_id: str | None = None
    policy: str
    baseline: str | None = None
    dataset_version: str
    dataset_hash: str
    dataset_size: int
    sessions: list[str] = []
    max_steps: int | None = None
    metrics: EvaluationMetricsModel
    baseline_metrics: EvaluationMetricsModel | None = None
    comparison: dict[str, Any] = {}
    per_session: list[EvaluationSessionRow] = []
    per_action: list[EvaluationActionRow] = []
    notes: list[str] = []


class EvaluationRunSummary(BaseModel):
    """A stored evaluation run, without its per-scope slices."""

    id: str
    policy: str
    baseline: str | None = None
    dataset_version: str
    dataset_hash: str | None = None
    dataset_size: int
    sessions: int
    max_steps: int | None = None
    status: str
    aggregate: dict[str, Any] = {}
    comparison: dict[str, Any] = {}
    notes: list[str] = []
    created_at: datetime | None = None
    completed_at: datetime | None = None


class EvaluationResultsResponse(BaseModel):
    total: int
    runs: list[EvaluationRunSummary]


class EvaluationResultDetail(BaseModel):
    """A stored run with its per-session and per-action slices."""

    id: str
    policy: str
    baseline: str | None = None
    dataset_version: str
    dataset_hash: str | None = None
    dataset_size: int
    sessions: int
    max_steps: int | None = None
    status: str
    config: dict[str, Any] = {}
    aggregate: dict[str, Any] = {}
    comparison: dict[str, Any] = {}
    notes: list[str] = []
    created_at: datetime | None = None
    completed_at: datetime | None = None
    results: list[dict[str, Any]] = []
