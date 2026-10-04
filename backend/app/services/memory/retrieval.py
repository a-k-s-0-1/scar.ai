"""Memory retrieval — score candidates, then rank them.

Recall blends three signals, and the weights change depending on whether a query
vector exists:

* **lexical overlap** (always available) — token overlap with a containment bonus, so
  an exact phrase match beats a bag of shared words;
* **embedding similarity** — semantic, when a provider gave us vectors;
* **decay weight** — importance and reuse, so ranking is stable rather than arbitrary
  among equally relevant items.

Without embeddings the lexical and decay weights are renormalised instead of leaving
the embedding term at zero, which would silently cap every score at 65 % and make the
absolute numbers incomparable between runs with and without vectors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.services.memory.embeddings import cosine_similarity
from app.services.memory.store import MemoryRecord, decay_weight

_TOKEN = re.compile(r"[a-z0-9]+")

# Stop words carry no retrieval signal and would let "the" match everything.
STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
        "was", "were", "be", "been", "it", "its", "this", "that", "with", "as",
        "by", "at", "from", "how", "what", "why", "when", "which", "who",
    }
)

#: Relative pull of each signal when a query vector is available.
WEIGHT_LEXICAL = 0.45
WEIGHT_EMBEDDING = 0.35
WEIGHT_DECAY = 0.20

#: Exact phrase containment is much stronger evidence than token overlap alone.
CONTAINMENT_BONUS = 0.25


def tokenize(text: str) -> set[str]:
    """Lowercase word tokens with stop words removed."""
    return {
        token
        for token in _TOKEN.findall((text or "").lower())
        if token not in STOPWORDS and len(token) > 1
    }


def lexical_score(query_tokens: set[str], text: str) -> float:
    """Overlap between query tokens and a candidate, in ``[0, 1]``."""
    if not query_tokens or not text:
        return 0.0

    candidate_tokens = tokenize(text)
    if not candidate_tokens:
        return 0.0

    overlap = len(query_tokens & candidate_tokens)
    if overlap == 0:
        return 0.0

    # Jaccard rewards precision, the coverage ratio rewards recall; averaging them
    # keeps a very long candidate from being penalised just for being long.
    jaccard = overlap / len(query_tokens | candidate_tokens)
    coverage = overlap / len(query_tokens)
    score = 0.5 * jaccard + 0.5 * coverage

    lowered = text.lower()
    if " ".join(sorted(query_tokens)) and all(
        token in lowered for token in query_tokens
    ):
        score = min(1.0, score + CONTAINMENT_BONUS)
    return min(1.0, score)


@dataclass
class ScoredMemory:
    """A recalled item with the score that put it there."""

    record: MemoryRecord
    score: float
    lexical: float
    semantic: float
    decay: float

    def to_dict(self) -> dict:
        payload = self.record.to_dict()
        payload["recall"] = {
            "score": round(self.score, 4),
            "lexical": round(self.lexical, 4),
            "semantic": round(self.semantic, 4),
            "decay": round(self.decay, 4),
        }
        return payload


def score_record(
    record: MemoryRecord,
    query_tokens: set[str],
    query_vector: list[float] | None,
    now: datetime | None = None,
    half_life_days: int = 180,
) -> ScoredMemory:
    """Score one candidate against a query."""
    lexical = lexical_score(query_tokens, f"{record.text} {record.key}")
    semantic = cosine_similarity(query_vector, record.embedding)
    decay = decay_weight(record, now=now, half_life_days=half_life_days)

    if query_vector and record.embedding:
        score = (
            WEIGHT_LEXICAL * lexical
            + WEIGHT_EMBEDDING * semantic
            + WEIGHT_DECAY * decay
        )
    else:
        # Renormalised: with no vectors, spending 35 % of the score on a signal that
        # is always zero would just compress every score.
        span = WEIGHT_LEXICAL + WEIGHT_DECAY
        score = (WEIGHT_LEXICAL * lexical + WEIGHT_DECAY * decay) / span

    return ScoredMemory(
        record=record, score=score, lexical=lexical, semantic=semantic, decay=decay
    )


def rank_records(
    records: list[MemoryRecord],
    query: str,
    query_vector: list[float] | None = None,
    limit: int = 8,
    now: datetime | None = None,
    half_life_days: int = 180,
    require_relevance: bool = True,
) -> list[ScoredMemory]:
    """Rank candidates for a query, dropping ones with nothing to do with it.

    ``require_relevance`` exists because "most relevant of an irrelevant set" is not a
    recall. With embeddings available, semantic similarity alone can qualify a hit;
    without them an item must share at least one token with the query.
    """
    query_tokens = tokenize(query)
    scored = [
        score_record(
            record,
            query_tokens,
            query_vector,
            now=now,
            half_life_days=half_life_days,
        )
        for record in records
    ]

    if require_relevance:
        scored = [
            item
            for item in scored
            if item.lexical > 0.0
            or (query_vector is not None and item.semantic >= 0.35)
        ]

    scored.sort(key=lambda item: (item.score, item.decay), reverse=True)
    return scored[: max(1, limit)]
