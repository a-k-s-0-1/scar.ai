"""Evaluation engine (V2 2.8 / 2.9): replay, metrics, breakdowns, honest estimates."""

from __future__ import annotations

from app.services.rl import JevPolicy, TabularPolicy, build_dataset, evaluate
from tests.conftest import make_state, make_transition


def _dataset(action: str = "SEARCH", count: int = 6):
    records = []
    for index in range(count):
        records.append(
            make_transition(
                index + 1,
                id=f"{action}-{index}",
                session_id="session-1",
                action=action,
                reward=1.0 + index * 0.1,
                done=index == count - 1,
                information_gain=0.3,
                coverage_before=0.3 + index * 0.05,
                coverage_after=0.35 + index * 0.05,
                # max_iterations is raised so JEV keeps choosing SEARCH rather than
                # hitting its own iteration cap and answering STOP.
                state_before=make_state(
                    iteration=index,
                    max_iterations=40,
                    coverage=0.4,
                    information_gain=0.3,
                ).to_dict(),
                state_after=make_state(
                    iteration=index + 1,
                    max_iterations=40,
                    coverage=0.45,
                    information_gain=0.3,
                ).to_dict(),
            )
        )
    return build_dataset(records)


def test_jev_evaluated_against_its_own_trajectory_is_all_observed() -> None:
    report = evaluate(_dataset(), JevPolicy())

    assert report.metrics.observed_steps == report.metrics.steps
    assert report.metrics.counterfactual_steps == 0
    assert report.metrics.estimated is False
    assert report.metrics.average_reward > 0
    assert "observed outcomes" in report.notes[0]


def test_learned_policy_is_compared_on_the_same_states() -> None:
    dataset = _dataset()
    records = [
        make_transition(
            index + 1,
            id=f"verify-{index}",
            action="VERIFY",
            reward=4.0,
            state_before=make_state(
                iteration=index,
                max_iterations=40,
                coverage=0.4,
                information_gain=0.3,
            ).to_dict(),
            state_after=make_state(
                iteration=index + 1,
                max_iterations=40,
                coverage=0.45,
                information_gain=0.3,
            ).to_dict(),
        )
        for index in range(6)
    ]
    policy = TabularPolicy.train(records, min_samples=1)

    report = evaluate(dataset, policy, baseline=JevPolicy())

    assert report.metrics.steps == report.baseline_metrics.steps == 6
    assert report.metrics.counterfactual_steps == 6
    assert report.metrics.observed_steps == 0
    assert report.comparison["agreement_rate"] == 0.0
    assert report.comparison["disagreement_rate"] == 1.0
    assert report.metrics.estimated is True
    assert any("estimates, not observed outcomes" in note for note in report.notes)


def test_per_action_breakdown_reports_sample_sizes() -> None:
    report = evaluate(_dataset(), JevPolicy(), baseline=JevPolicy())

    rows = {row["action"]: row for row in report.per_action}

    assert rows["SEARCH"]["sample_size"] == 6
    assert rows["SEARCH"]["observed_steps"] == 6
    assert rows["SEARCH"]["average_reward"] > 0
    assert rows["SEARCH"]["baseline_average_reward"] == rows["SEARCH"]["average_reward"]
    assert rows["SEARCH"]["reward_delta"] == 0.0


def test_per_session_breakdown_is_present() -> None:
    report = evaluate(_dataset(), JevPolicy())

    assert len(report.per_session) == 1
    row = report.per_session[0]
    assert row["session_id"] == "session-1"
    assert row["steps"] == 6
    assert row["total_reward"] > 0
    assert row["final_coverage"] > 0.3


def test_max_steps_caps_the_replay() -> None:
    report = evaluate(_dataset(count=6), JevPolicy(), max_steps=2)

    assert report.metrics.steps == 2
    assert report.max_steps == 2


def test_metrics_cover_the_documented_axes() -> None:
    report = evaluate(_dataset(), JevPolicy())
    payload = report.metrics.to_dict()

    for key in (
        "average_reward",
        "total_reward",
        "average_information_gain",
        "coverage_improvement",
        "average_iterations",
        "duplicate_search_rate",
        "contradiction_resolution_rate",
        "stop_rate",
        "unnecessary_action_rate",
        "research_cost_seconds",
        "time_to_convergence",
    ):
        assert key in payload


def test_stop_and_cost_metrics_reflect_the_trajectory() -> None:
    """A run that ends by STOP is reported as converged, not as still running."""
    records = [
        make_transition(
            index + 1,
            id=f"stop-{index}",
            action="STOP",
            reward=0.5,
            done=index == 2,
            # JEV stops when its iteration cap is reached, which is what makes the
            # recorded STOP action the policy's agreement rather than a disagreement.
            state_before=make_state(
                iteration=index + 1, max_iterations=index + 1, coverage=0.9
            ).to_dict(),
            state_after=make_state(
                iteration=index + 2, max_iterations=index + 2, coverage=0.9
            ).to_dict(),
        )
        for index in range(3)
    ]
    report = evaluate(build_dataset(records), JevPolicy())

    assert report.metrics.action_distribution == {"STOP": 3}
    assert report.metrics.stop_rate == 1.0
    assert report.metrics.time_to_convergence == 1.0
    assert report.metrics.research_cost_seconds > 0


def test_report_serialises_without_loss() -> None:
    report = evaluate(_dataset(), JevPolicy(), baseline=JevPolicy())
    payload = report.to_dict()

    assert payload["dataset_hash"] == report.dataset_hash
    assert payload["metrics"]["policy"] == "jev"
    assert payload["comparison"]["agreement_rate"] == 1.0
    assert isinstance(payload["notes"], list)


def test_empty_dataset_evaluates_to_zero_without_raising() -> None:
    report = evaluate(build_dataset([]), JevPolicy())

    assert report.metrics.steps == 0
    assert report.metrics.total_reward == 0.0
    assert report.per_session == []
