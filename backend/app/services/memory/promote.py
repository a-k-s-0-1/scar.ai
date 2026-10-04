"""Memory promotion (V2 2.12) — choose what a finished run is allowed to leave behind.

Promotion is deliberately selective. A deep run produces hundreds of claims; storing
all of them would make the memory store a second, worse copy of the database, and
recall quality would fall as volume rose. So the rules are:

* claims are ranked by **evidence strength** (the IKF score), not by how confident the
  extractor sounded, and only the top slice is stored;
* sources are ranked by credibility and capped;
* conclusions, strategies and constraints are stored because they are already
  synthesised judgements rather than raw findings;
* facts observed more than once are stored with their full version history, so a later
  contradiction can be seen against what was known before rather than overwriting it.

The same logic serves two callers: the end of a live run (Phase 2.1's write half) and
``POST /api/memory/promote``, which re-promotes a session recorded before memory
existed. Both paths are idempotent: memory keys are content-derived, so re-promoting a
session updates what is there instead of duplicating it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import ClaimRepository, SourceRepository
from app.services.ikf import build_knowledge_index, extraction_confidence
from app.services.memory.service import LongTermMemory
from app.services.memory.versions import claim_version_from_ikf
from app.utils.logger import logger

#: Caps for one promotion. Chosen so a single run can seed memory meaningfully without
#: letting any one investigation dominate what later runs recall.
DEFAULT_MAX_CLAIMS = 25
DEFAULT_MAX_SOURCES = 10
DEFAULT_MAX_VERSION_GROUPS = 15


async def promote_session(
    session_id: str,
    db: AsyncSession,
    memory: LongTermMemory,
    *,
    max_claims: int = DEFAULT_MAX_CLAIMS,
    max_sources: int = DEFAULT_MAX_SOURCES,
    max_version_groups: int = DEFAULT_MAX_VERSION_GROUPS,
) -> dict[str, Any]:
    """Re-derive the durable knowledge from a finished session's stored rows.

    Returns counts per memory kind plus what the claim-version layer decided
    (superseded / conflicting / needs verification), so promotion is observable.
    """
    claims = await ClaimRepository(db).get_by_session(session_id)
    sources = await SourceRepository(db).get_by_session(session_id)
    if not claims and not sources:
        return {"stored": {}, "updates": {}, "reason": "session has no evidence"}

    index = await build_knowledge_index(session_id, db)

    def strength(claim: Any) -> float:
        score = index.evidence.get(claim.id)
        if score is not None:
            return score.strength
        return extraction_confidence(claim.confidence)

    ranked_claims = sorted(claims, key=strength, reverse=True)
    ranked_sources = sorted(
        sources, key=lambda source: source.credibility_score or 0.0, reverse=True
    )
    url_by_source_id = {source.id: source.url for source in sources}

    version_groups: list[dict[str, Any]] = []
    ordered_groups = sorted(
        index.groups,
        key=lambda group: (len(group.versions), len(group.conflicts)),
        reverse=True,
    )
    for group in ordered_groups:
        if not group.versions:
            continue
        version_groups.append(
            {
                "subject": group.subject,
                "predicate": group.predicate,
                "versions": [
                    claim_version_from_ikf(
                        version,
                        session_id=session_id,
                        sources=[
                            url
                            for url in (
                                url_by_source_id.get(source_id)
                                for source_id in version.source_ids
                            )
                            if url
                        ],
                    )
                    for version in group.versions
                ],
            }
        )

    stored = await memory.remember_outcome(
        session_id=session_id,
        question=await _question_for(session_id, db),
        summary="",
        stop_reason="promoted from stored evidence",
        stats={"sources": len(sources), "claims": len(claims)},
        claims=[
            (claim.claim, round(strength(claim), 4))
            for claim in ranked_claims[:max_claims]
        ],
        sources=[
            (source.url, source.title or "", float(source.credibility_score or 0.5))
            for source in ranked_sources[:max_sources]
        ],
    )
    updates = await memory.remember_claim_versions(
        version_groups[:max_version_groups], session_id=session_id
    )
    logger.info(
        f"Promoted session {session_id} into memory: "
        f"{sum(stored.values())} item(s), {updates.updated_facts} versioned fact(s)."
    )
    return {"stored": stored, "updates": updates.to_dict()}


async def _question_for(session_id: str, db: AsyncSession) -> str:
    """The session's question, or a stable placeholder if the row is gone."""
    from app.database.repository import SessionRepository

    session = await SessionRepository(db).get_by_id(session_id)
    return session.question if session is not None else f"promoted session {session_id}"
