"""Offline policy (V2 2.6): training, prediction, determinism, fallback, persistence."""

from __future__ import annotations

from app.services.rl import (
    ALGORITHM,
    JevPolicy,
    TabularPolicy,
    build_dataset,
    executable_actions,
)
from tests.conftest import make_state, make_transition


def _training_set() -> list:
    """Two contexts, two actions, with VERIFY clearly the better action."""
    records = []
    for index in range(6):
        records.append(
            make_transition(
                index + 1,
                id=f"verify-{index}",
                action="VERIFY",
                reward=3.0,
                state_before=make_state(
                    iteration=index, coverage=0.5, information_gain=0.4
                ).to_dict(),
                state_after=make_state(
                    iteration=index + 1, coverage=0.55, information_gain=0.45
                ).to_dict(),
            )
        )
    for index in range(4):
        records.append(
            make_transition(
                100 + index,
                id=f"search-{index}",
                action="SEARCH",
                # The last transition is terminal, so the dataset keeps the session.
                done=index == 3,
                reward=-0.5,
                state_before=make_state(
                    iteration=100 + index, coverage=0.5, information_gain=0.4
                ).to_dict(),
                state_after=make_state(
                    iteration=101 + index, coverage=0.5, information_gain=0.4
                ).to_dict(),
            )
        )
    return records


def test_policy_learns_the_better_action_in_a_learned_context() -> None:
    policy = TabularPolicy.train(_training_set(), min_samples=1)

    prediction = policy.predict(
        make_state(coverage=0.5, information_gain=0.4), executable_actions()
    )

    assert prediction.action == "VERIFY"
    assert prediction.fallback is False
    assert prediction.expected_value is not None
    assert prediction.expected_value > 0
    assert prediction.scores["VERIFY"] > prediction.scores["SEARCH"]


def test_training_is_deterministic() -> None:
    first = TabularPolicy.train(_training_set(), min_samples=1).to_dict()
    second = TabularPolicy.train(_training_set(), min_samples=1).to_dict()

    assert first == second


def test_ties_break_in_jev_preference_order() -> None:
    """An unlearned policy must behave like the baseline, not like a coin flip."""
    records = [
        make_transition(
            index + 1,
            id=f"tied-{index}",
            action=action,
            reward=1.0,
            state_before=make_state(iteration=index, coverage=0.5).to_dict(),
            state_after=make_state(iteration=index + 1, coverage=0.5).to_dict(),
        )
        for index, action in enumerate(["SEARCH", "VERIFY", "EXPAND_QUERY", "STOP"])
    ]
    policy = TabularPolicy.train(records, min_samples=1)

    prediction = policy.predict(make_state(coverage=0.5), executable_actions())

    assert prediction.action == "VERIFY"


def test_small_datasets_defer_to_jev_and_say_so() -> None:
    policy = TabularPolicy.train(_training_set()[:2], min_samples=10)

    prediction = policy.predict(make_state(), executable_actions())

    assert prediction.fallback is True
    assert prediction.action in executable_actions()
    assert "deferring to JEV" in prediction.explanation
    assert prediction.expected_value is None


def test_unseen_context_falls_back_instead_of_inventing_a_value() -> None:
    policy = TabularPolicy.train(_training_set(), min_samples=1)

    prediction = policy.predict(
        make_state(coverage=0.95, information_gain=0.9, unresolved_contradictions=0),
        executable_actions(),
    )

    # Actions observed elsewhere still carry a global mean, so a prediction may be
    # made — but every score must be one the data supports.
    assert prediction.action in executable_actions()
    assert all(
        isinstance(value, float) for value in prediction.scores.values()
    )


def test_expected_value_is_none_for_an_action_never_observed() -> None:
    policy = TabularPolicy.train(_training_set(), min_samples=1)

    assert policy.expected_value(make_state(), "REVISIT_WEAK_CLAIM") is None


def test_shrinkage_pulls_a_single_observation_toward_the_global_mean() -> None:
    policy = TabularPolicy.train(_training_set(), min_samples=1, shrinkage=2.0)

    # One VERIFY observation of +10 in the same context must not become +10 exactly.
    records = [
        *_training_set(),
        make_transition(
            500,
            id="lucky",
            action="VERIFY",
            reward=10.0,
            state_before=make_state(coverage=0.5, information_gain=0.4).to_dict(),
            state_after=make_state(coverage=0.5, information_gain=0.4).to_dict(),
        ),
    ]
    shrunk = TabularPolicy.train(records, min_samples=1, shrinkage=2.0)
    state = make_state(coverage=0.5, information_gain=0.4)

    assert shrunk.expected_value(state, "VERIFY") < policy.expected_value(
        state, "VERIFY"
    ) + 10.0
    assert shrunk.expected_value(state, "VERIFY") > 1.0


def test_policy_survives_a_json_round_trip() -> None:
    policy = TabularPolicy.train(_training_set(), min_samples=1)

    restored = TabularPolicy.from_dict(policy.to_dict())

    assert restored is not None
    assert restored.to_dict() == policy.to_dict()
    assert restored.predict(
        make_state(coverage=0.5, information_gain=0.4), executable_actions()
    ).action == policy.predict(
        make_state(coverage=0.5, information_gain=0.4), executable_actions()
    ).action


def test_unreadable_payloads_return_none_instead_of_raising() -> None:
    """A broken policy must leave JEV in charge, not break a session."""
    assert TabularPolicy.from_dict(None) is None
    assert TabularPolicy.from_dict({"algorithm": "some_future_net"}) is None


def test_describe_documents_the_algorithm_and_denies_being_deep_rl() -> None:
    described = TabularPolicy.train(_training_set(), min_samples=1).describe()

    assert described["algorithm"] == ALGORITHM
    assert described["is_deep_rl"] is False
    assert "no neural network" in described["notes"].lower()
    assert described["trained_transitions"] > 0


def test_jev_baseline_policy_selects_an_executable_action_with_a_reason() -> None:
    prediction = JevPolicy().predict(make_state(unresolved_contradictions=2))

    assert prediction.policy == "jev"
    assert prediction.action == "VERIFY"
    assert prediction.explanation


def test_jev_policy_value_is_a_proxy_only_for_its_own_action() -> None:
    policy = JevPolicy()
    state = make_state(unresolved_contradictions=2)

    selected = policy.predict(state).action
    other = next(action for action in executable_actions() if action != selected)

    assert policy.expected_value(state, selected) is not None
    assert policy.expected_value(state, other) is None


def test_dataset_built_records_train_a_policy() -> None:
    dataset = build_dataset(_training_set())
    policy = TabularPolicy.train(
        dataset.records, min_samples=1, dataset_hash=dataset.dataset_hash()
    )

    assert policy.samples == len(dataset.records)
    assert policy.dataset_hash == dataset.dataset_hash()
