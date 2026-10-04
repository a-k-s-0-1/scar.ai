"""Final research report API endpoint."""

from typing import Any

from fastapi import APIRouter

from app.api.dependencies import ApiKeyAuth, DbSession
from app.api.errors import SessionNotFoundError
from app.database.repository import SessionRepository
from app.services.report_generator import ReportGenerator

router = APIRouter(prefix="/api/research", tags=["Reports"])


@router.get(
    "/{session_id}/report",
    summary="Get finalized research synthesis report",
)
async def get_report(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> dict[str, Any]:
    """Retrieve or generate the final executive summary and compiled report."""
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError(session_id)

    # If already compiled and stored in report_data, return it directly
    if session.report_data:
        return session.report_data

    # If session is completed or stopped but report_data not yet generated, compile it now
    generator = ReportGenerator(session_id)
    report = await generator.generate_report(db=db)
    await db.commit()
    return report
