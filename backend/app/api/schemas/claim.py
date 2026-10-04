"""Pydantic schemas for factual claims and contradiction pairs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ConfidenceLevel = Literal["high", "medium", "low"]
ContradictionSeverity = Literal["low", "medium", "high"]


class ClaimSourceLink(BaseModel):
    """Link between claim and supporting source."""

    source_id: str
    url: str
    title: str | None = None
    credibility_score: float = 0.5
    support_type: str = "supports"
    confidence: float = 0.8


class ClaimModel(BaseModel):
    """Factual atomic claim schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    claim: str
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    confidence: str = "medium"
    status: str = "active"
    sources: list[ClaimSourceLink] = []
    created_at: datetime


class ContradictionItem(BaseModel):
    """Contradiction pair flagged between two claims."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    claim_1_id: str
    claim_1_text: str
    claim_2_id: str
    claim_2_text: str
    severity: str = "medium"
    resolved: bool = False
    resolution_note: str | None = None
    created_at: datetime


class EvidenceResponse(BaseModel):
    """List of claims with their citations for the evidence table."""

    session_id: str
    total_claims: int
    claims: list[ClaimModel]
