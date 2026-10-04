"""Evidence strength — a defensible score in place of a flat confidence label.

A stored ``high``/``medium``/``low`` says only how sure the extractor sounded. What a
reader actually needs is:

    strength = source quality x independent support x recency
             x agreement x extraction confidence

Each factor is bounded to (0, 1] and the product is reported with its components, so
a weak claim can be *explained* ("three independent sources, but all from 2019")
instead of merely ranked.

Bands are calibrated against worked examples rather than picked for roundness:

* four independent, recent, government-grade sources → 0.86 → **high**
* two independent news sources, six months old        → 0.35 → **medium**
* one lone blog post, two years old, no corroboration → 0.08 → **low**

``HIGH_BAND``/``MEDIUM_BAND`` sit at 0.60/0.30; the low example lands an order of
magnitude below the medium one, which is the separation the label is meant to carry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from app.services.ikf.provenance import Provenance, SourceRef, build_provenance
from app.services.ikf.temporal import UNKNOWN_DATE_SCORE, recency_score

# Prior quality by source kind. Government and peer-reviewed material is the top of
# the range; social posts are not evidence of anything on their own.
SOURCE_TYPE_QUALITY = {
    "government": 1.0,
    "academic": 0.95,
    "journal": 0.9,
    "report": 0.8,
    "news": 0.75,
    "article": 0.7,
    "blog": 0.5,
    "forum": 0.35,
    "social": 0.25,
    "unknown": 0.55,
}
DEFAULT_SOURCE_QUALITY = 0.55
# The type prior anchors the score; the stored credibility refines it.
QUALITY_CREDIBILITY_BLEND = 0.6

# Independent corroboration climbs fast and then flattens: the second independent
# source matters far more than the fifth.
INDEPENDENCE_FLOOR = 0.35
INDEPENDENCE_SATURATION = 2.0

# One dissenting source should dent a claim, not erase it.
AGREEMENT_FLOOR = 0.15

EXTRACTION_CONFIDENCE = {"high": 1.0, "medium": 0.75, "low": 0.5}
DEFAULT_EXTRACTION_CONFIDENCE = 0.6

HIGH_BAND = 0.60
MEDIUM_BAND = 0.30

MIN_STRENGTH = 0.01
MAX_STRENGTH = 1.0


@dataclass
class EvidenceInput:
    """Everything needed to score one claim, already flattened by the service layer."""

    claim_id: str
    refs: list[SourceRef] = field(default_factory=list)
    extraction_confidence: str = "medium"
    extracted_at: datetime | None = None
    now: datetime | None = None
    #: Caller-supplied corroboration count when it knows better than the links.
    independent_sources: int | None = None


@dataclass
class EvidenceScore:
    """One claim's strength plus the components that produced it."""

    claim_id: str
    strength: float
    band: str
    components: dict[str, float] = field(default_factory=dict)
    provenance: Provenance | None = None

    @property
    def is_high(self) -> bool:
        return self.band == "high"

    def to_dict(self) -> dict:
        payload = {
            "claim_id": self.claim_id,
            "strength": round(self.strength, 4),
            "band": self.band,
            "components": {k: round(v, 4) for k, v in self.components.items()},
        }
        if self.provenance is not None:
            payload["provenance"] = self.provenance.to_dict()
        return payload


def band_for(strength: float) -> str:
    """Map a strength to the report's existing vocabulary."""
    if strength >= HIGH_BAND:
        return "high"
    if strength >= MEDIUM_BAND:
        return "medium"
    return "low"


def source_quality(refs: list[SourceRef]) -> float:
    """Mean source quality, weighted by how strongly each link supports the claim.

    A source linked weakly (low extraction confidence on the link) pulls the mean less
    than one linked strongly, which keeps the formula at its documented five factors
    while still using the link data.
    """
    if not refs:
        return DEFAULT_SOURCE_QUALITY

    total_weight = 0.0
    weighted = 0.0
    for ref in refs:
        kind_quality = SOURCE_TYPE_QUALITY.get(
            (ref.source_type or "unknown").lower(), DEFAULT_SOURCE_QUALITY
        )
        credibility = min(1.0, max(0.0, ref.credibility))
        quality = (
            QUALITY_CREDIBILITY_BLEND * kind_quality
            + (1 - QUALITY_CREDIBILITY_BLEND) * credibility
        )
        weight = min(1.0, max(0.05, ref.link_confidence))
        weighted += quality * weight
        total_weight += weight

    return max(0.0, min(1.0, weighted / total_weight if total_weight else 0.0))


def independent_support(count: int) -> float:
    """Saturating value of N independent sources."""
    if count <= 0:
        return INDEPENDENCE_FLOOR
    return INDEPENDENCE_FLOOR + (1 - INDEPENDENCE_FLOOR) * (
        1 - math.exp(-count / INDEPENDENCE_SATURATION)
    )


def agreement(supports: int, refutes: int) -> float:
    """Share of linked sources that support the claim, with a floor."""
    total = supports + refutes
    if total <= 0:
        return UNKNOWN_DATE_SCORE
    return max(AGREEMENT_FLOOR, supports / total)


def recency(refs: list[SourceRef], now: datetime | None = None) -> float:
    """Mean recency across linked sources; undated sources score as neutral."""
    if not refs:
        return UNKNOWN_DATE_SCORE
    scores = [recency_score(ref.published_at, now=now) for ref in refs]
    return sum(scores) / len(scores)


def extraction_confidence(label: str | None) -> float:
    return EXTRACTION_CONFIDENCE.get((label or "").lower(), DEFAULT_EXTRACTION_CONFIDENCE)


def score_claim(data: EvidenceInput) -> EvidenceScore:
    """Compute one claim's evidence strength and the components behind it."""
    provenance = build_provenance(data.refs, extracted_at=data.extracted_at)
    independent = (
        data.independent_sources
        if data.independent_sources is not None
        else provenance.independent_sources
    )

    components = {
        "source_quality": source_quality(data.refs),
        "independent_support": independent_support(independent),
        "recency": recency(data.refs, now=data.now),
        "agreement": agreement(provenance.supports, provenance.refutes),
        "extraction_confidence": extraction_confidence(data.extraction_confidence),
    }

    strength = 1.0
    for value in components.values():
        strength *= value
    strength = max(MIN_STRENGTH, min(MAX_STRENGTH, strength))

    return EvidenceScore(
        claim_id=data.claim_id,
        strength=strength,
        band=band_for(strength),
        components=components,
        provenance=provenance,
    )


def aggregate_evidence(inputs: list[EvidenceInput]) -> list[EvidenceScore]:
    """Score many claims, strongest first so the report can lead with them."""
    scores = [score_claim(item) for item in inputs]
    scores.sort(key=lambda score: score.strength, reverse=True)
    return scores


def evidence_summary(scores: list[EvidenceScore]) -> dict:
    """Run-level roll-up for telemetry, budgets and the report header."""
    if not scores:
        return {
            "claims": 0,
            "mean_strength": 0.0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "strongest_claim_id": None,
            "weakest_claim_id": None,
        }

    strengths = [score.strength for score in scores]
    ordered = sorted(scores, key=lambda score: score.strength)
    return {
        "claims": len(scores),
        "mean_strength": round(sum(strengths) / len(strengths), 4),
        "high": sum(1 for score in scores if score.band == "high"),
        "medium": sum(1 for score in scores if score.band == "medium"),
        "low": sum(1 for score in scores if score.band == "low"),
        "strongest_claim_id": ordered[-1].claim_id,
        "weakest_claim_id": ordered[0].claim_id,
    }


def confidence_from_strength(strength: float) -> str:
    """Banded label, for callers that need the old vocabulary."""
    return band_for(strength)
