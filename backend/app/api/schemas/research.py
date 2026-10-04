"""Pydantic schemas for research initiation and session responses."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DepthType = Literal["shallow", "standard", "deep"]
FormatType = Literal["report", "bullet_points", "briefing"]


class ResearchQuestionInput(BaseModel):
    """Payload for starting a new research session."""

    question: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="The research question to investigate",
        examples=[
            "What are the latest commercial developments in solid-state battery technology?"
        ],
    )
    depth: DepthType = Field(
        default="standard",
        description="Research depth: shallow (fast, ~3 mins), standard (comprehensive, ~5 mins), deep (~8 mins)",
    )
    domain: str | None = Field(
        default=None,
        max_length=100,
        description="Optional domain context, e.g. 'Biomedical', 'Economics', 'Computer Science'",
    )
    geographic_scope: str = Field(
        default="global",
        max_length=100,
        description="Geographic focus: 'global', 'US', 'EU', 'Asia-Pacific', etc.",
    )
    time_range: str | None = Field(
        default=None,
        max_length=100,
        description="Optional timeframe constraint, e.g. 'past_year', 'past_month', 'all_time'",
    )
    max_research_time_minutes: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum execution time in minutes before stopping",
    )
    min_sources_required: int = Field(
        default=10,
        ge=3,
        le=50,
        description="Minimum unique sources required before stopping",
    )
    output_format: FormatType = Field(
        default="report",
        description="Desired synthesis format",
    )

    @field_validator("question")
    @classmethod
    def validate_question_text(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 10:
            raise ValueError("Research question must be at least 10 characters long.")
        if len(cleaned.split()) < 3:
            raise ValueError("Research question must contain at least 3 words.")
        return cleaned


class ResearchSessionResponse(BaseModel):
    """Response returned upon session creation or lookup."""

    id: str
    question: str
    depth: str
    domain: str | None = None
    geographic_scope: str = "global"
    time_range: str | None = None
    max_research_time_minutes: int
    min_sources_required: int
    output_format: str
    status: str
    current_iteration: int
    max_iterations: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    estimated_time_seconds: int = 300
    error_message: str | None = None
    total_sources: int = 0
    total_claims: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StopSessionResponse(BaseModel):
    """Response returned when stopping a session."""

    session_id: str
    status: str
    message: str


class RetrySynthesisResponse(BaseModel):
    """Result of a one-click report re-synthesis."""

    session_id: str
    status: str
    synthesis: str
    retry_count: int
    max_retries: int
    report_data: dict[str, Any]


class SessionEventItem(BaseModel):
    """One persisted progress event from a session's timeline."""

    seq: int
    type: str
    iteration: int | None = None
    payload: dict[str, Any]
    created_at: datetime


class SessionEventsResponse(BaseModel):
    """Replayable event timeline for a session."""

    session_id: str
    total: int
    latest_seq: int
    events: list[SessionEventItem]
