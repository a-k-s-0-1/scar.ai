"""Evidence table and contradiction API routes."""

from fastapi import APIRouter

from app.api.dependencies import ApiKeyAuth, DbSession
from app.api.errors import SessionNotFoundError
from app.api.schemas.claim import (
    ClaimModel,
    ClaimSourceLink,
    ContradictionItem,
    EvidenceResponse,
)
from app.database.repository import (
    ClaimRepository,
    ContradictionRepository,
    SessionRepository,
)

router = APIRouter(prefix="/api/research", tags=["Evidence & Contradictions"])


@router.get(
    "/{session_id}/evidence",
    response_model=EvidenceResponse,
    summary="Get extracted claims and their citations for the evidence table",
)
async def get_evidence_table(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> EvidenceResponse:
    """Retrieve all claims with linked source references and confidence levels."""
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError(session_id)

    claim_repo = ClaimRepository(db)
    claims = await claim_repo.get_by_session(session_id)

    claim_models: list[ClaimModel] = []
    for c in claims:
        source_links: list[ClaimSourceLink] = []
        for link in getattr(c, "source_links", []):
            if link.source:
                source_links.append(
                    ClaimSourceLink(
                        source_id=link.source_id,
                        url=link.source.url,
                        title=link.source.title,
                        credibility_score=link.source.credibility_score,
                        support_type=link.support_type,
                        confidence=link.confidence,
                    )
                )

        claim_models.append(
            ClaimModel(
                id=c.id,
                session_id=c.session_id,
                claim=c.claim,
                subject=c.subject,
                predicate=c.predicate,
                object=c.object,
                confidence=c.confidence,
                status=c.status,
                sources=source_links,
                created_at=c.created_at,
            )
        )

    return EvidenceResponse(
        session_id=session_id,
        total_claims=len(claim_models),
        claims=claim_models,
    )


@router.get(
    "/{session_id}/contradictions",
    response_model=list[ContradictionItem],
    summary="Get detected contradictions and conflicts between claims",
)
async def get_contradictions(
    session_id: str,
    db: DbSession,
    auth: ApiKeyAuth,
) -> list[ContradictionItem]:
    """Retrieve list of identified contradictions and their severity."""
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError(session_id)

    contra_repo = ContradictionRepository(db)
    items = await contra_repo.get_by_session(session_id)

    return [
        ContradictionItem(
            id=c.id,
            session_id=c.session_id,
            claim_1_id=c.claim_1_id,
            claim_1_text=c.claim_1.claim if c.claim_1 else "",
            claim_2_id=c.claim_2_id,
            claim_2_text=c.claim_2.claim if c.claim_2 else "",
            severity=c.severity,
            resolved=c.resolved,
            resolution_note=c.resolution_note,
            created_at=c.created_at,
        )
        for c in items
    ]
