"""Research orchestration API endpoints and WebSocket progression handler."""

import secrets

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.api.dependencies import ApiKeyAuth, DbSession
from app.api.errors import (
    InvalidQuestionError,
    SessionNotFoundError,
    SynthesisNotRetryableError,
)
from app.api.rate_limit import enforce_rate_limit
from app.api.schemas.research import (
    ResearchQuestionInput,
    ResearchSessionResponse,
    RetrySynthesisResponse,
    SessionEventItem,
    SessionEventsResponse,
    StopSessionResponse,
)
from app.config import get_settings
from app.database.repository import SessionEventRepository, SessionRepository
from app.services.depth_config import get_depth_profile
from app.services.report_generator import (
    MAX_SYNTHESIS_RETRIES,
    ReportGenerator,
    synthesis_lock,
)
from app.services.research_orchestrator import launch_research_task
from app.services.session_manager import SessionManager
from app.utils.logger import logger
from app.utils.validators import validate_question
from app.ws.managers import ws_manager

router = APIRouter(prefix="/api/research", tags=["Research"])

settings = get_settings()


@router.post(
    "/start",
    response_model=ResearchSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new research investigation",
)
async def start_research(
    payload: ResearchQuestionInput,
    db: DbSession,
    auth: ApiKeyAuth,
) -> ResearchSessionResponse:
    """Validate question, persist initial session, and trigger asynchronous orchestrator."""
    enforce_rate_limit(
        "research:start",
        auth,
        settings.HTTP_RATE_LIMIT_STARTS_PER_MINUTE,
        context={"endpoint": "POST /api/research/start"},
    )

    is_valid, reason = validate_question(payload.question)
    if not is_valid:
        raise InvalidQuestionError(reason)

    session = await SessionManager.create_session(
        question=payload.question,
        depth=payload.depth,
        db=db,
        domain=payload.domain,
        geographic_scope=payload.geographic_scope,
        time_range=payload.time_range,
        max_research_time_minutes=payload.max_research_time_minutes,
        min_sources_required=payload.min_sources_required,
        output_format=payload.output_format,
    )

    # Launch background task
    launch_research_task(session.id)

    profile = get_depth_profile(payload.depth)

    return ResearchSessionResponse(
        id=session.id,
        question=session.question,
        depth=session.depth,
        domain=session.domain,
        geographic_scope=session.geographic_scope,
        time_range=session.time_range,
        max_research_time_minutes=session.max_research_time_minutes,
        min_sources_required=session.min_sources_required,
        output_format=session.output_format,
        status=session.status,
        current_iteration=session.current_iteration,
        max_iterations=profile.max_iterations,
        started_at=session.started_at,
        completed_at=session.completed_at,
        estimated_time_seconds=profile.estimated_seconds,
        error_message=session.error_message,
        total_sources=0,
        total_claims=0,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get(
    "/{session_id}",
    response_model=ResearchSessionResponse,
    summary="Get current state and metadata of a research session",
)
async def get_research_session(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> ResearchSessionResponse:
    """Retrieve session status, metrics, and summary data."""
    enforce_rate_limit(
        "research:read",
        auth,
        settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE,
        context={"session_id": session_id},
    )

    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError(session_id)

    stats = await SessionManager.get_session_stats(session_id, db)
    profile = get_depth_profile(session.depth)

    return ResearchSessionResponse(
        id=session.id,
        question=session.question,
        depth=session.depth,
        domain=session.domain,
        geographic_scope=session.geographic_scope,
        time_range=session.time_range,
        max_research_time_minutes=session.max_research_time_minutes,
        min_sources_required=session.min_sources_required,
        output_format=session.output_format,
        status=session.status,
        current_iteration=session.current_iteration,
        max_iterations=profile.max_iterations,
        started_at=session.started_at,
        completed_at=session.completed_at,
        estimated_time_seconds=profile.estimated_seconds,
        error_message=session.error_message,
        total_sources=stats["total_sources"],
        total_claims=stats["total_claims"],
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post(
    "/{session_id}/stop",
    response_model=StopSessionResponse,
    summary="Halt a running research session",
)
async def stop_research_session(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> StopSessionResponse:
    """Manually halt an active research loop."""
    enforce_rate_limit(
        "research:stop",
        auth,
        settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE,
        context={"session_id": session_id},
    )

    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError(session_id)

    await SessionManager.stop_session(session_id, db)
    await ws_manager.broadcast(session_id, {"type": "stopped", "by": "user"})

    return StopSessionResponse(
        session_id=session_id,
        status="stopped",
        message="Session successfully stopped by user request.",
    )


@router.post(
    "/{session_id}/retry-synthesis",
    response_model=RetrySynthesisResponse,
    summary="Re-run report synthesis without new web research",
)
async def retry_report_synthesis(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> RetrySynthesisResponse:
    """Spend one more model pass on the evidence already gathered.

    Synthesis is the one step that degrades silently: when a provider rate limits
    mid-run the report still compiles, but from the rule-based fallback. This
    re-runs only that step against the stored claims and sources, so a finished
    investigation can be recovered without paying for the research again.
    """
    enforce_rate_limit(
        "research:retry_synthesis",
        auth,
        settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE,
        context={"session_id": session_id},
    )

    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError(session_id)

    # Everything that reads or advances the attempt count happens under the
    # session's lock, so a double submit cannot buy two model calls for one
    # recorded attempt or slip past the retry cap on a stale count.
    async with synthesis_lock(session_id):
        session = await repo.get_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        # Sessions do not expire attributes on commit, so a retry that finished
        # while this one waited on the lock is only visible after an explicit read.
        await db.refresh(session)

        if session.status in ("initializing", "running", "pending"):
            raise SynthesisNotRetryableError(
                session_id, "the run is still in progress"
            )
        if not session.report_data:
            raise SynthesisNotRetryableError(
                session_id, "no report has been generated yet"
            )

        previous_retries = int(
            (session.report_data.get("metadata") or {}).get("retry_count") or 0
        )
        if previous_retries >= MAX_SYNTHESIS_RETRIES:
            raise SynthesisNotRetryableError(
                session_id,
                f"the retry limit of {MAX_SYNTHESIS_RETRIES} has been reached",
            )

        retry_count = previous_retries + 1
        report = await ReportGenerator(session_id).generate_report(
            db=db, retry_count=retry_count, mark_completed=False
        )
        await db.commit()

    synthesis = str(report.get("metadata", {}).get("synthesis", "fallback"))
    await ws_manager.broadcast(
        session_id,
        {
            "type": "synthesis_regenerated",
            "report_ready": True,
            "synthesis": synthesis,
            "retry_count": retry_count,
        },
    )

    return RetrySynthesisResponse(
        session_id=session_id,
        status="regenerated",
        synthesis=synthesis,
        retry_count=retry_count,
        max_retries=MAX_SYNTHESIS_RETRIES,
        report_data=report,
    )


@router.get(
    "/{session_id}/events",
    response_model=SessionEventsResponse,
    summary="Replay the persisted event timeline of a session",
)
async def get_session_events(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
    after_seq: int = Query(default=0, ge=0, description="Resume after this sequence"),
    limit: int = Query(default=500, ge=1, le=2000),
) -> SessionEventsResponse:
    """Return the durable progress log so finished runs can be replayed.

    Live updates only travel over the WebSocket, so this is what lets the UI show
    a completed investigation's activity instead of an empty panel.
    """
    enforce_rate_limit(
        "research:read",
        auth,
        settings.HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE,
        context={"session_id": session_id},
    )

    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError(session_id)

    events = await SessionEventRepository(db).list_events(
        session_id, after_seq=after_seq, limit=limit
    )

    return SessionEventsResponse(
        session_id=session_id,
        total=len(events),
        latest_seq=events[-1].seq if events else after_seq,
        events=[
            SessionEventItem(
                seq=event.seq,
                type=event.event_type,
                iteration=event.iteration,
                payload=event.payload,
                created_at=event.created_at,
            )
            for event in events
        ],
    )


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """Stream live iteration updates and findings over WebSocket.

    Browser sockets cannot set headers, so the key travels as a query parameter.
    The socket is refused before acceptance when the key does not match, otherwise
    anyone could subscribe to another user's live research stream.
    """
    settings = get_settings()
    provided_key = websocket.query_params.get("api_key", "")
    if settings.API_KEY and not secrets.compare_digest(provided_key, settings.API_KEY):
        logger.warning(
            f"Rejected unauthenticated WebSocket subscription for session {session_id}."
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(websocket, session_id)
    try:
        while True:
            # Keep connection alive; clients can send ping/pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)
    except Exception as e:
        logger.warning(f"WebSocket connection error: {e}")
        ws_manager.disconnect(websocket, session_id)
