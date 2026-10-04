"""Recorder and shadow mode (V2 2.3 / 2.7): transitions, predictions, safety."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ResearchSession
from app.database.repository import (
    PolicyRepository,
    PredictionRepository,
    SessionRepository,
    TransitionRepository,
)
from app.services.rl import (
    JevPolicy,
    TabularPolicy,
    TrajectoryRecorder,
    count_duplicate_claims,
    executable_actions,
)
from tests.conftest import make_state, make_transition


async def _session(db: AsyncSession) -> ResearchSession:
    session = await SessionRepository(db).create(
        question="Is solar green hydrogen viable at utility scale?", depth="shallow"
    )
    await db.commit()
    return session


def _recorder(session: ResearchSession, **overrides) -> TrajectoryRecorder:
    payload = {
        "question": session.question,
        "depth": session.depth,
        "max_iterations": 3,
        "min_sources_required": session.min_sources_required,
        "max_research_time_minutes": session.max_research_time_minutes,
    }
    payload.update(overrides)
    return TrajectoryRecorder(session.id, **payload)


async def _record(recorder: TrajectoryRecorder, iteration: int = 1, **overrides):
    payload = {
        "iteration": iteration,
        "executed_action": "SEARCH",
        "action_parameters": {"query": "q", "facet": "economic"},
        "next_action": "VERIFY",
        "next_action_reasoning": "contradiction found",
        "information_gain": 0.4,
        "coverage": 0.5,
        "new_sources": 2,
        "new_claims": 3,
        "new_nodes": 1,
        "new_edges": 1,
        "total_sources": 2,
        "total_claims": 3,
        "total_nodes": 1,
        "total_edges": 1,
        "unresolved_contradictions": 1,
        "resolved_contradictions": 0,
        "gaps": ["economic"],
        "facet_coverage": 0.4,
        "source_credibilities": [0.8, 0.3],
        "source_urls": ["https://a.example/x", "https://b.example/y"],
        "claim_confidences": ["high", "medium", "low"],
        "duplicate_claim_count": 0,
        "contradictions_are_new": True,
        "plateau_iterations": 0,
        "duration_seconds": 12.0,
        "elapsed_seconds": 20.0,
        "llm_calls": 4,
        "llm_call_budget": 150,
        "queries_executed": 1,
        "max_queries": 30,
    }
    payload.update(overrides)
    return await recorder.record_iteration(**payload)


@pytest.mark.asyncio
async def test_recorder_persists_a_full_transition(db_session: AsyncSession) -> None:
    session = await _session(db_session)
    recorder = _recorder(session)

    step = await _record(recorder)

    assert step is not None
    rows = await TransitionRepository(db_session).get_by_session(session.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.action_type == "SEARCH"
    assert row.state_before["iteration"] == 0
    assert row.state_after["iteration"] == 1
    assert row.reward == step.reward
    assert row.reward_components["total"] == step.reward
    assert row.policy_source == "JEV"
    assert row.done is False
    assert row.state_hash and row.state_bytes > 0
    assert row.observation["sources_added"] == 2


@pytest.mark.asyncio
async def test_recording_the_same_iteration_twice_updates_in_place(
    db_session: AsyncSession,
) -> None:
    """A replayed step must not double-count in every future dataset."""
    session = await _session(db_session)
    recorder = _recorder(session)

    await _record(recorder)
    await _record(recorder, information_gain=0.9)

    rows = await TransitionRepository(db_session).get_by_session(session.id)
    assert len(rows) == 1
    assert rows[0].information_gain == 0.9


@pytest.mark.asyncio
async def test_terminal_step_is_marked_done(db_session: AsyncSession) -> None:
    session = await _session(db_session)
    recorder = _recorder(session)

    step = await _record(recorder, next_action="STOP")

    rows = await TransitionRepository(db_session).get_by_session(session.id)
    assert step is not None
    assert rows[0].done is True


@pytest.mark.asyncio
async def test_shadow_prediction_is_recorded_but_never_executed(
    db_session: AsyncSession,
) -> None:
    session = await _session(db_session)
    training = [
        make_state(iteration=index, coverage=0.5, information_gain=0.4) for index in range(6)
    ]
    policy = TabularPolicy.train(
        [
            make_transition(
                index + 1,
                id=f"t{index}",
                action="VERIFY",
                reward=3.0,
                state_before=training[index].to_dict(),
                state_after=training[index].to_dict(),
            )
            for index in range(6)
        ],
        min_samples=1,
    )
    await PolicyRepository(db_session).create(
        name="test-policy",
        algorithm=policy.to_dict()["algorithm"],
        payload=policy.to_dict(),
        samples=policy.samples,
        active=True,
    )
    await db_session.commit()

    recorder = _recorder(session)
    # The state the shadow compares against is built by the recorder from its own
    # inputs; drive it into the learned context (coverage 0.5, gain 0.4).
    step = await _record(recorder, next_action="SEARCH")

    assert step is not None
    assert step.shadow is not None
    assert step.shadow["jev_action"] == "SEARCH"
    assert step.shadow["rl_action"] == "VERIFY"
    assert step.shadow["disagreement"] is True

    predictions = await PredictionRepository(db_session).get_by_session(session.id)
    assert len(predictions) == 1
    assert predictions[0].rl_action == "VERIFY"
    assert predictions[0].actual_reward is None  # nothing has run yet

    # The transition still records what JEV did — the prediction did not execute.
    rows = await TransitionRepository(db_session).get_by_session(session.id)
    assert rows[0].action_type == "SEARCH"


@pytest.mark.asyncio
async def test_shadow_backfills_the_previous_action_reward(
    db_session: AsyncSession,
) -> None:
    session = await _session(db_session)
    policy = TabularPolicy.train(
        [
            make_transition(
                index + 1,
                id=f"b{index}",
                action="SEARCH",
                reward=1.0,
                state_before=make_state(iteration=index).to_dict(),
                state_after=make_state(iteration=index + 1).to_dict(),
            )
            for index in range(6)
        ],
        min_samples=1,
    )
    await PolicyRepository(db_session).create(
        name="test-policy",
        algorithm=policy.to_dict()["algorithm"],
        payload=policy.to_dict(),
        samples=policy.samples,
        active=True,
    )
    await db_session.commit()

    recorder = _recorder(session)
    await _record(recorder, iteration=1)
    # Second iteration records no new era of its own prediction; the first prediction
    # must now know what its action earned.
    await _record(recorder, iteration=2, executed_action="VERIFY")

    predictions = await PredictionRepository(db_session).get_by_session(session.id)
    assert predictions[0].actual_reward is not None
    assert predictions[1].actual_reward is None


@pytest.mark.asyncio
async def test_shadow_is_skipped_when_no_policy_is_active(
    db_session: AsyncSession,
) -> None:
    session = await _session(db_session)
    recorder = _recorder(session)

    step = await _record(recorder)

    assert step is not None
    assert step.shadow is None
    assert await PredictionRepository(db_session).get_by_session(session.id) == []


@pytest.mark.asyncio
async def test_recorder_never_raises_even_when_the_database_is_unusable(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Telemetry failure must cost the run nothing."""
    from app.services.rl import recorder as recorder_module

    session = await _session(db_session)

    class ExplodingFactory:
        def __call__(self):
            raise RuntimeError("database is down")

    monkeypatch.setattr(recorder_module, "_session_factory", ExplodingFactory())
    recorder = _recorder(session)

    assert await _record(recorder) is None


@pytest.mark.asyncio
async def test_disabled_recorder_writes_nothing(db_session: AsyncSession) -> None:
    session = await _session(db_session)
    recorder = _recorder(session, enabled=False)

    assert await _record(recorder) is None
    assert await TransitionRepository(db_session).count(session.id) == 0


@pytest.mark.asyncio
async def test_recorder_tracks_state_between_iterations(
    db_session: AsyncSession,
) -> None:
    session = await _session(db_session)
    recorder = _recorder(session)

    await _record(recorder, iteration=1, coverage=0.3)
    initial_before = recorder.state_before

    await _record(
        recorder,
        iteration=2,
        coverage=0.6,
        executed_action="VERIFY",
        total_sources=5,
        total_claims=9,
    )

    rows = await TransitionRepository(db_session).get_by_session(session.id)
    assert len(rows) == 2
    # Iteration 2 starts where iteration 1 finished.
    assert rows[1].state_before["coverage"] == initial_before.to_dict()["coverage"]
    assert rows[1].state_before["previous_action"] == "SEARCH"
    assert rows[1].action_type == "VERIFY"


@pytest.mark.asyncio
async def test_shadow_prediction_failure_is_contained(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken policy object must not stop the transition from being recorded."""
    session = await _session(db_session)
    recorder = _recorder(session)

    async def broken_load() -> None:
        recorder._policy_loaded = True
        recorder._policy = object()  # not a policy at all

    monkeypatch.setattr(recorder, "_load_policy", broken_load)

    step = await _record(recorder)

    assert step is not None
    assert step.shadow is None
    assert await TransitionRepository(db_session).count(session.id) == 1


def test_duplicate_claim_counter_normalises_case_and_spacing() -> None:
    assert count_duplicate_claims(["Solar costs fell", "solar costs  fell", "Other"]) == 1
    assert count_duplicate_claims([]) == 0


def test_jev_baseline_expects_an_executable_action() -> None:
    assert JevPolicy().predict(make_state()).action in executable_actions()
