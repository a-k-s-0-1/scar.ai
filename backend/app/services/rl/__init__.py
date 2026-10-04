"""Offline learning layer (V2 2.1 – 2.9) — JEV stays the production policy.

The pipeline this package implements:

* ``research_state`` — the formal, serialisable observation a decision is made from.
* ``actions``       — the extensible action space, with executability made explicit.
* ``rewards``       — the named reward components an iteration earns.
* ``dataset``       — transitions validated into a learnable, exportable dataset.
* ``policy``        — the lightweight offline policy (tabular Monte-Carlo) plus the
                      JEV baseline behind one ``predict``/``expected_value`` interface.
* ``evaluation``    — replaying a policy over recorded states, JEV versus RL.
* ``recorder``      — the only module the live loop touches: it records the
                      transition and the shadow recommendation, and never executes a
                      learned decision.
* ``service``       — the database-facing services over all of the above.
"""

from app.services.rl.actions import (
    ACTION_PRIORITY,
    ACTION_SPECS,
    ActionRequest,
    ActionSpec,
    PolicyAction,
    action_spec,
    all_action_values,
    executable_action_request,
    executable_actions,
    from_jev_action,
    is_executable,
    is_stop,
    to_jev_action,
)
from app.services.rl.dataset import (
    DATASET_VERSION,
    DatasetIssue,
    TrajectoryDataset,
    TransitionRecord,
    build_dataset,
    dataset_from_jsonl,
    trajectory_is_complete,
    validate_transition,
)
from app.services.rl.evaluation import (
    EvaluationReport,
    PolicyMetrics,
    StepEvaluation,
    evaluate,
)
from app.services.rl.policy import (
    ALGORITHM,
    POLICY_VERSION,
    ActionPolicy,
    JevPolicy,
    PolicyPrediction,
    TabularPolicy,
    jev_reference_action,
    research_state_to_knowledge_state,
)
from app.services.rl.recorder import (
    RecordedStep,
    TrajectoryRecorder,
    count_duplicate_claims,
    set_session_factory,
)
from app.services.rl.research_state import (
    MAX_GAPS_STORED,
    STATE_PRECISION,
    ResearchState,
    StateObservation,
    build_research_state,
)
from app.services.rl.rewards import (
    PENALTY_FIELDS,
    POSITIVE_FIELDS,
    RewardComponents,
    components_from_dict,
    compute_reward_components,
    explain_components,
    is_repeated_without_yield,
    reward_formula,
)
from app.services.rl.service import (
    EvaluationService,
    PolicyService,
    ShadowService,
    TrajectoryService,
    build_state_from_db,
    decision_to_dict,
    to_transition_record,
)

__all__ = [
    "ACTION_PRIORITY",
    "ACTION_SPECS",
    "ALGORITHM",
    "DATASET_VERSION",
    "MAX_GAPS_STORED",
    "PENALTY_FIELDS",
    "POLICY_VERSION",
    "POSITIVE_FIELDS",
    "STATE_PRECISION",
    "ActionPolicy",
    "ActionRequest",
    "ActionSpec",
    "DatasetIssue",
    "EvaluationReport",
    "EvaluationService",
    "JevPolicy",
    "PolicyAction",
    "PolicyMetrics",
    "PolicyPrediction",
    "PolicyService",
    "RecordedStep",
    "ResearchState",
    "RewardComponents",
    "ShadowService",
    "StateObservation",
    "StepEvaluation",
    "TabularPolicy",
    "TrajectoryDataset",
    "TrajectoryRecorder",
    "TrajectoryService",
    "TransitionRecord",
    "action_spec",
    "all_action_values",
    "build_dataset",
    "build_research_state",
    "build_state_from_db",
    "components_from_dict",
    "compute_reward_components",
    "count_duplicate_claims",
    "dataset_from_jsonl",
    "decision_to_dict",
    "evaluate",
    "executable_action_request",
    "executable_actions",
    "explain_components",
    "from_jev_action",
    "is_executable",
    "is_repeated_without_yield",
    "is_stop",
    "jev_reference_action",
    "research_state_to_knowledge_state",
    "reward_formula",
    "set_session_factory",
    "to_jev_action",
    "to_transition_record",
    "trajectory_is_complete",
    "validate_transition",
]
