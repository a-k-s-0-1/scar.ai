"""Per-session search memory.

The loop used to re-issue the same query text (and near-identical variants) with
no memory of the outcome, so a query that returned nothing could be paid for
three times. This module records what a session has already asked and what came
back, which lets the planner skip a known dead end instead of repeating it.

Deliberately in-process and per-run: it is an optimisation for one research loop,
not session state worth persisting. Losing it on restart costs one duplicate
search, not correctness.
"""

import re
from dataclasses import dataclass

# A dimension is only abandoned after repeated emptiness: one query with no
# results is often a bad query rather than a dimension with no evidence.
DEAD_END_ATTEMPTS_BEFORE_SKIP = 2


def query_fingerprint(query: str) -> str:
    """Normalize a query into a stable key for "have we asked this already?".

    Case, punctuation and whitespace differences produce the same fingerprint,
    so ``"Hydrogen Cost?"`` and ``"hydrogen  cost"`` are recognised as repeats.
    """
    normalized = re.sub(r"[^\w\s]", " ", query.lower())
    return re.sub(r"\s+", " ", normalized).strip()


@dataclass(frozen=True)
class QueryRecord:
    """What one issued query was and what it produced."""

    query: str
    new_sources: int
    new_claims: int
    iteration: int
    facet: str = ""

    @property
    def is_dead_end(self) -> bool:
        """A query that surfaced no usable source is a dead end for this session."""
        return self.new_sources == 0


class SearchMemory:
    """Fingerprint-keyed history of a single research run's searches."""

    def __init__(self) -> None:
        self._records: dict[str, QueryRecord] = {}

    def attempted(self, query: str) -> bool:
        """True when this query text has already been issued in this run."""
        return query_fingerprint(query) in self._records

    def attempts_for_facet(self, facet: str) -> int:
        """How many searches have been aimed at one dimension of the question.

        The planner uses this to give every dimension its first look before any
        dimension gets a second: a reworded retry of a search that already ran is
        a worse bet than looking somewhere nobody has looked yet.
        """
        return sum(1 for record in self._records.values() if record.facet == facet)

    def is_dead_end(self, query: str) -> bool:
        """True when this query was already tried and returned no sources."""
        record = self._records.get(query_fingerprint(query))
        return record is not None and record.is_dead_end

    def record(
        self,
        query: str,
        *,
        new_sources: int,
        new_claims: int = 0,
        iteration: int = 0,
        facet: str = "",
    ) -> None:
        """Store the outcome of an issued query, overwriting an earlier attempt.

        Overwriting (rather than keeping the first) means a query that was retried
        later with more context is judged on its most recent outcome.
        """
        fingerprint = query_fingerprint(query)
        if not fingerprint:
            return
        self._records[fingerprint] = QueryRecord(
            query=query,
            new_sources=new_sources,
            new_claims=new_claims,
            iteration=iteration,
            facet=facet,
        )

    def prime_dead_ends(self, queries: set[str] | list[str]) -> int:
        """Seed known dead ends from *earlier* runs, before the first search.

        Per-run memory cannot know that a query already failed yesterday, which is
        why a dead end used to cost one search in every session that tried it.
        Seeding is not an attempt: it records no iteration and is never reported as
        this run's own dead end, but ``is_dead_end`` now answers true for it.

        Returns how many were newly seeded, so the caller can log the benefit.
        """
        seeded = 0
        for query in queries:
            fingerprint = query_fingerprint(query)
            if not fingerprint or fingerprint in self._records:
                continue
            self._records[fingerprint] = QueryRecord(
                query=query, new_sources=0, new_claims=0, iteration=0, facet=""
            )
            seeded += 1
        return seeded

    def exhausted_facets(self) -> set[str]:
        """Facets whose *every* attempt returned nothing.

        The distinction matters: one empty query about cost does not prove cost
        evidence is unobtainable, whereas every cost query coming back empty is a
        reason to spend the next search on a different dimension.
        """
        outcomes: dict[str, list[bool]] = {}
        for record in self._records.values():
            if record.facet:
                outcomes.setdefault(record.facet, []).append(record.is_dead_end)
        return {
            facet
            for facet, dead_ends in outcomes.items()
            if len(dead_ends) >= DEAD_END_ATTEMPTS_BEFORE_SKIP and all(dead_ends)
        }

    def dead_end_queries(self) -> list[QueryRecord]:
        """Queries already proven unproductive (diagnostics and evaluation)."""
        return [record for record in self._records.values() if record.is_dead_end]

    def successful_queries(self) -> list[QueryRecord]:
        """Queries that actually produced sources, best first.

        The mirror of ``dead_end_queries``: a query that worked is worth reusing in a
        later session on the same subject, whereas one that produced nothing is worth
        never paying for again. Seeded dead ends are excluded — they were never issued
        here, so they cannot be reported as this run's own success.
        """
        productive = [
            record
            for record in self._records.values()
            if record.new_sources > 0 and record.iteration > 0
        ]
        productive.sort(key=lambda record: (record.new_sources, record.new_claims), reverse=True)
        return productive
