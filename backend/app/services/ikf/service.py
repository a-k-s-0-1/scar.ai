"""Knowledge intelligence service — the one place the IKF 2.0 modules meet the database.

The pure modules next door know nothing about SQLAlchemy; this layer maps ORM rows onto
their inputs and returns a single ``KnowledgeIndex`` that the orchestrator, the report
generator and the API can all read. Scores are *derived*, never stored: recomputing
them from the claims and sources on demand is cheap, deterministic, and cannot drift
away from the evidence it claims to describe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import DetachedInstanceError

from app.database.models import Claim, Source
from app.database.repository import ClaimRepository, SourceRepository
from app.services.ikf.claim_versioning import (
    ClaimVersion,
    VersionGroup,
    build_version_groups,
    versioning_summary,
)
from app.services.ikf.entity_resolution import EntityResolver, normalize_entity
from app.services.ikf.evidence import (
    EvidenceInput,
    EvidenceScore,
    aggregate_evidence,
    evidence_summary,
)
from app.services.ikf.provenance import SourceRef
from app.services.ikf.temporal import extract_validity_window
from app.utils.logger import logger

# Where a claim's own text says nothing about time, the newest supporting source is
# the best available proxy for when it was true.
FALLBACK_PUBLISHED_YEAR = True


@dataclass
class KnowledgeIndex:
    """One session's resolved entities, scored evidence and versioned claims."""

    session_id: str
    evidence: dict[str, EvidenceScore] = field(default_factory=dict)
    groups: list[VersionGroup] = field(default_factory=list)
    resolver: EntityResolver = field(default_factory=EntityResolver)
    evidence_stats: dict = field(default_factory=dict)
    version_stats: dict = field(default_factory=dict)

    def strength_of(self, claim_id: str) -> float | None:
        score = self.evidence.get(claim_id)
        return score.strength if score else None

    def band_of(self, claim_id: str) -> str | None:
        score = self.evidence.get(claim_id)
        return score.band if score else None

    def conflicted_pairs(self) -> list[tuple[str, str]]:
        return [pair for group in self.groups for pair in group.conflicts]

    def versioned_claim_ids(self) -> set[str]:
        """Claims that belong to a group whose value moved over time."""
        ids: set[str] = set()
        for group in self.groups:
            if group.status == "versioned":
                ids.update(version.claim_id for version in group.versions)
        return ids

    def to_summary(self) -> dict:
        return {
            "entities": self.resolver.stats(),
            "evidence": self.evidence_stats,
            "versions": self.version_stats,
        }


def link_to_source_ref(link: Any) -> SourceRef | None:
    """Flatten one ``ClaimSource`` row (with its ``Source`` loaded) into a ref."""
    source = getattr(link, "source", None)
    if source is None:
        return None
    return SourceRef(
        source_id=source.id,
        url=source.url or "",
        source_type=source.source_type or "unknown",
        credibility=(
            source.credibility_score if source.credibility_score is not None else 0.5
        ),
        published_at=source.published_at,
        support_type=link.support_type or "supports",
        link_confidence=link.confidence if link.confidence is not None else 0.8,
    )


def source_refs_from_links(links: list[Any]) -> list[SourceRef]:
    """Flatten explicitly loaded link rows into scoring inputs."""
    refs = [link_to_source_ref(link) for link in links or []]
    return [ref for ref in refs if ref is not None]


def claim_source_refs(claim: Claim) -> list[SourceRef]:
    """Flatten a claim's source links into scoring inputs.

    Returns nothing for a *detached* claim rather than raising: the research loop
    hands claims to later stages after their session has closed, and a lazy load there
    explodes with ``DetachedInstanceError``. Callers on that path use
    ``source_refs_from_links`` with links they loaded themselves.
    """
    try:
        links = claim.source_links
    except DetachedInstanceError:
        return []
    return source_refs_from_links(list(links or []))


def newest_published_year(refs: list[SourceRef]) -> int | None:
    """Year of the most recent supporting source, used as a date fallback."""
    years = [ref.published_at.year for ref in refs if ref.published_at is not None]
    return max(years) if years else None


def build_evidence_inputs(
    claims: list[Claim],
    now: datetime | None = None,
) -> list[EvidenceInput]:
    """Turn ORM claims into scoring inputs (pure, so tests need no database)."""
    inputs: list[EvidenceInput] = []
    for claim in claims:
        refs = claim_source_refs(claim)
        inputs.append(
            EvidenceInput(
                claim_id=claim.id,
                refs=refs,
                extraction_confidence=claim.confidence or "medium",
                extracted_at=claim.created_at,
                now=now,
            )
        )
    return inputs


def build_claim_versions(
    claims: list[Claim],
    evidence: dict[str, EvidenceScore],
    resolver: EntityResolver,
) -> list[ClaimVersion]:
    """Version each claim against its resolved subject/predicate and evidence strength."""
    versions: list[ClaimVersion] = []
    for claim in claims:
        refs = claim_source_refs(claim)
        subject_raw = (claim.subject or "").strip()
        predicate_raw = (claim.predicate or "").strip()
        if not subject_raw or not predicate_raw:
            # Without both halves there is nothing to version against; the claim still
            # keeps its evidence score, it just cannot be part of a group.
            continue

        window = extract_validity_window(
            f"{claim.claim} {claim.object or ''}",
            fallback_year=(
                newest_published_year(refs) if FALLBACK_PUBLISHED_YEAR else None
            ),
        )
        score = evidence.get(claim.id)
        versions.append(
            ClaimVersion(
                claim_id=claim.id,
                text=claim.claim,
                subject=resolver.resolve(subject_raw),
                predicate=normalize_entity(predicate_raw),
                value=(claim.object or "").strip(),
                window=window,
                confidence=claim.confidence or "medium",
                extracted_at=claim.created_at,
                source_ids=[ref.source_id for ref in refs],
                strength=score.strength if score else None,
            )
        )
    return versions


async def build_knowledge_index(
    session_id: str,
    db: AsyncSession,
    resolver: EntityResolver | None = None,
    seed_aliases: dict[str, list[str]] | None = None,
    now: datetime | None = None,
) -> KnowledgeIndex:
    """Compute the full knowledge index for a session.

    ``seed_aliases`` lets long-term memory hand in entity aliases learned in earlier
    runs, so resolution improves as the project is used rather than restarting from
    nothing every time.
    """
    reference = now or datetime.now(timezone.utc)

    claims = await ClaimRepository(db).get_by_session(session_id)
    # Sources are needed for provenance detail (type, credibility, date) even when a
    # claim's link rows are the ones carrying the relationship.
    sources = await SourceRepository(db).get_by_session(session_id)
    sources_by_id: dict[str, Source] = {source.id: source for source in sources}

    resolver = resolver or EntityResolver()
    if seed_aliases:
        resolver.seed(seed_aliases)

    evidence_inputs = build_evidence_inputs(claims, now=reference)
    scores = aggregate_evidence(evidence_inputs)
    evidence_by_id = {score.claim_id: score for score in scores}

    versions = build_claim_versions(claims, evidence_by_id, resolver)
    groups = build_version_groups(versions)

    index = KnowledgeIndex(
        session_id=session_id,
        evidence=evidence_by_id,
        groups=groups,
        resolver=resolver,
        evidence_stats={**evidence_summary(scores), "sources": len(sources_by_id)},
        version_stats=versioning_summary(groups),
    )
    logger.info(
        f"IKF index for {session_id}: {index.evidence_stats['claims']} scored claims, "
        f"{index.version_stats['versioned']} versioned groups, "
        f"{index.version_stats['conflicted']} conflicted, "
        f"{index.resolver.stats()['merges']} entity merges."
    )
    return index
