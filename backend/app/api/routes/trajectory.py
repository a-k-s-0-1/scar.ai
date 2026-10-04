"""Trajectory, decision-inspector and state endpoints (V2 2.1 – 2.3).

These are the read side of the learning layer: what the run actually did, why it did
it, and what the offline policy would have done instead. All of them are projections
over rows the research loop already wrote, so none of them can affect a running
session.
"""

from typing import Any

from fastapi import APIRouter, Query

from app.api.dependencies import ApiKeyAuth, DbSession
from app.api.errors import SessionNotFoundError
from app.api.rate_limit import enforce_rate_limit
from app.api.schemas.learning import (
    DecisionInspectorEntry,
    DecisionInspectorResponse,
    DecisionModel,
    DecisionsResponse,
    PredictionsResponse,
    ShadowPredictionModel,
    StateResponse,
    TrajectoryResponse,
    TransitionModel,
)
from app.config import get_settings
from app.database.models import ResearchTransition, RLPrediction
from app.database.repository import (
    DecisionRepository,
    PredictionRepository,
    SessionRepository,
    TransitionRepository,
)
from app.services.rl import (
    build_state_from_db,
    decision_to_dict,
    explain_components,
    to_transition_record,
    trajectory_is_complete,
)

router = APIRouter(prefix="/api/research", tags=["Trajectory"])
settings = get_settings()


def _transition_model(row: ResearchTransition) -> TransitionModel:
    return TransitionModel(
        id=row.id,
        session_id=row.session_id,
        iteration=row.iteration,
        action_type=row.action_type,
        action_parameters=row.action_parameters or {},
        observation=row.observation or {},
        reward=float(row.reward or 0.0),
        reward_components=row.reward_components or {},
        information_gain=float(row.information_gain or 0.0),
        coverage_before=float(row.coverage_before or 0.0),
        coverage_after=float(row.coverage_after or 0.0),
        contradictions_before=int(row.contradictions_before or 0),
        contradictions_after=int(row.contradictions_after or 0),
        sources_added=int(row.sources_added or 0),
        claims_added=int(row.claims_added or 0),
        execution_time=float(row.execution_time or 0.0),
        policy_source=row.policy_source or "JEV",
        done=bool(row.done),
        state_hash=row.state_hash,
        state_bytes=int(row.state_bytes or 0),
        state_before=row.state_before or {},
        state_after=row.state_after,
        created_at=row.created_at,
    )


def _prediction_model(row: RLPrediction) -> ShadowPredictionModel:
    return ShadowPredictionModel(
        id=row.id,
        iteration=row.iteration,
        policy_id=row.policy_id,
        state_key=row.state_key,
        jev_action=row.jev_action,
        jev_reasoning=row.jev_reasoning,
        jev_expected_value=row.jev_expected_value,
        rl_action=row.rl_action,
        rl_expected_value=row.rl_expected_value,
        rl_scores=row.rl_scores or {},
        rl_support=int(row.rl_support or 0),
        fallback=bool(row.fallback),
        actual_reward=row.actual_reward,
        estimated_rl_reward=row.estimated_rl_reward,
        disagreement=bool(row.disagreement),
        created_at=row.created_at,
    )


async def _require_session(session_id: str, db: Any) -> None:
    if await SessionRepository(db).get_by_id(session_id) is None:
        raise SessionNotFoundError(session_id)


@router.get(
    "/{session_id}/trajectory",
    response_model=TrajectoryResponse,
    summary="Recorded state/action/reward/next-state trajectory for a session",
)
async def get_session_trajectory(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
    limit: int = Query(default=200, ge=1, le=1000),
) -> TrajectoryResponse:
    """The session's transitions in iteration order, with rewards and components."""
    enforce_rate_limit(
        "research:read",
        auth,
        settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE,
        context={"session_id": session_id},
    )
    await _require_session(session_id, db)

    rows = await TransitionRepository(db).get_by_session(session_id, limit=limit)
    records = [to_transition_record(row) for row in rows]
    rewards = [record.reward for record in records]
    policies: dict[str, int] = {}
    for record in records:
        policies[record.policy_source] = policies.get(record.policy_source, 0) + 1

    return TrajectoryResponse(
        session_id=session_id,
        total=len(rows),
        complete=trajectory_is_complete(records),
        total_reward=round(sum(rewards), 4),
        average_reward=(round(sum(rewards) / len(rewards), 4) if rewards else 0.0),
        policies=policies,
        transitions=[_transition_model(row) for row in rows],
    )


@router.get(
    "/{session_id}/decisions",
    response_model=DecisionInspectorResponse,
    summary="Decision inspector: state, options, JEV choice, RL choice, reward",
)
async def get_session_decisions(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> DecisionInspectorResponse:
    """Join the decision log, the executed transition and the shadow prediction.

    One entry per iteration: what state the decision was made from, which actions were
    available, what JEV chose and why, what the offline policy would have chosen, what
    actually ran and what it earned. When there is no learned policy the RL fields are
    simply ``None``, which is the truthful answer.
    """
    enforce_rate_limit(
        "research:read",
        auth,
        settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE,
        context={"session_id": session_id},
    )
    await _require_session(session_id, db)

    decisions = await DecisionRepository(db).get_by_session(session_id)
    transitions = {
        row.iteration: row
        for row in await TransitionRepository(db).get_by_session(session_id)
    }
    predictions = {
        row.iteration: row
        for row in await PredictionRepository(db).get_by_session(session_id)
    }

    entries: list[DecisionInspectorEntry] = []
    for decision in decisions:
        iteration = decision.iteration_number
        transition = transitions.get(iteration)
        prediction = predictions.get(iteration)
        stored_state = decision.knowledge_state_snapshot or {}
        formal_state = (
            transition.state_before if transition is not None else stored_state
        )
        components = (
            transition.reward_components if transition is not None else {}
        ) or {}

        entries.append(
            DecisionInspectorEntry(
                iteration=iteration,
                state=formal_state or {},
                state_key=prediction.state_key if prediction else None,
                available_actions=decision.available_actions or [],
                jev_action=decision.selected_action,
                jev_reasoning=decision.action_reasoning or "",
                jev_expected_value=(
                    prediction.jev_expected_value
                    if prediction
                    else decision.reward_signal
                ),
                rl_action=prediction.rl_action if prediction else None,
                rl_expected_value=(
                    prediction.rl_expected_value if prediction else None
                ),
                rl_scores=(prediction.rl_scores if prediction else None) or {},
                rl_support=int(prediction.rl_support) if prediction else 0,
                disagreement=bool(prediction.disagreement) if prediction else False,
                actual_action=(
                    transition.action_type if transition else decision.selected_action
                ),
                reward=(
                    float(transition.reward) if transition is not None else None
                ),
                reward_components=components,
                reward_explanation=explain_components(components),
                information_gain=(
                    float(transition.information_gain)
                    if transition is not None
                    else None
                ),
                coverage_after=(
                    float(transition.coverage_after)
                    if transition is not None
                    else None
                ),
                policy_source=transition.policy_source if transition else None,
            )
        )

    return DecisionInspectorResponse(
        session_id=session_id, total=len(entries), entries=entries
    )


@router.get(
    "/{session_id}/decisions/raw",
    response_model=DecisionsResponse,
    summary="Raw JEV decision log for a session",
)
async def get_raw_decisions(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> DecisionsResponse:
    """The unjoined decision rows, for callers that want the original record."""
    enforce_rate_limit(
        "research:read",
        auth,
        settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE,
        context={"session_id": session_id},
    )
    await _require_session(session_id, db)

    decisions = await DecisionRepository(db).get_by_session(session_id)
    return DecisionsResponse(
        session_id=session_id,
        total=len(decisions),
        decisions=[DecisionModel(**decision_to_dict(row)) for row in decisions],
    )


@router.get(
    "/{session_id}/predictions",
    response_model=PredictionsResponse,
    summary="Shadow-mode RL predictions for a session, with agreement totals",
)
async def get_session_predictions(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
    limit: int = Query(default=200, ge=1, le=1000),
) -> PredictionsResponse:
    """What the offline policy would have done at each step of this run."""
    enforce_rate_limit(
        "research:read",
        auth,
        settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE,
        context={"session_id": session_id},
    )
    await _require_session(session_id, db)

    rows = await PredictionRepository(db).get_by_session(session_id, limit=limit)
    disagreements = sum(1 for row in rows if row.disagreement)
    return PredictionsResponse(
        session_id=session_id,
        total=len(rows),
        agreements=len(rows) - disagreements,
        disagreements=disagreements,
        predictions=[_prediction_model(row) for row in rows],
    )


@router.get(
    "/{session_id}/state",
    response_model=StateResponse,
    summary="Formal research state for a session (V2 2.1)",
)
async def get_session_state(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> StateResponse:
    """The latest formal state, from the recorded trajectory where one exists."""
    enforce_rate_limit(
        "research:read",
        auth,
        settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE,
        context={"session_id": session_id},
    )

    transitions = await TransitionRepository(db).get_by_session(session_id)
    state = await build_state_from_db(session_id, db)
    if state is None:
        raise SessionNotFoundError(session_id)

    latest_prediction = await PredictionRepository(db).latest_for_session(session_id)
    return StateResponse(
        session_id=session_id,
        state=state.to_dict(),
        state_hash=state.state_hash(),
        state_bytes=state.state_size(),
        features=state.features(),
        state_key=state.state_key(),
        source="trajectory" if transitions and transitions[-1].state_after else "reconstructed",
        latest_prediction=(
            _prediction_model(latest_prediction) if latest_prediction else None
        ),
    )
