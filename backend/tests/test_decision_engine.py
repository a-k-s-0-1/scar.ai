"""Tests for Judgment Evaluation Vector (JEV) decision rules."""

from collections.abc import Callable

import pytest

from app.services.decision_engine import ActionType, DecisionEngine, KnowledgeState

STATE_DEFAULTS: dict[str, object] = {
    "iteration": 2,
    "sources_count": 5,
    "claims_count": 10,
    "nodes_count": 5,
    "edges_count": 4,
    "unresolved_contradictions": 0,
    "coverage_estimate": 0.5,
    "information_gain": 0.5,
    "gaps": [],
    "max_iterations": 5,
    "elapsed_time_minutes": 1.0,
    "max_research_time_minutes": 10,
    "previous_information_gain": 1.0,
}


@pytest.fixture
def engine() -> DecisionEngine:
    return DecisionEngine(session_id="test_session")


@pytest.fixture
def state_factory() -> Callable[..., KnowledgeState]:
    """Build a KnowledgeState from sensible defaults with per-test overrides."""

    def _make(**overrides: object) -> KnowledgeState:
        return KnowledgeState(**{**STATE_DEFAULTS, **overrides})

    return _make


@pytest.mark.parametrize(
    ("overrides", "expected_action", "reason_fragment"),
    [
        # Hard stops take precedence over everything.
        ({"elapsed_time_minutes": 10.5}, ActionType.STOP, "maximum allowed research time"),
        ({"iteration": 5}, ActionType.STOP, "maximum iteration limit"),
        # Unresolved contradictions trigger verification.
        ({"unresolved_contradictions": 1}, ActionType.VERIFY, "unresolved contradiction"),
        # Low coverage keeps the primary search running.
        ({"coverage_estimate": 0.4}, ActionType.SEARCH, "below threshold"),
        # Gap expansion is the first response to a signal-poor iteration.
        (
            {"iteration": 3, "coverage_estimate": 0.8, "gaps": ["costs"], "information_gain": 0.3},
            ActionType.EXPAND_QUERY,
            "unexplored knowledge facets",
        ),
        (
            {
                "iteration": 3,
                "coverage_estimate": 0.8,
                "gaps": ["costs"],
                "information_gain": 0.05,
                "previous_information_gain": 0.4,
            },
            ActionType.EXPAND_QUERY,
            "unexplored knowledge facets",
        ),
        # A plateau that survives the corrective iteration converges.
        (
            {
                "iteration": 4,
                "coverage_estimate": 0.8,
                "gaps": ["costs"],
                "information_gain": 0.05,
                "previous_information_gain": 0.02,
            },
            ActionType.STOP,
            "Convergence achieved",
        ),
        # Low coverage still outranks convergence.
        (
            {
                "iteration": 4,
                "coverage_estimate": 0.6,
                "information_gain": 0.05,
                "previous_information_gain": 0.02,
            },
            ActionType.SEARCH,
            "below threshold",
        ),
        # An iteration that found nothing new stops the run however good coverage is.
        (
            {
                "iteration": 2,
                "coverage_estimate": 0.9,
                "information_gain": 0.05,
                "previous_information_gain": 0.4,
                "new_sources_last_iteration": 0,
                "new_claims_last_iteration": 0,
                "new_nodes_last_iteration": 0,
            },
            ActionType.STOP,
            "No new sources",
        ),
        # Diminishing returns: marginal gains for several iterations and coverage stalled.
        (
            {
                "iteration": 4,
                "coverage_estimate": 0.7,
                "previous_coverage": 0.698,
                "information_gain": 0.05,
                "previous_information_gain": 0.05,
                "plateau_iterations": 3,
            },
            ActionType.STOP,
            "Diminishing returns",
        ),
        # A dimension of the question with no evidence outranks a generic deepening
        # search, even when aggregate coverage already looks adequate.
        (
            {
                "iteration": 3,
                "coverage_estimate": 0.9,
                "information_gain": 0.4,
                "facet_coverage": 0.4,
                "facet_gaps": ["economic", "risks"],
            },
            ActionType.EXPAND_QUERY,
            "Coverage gap",
        ),
        # A plateaued run stops instead of chasing a gap further searching cannot fill.
        (
            {
                "iteration": 4,
                "coverage_estimate": 0.9,
                "information_gain": 0.05,
                "previous_information_gain": 0.02,
                "plateau_iterations": 3,
                "facet_coverage": 0.4,
                "facet_gaps": ["economic"],
            },
            ActionType.STOP,
            "Convergence achieved",
        ),
        # Near the iteration cap the run finishes rather than starting another search.
        (
            {
                "iteration": 4,
                "max_iterations": 5,
                "coverage_estimate": 0.9,
                "information_gain": 0.4,
                "previous_information_gain": 0.5,
                "facet_coverage": 0.4,
                "facet_gaps": ["economic"],
            },
            ActionType.SEARCH,
            "Deepening evidence base",
        ),
        # An already verified contradiction set must not buy another verification pass.
        (
            {
                "iteration": 2,
                "unresolved_contradictions": 2,
                "contradictions_are_new": False,
                "coverage_estimate": 0.9,
            },
            ActionType.SEARCH,
            "Deepening evidence base",
        ),
    ],
)
def test_decision_rule_table(
    engine: DecisionEngine,
    state_factory: Callable[..., KnowledgeState],
    overrides: dict[str, object],
    expected_action: ActionType,
    reason_fragment: str,
) -> None:
    """Each state maps to its expected action with an explanatory reason."""
    action, reasoning = engine.select_action(state_factory(**overrides))
    assert action == expected_action
    assert reason_fragment.lower() in reasoning.lower()


def test_unreported_yield_never_looks_like_stagnation(
    engine: DecisionEngine, state_factory: Callable[..., KnowledgeState]
) -> None:
    """Yield defaults are unknown (-1), so a caller that omits them keeps digging.

    Only measured zeroes should end a run: treating "not reported" as "nothing
    found" would stop healthy sessions as soon as a caller stopped passing counts.
    """
    action, _ = engine.select_action(
        state_factory(
            iteration=3,
            coverage_estimate=0.9,
            information_gain=0.4,
            previous_information_gain=0.5,
        )
    )
    assert action == ActionType.SEARCH


def test_diminishing_returns_keeps_going_while_coverage_moves(
    engine: DecisionEngine, state_factory: Callable[..., KnowledgeState]
) -> None:
    """Low gain alone is not a stop: slow but real progress still earns iterations."""
    action, _ = engine.select_action(
        state_factory(
            iteration=4,
            coverage_estimate=0.7,
            previous_coverage=0.4,
            information_gain=0.05,
            previous_information_gain=0.05,
            plateau_iterations=3,
        )
    )
    assert action == ActionType.SEARCH


def test_plateau_stops_only_after_a_corrective_iteration(
    engine: DecisionEngine, state_factory: Callable[..., KnowledgeState]
) -> None:
    """A single low-gain iteration gets one gap-directed attempt before converging."""
    low_gain_with_gaps = {
        "iteration": 3,
        "coverage_estimate": 0.8,
        "gaps": ["commercial production costs"],
        "information_gain": 0.02,
    }

    first_action, _ = engine.select_action(
        state_factory(**low_gain_with_gaps, previous_information_gain=0.5)
    )
    second_action, _ = engine.select_action(
        state_factory(**low_gain_with_gaps, previous_information_gain=0.02)
    )

    assert first_action == ActionType.EXPAND_QUERY
    assert second_action == ActionType.STOP


def test_recorded_session_trajectory_never_triggers_convergence(
    engine: DecisionEngine, state_factory: Callable[..., KnowledgeState]
) -> None:
    """Regression: the recorded trajectory (35 -> 59 -> 90 claims) must keep digging.

    Before the fix, gains pinned at 1.0 and coverage pinned at 1.0, so iteration 3
    (the shallow cap) was always reached. The inverse failure must not appear either:
    healthy yield must not be mistaken for a plateau.
    """
    for iteration, gains in enumerate([(1.0, 1.0), (0.364, 1.0), (0.287, 0.364)], start=1):
        information_gain, previous_gain = gains
        action, _ = engine.select_action(
            state_factory(
                iteration=iteration,
                coverage_estimate=1.0,
                gaps=["a", "b", "c"],
                information_gain=information_gain,
                previous_information_gain=previous_gain,
            )
        )
        assert action != ActionType.STOP
