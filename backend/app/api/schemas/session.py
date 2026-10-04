"""Pydantic schemas for session list and summaries."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SessionSummary(BaseModel):
    """Summary of a research session for dashboard listing."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    question: str
    depth: str
    status: str
    current_iteration: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    sources_count: int = 0
    claims_count: int = 0


class SessionListResponse(BaseModel):
    """Paginated list of research sessions."""

    total: int
    sessions: list[SessionSummary]
