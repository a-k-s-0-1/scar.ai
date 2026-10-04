"""Durable session event log.

Live progress is broadcast over WebSockets, which disappear the moment a run ends
or a page is closed. Scrubbing the same events into the database gives the UI a
replayable timeline, so opening a finished investigation shows what happened
instead of an empty activity feed.

Wired into the broadcast path at startup (see app/main.py) rather than imported by
the connection manager, which keeps the WebSocket layer free of database imports
and therefore free of import cycles.
"""

from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.database.repository import SessionEventRepository
from app.database.session import async_session_maker
from app.utils.logger import logger

# Indirection so tests can bind the recorder to their own database engine
# without touching the module-level session maker.
_session_factory = async_session_maker

# Event types worth keeping. Anything else (ad-hoc pings) is skipped so the log
# stays a faithful record of research progress.
RECORDED_EVENT_TYPES = frozenset(
    {
        "initialized",
        "search_started",
        "sources_found",
        "extraction_started",
        "claims_extracted",
        "knowledge_updated",
        "facet_updated",
        # IKF 2.0 snapshot. Without an entry here it still streams live but is never
        # persisted, so a replayed run would silently lose its evidence telemetry.
        "ikf_updated",
        # V2 2.1 cross-session knowledge: what was recalled on the way in and what
        # this run left behind. Kept so a replayed investigation can show it.
        "memory_recalled",
        "memory_updated",
        "contradiction_detected",
        "decision_made",
        # V2 offline learning: the reward-bearing transition and the policy's
        # recommendation beside JEV's. Recorded so a replayed run shows the decision
        # comparison, not just the outcome.
        "transition_recorded",
        "rl_shadow",
        "iteration_complete",
        "synthesis_regenerated",
        "completed",
        "stopped",
        "error",
    }
)


async def record_session_event(session_id: str, message: dict[str, Any]) -> int | None:
    """Persist one broadcast and return its sequence number.

    Never raises: losing a log line must not break the live research stream, so
    failures are logged and reported as ``None`` (the caller then broadcasts the
    message unmodified).
    """
    event_type = str(message.get("type", ""))
    if event_type not in RECORDED_EVENT_TYPES:
        return None

    try:
        async with _session_factory() as db:
            seq = await SessionEventRepository(db).append(session_id, message)
            await db.commit()
            return seq
    except SQLAlchemyError as e:  # pragma: no cover - defensive: DB down mid-run
        logger.warning(
            f"Could not persist '{event_type}' event for session {session_id}: {e}"
        )
        return None
