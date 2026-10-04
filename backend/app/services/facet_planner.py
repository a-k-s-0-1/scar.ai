"""Facet-aware research planning.

V1 asked "what should I search next?" and answered from a flat list of
LLM-generated gap queries. That list had no memory of what had already been
covered, so a session could spend three iterations on the same dimension of a
question under slightly different wording while another dimension had no
evidence at all.

This module keeps a coverage model instead: which dimensions a question
decomposes into, how much evidence each one actually has, and which dimension is
the largest *useful* gap.

The planner is deliberately deterministic. Facet attribution runs over every
claim of every iteration, so it must be free and testable offline rather than
another model call; an LLM-refined facet set can be layered on top later.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.database.models import Claim
from app.services.depth_config import get_depth_profile
from app.services.metrics import saturate_coverage
from app.services.search_memory import SearchMemory

# Display and tie-break order. Iteration follows this order, so an equal-scoring
# claim lands on the earlier facet deterministically.
FACET_ORDER: tuple[str, ...] = (
    "feasibility",
    "technical",
    "economic",
    "environmental",
    "regulatory",
    "risks",
    "impact",
    "timeline",
    "alternatives",
    "recent_evidence",
)

# Lexicons, not classifiers: a facet is worth counting evidence for when the
# words that signal it show up in the claim text.
FACET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "feasibility": (
        "feasib",
        "viab",
        "scalab",
        "practical",
        "realistic",
        "implement",
        "adopt",
        "commerciali",
    ),
    "technical": (
        "technical",
        "technolog",
        "efficien",
        "performance",
        "engineering",
        "capacity",
        "specification",
        "throughput",
        "reliab",
        "yield",
        "design",
    ),
    "economic": (
        "cost",
        "price",
        "economic",
        "roi",
        "investment",
        "subsid",
        "market",
        "capex",
        "opex",
        "funding",
        "budget",
        "affordab",
        "payback",
        "revenue",
        "expens",
    ),
    "environmental": (
        "emission",
        "environment",
        "carbon",
        "climate",
        "sustainab",
        "pollut",
        "ecolog",
        "footprint",
        "land use",
        "recycl",
    ),
    "regulatory": (
        "regulat",
        "policy",
        "legislation",
        "compliance",
        "permit",
        "standard",
        "government",
        "tax credit",
        "incentive",
        "approval",
        "licens",
    ),
    "risks": (
        "risk",
        "concern",
        "challenge",
        "barrier",
        "uncertain",
        "limitation",
        "obstacle",
        "drawback",
        "downside",
        "threat",
        "safety",
        "fail",
    ),
    "impact": (
        "impact",
        "benefit",
        "outcome",
        "effect",
        "improve",
        "growth",
        "job",
        "gdp",
        "health",
        "wellbeing",
    ),
    "timeline": (
        "timeline",
        "deadline",
        "roadmap",
        "schedule",
        "milestone",
        "by 20",
        "target date",
        "deploy by",
    ),
    "alternatives": (
        "alternative",
        "compare",
        "versus",
        " vs ",
        "instead",
        "competitor",
        "substitute",
        "option",
        "rival",
    ),
    "recent_evidence": (
        "latest",
        "recent",
        "new study",
        "current",
        "this year",
        "pilot",
        "announced",
        "2025",
        "2026",
        "2027",
    ),
}

# How much an un-evidenced dimension costs the answer. A missing feasibility or
# technical dimension invalidates a viability verdict; a missing alternatives
# comparison weakens it.
FACET_WEIGHTS: dict[str, float] = {
    "feasibility": 1.15,
    "technical": 1.05,
    "economic": 1.0,
    "regulatory": 0.95,
    "risks": 0.95,
    "environmental": 0.9,
    "impact": 0.85,
    "timeline": 0.85,
    "alternatives": 0.8,
    "recent_evidence": 0.75,
}

# A "is it viable / worth it" question is an evaluation, so it implies the full
# set of evaluation dimensions even though the wording names none of them.
VIABILITY_FACETS: tuple[str, ...] = (
    "feasibility",
    "technical",
    "economic",
    "environmental",
    "regulatory",
    "risks",
    "alternatives",
    "recent_evidence",
)

DEFAULT_FACETS: tuple[str, ...] = (
    "feasibility",
    "technical",
    "economic",
    "risks",
    "recent_evidence",
)

_VIABILITY_MARKERS: tuple[str, ...] = (
    "viab",
    "feasib",
    "worth it",
    "worthwhile",
    "succeed",
    "realistic",
    "practical",
    "overhyped",
    "sustainable",
)

# Facets at or below this coverage are reported as gaps and targeted next.
FACET_GAP_THRESHOLD = 0.5

# Per-facet evidence target is a share of the depth profile's claim target: a
# dimension is not expected to carry a whole session's worth of claims.
_FACET_TARGET_SHARE = 0.5

# Query shapes per facet. Rotating through them is what turns "search the same
# thing again" into "search the angle that is still missing".
FACET_QUERY_TEMPLATES: dict[str, tuple[str, ...]] = {
    "feasibility": (
        "{subject} feasibility and scalability evidence",
        "{subject} practical implementation challenges",
    ),
    "technical": (
        "{subject} technical performance and specifications",
        "{subject} technical limitations and efficiency data",
    ),
    "economic": (
        "{subject} cost and economic viability",
        "{subject} investment, subsidies and payback period",
    ),
    "environmental": (
        "{subject} environmental impact and emissions data",
        "{subject} environmental tradeoffs and lifecycle analysis",
    ),
    "regulatory": (
        "{subject} regulation, policy and compliance requirements",
        "{subject} government incentives and regulatory barriers",
    ),
    "risks": (
        "{subject} risks and failure modes",
        "{subject} challenges, barriers and downside evidence",
    ),
    "impact": (
        "{subject} measurable impact and outcomes",
        "{subject} economic and social effects",
    ),
    "timeline": (
        "{subject} deployment timeline and milestones",
        "{subject} target dates and commercialisation schedule",
    ),
    "alternatives": (
        "{subject} alternatives and competing approaches",
        "{subject} comparison with alternative solutions",
    ),
    "recent_evidence": (
        "{subject} latest results and announcements",
        "{subject} most recent studies and pilot results",
    ),
}

_LEADING_STOPWORDS = frozenset(
    {
        "is",
        "are",
        "was",
        "were",
        "can",
        "could",
        "should",
        "would",
        "will",
        "do",
        "does",
        "did",
        "what",
        "which",
        "who",
        "how",
        "why",
        "when",
        "where",
        "the",
        "a",
        "an",
        "to",
        "be",
        "of",
        "for",
        "in",
        "on",
        "at",
        "with",
    }
)

# Evaluation words end a question but add nothing to a search query: "solar
# green hydrogen viable" searches worse than "solar green hydrogen".
_TRAILING_STOPWORDS = frozenset(
    {
        "viable",
        "viability",
        "feasible",
        "feasibility",
        "worth",
        "it",
        "realistic",
        "practical",
        "sustainable",
        "possible",
        "and",
        "or",
        "the",
        "a",
        "an",
    }
)


def _subject_phrase(question: str) -> str:
    """Reduce a question to the subject it is really about.

    Search engines match noun phrases, not interrogatives, so the leading
    question words and the trailing evaluation word are stripped.
    """
    cleaned = question.strip().rstrip("?.!").strip()
    words = [word for word in re.split(r"\s+", cleaned) if word]
    while words and words[0].lower().strip(",;:") in _LEADING_STOPWORDS:
        words.pop(0)
    while words and words[-1].lower().strip(",;:") in _TRAILING_STOPWORDS:
        words.pop()
    phrase = " ".join(words[:14]).strip()
    return phrase or cleaned[:80]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def classify_facet_text(text: str) -> str:
    """Return the best-matching facet for a piece of text, or ``""``.

    Facets are scored by how many of their signal words appear, and ties resolve
    to facet order so the same text always classifies the same way.
    """
    haystack = _normalize(text)
    if not haystack:
        return ""

    best_facet = ""
    best_score = 0
    for facet in FACET_ORDER:
        score = sum(1 for keyword in FACET_KEYWORDS[facet] if keyword in haystack)
        if score > best_score:
            best_facet, best_score = facet, score
    return best_facet


def classify_claim_facet(claim: Claim) -> str:
    """Attribute a claim to the dimension of the question it speaks to."""
    parts = [
        claim.claim or "",
        claim.subject or "",
        claim.predicate or "",
        claim.object or "",
    ]
    return classify_facet_text(" ".join(parts))


def extract_facets(question: str) -> tuple[str, ...]:
    """Work out which dimensions a question decomposes into.

    A fixed ten-dimension meter over a narrow question is noise, and a fixed
    three-dimension meter over an evaluation question hides the dimension that is
    actually missing, so the set is derived from the wording.
    """
    text = _normalize(question)
    facets = {
        facet
        for facet in FACET_ORDER
        if any(keyword in text for keyword in FACET_KEYWORDS[facet])
    }
    if any(marker in text for marker in _VIABILITY_MARKERS):
        facets.update(VIABILITY_FACETS)
    if not facets:
        facets.update(DEFAULT_FACETS)
    return tuple(facet for facet in FACET_ORDER if facet in facets)


@dataclass(frozen=True)
class FacetCoverage:
    """How much evidence one dimension of the question currently has."""

    facet: str
    claims: int
    coverage: float
    is_gap: bool


@dataclass(frozen=True)
class FacetSnapshot:
    """The whole coverage model at one iteration."""

    iteration: int
    coverage: float
    facets: tuple[FacetCoverage, ...]
    gaps: tuple[str, ...]

    @property
    def weakest(self) -> str | None:
        """The single most valuable missing dimension, if any."""
        return self.gaps[0] if self.gaps else None


@dataclass(frozen=True)
class FacetQuery:
    """A query chosen to fill a specific coverage gap."""

    facet: str
    query: str


class FacetPlanner:
    """Tracks per-facet coverage for one research question and targets the gaps."""

    def __init__(self, question: str, depth: str = "standard") -> None:
        self.question = question
        self.depth = depth
        self.facets: tuple[str, ...] = extract_facets(question)
        self._subject = _subject_phrase(question)
        self._snapshot: FacetSnapshot | None = None

        target_claims = get_depth_profile(depth).target_claims
        self._per_facet_target = max(
            2, round(target_claims * _FACET_TARGET_SHARE / len(self.facets))
        )

    @property
    def per_facet_target(self) -> int:
        """Claim count at which a dimension counts as well evidenced."""
        return self._per_facet_target

    def observe(
        self, claims: Sequence[Claim], *, iteration: int = 0
    ) -> FacetSnapshot:
        """Recompute coverage from the session's current claim corpus."""
        counts = dict.fromkeys(self.facets, 0)
        for claim in claims:
            facet = classify_claim_facet(claim)
            if facet in counts:
                counts[facet] += 1

        coverages = []
        for facet in self.facets:
            coverage = saturate_coverage(
                counts[facet] / max(1, self._per_facet_target)
            )
            coverages.append(
                FacetCoverage(
                    facet=facet,
                    claims=counts[facet],
                    coverage=coverage,
                    is_gap=coverage < FACET_GAP_THRESHOLD,
                )
            )

        gaps = tuple(
            entry.facet
            for entry in sorted(
                (entry for entry in coverages if entry.is_gap),
                key=lambda entry: (
                    (1.0 - entry.coverage) * FACET_WEIGHTS.get(entry.facet, 0.8)
                ),
                reverse=True,
            )
        )

        snapshot = FacetSnapshot(
            iteration=iteration,
            coverage=round(
                sum(entry.coverage for entry in coverages) / max(1, len(coverages)), 3
            ),
            facets=tuple(coverages),
            gaps=gaps,
        )
        self._snapshot = snapshot
        return snapshot

    def snapshot(self) -> FacetSnapshot | None:
        """Last computed coverage model, if the planner has observed any claims."""
        return self._snapshot

    def next_query(
        self,
        *,
        preferred: Sequence[str] = (),
        memory: SearchMemory | None = None,
    ) -> FacetQuery | None:
        """Choose the query that buys the most coverage for one search.

        A gap-detector query is used when it happens to target a missing
        dimension (it is content-specific and usually the better query); the
        facet templates fill the gaps the detector did not mention. Queries
        already issued, and dimensions whose every attempt came back empty, are
        skipped rather than paid for twice.

        Dimensions nobody has searched yet come first. One search that came back
        thin may just have found the wrong material, but a dimension that was never
        looked at is still an unknown, and re-wording a search that already ran is
        the least likely way to learn something new.
        """
        if self._snapshot is None or not self._snapshot.gaps:
            return None

        exhausted = memory.exhausted_facets() if memory is not None else set()
        candidates = tuple(
            facet for facet in self._snapshot.gaps if facet not in exhausted
        )
        if not candidates:
            return None

        def attempts(facet: str) -> int:
            return memory.attempts_for_facet(facet) if memory is not None else 0

        untried = tuple(facet for facet in candidates if attempts(facet) == 0)
        retried = tuple(facet for facet in candidates if attempts(facet) > 0)
        candidate_facets = (*untried, *retried)

        for candidate in preferred:
            clean = candidate.strip()
            if not clean or (memory is not None and memory.attempted(clean)):
                continue
            facet = classify_facet_text(clean)
            if facet in candidate_facets:
                return FacetQuery(facet=facet, query=clean)

        # Within a bucket, gap weight decides; across buckets, a first look beats a
        # second one.
        for facet in candidate_facets:
            for template in FACET_QUERY_TEMPLATES.get(
                facet, ("{subject} " + facet.replace("_", " "),)
            ):
                query = template.format(subject=self._subject)
                if memory is not None and memory.attempted(query):
                    continue
                return FacetQuery(facet=facet, query=query)

        return None

    def describe(self) -> dict[str, Any]:
        """Compact view of the coverage model for logs and diagnostics."""
        if self._snapshot is None:
            return {"question": self.question, "facets": list(self.facets)}
        return {
            "question": self.question,
            "coverage": self._snapshot.coverage,
            "gaps": list(self._snapshot.gaps),
            "facets": [
                {
                    "facet": entry.facet,
                    "claims": entry.claims,
                    "coverage": entry.coverage,
                }
                for entry in self._snapshot.facets
            ],
        }
