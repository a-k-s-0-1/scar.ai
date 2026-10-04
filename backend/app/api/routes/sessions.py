"""Session history and dashboard listing routes."""

from fastapi import APIRouter, Query, status

from app.api.dependencies import ApiKeyAuth, DbSession
from app.api.errors import SessionNotFoundError
from app.api.schemas.session import SessionListResponse, SessionSummary
from app.database.repository import SessionRepository
from app.services.session_manager import SessionManager

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


@router.get(
    "", response_model=SessionListResponse, summary="List past research sessions"
)
@router.get("/", response_model=SessionListResponse, include_in_schema=False)
async def list_sessions(
    db: DbSession,
    auth: ApiKeyAuth,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> SessionListResponse:
    """Retrieve paginated list of research sessions."""
    repo = SessionRepository(db)
    sessions = await repo.list_sessions(skip=skip, limit=limit)

    summaries: list[SessionSummary] = []
    for s in sessions:
        stats = await SessionManager.get_session_stats(s.id, db)
        summaries.append(
            SessionSummary(
                id=s.id,
                question=s.question,
                depth=s.depth,
                status=s.status,
                current_iteration=s.current_iteration,
                started_at=s.started_at,
                completed_at=s.completed_at,
                created_at=s.created_at,
                sources_count=stats["total_sources"],
                claims_count=stats["total_claims"],
            )
        )

    return SessionListResponse(
        total=len(summaries),
        sessions=summaries,
    )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a research session and all associated data",
)
async def delete_session(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> None:
    """Permanently delete a research session and cascaded entities."""
    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError(session_id)

    await repo.delete(session_id)
    await db.commit()
