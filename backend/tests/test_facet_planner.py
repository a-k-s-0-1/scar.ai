"""Tests for the facet-aware research planner and its coverage model."""

from app.database.models import Claim
from app.services.facet_planner import (
    FACET_GAP_THRESHOLD,
    FacetPlanner,
    classify_claim_facet,
    classify_facet_text,
    extract_facets,
)
from app.services.search_memory import SearchMemory


def make_claim(
    text: str,
    *,
    subject: str | None = None,
    predicate: str | None = None,
    obj: str | None = None,
    confidence: str = "medium",
) -> Claim:
    """Build an unsaved Claim: attribution only reads its text fields."""
    return Claim(
        session_id="s1",
        claim=text,
        subject=subject,
        predicate=predicate,
        object=obj,
        confidence=confidence,
        status="active",
    )


def test_viability_question_expands_to_evaluation_dimensions() -> None:
    """A "is it viable" question implies the full set of evaluation dimensions.

    None of those words appear in the question, so a keyword-only reading would
    report a coverage meter with one bar for the whole investigation.
    """
    facets = extract_facets("Is solar green hydrogen viable?")

    assert facets == (
        "feasibility",
        "technical",
        "economic",
        "environmental",
        "regulatory",
        "risks",
        "alternatives",
        "recent_evidence",
    )


def test_narrow_question_keeps_only_its_implied_dimensions() -> None:
    """A question about cost gets a cost meter, not a ten-bar one."""
    assert extract_facets("What is the manufacturing cost of sodium cells?") == (
        "economic",
    )


def test_question_with_no_recognisable_facet_falls_back_to_defaults() -> None:
    """An unrecognised question still gets a usable set of dimensions to cover."""
    facets = extract_facets("Tell me about the history of the thing")

    assert facets == (
        "feasibility",
        "technical",
        "economic",
        "risks",
        "recent_evidence",
    )


def test_claim_attribution_reads_the_whole_claim() -> None:
    """Attribution uses claim text plus its subject/object, not just one field."""
    assert (
        classify_claim_facet(
            make_claim("Cost per kilogram fell to $3", subject="green hydrogen")
        )
        == "economic"
    )
    assert (
        classify_claim_facet(
            make_claim("Electrolyser efficiency reached 74%", subject="electrolyser")
        )
        == "technical"
    )
    assert classify_claim_facet(make_claim("asdf qwer")) == ""
    assert classify_facet_text("") == ""


def test_coverage_rises_with_evidence_and_gaps_are_weighted() -> None:
    """Well-evidenced dimensions leave the gap list; the rest are ranked.

    Feasibility outranks environmental at equal (zero) coverage because a missing
    viability dimension costs the answer more than a missing sustainability one.
    """
    planner = FacetPlanner("Is solar green hydrogen viable?", "standard")
    claims = [
        make_claim(f"Electrolyser efficiency finding {i}", subject="electrolyser")
        for i in range(planner.per_facet_target)
    ]

    snapshot = planner.observe(claims, iteration=1)
    technical = next(entry for entry in snapshot.facets if entry.facet == "technical")

    assert technical.is_gap is False
    assert technical.coverage >= FACET_GAP_THRESHOLD
    assert "technical" not in snapshot.gaps
    assert snapshot.gaps[0] == "feasibility"
    assert "environmental" in snapshot.gaps
    assert snapshot.gaps.index("feasibility") < snapshot.gaps.index("environmental")
    assert snapshot.weakest == "feasibility"


def test_every_dimension_gets_one_look_before_any_gets_a_second() -> None:
    """The next query buys the strongest gap nobody has searched yet.

    Re-wording a search that already ran is the least likely way to learn
    something new, so an untouched dimension outranks a retry of a filled one.
    """
    planner = FacetPlanner("Is solar green hydrogen viable?", "standard")
    planner.observe([], iteration=1)
    memory = SearchMemory()

    first = planner.next_query(memory=memory)
    assert first is not None
    assert first.facet == "feasibility"
    assert "solar green hydrogen" in first.query
    memory.record(first.query, new_sources=0, facet=first.facet)

    second = planner.next_query(memory=memory)
    assert second is not None
    assert second.facet == "technical", "an untouched dimension comes before a reworded repeat"
    assert second.query != first.query

    # Once nothing is untried, the strongest remaining gap gets its second look.
    memory.record(second.query, new_sources=0, facet=second.facet)
    for facet in (
        "economic",
        "environmental",
        "regulatory",
        "risks",
        "alternatives",
        "recent_evidence",
    ):
        memory.record(f"probe {facet}", new_sources=4, facet=facet)

    third = planner.next_query(memory=memory)
    assert third is not None
    assert third.facet == "feasibility"
    assert third.query != first.query

    # With no search history at all, the weakest dimension simply ranks first.
    assert planner.next_query().facet == "feasibility"


def test_preferred_gap_query_wins_when_it_addresses_a_missing_dimension() -> None:
    """A content-specific gap query beats the template when it fills a real gap."""
    planner = FacetPlanner("Is solar green hydrogen viable?", "standard")
    planner.observe([], iteration=1)

    chosen = planner.next_query(
        preferred=["green hydrogen subsidy and payback economics"]
    )

    assert chosen is not None
    assert chosen.facet == "economic"
    assert chosen.query == "green hydrogen subsidy and payback economics"


def test_preferred_query_is_ignored_when_its_dimension_is_already_covered() -> None:
    """The gap detector cannot pull the loop back into a covered dimension."""
    planner = FacetPlanner("Is solar green hydrogen viable?", "standard")
    covered = [
        make_claim(f"Electrolyser efficiency {i}", subject="electrolyser")
        for i in range(planner.per_facet_target)
    ]
    planner.observe(covered, iteration=1)

    chosen = planner.next_query(preferred=["electrolyser efficiency test results"])

    assert chosen is not None
    assert chosen.facet != "technical"


def test_no_facet_gaps_means_no_facet_query() -> None:
    """A fully covered question leaves query choice to the gap detector."""
    planner = FacetPlanner("What is the manufacturing cost of sodium cells?")
    planner.observe(
        [
            make_claim(f"Sodium cell cost is ${i}", subject="sodium cell")
            for i in range(planner.per_facet_target)
        ],
        iteration=1,
    )

    assert planner.snapshot() is not None
    assert planner.snapshot().gaps == ()

    # A question with no facets modelled yet cannot target anything either.
    assert FacetPlanner("Is it viable?", "standard").next_query() is None


def test_describe_reports_the_coverage_model() -> None:
    """The diagnostic view names the gaps the loop is acting on."""
    planner = FacetPlanner("Is solar green hydrogen viable?", "standard")
    planner.observe([], iteration=2)

    described = planner.describe()

    assert described["coverage"] == 0.0
    assert described["gaps"][0] == "feasibility"
    assert {key for entry in described["facets"] for key in entry} == {
        "facet",
        "claims",
        "coverage",
    }
