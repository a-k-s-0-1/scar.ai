"""Tests for research quality metrics: information gain and coverage estimation."""

import pytest

from app.services.metrics import compute_coverage_estimate, compute_information_gain


@pytest.mark.parametrize(
    ("previous", "current", "new_entities", "existing_entities", "expected"),
    [
        # First pass with any yield is maximally informative.
        (0, 35, 40, 0, 1.0),
        # No yield on the first pass carries no signal.
        (0, 0, 0, 0, 0.0),
        # Growing corpus: novelty decays relative to what is already known.
        (35, 59, 30, 70, 0.364),
        (59, 90, 25, 100, 0.287),
        # A true plateau must read below the 0.15 convergence threshold.
        (100, 102, 1, 150, 0.014),
        # Zero new claims and entities is zero novelty.
        (50, 50, 0, 200, 0.0),
    ],
)
def test_information_gain_is_novelty_relative(
    previous: int,
    current: int,
    new_entities: int,
    existing_entities: int,
    expected: float,
) -> None:
    """Gain reflects new knowledge share, not raw counts against fixed constants."""
    gain = compute_information_gain(
        previous_claims_count=previous,
        current_claims_count=current,
        new_unique_entities=new_entities,
        existing_entities=existing_entities,
    )
    assert gain == pytest.approx(expected, abs=0.001)


def test_information_gain_decays_with_constant_yield() -> None:
    """With steady per-iteration yield, gain must strictly decay as knowledge grows."""
    gains: list[float] = []
    current = 0
    entities = 0
    for _ in range(4):
        previous = current
        current += 30
        gains.append(
            compute_information_gain(previous, current, 20, existing_entities=entities)
        )
        entities += 20

    assert gains == sorted(gains, reverse=True)
    assert gains[0] == 1.0
    assert gains[-1] < gains[0]


def test_recorded_session_yield_is_not_a_plateau() -> None:
    """Regression: the recorded E2E session (35 -> 59 -> 90 claims) kept learning.

    Fixed per-iteration normalizers pinned this trajectory at gain = 1.0 and made
    plateau detection unreachable. Any future normalization must keep real research
    above the convergence threshold until yield genuinely dries up.
    """
    gains = [
        compute_information_gain(0, 35, 40, 0),
        compute_information_gain(35, 59, 30, 70),
        compute_information_gain(59, 90, 25, 100),
    ]
    assert all(gain >= 0.15 for gain in gains)


@pytest.mark.parametrize(
    ("claims", "sources", "min_sources", "depth"),
    [
        (0, 0, 10, "shallow"),
        (5, 3, 10, "standard"),
        (35, 8, 10, "shallow"),
        (90, 23, 10, "deep"),
    ],
)
def test_coverage_is_bounded(
    claims: int, sources: int, min_sources: int, depth: str
) -> None:
    """Coverage stays inside [0, 1] and never exceeds a full estimate."""
    coverage = compute_coverage_estimate(claims, sources, min_sources, depth)
    assert 0.0 <= coverage <= 1.0


def test_coverage_meeting_targets_reads_at_the_stop_threshold() -> None:
    """Exactly meeting every depth target calibrates to the PRD's ~80% coverage."""
    meeting = compute_coverage_estimate(30, 10, 10, "shallow", nodes_count=40)
    assert meeting == pytest.approx(0.798, abs=0.005)
    assert meeting >= 0.79


def test_coverage_half_of_target_keeps_research_running() -> None:
    """Below target the estimate stays under the 65% continue-searching gate."""
    assert compute_coverage_estimate(15, 5, 10, "shallow", nodes_count=20) < 0.65


def test_coverage_climbs_past_targets_without_pinning() -> None:
    """Exceeding targets keeps rising and never locks at 100%."""
    rich = compute_coverage_estimate(60, 20, 10, "shallow", nodes_count=80)
    assert 0.90 < rich < 1.0


def test_coverage_counts_knowledge_graph_richness() -> None:
    """Entity depth raises the estimate even at identical claim/source counts."""
    sparse = compute_coverage_estimate(30, 10, 10, "shallow", nodes_count=0)
    rich = compute_coverage_estimate(30, 10, 10, "shallow", nodes_count=40)
    assert rich > sparse


def test_recorded_session_no_longer_reads_full_coverage_immediately() -> None:
    """Regression: the old ratio-capped metric pinned at 1.000 by iteration 1.

    The recorded shallow session reached 35 claims / 8 sources / ~40 entities in
    its first iteration; coverage must stay informative rather than maxing out.
    """
    observed = compute_coverage_estimate(35, 8, 10, "shallow", nodes_count=40)
    assert 0.75 < observed < 0.95


def test_coverage_is_monotonic_in_claims() -> None:
    """More claims never reduce the recorded coverage estimate."""
    values = [
        compute_coverage_estimate(claims, 10, 10, "deep")
        for claims in (0, 10, 20, 40, 80)
    ]
    assert values == sorted(values)
