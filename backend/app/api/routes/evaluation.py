"""Offline evaluation API (V2 2.5 – 2.9).

Everything here is *offline*: building datasets from recorded trajectories, training
the lightweight policy, replaying JEV against it and reading past runs. None of it
touches a live session, and none of it can promote a policy into the production loop —
``activate`` only decides whose recommendations the shadow comparison records.
"""

from typing import Any

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import ApiKeyAuth, DbSession
from app.api.errors import EvaluationOptionsError
from app.api.rate_limit import enforce_rate_limit
from app.api.schemas.learning import (
    DatasetBuildRequest,
    DatasetBuildResponse,
    DatasetIssueModel,
    DatasetResponse,
    DatasetSampleModel,
    DatasetStatsResponse,
    EvaluationActionRow,
    EvaluationMetricsModel,
    EvaluationReportModel,
    EvaluationResultDetail,
    EvaluationResultsResponse,
    EvaluationRunRequest,
    EvaluationRunSummary,
    EvaluationSessionRow,
    PoliciesResponse,
    PolicyActivateResponse,
    PolicyModel,
)
from app.config import get_settings
from app.database.models import RLPolicy
from app.services.rl import (
    ACTION_SPECS,
    DATASET_VERSION,
    executable_actions,
    reward_formula,
)
from app.services.rl.service import EvaluationService, PolicyService, TrajectoryService

router = APIRouter(prefix="/api/evaluation", tags=["Evaluation"])
settings = get_settings()


def _policy_model(row: RLPolicy) -> PolicyModel:
    return PolicyModel(
        id=row.id,
        name=row.name,
        version=row.version,
        algorithm=row.algorithm,
        dataset_version=row.dataset_version,
        dataset_hash=row.dataset_hash,
        baseline=row.baseline,
        samples=row.samples,
        sessions=row.sessions,
        active=row.active,
        metrics=row.metrics or {},
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _dataset_stats(dataset: Any, stats: dict[str, Any]) -> DatasetStatsResponse:
    return DatasetStatsResponse(
        version=dataset.version,
        dataset_hash=dataset.dataset_hash(),
        transitions=stats["transitions"],
        sessions=stats["sessions"],
        session_ids=stats["session_ids"],
        actions=stats["actions"],
        policy_sources=stats["policy_sources"],
        done_transitions=stats["done_transitions"],
        average_reward=stats["average_reward"],
        total_reward=stats["total_reward"],
        average_information_gain=stats["average_information_gain"],
        average_steps_per_session=stats["average_steps_per_session"],
        recorded_transitions=stats.get("recorded_transitions", stats["transitions"]),
        sessions_with_transitions=stats.get(
            "sessions_with_transitions", stats["sessions"]
        ),
        complete_sessions=stats.get("complete_sessions", 0),
        by_policy_source=stats.get("by_policy_source", {}),
        issues=stats["issues"],
        dropped=stats["dropped"],
    )


def _report_model(report: Any, run_id: str | None = None) -> EvaluationReportModel:
    payload = report.to_dict()
    return EvaluationReportModel(
        run_id=run_id,
        policy=payload["policy"],
        baseline=payload["baseline"],
        dataset_version=payload["dataset_version"],
        dataset_hash=payload["dataset_hash"],
        dataset_size=payload["dataset_size"],
        sessions=payload["sessions"],
        max_steps=payload["max_steps"],
        metrics=EvaluationMetricsModel(**payload["metrics"]),
        baseline_metrics=(
            EvaluationMetricsModel(**payload["baseline_metrics"])
            if payload["baseline_metrics"]
            else None
        ),
        comparison=payload["comparison"],
        per_session=[EvaluationSessionRow(**row) for row in payload["per_session"]],
        per_action=[EvaluationActionRow(**row) for row in payload["per_action"]],
        notes=payload["notes"],
    )


@router.get(
    "/dataset",
    response_model=DatasetResponse,
    summary="Export the offline research trajectory dataset",
)
async def get_dataset(
    db: DbSession,
    auth: ApiKeyAuth,
    include_incomplete: bool = Query(default=False),
    session_ids: str | None = Query(
        default=None, description="Comma-separated session ids to restrict to"
    ),
    limit: int = Query(default=1000, ge=1, le=10000),
) -> DatasetResponse:
    """Validated transitions, ready to train on. Incomplete runs are excluded unless asked."""
    enforce_rate_limit(
        "evaluation:read", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )

    ids = (
        [value.strip() for value in session_ids.split(",") if value.strip()]
        if session_ids
        else None
    ) or None
    dataset = await TrajectoryService(db).build(
        ids, include_incomplete=include_incomplete
    )
    stats = dataset.stats()
    return DatasetResponse(
        version=dataset.version,
        dataset_hash=dataset.dataset_hash(),
        transitions=stats["transitions"],
        sessions=stats["sessions"],
        session_ids=stats["session_ids"],
        actions=stats["actions"],
        policy_sources=stats["policy_sources"],
        done_transitions=stats["done_transitions"],
        average_reward=stats["average_reward"],
        total_reward=stats["total_reward"],
        average_information_gain=stats["average_information_gain"],
        average_steps_per_session=stats["average_steps_per_session"],
        dropped=stats["dropped"],
        issues=[DatasetIssueModel(**issue.to_dict()) for issue in dataset.issues],
        samples=[
            DatasetSampleModel(**sample)
            for sample in dataset.samples[:limit]
        ],
    )


@router.get(
    "/dataset/export",
    summary="Export the dataset as JSONL (one training sample per line)",
    response_class=Response,
)
async def export_dataset(
    db: DbSession,
    auth: ApiKeyAuth,
    include_incomplete: bool = Query(default=False),
    include_metadata: bool = Query(default=False),
) -> Response:
    """JSONL, the format an external trainer consumes. No policy is touched."""
    enforce_rate_limit(
        "evaluation:read", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )
    dataset = await TrajectoryService(db).build(include_incomplete=include_incomplete)
    return Response(
        content=dataset.to_jsonl(include_metadata=include_metadata),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": (
                f'attachment; filename="trajectory-{dataset.dataset_hash()}.jsonl"'
            )
        },
    )


@router.get(
    "/dataset/stats",
    response_model=DatasetStatsResponse,
    summary="Dataset size, composition and validation issues",
)
async def get_dataset_stats(db: DbSession, auth: ApiKeyAuth) -> DatasetStatsResponse:
    enforce_rate_limit(
        "evaluation:read", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )
    service = TrajectoryService(db)
    dataset = await service.build(include_incomplete=True)
    stats = dataset.stats()
    stats["recorded_transitions"] = await service.repo.count()
    stats["sessions_with_transitions"] = len(
        await service.repo.session_ids_with_transitions()
    )
    stats["complete_sessions"] = len(await service.repo.completed_session_ids())
    stats["by_policy_source"] = await service.dataset_stats_by_source()
    return _dataset_stats(dataset, stats)


@router.post(
    "/dataset/build",
    response_model=DatasetBuildResponse,
    status_code=status.HTTP_200_OK,
    summary="Build the dataset (and optionally train the offline policy)",
)
async def build_dataset(
    payload: DatasetBuildRequest,
    db: DbSession,
    auth: ApiKeyAuth,
) -> DatasetBuildResponse:
    """Build from recorded trajectories; ``train=true`` also fits and stores a policy.

    This is the only place a policy is created. It never activates anything in the
    production loop — JEV keeps deciding — it only gives the shadow comparison a model.
    """
    enforce_rate_limit(
        "evaluation:write", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )
    trajectories = TrajectoryService(db)
    backfill: dict[str, Any] = {}
    if payload.backfill:
        backfill = await trajectories.backfill_history(
            payload.session_ids,
            limit=settings.RL_DATASET_MAX_TRANSITIONS,
        )
    dataset = await trajectories.build(
        payload.session_ids, include_incomplete=payload.include_incomplete
    )
    stats = dataset.stats()
    if backfill:
        stats = {**stats, "backfill": backfill}

    trained = False
    policy_model: PolicyModel | None = None
    policy_metrics: dict[str, Any] = {}
    if payload.train:
        record, _dataset, policy = await PolicyService(db).train(
            session_ids=payload.session_ids,
            include_incomplete=payload.include_incomplete,
            name=payload.policy_name,
            activate=payload.activate,
        )
        if record is not None:
            trained = True
            policy_model = _policy_model(record)
            policy_metrics = policy.describe() if policy else {}

    return DatasetBuildResponse(
        dataset=_dataset_stats(dataset, stats),
        trained=trained,
        policy=policy_model,
        policy_metrics=policy_metrics,
        backfill=backfill or None,
    )


@router.post(
    "/dataset/backfill",
    summary="Reconstruct transitions for completed sessions that predate the recorder",
)
async def backfill_dataset(
    db: DbSession,
    auth: ApiKeyAuth,
    payload: DatasetBuildRequest | None = None,
) -> dict[str, Any]:
    """Join V1 history (decisions + research_actions) into the training dataset.

    Idempotent and safe to repeat: sessions with transitions are skipped, one bad
    session never stops the rest. Nothing here touches a live run.
    """
    enforce_rate_limit(
        "evaluation:write", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )
    session_ids = payload.session_ids if payload else None
    limit = settings.RL_DATASET_MAX_TRANSITIONS
    return await TrajectoryService(db).backfill_history(session_ids, limit=limit)


@router.post(
    "/run",
    response_model=EvaluationReportModel,
    status_code=status.HTTP_200_OK,
    summary="Replay the dataset through JEV and/or the offline policy",
)
async def run_evaluation(
    payload: EvaluationRunRequest,
    db: DbSession,
    auth: ApiKeyAuth,
) -> EvaluationReportModel:
    """Offline comparison on recorded states. Nothing here executes in a live run."""
    enforce_rate_limit(
        "evaluation:write", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )
    if payload.dataset_version not in (None, DATASET_VERSION):
        raise EvaluationOptionsError(
            f"Unknown dataset_version '{payload.dataset_version}'. "
            f"Supported versions: {DATASET_VERSION}.",
            {"supported": [DATASET_VERSION]},
        )

    service = EvaluationService(db)
    report = await service.run(
        policy=payload.policy,
        baseline=payload.baseline,
        dataset_version=payload.dataset_version,
        session_ids=payload.session_ids,
        max_steps=payload.max_steps,
        include_incomplete=payload.include_incomplete,
        persist=payload.persist,
    )
    run_id: str | None = None
    if payload.persist and report.dataset_size:
        runs = await service.list_runs(limit=1)
        run_id = runs[0].id if runs else None
    return _report_model(report, run_id=run_id)


@router.get(
    "/results",
    response_model=EvaluationResultsResponse,
    summary="Past evaluation runs",
)
async def list_evaluation_results(
    db: DbSession,
    auth: ApiKeyAuth,
    limit: int = Query(default=20, ge=1, le=100),
) -> EvaluationResultsResponse:
    enforce_rate_limit(
        "evaluation:read", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )
    runs = await EvaluationService(db).list_runs(limit=limit)
    return EvaluationResultsResponse(
        total=len(runs),
        runs=[
            EvaluationRunSummary(
                id=run.id,
                policy=run.policy,
                baseline=run.baseline,
                dataset_version=run.dataset_version,
                dataset_hash=run.dataset_hash,
                dataset_size=run.dataset_size,
                sessions=run.sessions,
                max_steps=run.max_steps,
                status=run.status,
                aggregate=run.aggregate or {},
                comparison=run.comparison or {},
                notes=run.notes or [],
                created_at=run.created_at,
                completed_at=run.completed_at,
            )
            for run in runs
        ],
    )


@router.get(
    "/results/{run_id}",
    response_model=EvaluationResultDetail,
    summary="One evaluation run with its per-session and per-action slices",
)
async def get_evaluation_result(
    run_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> EvaluationResultDetail:
    enforce_rate_limit(
        "evaluation:read", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )
    detail = await EvaluationService(db).get_run(run_id)
    if detail is None:
        raise EvaluationOptionsError(
            f"Evaluation run '{run_id}' not found.", {"run_id": run_id}
        )
    return EvaluationResultDetail(**detail)


@router.get(
    "/policies",
    response_model=PoliciesResponse,
    summary="Stored offline policies",
)
async def list_policies(db: DbSession, auth: ApiKeyAuth) -> PoliciesResponse:
    enforce_rate_limit(
        "evaluation:read", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )
    rows = await PolicyService(db).list_policies()
    return PoliciesResponse(total=len(rows), policies=[_policy_model(row) for row in rows])


@router.post(
    "/policies/train",
    response_model=DatasetBuildResponse,
    summary="Train the lightweight offline policy from stored trajectories",
)
async def train_policy(
    db: DbSession,
    auth: ApiKeyAuth,
    include_incomplete: bool = Query(default=False),
    activate: bool = Query(default=True),
    name: str = Query(default="jev-baseline-shadow", max_length=80),
) -> DatasetBuildResponse:
    """Fit the tabular policy and store it. Training is offline and O(dataset size)."""
    enforce_rate_limit(
        "evaluation:write", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )
    record, dataset, policy = await PolicyService(db).train(
        include_incomplete=include_incomplete, name=name, activate=activate
    )
    stats = dataset.stats()
    return DatasetBuildResponse(
        dataset=_dataset_stats(dataset, stats),
        trained=record is not None,
        policy=_policy_model(record) if record else None,
        policy_metrics=policy.describe() if policy else {},
    )


@router.post(
    "/policies/{policy_id}/activate",
    response_model=PolicyActivateResponse,
    summary="Make one policy the active one (shadow comparison, never production)",
)
async def activate_policy(
    policy_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> PolicyActivateResponse:
    enforce_rate_limit(
        "evaluation:write", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )
    service = PolicyService(db)
    row = await service.activate(policy_id)
    if row is None:
        raise EvaluationOptionsError(
            f"Policy '{policy_id}' not found.", {"policy_id": policy_id}
        )
    return PolicyActivateResponse(
        policy=_policy_model(row),
        message=(
            "Policy activated for shadow predictions and offline evaluation. "
            "JEV continues to make every live decision."
        ),
    )


@router.get(
    "/reward-formula",
    summary="The exact reward formula and action space, for the UI to document itself",
)
async def get_reward_formula(auth: ApiKeyAuth) -> dict[str, Any]:
    """Nothing hidden: the weights, the action space and what is executable."""
    enforce_rate_limit(
        "evaluation:read", auth, settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE
    )
    return {
        "reward": reward_formula(),
        "actions": {
            "executable": executable_actions(),
            "all": [spec.to_dict() for spec in ACTION_SPECS.values()],
        },
        "dataset_version": DATASET_VERSION,
        "production_policy": "JEV",
    }
