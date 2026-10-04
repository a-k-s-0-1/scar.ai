"""Pydantic schemas for external sources."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SourceModel(BaseModel):
    """External source representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    url: str
    title: str | None = None
    source_type: str = "article"
    credibility_score: float = 0.5
    published_at: datetime | None = None
    accessed_at: datetime
    content_snippet: str | None = None
