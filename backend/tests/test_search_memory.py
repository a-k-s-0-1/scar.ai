"""Tests for the per-session search memory (negative-result caching)."""

from app.services.search_memory import (
    DEAD_END_ATTEMPTS_BEFORE_SKIP,
    SearchMemory,
    query_fingerprint,
)


def test_fingerprint_normalizes_case_punctuation_and_spacing() -> None:
    """Wording noise must not let the same query be paid for twice."""
    assert query_fingerprint("Hydrogen Cost?") == query_fingerprint("hydrogen  cost")
    assert query_fingerprint("  A, B;  C ") == "a b c"
    assert query_fingerprint("") == ""


def test_attempted_and_dead_end_tracking() -> None:
    memory = SearchMemory()

    assert memory.attempted("green hydrogen cost") is False
    assert memory.is_dead_end("green hydrogen cost") is False

    memory.record("green hydrogen cost", new_sources=0, iteration=1, facet="economic")

    assert memory.attempted("Green  Hydrogen Cost?") is True
    assert memory.is_dead_end("green hydrogen cost") is True
    assert [record.query for record in memory.dead_end_queries()] == [
        "green hydrogen cost"
    ]


def test_a_productive_retry_clears_the_dead_end() -> None:
    """A later attempt with more context is judged on its newest outcome."""
    memory = SearchMemory()
    memory.record("solar hydrogen", new_sources=0, iteration=1, facet="technical")

    assert memory.is_dead_end("solar hydrogen") is True

    memory.record("solar hydrogen", new_sources=3, iteration=2, facet="technical")

    assert memory.is_dead_end("solar hydrogen") is False
    assert memory.exhausted_facets() == set()


def test_facet_is_only_exhausted_after_repeated_emptiness() -> None:
    """One empty result is a bad query, not a dimension with no evidence."""
    memory = SearchMemory()

    memory.record("hydrogen cost", new_sources=0, facet="economic")
    assert memory.exhausted_facets() == set()

    memory.record("hydrogen payback", new_sources=0, facet="economic")
    assert memory.exhausted_facets() == {"economic"}

    # A productive query for another dimension must not exhaust it.
    memory.record("hydrogen efficiency", new_sources=4, facet="technical")
    assert memory.exhausted_facets() == {"economic"}


def test_unlabelled_queries_never_exhaust_a_facet() -> None:
    """Facet exhaustion needs attribution; unattributed repeats cannot imply one."""
    memory = SearchMemory()
    for _ in range(DEAD_END_ATTEMPTS_BEFORE_SKIP + 1):
        memory.record("orphan query", new_sources=0)

    assert memory.exhausted_facets() == set()
    assert memory.is_dead_end("orphan query") is True
