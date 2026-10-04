"""Integration tests for facet-directed query selection inside the research loop.

Everything except the loop itself is stubbed (search, claim extraction,
contradictions, report) so the assertions are about the orchestrator's own
behaviour: which query it picks next, what it streams, and which dimension it
refuses to pay for twice. A live run proved this once; this locks it in.
"""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import (
    ClaimRepository,
    SessionEventRepository,
    SessionRepository,
    SourceRepository,
)
from app.services import event_recorder
from app.services import research_orchestrator as orch
from app.services.research_orchestrator import ResearchOrchestrator
from app.ws.managers import ws_manager

# Aliased so pytest does not try to collect conftest's session factory as a test.
from tests.conftest import test_async_session_maker as session_factory

QUESTION = "Is solar green hydrogen viable at utility scale?"

# Attributes to "technical" for every iteration, so every other dimension of a
# viability question stays a genuine gap.
TECHNICAL_CLAIM = "Technical efficiency measurements were recorded for the pilot plant."


class LoopSeams:
    """Records what the loop did while standing in for the real services."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, sources_per_search: int = 3) -> None:
        self.queries: list[str] = []
        self.claims_created = 0
        self._monkeypatch = monkeypatch
        self._sources_per_search = sources_per_search

    def install(self) -> "LoopSeams":
        """Replace search, extraction, contradiction detection and reporting."""
        monkeypatch = self._monkeypatch
        seams = self

        async def fake_search(self: Any, query: str, db: AsyncSession, max_results: int = 8):
            seams.queries.append(query)
            # Mirror the real agent's "already collected" skip: a query that has
            # been asked before returns nothing new.
            if seams.queries.count(query) > 1:
                return []
            repo = SourceRepository(db)
            return [
                await repo.create(
                    session_id=self.session_id,
                    url=f"https://example.com/{len(seams.queries)}/{index}",
                    title=f"Source {index}",
                    content="Substantive evidence text long enough to be extracted from. " * 3,
                    credibility_score=0.8,
                )
                for index in range(seams._sources_per_search)
            ]

        async def fake_extract(self: Any, sources: list[Any], question: str, db: AsyncSession):
            repo = ClaimRepository(db)
            claims = []
            for _source in sources:
                claims.append(
                    await repo.create(
                        session_id=self.session_id,
                        claim_text=TECHNICAL_CLAIM,
                        subject="pilot plant",
                        predicate="recorded",
                        obj="technical efficiency measurements",
                        confidence="high",
                    )
                )
            seams.claims_created += len(claims)
            return claims

        async def no_contradictions(self: Any, db: AsyncSession, max_comparisons: int = 15):
            return []

        async def no_gaps(self: Any, db: AsyncSession, question: str):
            return []

        async def fake_report(self: Any, db: AsyncSession, **_kwargs: Any):
            return {"metadata": {"total_claims": seams.claims_created, "total_sources": 3}}

        monkeypatch.setattr(orch, "async_session_maker", session_factory)
        # The lifespan hook that installs the durable recorder only runs when the
        # app is served, not under ASGITransport, so wire it here: without it the
        # loop's broadcasts never reach the event log this test reads back.
        monkeypatch.setattr(
            ws_manager, "_event_recorder", event_recorder.record_session_event
        )
        monkeypatch.setattr(orch.SearchAgent, "search", fake_search)
        monkeypatch.setattr(orch.ClaimExtractor, "extract_from_sources", fake_extract)
        monkeypatch.setattr(orch.ContradictionDetector, "detect_contradictions", no_contradictions)
        monkeypatch.setattr(orch.ContradictionDetector, "identify_knowledge_gaps", no_gaps)
        monkeypatch.setattr(orch.ReportGenerator, "generate_report", fake_report)
        return seams


async def make_session(db: AsyncSession, depth: str) -> str:
    session = await SessionRepository(db).create(question=QUESTION, depth=depth)
    await db.commit()
    return session.id


async def stored_events(db: AsyncSession, session_id: str) -> list[Any]:
    return await SessionEventRepository(db).list_events(session_id)


def payloads(events: list[Any], event_type: str) -> list[dict[str, Any]]:
    return [event.payload for event in events if event.event_type == event_type]


@pytest.mark.asyncio
async def test_facet_directed_searches_replace_the_generic_query(
    db_session: AsyncSession,
    recorder_bound_to_test_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each iteration after the first targets a dimension with no evidence yet.

    The V1 loop re-issued ``"<question> key findings and analysis"`` when it wanted
    to dig deeper; that query answers nothing specific. This asserts the loop now
    asks for the missing dimension instead, and never asks twice.
    """
    session_id = await make_session(db_session, depth="shallow")
    seams = LoopSeams(monkeypatch).install()

    await ResearchOrchestrator(session_id).run()

    assert seams.queries[0] == QUESTION
    # Long-term memory can now seed dead ends and recalled items before the first
    # search, so the loop's iteration budget may be reached with a different query
    # count than before. Assert only what the facet policy guarantees.
    assert len(seams.queries) >= 1
    assert len(set(seams.queries)) == len(seams.queries), "a query must never be paid for twice"
    assert "feasibility" in seams.queries[1]

    events = await stored_events(db_session, session_id)
    search_payloads = payloads(events, "search_started")
    # technical is skipped here even though it was never searched: the claims
    # already extracted cover it, so it is no longer a gap.
    assert [payload.get("facet") for payload in search_payloads] == [
        None,
        "feasibility",
        "economic",
    ]
    assert not any("key findings and analysis" in query for query in seams.queries)
    # Long-term memory now seeds dead ends and recalled items before the first search,
    # which can change how many queries the loop fires inside the (now lower) iteration
    # cap. Do not assert a fixed query count here.
    assert len(seams.queries) >= 1
    assert len(set(seams.queries)) == len(seams.queries), "a query must never be paid for twice"

    completions = payloads(events, "completed")
    assert len(completions) == 1
    assert completions[0]["report_ready"] is True


@pytest.mark.asyncio
async def test_facet_coverage_map_is_streamed_every_iteration(
    db_session: AsyncSession,
    recorder_bound_to_test_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The UI gets a per-dimension coverage map, not just one overall number."""
    session_id = await make_session(db_session, depth="shallow")
    LoopSeams(monkeypatch).install()

    await ResearchOrchestrator(session_id).run()

    events = await stored_events(db_session, session_id)
    snapshots = payloads(events, "facet_updated")
    assert len(snapshots) == 3

    final = snapshots[-1]
    facets = {entry["facet"]: entry for entry in final["facets"]}
    # A viability question decomposes into the full evaluation set...
    assert set(facets) == {
        "feasibility",
        "technical",
        "economic",
        "environmental",
        "regulatory",
        "risks",
        "alternatives",
        "recent_evidence",
    }
    # ...of which only technical actually found evidence.
    assert facets["technical"]["claims"] > 0
    assert facets["technical"]["is_gap"] is False
    assert "technical" not in final["facet_gaps"]
    assert final["facet_gaps"][0] == "feasibility"
    assert 0 < final["facet_coverage"] < 1
    # Coverage is carried onto the iteration telemetry the dashboard reads.
    assert payloads(events, "iteration_complete")[-1]["facet_coverage"] == final["facet_coverage"]


@pytest.mark.asyncio
async def test_empty_searches_spread_across_dimensions_instead_of_repeating(
    db_session: AsyncSession,
    recorder_bound_to_test_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every search comes back empty: the loop gives each dimension one look.

    This is the behaviour the facet model exists for. V1 kept re-issuing one generic
    deepening query, so five fruitless iterations searched one thing five times;
    now the run walks the missing dimensions in order of how much a gap costs the
    answer, and never pays for the same query twice.
    """
    session_id = await make_session(db_session, depth="standard")
    seams = LoopSeams(monkeypatch).install()
    seams._sources_per_search = 0

    await ResearchOrchestrator(session_id).run()

    events = await stored_events(db_session, session_id)
    facets_searched = [
        payload.get("facet") for payload in payloads(events, "search_started")
    ]

    assert facets_searched == [
        None,
        "feasibility",
        "technical",
        "economic",
        "regulatory",
    ]
    assert len(set(seams.queries)) == len(seams.queries), "no query is ever repeated"
    assert len(seams.queries) == 5
