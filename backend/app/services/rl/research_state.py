"""Formal research state (V2 2.1) — the observation a policy decision is made from.

``decision_engine.KnowledgeState`` is the JEV heuristic's *input*; it was never meant
to be stored. A trajectory, however, is only useful for offline learning if its state
is (a) complete enough to reproduce the decision, (b) serialisable into JSON and
(c) small — a state snapshot is written once per iteration per session, and an
unbounded snapshot would put raw source text into the learning dataset.

This module is therefore a *formal* state: a flat, rounded, JSON-compatible record
plus the derived signals a policy needs (discretised feature bins and a stable hash).
It deliberately contains no ORM imports and no database access, so it can be built,
compared and tested without a session.

Design decisions worth stating:

* **Aggregates, not content.** Counts, means and ids only: no claim text, no source
  bodies, no query history. ``unresolved_gaps`` is capped, because a gap list can grow
  with the corpus while its usefulness does not.
* **Rounded at the boundary.** Floats are rounded to ``STATE_PRECISION`` when
  serialised so the same run replays to the same bytes, which is what makes the state
  hash meaningful.
* **The hash is over the serialised payload.** Two states that serialise identically
  hash identically; the hash is what telemetry logs and duplicate detection compare.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

#: Decimal places kept for every float in a serialised state. Four is enough to
#: distinguish coverage 0.6543 from 0.6544 while absorbing float noise.
STATE_PRECISION = 4

#: Gaps are context for a decision, not an archive: the strongest few carry the
#: signal, and a snapshot is written every iteration.
MAX_GAPS_STORED = 8

#: Percentile-style bins for the discretised feature encoding used by the offline
#: policy. Each tuple is (upper bound, label); the label of the first bound a value
#: falls at or below wins. Values above the last bound take the top label.
COVERAGE_BINS: list[tuple[float, str]] = [
    (0.40, "very_low"),
    (0.65, "low"),
    (0.80, "medium"),
    (1.01, "high"),
]
GAIN_BINS: list[tuple[float, str]] = [
    (0.10, "flat"),
    (0.30, "some"),
    (1.01, "high"),
]
FACET_BINS: list[tuple[float, str]] = [
    (0.25, "none"),
    (0.50, "partial"),
    (0.75, "good"),
    (1.01, "full"),
]


def bin_label(value: float, bins: list[tuple[float, str]]) -> str:
    """Map a number onto the first bin whose upper bound it does not exceed."""
    for upper, label in bins:
        if value <= upper:
            return label
    return bins[-1][1]


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), STATE_PRECISION)


@dataclass(frozen=True)
class ResearchState:
    """One deterministic, serialisable snapshot of a research run.

    Field names follow the existing codebase vocabulary (``coverage``,
    ``information_gain``, ``unresolved_contradictions``) rather than inventing a second
    dialect for the same quantities.
    """

    session_id: str
    question: str
    iteration: int
    depth: str
    total_sources: int
    total_claims: int
    total_nodes: int
    total_edges: int
    information_gain: float
    coverage: float
    unresolved_contradictions: int
    resolved_contradictions: int
    unresolved_gaps: tuple[str, ...]
    facet_coverage: float
    source_quality: float
    source_diversity: int
    confidence_distribution: dict[str, int]
    duplicate_count: int
    time_elapsed: float
    remaining_time: float
    remaining_search_budget: int
    remaining_llm_budget: int
    max_iterations: int
    previous_action: str | None = None
    previous_reward: float | None = None
    #: Which query the run is currently working from; useful for duplicate detection
    #: and for replay, and deliberately the *only* free text beyond the question.
    current_query: str | None = None
    #: True when the latest iteration's contradiction set has already been verified.
    contradictions_are_new: bool = True
    #: Consecutive iterations whose information gain stayed under the plateau floor.
    plateau_iterations: int = 0
    #: Number of independent model calls the session has spent, and their ceiling.
    llm_calls: int = 0

    # ─── serialisation ───────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        """JSON-compatible payload. Key order is irrelevant; content is canonical."""
        return {
            "session_id": self.session_id,
            "question": self.question,
            "iteration": int(self.iteration),
            "depth": self.depth,
            "total_sources": int(self.total_sources),
            "total_claims": int(self.total_claims),
            "total_nodes": int(self.total_nodes),
            "total_edges": int(self.total_edges),
            "information_gain": _round(self.information_gain),
            "coverage": _round(self.coverage),
            "unresolved_contradictions": int(self.unresolved_contradictions),
            "resolved_contradictions": int(self.resolved_contradictions),
            "unresolved_gaps": list(self.unresolved_gaps[:MAX_GAPS_STORED]),
            "facet_coverage": _round(self.facet_coverage),
            "source_quality": _round(self.source_quality),
            "source_diversity": int(self.source_diversity),
            "confidence_distribution": {
                key: int(self.confidence_distribution.get(key, 0))
                for key in ("high", "medium", "low")
            },
            "duplicate_count": int(self.duplicate_count),
            "time_elapsed": _round(self.time_elapsed),
            "remaining_time": _round(self.remaining_time),
            "remaining_search_budget": int(self.remaining_search_budget),
            "remaining_llm_budget": int(self.remaining_llm_budget),
            "max_iterations": int(self.max_iterations),
            "previous_action": self.previous_action,
            "previous_reward": _round(self.previous_reward),
            "current_query": self.current_query,
            "contradictions_are_new": bool(self.contradictions_are_new),
            "plateau_iterations": int(self.plateau_iterations),
            "llm_calls": int(self.llm_calls),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ResearchState:
        """Inverse of :meth:`to_dict`; tolerant of extra keys from newer versions."""
        return cls(
            session_id=str(payload.get("session_id", "")),
            question=str(payload.get("question", "")),
            iteration=int(payload.get("iteration", 0)),
            depth=str(payload.get("depth", "standard")),
            total_sources=int(payload.get("total_sources", 0)),
            total_claims=int(payload.get("total_claims", 0)),
            total_nodes=int(payload.get("total_nodes", 0)),
            total_edges=int(payload.get("total_edges", 0)),
            information_gain=float(payload.get("information_gain", 0.0)),
            coverage=float(payload.get("coverage", 0.0)),
            unresolved_contradictions=int(
                payload.get("unresolved_contradictions", 0)
            ),
            resolved_contradictions=int(payload.get("resolved_contradictions", 0)),
            unresolved_gaps=tuple(payload.get("unresolved_gaps") or ()),
            facet_coverage=float(payload.get("facet_coverage", 0.0)),
            source_quality=float(payload.get("source_quality", 0.0)),
            source_diversity=int(payload.get("source_diversity", 0)),
            confidence_distribution={
                str(key): int(value)
                for key, value in (payload.get("confidence_distribution") or {}).items()
            },
            duplicate_count=int(payload.get("duplicate_count", 0)),
            time_elapsed=float(payload.get("time_elapsed", 0.0)),
            remaining_time=float(payload.get("remaining_time", 0.0)),
            remaining_search_budget=int(payload.get("remaining_search_budget", 0)),
            remaining_llm_budget=int(payload.get("remaining_llm_budget", 0)),
            max_iterations=int(payload.get("max_iterations", 0)),
            previous_action=payload.get("previous_action"),
            previous_reward=(
                None
                if payload.get("previous_reward") is None
                else float(payload["previous_reward"])
            ),
            current_query=payload.get("current_query"),
            contradictions_are_new=bool(payload.get("contradictions_are_new", True)),
            plateau_iterations=int(payload.get("plateau_iterations", 0)),
            llm_calls=int(payload.get("llm_calls", 0)),
        )

    @classmethod
    def from_json(cls, raw: str) -> ResearchState:
        return cls.from_dict(json.loads(raw))

    def to_json(self) -> str:
        """Canonical JSON: sorted keys, no whitespace, stable across processes."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def state_hash(self) -> str:
        """Stable fingerprint of this state over its canonical serialisation."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    def state_size(self) -> int:
        """Byte size of the serialised state, so telemetry can warn on growth."""
        return len(self.to_json().encode("utf-8"))

    # ─── derived signals ─────────────────────────────────────────────────────
    def budget_pressure(self) -> float:
        """Share of the session's remaining allowances already spent, 0.0–1.0."""
        time_total = self.time_elapsed + self.remaining_time
        time_spent = (self.time_elapsed / time_total) if time_total > 0 else 0.0
        llm_total = self.llm_calls + self.remaining_llm_budget
        llm_spent = (self.llm_calls / llm_total) if llm_total > 0 else 0.0
        return round(max(time_spent, llm_spent), STATE_PRECISION)

    def features(self) -> dict[str, str]:
        """Discretised context used as the tabular policy's state key.

        Every feature is categorical and bounded, so the table cannot grow without
        limit: there are at most 4 × 3 × 3 × 2 × 4 × 2 × 3 × 5 contexts.
        """
        return {
            "coverage": bin_label(self.coverage, COVERAGE_BINS),
            "gain": bin_label(self.information_gain, GAIN_BINS),
            "contradictions": (
                "none"
                if self.unresolved_contradictions == 0
                else "few"
                if self.unresolved_contradictions <= 2
                else "many"
            ),
            "gaps": "none" if not self.unresolved_gaps else "some",
            "facets": bin_label(self.facet_coverage, FACET_BINS),
            "budget": "tight" if self.budget_pressure() >= 0.8 else "ok",
            "phase": (
                "early"
                if self.iteration <= 1
                else "late"
                if self.max_iterations and self.iteration >= self.max_iterations - 1
                else "mid"
            ),
            "previous": (self.previous_action or "NONE").upper(),
        }

    def state_key(self) -> str:
        """One string key for the discretised context (stable feature order)."""
        features = self.features()
        return "|".join(f"{name}={value}" for name, value in features.items())


def build_research_state(
    *,
    session_id: str,
    question: str,
    iteration: int,
    depth: str = "standard",
    max_iterations: int = 0,
    total_sources: int = 0,
    total_claims: int = 0,
    total_nodes: int = 0,
    total_edges: int = 0,
    information_gain: float = 0.0,
    coverage: float = 0.0,
    unresolved_contradictions: int = 0,
    resolved_contradictions: int = 0,
    gaps: list[str] | tuple[str, ...] | None = None,
    facet_coverage: float = 0.0,
    source_quality: float = 0.0,
    source_diversity: int = 0,
    confidence_distribution: dict[str, int] | None = None,
    duplicate_count: int = 0,
    time_elapsed: float = 0.0,
    remaining_time: float = 0.0,
    remaining_search_budget: int = 0,
    remaining_llm_budget: int = 0,
    previous_action: str | None = None,
    previous_reward: float | None = None,
    current_query: str | None = None,
    contradictions_are_new: bool = True,
    plateau_iterations: int = 0,
    llm_calls: int = 0,
) -> ResearchState:
    """Build a state with every field explicit, defaulting to an empty run."""
    return ResearchState(
        session_id=session_id,
        question=question,
        iteration=iteration,
        depth=depth,
        total_sources=total_sources,
        total_claims=total_claims,
        total_nodes=total_nodes,
        total_edges=total_edges,
        information_gain=information_gain,
        coverage=coverage,
        unresolved_contradictions=unresolved_contradictions,
        resolved_contradictions=resolved_contradictions,
        unresolved_gaps=tuple(gaps or ()),
        facet_coverage=facet_coverage,
        source_quality=source_quality,
        source_diversity=source_diversity,
        confidence_distribution=dict(confidence_distribution or {}),
        duplicate_count=duplicate_count,
        time_elapsed=time_elapsed,
        remaining_time=remaining_time,
        remaining_search_budget=remaining_search_budget,
        remaining_llm_budget=remaining_llm_budget,
        max_iterations=max_iterations,
        previous_action=previous_action,
        previous_reward=previous_reward,
        current_query=current_query,
        contradictions_are_new=contradictions_are_new,
        plateau_iterations=plateau_iterations,
        llm_calls=llm_calls,
    )


@dataclass
class StateObservation:
    """Compact summary of one iteration's *outcome* (the observation in the tuple).

    Stored next to a transition instead of the claim/source rows themselves: ids and
    counts make the transition inspectable without copying the session into it.
    """

    query: str | None = None
    facet: str | None = None
    sources_added: int = 0
    claims_added: int = 0
    nodes_added: int = 0
    edges_added: int = 0
    new_domains: int = 0
    contradictions_found: int = 0
    contradictions_resolved: int = 0
    gaps_found: list[str] = field(default_factory=list)
    duplicate_claims: int = 0
    low_quality_sources: int = 0
    llm_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "facet": self.facet,
            "sources_added": int(self.sources_added),
            "claims_added": int(self.claims_added),
            "nodes_added": int(self.nodes_added),
            "edges_added": int(self.edges_added),
            "new_domains": int(self.new_domains),
            "contradictions_found": int(self.contradictions_found),
            "contradictions_resolved": int(self.contradictions_resolved),
            "gaps_found": list(self.gaps_found[:MAX_GAPS_STORED]),
            "duplicate_claims": int(self.duplicate_claims),
            "low_quality_sources": int(self.low_quality_sources),
            "llm_calls": int(self.llm_calls),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> StateObservation:
        data = payload or {}
        return cls(
            query=data.get("query"),
            facet=data.get("facet"),
            sources_added=int(data.get("sources_added", 0)),
            claims_added=int(data.get("claims_added", 0)),
            nodes_added=int(data.get("nodes_added", 0)),
            edges_added=int(data.get("edges_added", 0)),
            new_domains=int(data.get("new_domains", 0)),
            contradictions_found=int(data.get("contradictions_found", 0)),
            contradictions_resolved=int(data.get("contradictions_resolved", 0)),
            gaps_found=list(data.get("gaps_found") or []),
            duplicate_claims=int(data.get("duplicate_claims", 0)),
            low_quality_sources=int(data.get("low_quality_sources", 0)),
            llm_calls=int(data.get("llm_calls", 0)),
        )
