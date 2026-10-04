"""Session manager handling research session lifecycles."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ResearchSession
from app.database.repository import (
    ClaimRepository,
    SessionRepository,
    SourceRepository,
)
from app.utils.logger import logger


class SessionManager:
    """Orchestrates session creation, retrieval, and status tracking."""

    @staticmethod
    async def create_session(
        question: str,
        depth: str,
        db: AsyncSession,
        domain: str | None = None,
        geographic_scope: str = "global",
        time_range: str | None = None,
        max_research_time_minutes: int = 5,
        min_sources_required: int = 10,
        output_format: str = "report",
    ) -> ResearchSession:
        repo = SessionRepository(db)
        session = await repo.create(
            question=question,
            depth=depth,
            domain=domain,
            geographic_scope=geographic_scope,
            time_range=time_range,
            max_research_time_minutes=max_research_time_minutes,
            min_sources_required=min_sources_required,
            output_format=output_format,
        )
        logger.info(f"Initialized new research session {session.id} for: '{question}'")
        return session

    @staticmethod
    async def stop_session(session_id: str, db: AsyncSession) -> ResearchSession | None:
        repo = SessionRepository(db)
        session = await repo.update_status(
            session_id, status="stopped", error_message="Stopped by user."
        )
        logger.info(f"Research session {session_id} manually stopped.")
        return session

    @staticmethod
    async def reconcile_interrupted_sessions(db: AsyncSession) -> int:
        """Mark sessions left mid-run by a previous process as interrupted.

        Research loops run as in-process background tasks, so when the server
        restarts there is no task behind a 'running' session: without this it
        would stay 'running' forever and the UI would show phantom work.
        """
        result = await db.execute(
            update(ResearchSession)
            .where(ResearchSession.status.in_(("running", "initializing")))
            .values(
                status="error",
                error_message="Interrupted by server restart.",
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        interrupted = result.rowcount or 0
        if interrupted:
            logger.warning(
                f"Reconciled {interrupted} session(s) left running by a previous process."
            )
        return interrupted

    @staticmethod
    async def get_session_stats(session_id: str, db: AsyncSession) -> dict[str, Any]:
        source_repo = SourceRepository(db)
        claim_repo = ClaimRepository(db)

        sources = await source_repo.get_by_session(session_id)
        claims = await claim_repo.get_by_session(session_id)

        return {
            "total_sources": len(sources),
            "total_claims": len(claims),
        }
