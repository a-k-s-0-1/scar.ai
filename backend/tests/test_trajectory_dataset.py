"""Trajectory dataset (V2 2.5 / 2.6): transitions, ordering, validation, JSONL."""

from __future__ import annotations

import json

from app.services.rl import (
    DATASET_VERSION,
    TrajectoryDataset,
    TransitionRecord,
    build_dataset,
    dataset_from_jsonl,
    trajectory_is_complete,
    validate_transition,
)
from tests.conftest import make_state, make_transition


def _session(
    session_id: str, count: int, *, done_at_end: bool = True
) -> list[TransitionRecord]:
    return [
        make_transition(
            iteration,
            session_id=session_id,
            id=f"{session_id}-{iteration}",
            done=done_at_end and iteration == count,
        )
        for iteration in range(1, count + 1)
    ]


def test_sample_shape_is_state_action_reward_next_state_done() -> None:
    sample = make_transition(1).to_sample()

    assert set(sample) == {"state", "action", "reward", "next_state", "done"}
    assert isinstance(sample["state"], dict)
    assert isinstance(sample["next_state"], dict)


def test_sample_metadata_is_available_for_inspection_but_off_by_default() -> None:
    record = make_transition(2)

    assert "metadata" not in record.to_sample()
    metadata = record.to_sample(include_metadata=True)["metadata"]
    assert metadata["iteration"] == 2
    assert metadata["policy_source"] == "JEV"
    assert "reward_components" in metadata


def test_transition_round_trips_through_a_stored_payload() -> None:
    record = make_transition(3, reward=2.5)

    restored = TransitionRecord.from_dict(record.to_dict())

    assert restored.iteration == record.iteration
    assert restored.reward == record.reward
    assert restored.action == record.action
    assert restored.state_after == record.state_after


def test_valid_transition_reports_no_issues() -> None:
    assert validate_transition(make_transition(1)) == []


def test_missing_state_is_named_as_an_issue() -> None:
    issues = validate_transition(make_transition(1, state_before=None))

    assert [issue.kind for issue in issues] == ["missing_state"]


def test_missing_action_is_named_as_an_issue() -> None:
    issues = validate_transition(make_transition(1, action=""))

    assert "missing_action" in [issue.kind for issue in issues]


def test_invalid_reward_is_rejected() -> None:
    issues = validate_transition(make_transition(1, reward=float("inf")))

    assert "invalid_reward" in [issue.kind for issue in issues]


def test_broken_chain_is_rejected_when_next_state_skips_an_iteration() -> None:
    record = make_transition(
        1,
        state_before=make_state(iteration=1).to_dict(),
        state_after=make_state(iteration=5).to_dict(),
    )

    kinds = [issue.kind for issue in validate_transition(record)]

    assert "broken_transition" in kinds


def test_dataset_drops_duplicates_and_orders_by_session_then_iteration() -> None:
    records = [
        *_session("session-b", 2),
        *_session("session-a", 2),
        make_transition(1, session_id="session-a", id="duplicate"),
    ]

    dataset = build_dataset(records)

    keys = [(record.session_id, record.iteration) for record in dataset.records]
    assert keys == [
        ("session-a", 1),
        ("session-a", 2),
        ("session-b", 1),
        ("session-b", 2),
    ]
    assert "duplicate_transition" in dataset.stats()["issues"]
    assert dataset.dropped == 1


def test_incomplete_sessions_are_excluded_by_default() -> None:
    complete = _session("finished", 2, done_at_end=True)
    unfinished = _session("stopped-early", 2, done_at_end=False)

    default = build_dataset([*complete, *unfinished])
    inclusive = build_dataset(
        [*complete, *unfinished], include_incomplete=True
    )

    assert default.sessions == ["finished"]
    assert "incomplete_session" in default.stats()["issues"]
    assert set(inclusive.sessions) == {"finished", "stopped-early"}


def test_dataset_hash_is_content_derived_and_stable() -> None:
    records = _session("s", 2)

    first = build_dataset(records)
    second = build_dataset(list(reversed(records)))

    assert first.dataset_hash() == second.dataset_hash()
    assert len(first.dataset_hash()) == 16
    other = _session("other", 1)
    assert build_dataset([*records, *other]).dataset_hash() != first.dataset_hash()


def test_jsonl_export_is_one_sample_per_line_and_reimportable() -> None:
    dataset = build_dataset(_session("s", 3))

    raw = dataset.to_jsonl()
    lines = raw.splitlines()

    assert len(lines) == 3
    assert all(json.loads(line)["action"] for line in lines)
    assert dataset_from_jsonl(raw).samples == dataset.samples


def test_stats_summarise_actions_sources_and_rewards() -> None:
    dataset = build_dataset(_session("s", 3))
    stats = dataset.stats()

    assert stats["version"] == DATASET_VERSION
    assert stats["transitions"] == 3
    assert stats["sessions"] == 1
    assert stats["actions"] == {"SEARCH": 3}
    # All three provenance classes are reported, including the ones a V2 run never
    # produces: a zero is information, an absent key is a guess.
    assert stats["policy_sources"] == {"JEV": 3, "RL_SHADOW": 0, "OTHER": 0}
    assert stats["done_transitions"] == 1
    assert stats["average_reward"] == 1.5


def test_completeness_requires_a_terminal_step() -> None:
    assert trajectory_is_complete(_session("s", 2, done_at_end=True))
    assert not trajectory_is_complete([])
    assert trajectory_is_complete(
        [make_transition(1, action="STOP", done=True)]
    )


def test_empty_dataset_is_valid_and_exportable() -> None:
    dataset = build_dataset([])

    assert isinstance(dataset, TrajectoryDataset)
    assert dataset.samples == []
    assert dataset.to_jsonl() == ""
    assert dataset.stats()["transitions"] == 0
