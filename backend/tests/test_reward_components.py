"""Reward components (V2 2.4): named, inspectable, and V1-compatible."""

from __future__ import annotations

from app.services.metrics import compute_reward_signal
from app.services.rl import (
    PENALTY_FIELDS,
    POSITIVE_FIELDS,
    compute_reward_components,
    explain_components,
    reward_formula,
)


def test_v2_total_matches_the_v1_signal_when_only_v1_terms_are_present() -> None:
    """The baseline comparison only means something if the numbers line up."""
    gain, credibility, contradictions = 0.42, 0.75, 2

    components = compute_reward_components(
        information_gain=gain,
        avg_credibility=credibility,
        unresolved_contradictions=contradictions,
    )

    assert components.v1_reward == compute_reward_signal(
        information_gain=gain,
        avg_credibility=credibility,
        unresolved_contradictions=contradictions,
    )
    assert components.total == components.v1_reward


def test_positive_components_are_summed_and_penalties_subtracted() -> None:
    components = compute_reward_components(
        information_gain=1.0,
        avg_credibility=0.8,
        coverage_before=0.3,
        coverage_after=0.5,
        resolved_contradictions=2,
        new_domains=2,
        duplicate_findings=1,
        low_quality_sources=1,
        duration_seconds=300.0,
        llm_calls=10,
        llm_call_budget=100,
    )

    assert components.positive_total == round(
        sum(getattr(components, name) for name in POSITIVE_FIELDS), 4
    )
    assert components.penalty_total == round(
        sum(getattr(components, name) for name in PENALTY_FIELDS), 4
    )
    assert components.total == round(
        components.positive_total - components.penalty_total, 4
    )
    assert components.coverage_gain_reward > 0
    assert components.contradiction_resolution_reward > 0
    assert components.source_diversity_reward > 0
    assert components.redundancy_penalty > 0
    assert components.low_quality_source_penalty > 0
    assert components.time_cost_penalty > 0
    assert components.budget_cost_penalty > 0


def test_coverage_loss_is_never_credited() -> None:
    components = compute_reward_components(
        information_gain=0.1,
        avg_credibility=0.5,
        coverage_before=0.8,
        coverage_after=0.4,
    )

    assert components.coverage_gain_reward == 0.0


def test_repeating_an_action_with_no_yield_costs_more_than_its_base_cost() -> None:
    plain = compute_reward_components(information_gain=0.0, avg_credibility=0.0)
    repeated = compute_reward_components(
        information_gain=0.02,
        avg_credibility=0.0,
        repeated_action_without_yield=True,
    )

    assert plain.unnecessary_action_penalty < repeated.unnecessary_action_penalty


def test_penalties_are_capped_so_cost_cannot_swamp_the_signal() -> None:
    components = compute_reward_components(
        information_gain=0.0,
        avg_credibility=0.0,
        duration_seconds=100_000.0,
        llm_calls=10_000,
        llm_call_budget=100,
    )

    assert components.time_cost_penalty <= 0.3
    assert components.budget_cost_penalty <= 0.5


def test_explanation_names_each_non_zero_component() -> None:
    components = compute_reward_components(
        information_gain=0.9,
        avg_credibility=0.6,
        coverage_before=0.1,
        coverage_after=0.4,
        unresolved_contradictions=1,
    )

    rows = components.explain()
    names = {row["component"] for row in rows}

    assert "information_gain_reward" in names
    assert "coverage_gain_reward" in names
    assert "unresolved_contradiction_penalty" in names
    assert all(
        row["direction"] in ("credit", "debit") for row in rows
    )
    # Every row is a real number a reader can check against the total.
    assert all(isinstance(row["value"], float) for row in rows)


def test_components_survive_the_stored_json_shape() -> None:
    components = compute_reward_components(
        information_gain=0.5, avg_credibility=0.5, duplicate_findings=2
    )

    rows = explain_components(components.to_dict())

    assert {row["component"] for row in rows} == {
        "information_gain_reward",
        "evidence_quality_reward",
        "redundancy_penalty",
        "unnecessary_action_penalty",
    }


def test_explanation_of_an_empty_payload_is_empty_not_an_error() -> None:
    assert explain_components(None) == []


def test_formula_is_exposed_without_hiding_anything() -> None:
    formula = reward_formula()

    assert formula["total"] == "sum(positive) - sum(penalties)"
    assert "information_gain_reward" in formula["positive"]
    assert "budget_cost_penalty" in formula["penalties"]
    assert "compute_reward_signal" in formula["v1_equivalent"]
