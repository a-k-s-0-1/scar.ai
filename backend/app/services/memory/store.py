"""Long-term memory records and the pure rules that decide what is worth keeping.

Two ideas drive everything here:

* **Importance is set at write time, weight is computed at read time.** Importance says
  how much the fact mattered when it was learned; weight folds in how long it has sat
  unused and how often it has since been recalled. Storing a single "score" would bake
  in the date it was written.
* **Reuse is the strongest signal.** A conclusion recalled by five later runs is worth
  more than one written yesterday and never used again, so hits lift the weight rather
  than merely resetting its clock.

Everything in this module is pure so the forgetting policy is testable without a
database — a policy nobody can test is a policy nobody can trust.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

_WHITESPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
MAX_KEY_LENGTH = 240


class MemoryKind(str, Enum):
    """What kind of knowledge an item holds.

    Kept coarse on purpose: the kind decides importance and lets a caller ask for
    "what did we conclude before" without knowing how it was stored.
    """

    RESEARCH_HISTORY = "research_history"
    CLAIM = "claim"
    SOURCE = "source"
    ENTITY = "entity"
    CONCLUSION = "conclusion"
    RESOLVED_CONTRADICTION = "resolved_contradiction"
    STRATEGY = "strategy"
    SUCCESSFUL_QUERY = "successful_query"
    FAILED_QUERY = "failed_query"
    DOMAIN = "domain"
    CONSTRAINT = "user_constraint"


#: Base importance by kind. A constraint the user stated outranks anything the system
#: inferred about itself; a raw source URL is the cheapest thing to re-fetch.
BASE_IMPORTANCE: dict[str, float] = {
    MemoryKind.CONSTRAINT.value: 1.0,
    MemoryKind.RESOLVED_CONTRADICTION.value: 0.9,
    MemoryKind.CONCLUSION.value: 0.85,
    MemoryKind.STRATEGY.value: 0.8,
    MemoryKind.ENTITY.value: 0.7,
    MemoryKind.DOMAIN.value: 0.65,
    MemoryKind.CLAIM.value: 0.55,
    MemoryKind.RESEARCH_HISTORY.value: 0.5,
    MemoryKind.SUCCESSFUL_QUERY.value: 0.6,
    MemoryKind.FAILED_QUERY.value: 0.5,
    MemoryKind.SOURCE.value: 0.4,
}
DEFAULT_IMPORTANCE = 0.5

#: A recalled item gets a bounded boost: 0.15 * log1p(hits), capped so a single
#: frequently-hit item cannot permanently crowd out everything else.
REUSE_BOOST_PER_LOG_HIT = 0.15
MAX_REUSE_BOOST = 0.35

CLOSED_STRATEGY_KINDS = frozenset(
    {MemoryKind.FAILED_QUERY.value, MemoryKind.CONSTRAINT.value}
)


@dataclass
class MemoryRecord:
    """A stored item, detached from the ORM for scoring and transport."""

    id: str
    kind: str
    key: str
    text: str
    payload: dict = field(default_factory=dict)
    importance: float = DEFAULT_IMPORTANCE
    confidence: float = 0.6
    hits: int = 0
    embedding: list[float] | None = None
    embedding_model: str | None = None
    source_session_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_used_at: datetime | None = None

    @property
    def last_touched(self) -> datetime | None:
        """The freshest of the three timestamps."""
        candidates = [t for t in (self.last_used_at, self.updated_at, self.created_at) if t]
        return max(candidates) if candidates else None

    def to_dict(self, include_embedding: bool = False) -> dict:
        payload = {
            "id": self.id,
            "kind": self.kind,
            "key": self.key,
            "text": self.text,
            "payload": self.payload or {},
            "importance": round(self.importance, 4),
            "confidence": round(self.confidence, 4),
            "hits": self.hits,
            "source_session_id": self.source_session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }
        if include_embedding:
            payload["embedding_dim"] = len(self.embedding or [])
            payload["embedding_model"] = self.embedding_model
        return payload


def normalize_key(kind: str, text: str) -> str:
    """Stable dedupe key for an item, so re-learning updates instead of duplicating.

    Case, punctuation and spacing are all noise: "OpenAI, Inc." and "openai inc"
    describe the same entity and must not become two rows.
    """
    cleaned = _NON_WORD.sub(" ", (text or "").strip().lower())
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    if not cleaned:
        return f"{kind}:{abs(hash(text or '')):x}"[:MAX_KEY_LENGTH]
    return cleaned[:MAX_KEY_LENGTH]


def age_days(moment: datetime | None, now: datetime | None = None) -> float:
    """Days since ``moment``, never negative (clock skew must not add weight)."""
    if moment is None:
        return 0.0
    reference = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max(0.0, (reference - moment).total_seconds() / 86_400)


def reuse_boost(hits: int) -> float:
    """Bounded lift from being recalled, so useful knowledge survives decay."""
    if hits <= 0:
        return 0.0
    return min(MAX_REUSE_BOOST, REUSE_BOOST_PER_LOG_HIT * math.log1p(hits))


def decay_weight(
    record: MemoryRecord,
    now: datetime | None = None,
    half_life_days: int = 180,
) -> float:
    """Importance decayed by idleness, lifted by reuse. Always within ``[0, 1]``.

    Idleness is measured from the last time the item was *used*, not when it was
    written, so a fact recalled regularly never ages out.
    """
    idle = age_days(record.last_touched, now)
    decayed = record.importance * (0.5 ** (idle / max(1, half_life_days)))
    # Reuse resists decay but cannot exceed 1.0 overall, or a single hot item would
    # permanently dominate ranking.
    return max(0.0, min(1.0, decayed + reuse_boost(record.hits) * (1 - decayed)))


def should_forget(weight: float, threshold: float) -> bool:
    """Whether an item has decayed past the point of being worth its storage."""
    return weight < threshold


def importance_for(
    kind: str, confidence: float | None = None, boost: float = 0.0
) -> float:
    """Importance for a new (or refreshed) item.

    A caller-supplied confidence lets measured quality move the number — a claim the
    extractor was sure about and the evidence supports outranks a guess — but the
    per-kind base always contributes, so kind still orders the shelves.
    """
    base = BASE_IMPORTANCE.get(kind, DEFAULT_IMPORTANCE)
    if confidence is None:
        return max(0.0, min(1.0, base + boost))
    return max(0.0, min(1.0, 0.6 * base + 0.4 * confidence + boost))
