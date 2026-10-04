"""Action space (V2 2.2): executability, parameters, and V1 compatibility."""

from __future__ import annotations

import pytest

from app.services.decision_engine import ActionType as JevActionType
from app.services.rl import (
    ACTION_PRIORITY,
    ACTION_SPECS,
    ActionRequest,
    PolicyAction,
    action_spec,
    executable_action_request,
    executable_actions,
    from_jev_action,
    is_executable,
    is_stop,
    to_jev_action,
)


def test_only_executable_actions_are_offered_to_a_policy() -> None:
    """A policy must never be able to recommend something the loop cannot run."""
    assert executable_actions() == ["VERIFY", "EXPAND_QUERY", "SEARCH", "STOP"]
    assert all(is_executable(action) for action in executable_actions())


def test_declared_future_actions_are_not_executable() -> None:
    for action in (
        PolicyAction.SEARCH_NEW_FACET,
        PolicyAction.SEARCH_PRIMARY_SOURCE,
        PolicyAction.SEARCH_RECENT_SOURCE,
        PolicyAction.SEARCH_COUNTER_EVIDENCE,
        PolicyAction.COMPARE_SOURCES,
        PolicyAction.REVISIT_WEAK_CLAIM,
    ):
        assert not is_executable(action)
        assert to_jev_action(action) is None


def test_every_executable_action_maps_onto_a_v1_jev_action() -> None:
    """Backward compatibility: the live loop still speaks V1's vocabulary."""
    for value in executable_actions():
        jev = to_jev_action(value)
        assert isinstance(jev, JevActionType)
        assert from_jev_action(jev) is not None


def test_v1_loop_stages_map_to_no_policy_action() -> None:
    """EXTRACT/FUSE are loop stages, not decisions; they must not be coerced."""
    assert from_jev_action(JevActionType.EXTRACT) is None
    assert from_jev_action(JevActionType.FUSE) is None


def test_jev_action_enum_is_unchanged() -> None:
    """The V1 enum keeps its members and order — existing logs and tests depend on it."""
    assert [action.value for action in JevActionType] == [
        "SEARCH",
        "EXTRACT",
        "FUSE",
        "VERIFY",
        "EXPAND_QUERY",
        "STOP",
    ]


def test_action_specs_carry_parameters_and_metadata() -> None:
    spec = action_spec("SEARCH")

    assert spec.parameters == ("query", "facet", "max_results")
    assert spec.cost_weight == 1.0
    assert "search" in spec.description.lower()
    assert spec.to_dict()["executable"] is True


def test_action_request_round_trips_through_json_shape() -> None:
    request = ActionRequest("VERIFY", {"claim_id": "c1", "query": "evidence for X"})

    payload = request.to_dict()
    restored = ActionRequest.from_dict(payload)

    assert restored == request
    assert payload["action_type"] == "VERIFY"


def test_action_request_rejects_unknown_actions() -> None:
    with pytest.raises(ValueError, match="Unknown research action"):
        ActionRequest("DROP_DATABASE")


def test_action_request_requires_mandatory_parameters() -> None:
    with pytest.raises(ValueError, match="missing required parameter"):
        ActionRequest("COMPARE_SOURCES", {})


def test_unknown_action_requests_survive_dataset_parsing_as_none() -> None:
    assert ActionRequest.from_dict({"action_type": "NOPE"}) is None
    assert ActionRequest.from_dict(None) is None


def test_executable_action_request_refuses_declared_only_actions() -> None:
    with pytest.raises(ValueError, match="not executable"):
        executable_action_request("SEARCH_NEW_FACET", {"facet": "economic"})


def test_stop_detection_is_case_insensitive() -> None:
    assert is_stop("stop") and is_stop(PolicyAction.STOP)
    assert not is_stop("SEARCH")


def test_priority_order_covers_the_executable_set() -> None:
    assert set(ACTION_PRIORITY) == set(executable_actions())
    assert set(ACTION_SPECS) >= set(ACTION_PRIORITY)
