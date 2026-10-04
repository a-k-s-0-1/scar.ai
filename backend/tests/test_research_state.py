"""Research state (V2 2.1): serialisation, determinism, compactness and features."""

from __future__ import annotations

import json

import pytest

from app.services.rl import ResearchState, build_research_state
from app.services.rl.research_state import MAX_GAPS_STORED, STATE_PRECISION
from tests.conftest import make_state


def test_state_is_json_serialisable_and_round_trips() -> None:
    """Every field survives a JSON round trip unchanged."""
    state = make_state()

    payload = state.to_dict()
    encoded = json.dumps(payload)  # would raise on a non-JSON value
    restored = ResearchState.from_dict(json.loads(encoded))

    assert restored == state
    assert restored.to_json() == state.to_json()


def test_state_serialisation_is_deterministic_and_stable() -> None:
    """Equal inputs produce equal bytes, and the hash matches those bytes."""
    first = make_state(coverage=0.54321, information_gain=0.12349)
    second = make_state(coverage=0.54321, information_gain=0.12349)

    assert first.to_json() == second.to_json()
    assert first.state_hash() == second.state_hash()
    assert len(first.state_hash()) == 64


def test_state_hash_tracks_a_real_change() -> None:
    base = make_state()
    changed = make_state(coverage=0.9)

    assert base.state_hash() != changed.state_hash()


def test_floats_are_rounded_to_the_documented_precision() -> None:
    state = make_state(coverage=0.123456789)

    payload = state.to_dict()

    assert payload["coverage"] == round(0.123456789, STATE_PRECISION)


def test_state_carries_no_source_content_and_stays_small() -> None:
    """A snapshot is aggregates only: it must not smuggle the corpus into the dataset."""
    state = make_state(
        total_sources=900,
        total_claims=4000,
        gaps=[f"gap-{index}" for index in range(40)],
        current_query="a query",
    )

    payload = state.to_dict()
    serialised = state.to_json()

    assert "content" not in payload
    assert len(payload["unresolved_gaps"]) == MAX_GAPS_STORED
    # A state written once per iteration per session must stay a rounding error next
    # to the claim and source rows it summarises.
    assert state.state_size() == len(serialised.encode("utf-8"))
    assert state.state_size() < 4096


def test_features_are_bounded_and_categorical() -> None:
    features = make_state(coverage=0.5, information_gain=0.2).features()

    assert set(features) == {
        "coverage",
        "gain",
        "contradictions",
        "gaps",
        "facets",
        "budget",
        "phase",
        "previous",
    }
    assert features["coverage"] == "low"
    assert features["gain"] == "some"
    assert features["contradictions"] == "none"
    assert features["gaps"] == "some"


def test_state_key_is_a_stable_function_of_the_features() -> None:
    state = make_state()

    assert state.state_key() == make_state().state_key()
    assert state.state_key().count("|") == 7
    assert "coverage=" in state.state_key()


def test_budget_pressure_reports_the_most_pressured_allowance() -> None:
    healthy = make_state(time_elapsed=10.0, remaining_time=290.0, llm_calls=1)
    tight = make_state(time_elapsed=280.0, remaining_time=20.0, llm_calls=1)

    assert healthy.budget_pressure() < 0.1
    assert tight.budget_pressure() > 0.9
    assert tight.features()["budget"] == "tight"


def test_from_dict_tolerates_unknown_and_missing_keys() -> None:
    """A state written by a newer version must not crash an older reader."""
    payload = make_state().to_dict()
    payload["something_new"] = {"a": 1}
    del payload["facet_coverage"]

    restored = ResearchState.from_dict(payload)

    assert restored.facet_coverage == 0.0
    assert restored.session_id == "session-1"


def test_empty_state_is_a_valid_zero() -> None:
    state = build_research_state(session_id="s", question="q", iteration=0)

    assert state.coverage == 0.0
    assert state.state_key()
    assert state.to_dict()["unresolved_gaps"] == []


@pytest.mark.parametrize(
    ("previous", "expectation"),
    [("NONE", "NONE"), (None, "NONE"), ("verify", "VERIFY")],
)
def test_previous_action_is_normalised_in_features(previous, expectation) -> None:
    assert make_state(previous_action=previous).features()["previous"] == expectation
