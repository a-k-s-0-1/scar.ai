"""History backfill (V2 2.5): completed sessions that predate the recorder.

``research_actions`` carry the per-iteration yield but V1 never joined a decision to
its outcome. The backfill reconstructs that join from stored rows; these tests hold
it to: correct per-iteration yields, honest ``backfilled`` labelling, idempotency,
a ``done`` terminal step, and a dataset that trains from the result.
"""

from __future__ import annotations

from datetime import timedelta
from itertools import pairwise

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ResearchAction, ResearchSession, utc_now
from app.database.repository import (
    ClaimRepository,
    DecisionRepository,
    SessionRepository,
    SourceRepository,
    TransitionRepository,
)
from app.services.rl import TrajectoryDataset
from app.services.rl.service import TrajectoryService


async def _seed_completed_session(
    db: AsyncSession, *, with_actions: bool = True
) -> ResearchSession:
    """A finished 3-iteration run with V1-shaped rows and no transitions."""
    session = await SessionRepository(db).create(question="Is green hydrogen viable?", depth="standard")
    session.status = "completed"
    session.started_at = utc_now() - timedelta(minutes=10)
    session.completed_at = utc_now() - timedelta(minutes=2)
    await db.commit()

    if not with_actions:
        return session

    base = utc_now() - timedelta(minutes=9)
    decisions = DecisionRepository(db)
    for iteration in range(1, 4):
        action_at = base + timedelta(minutes=iteration)
        db.add(
            ResearchAction(
                session_id=session.id,
                iteration_number=iteration,
                action_type="STOP" if iteration == 3 else "SEARCH",
                query=f"query {iteration}",
                sources_found=2 if iteration < 3 else 0,
                new_claims_extracted=3 if iteration < 3 else 0,
                information_gain=0.3 if iteration < 3 else 0.0,
                duration_seconds=30,
                created_at=action_at,
            )
        )
        await decisions.log_decision(
            session.id,
            iteration_number=iteration,
            knowledge_state_snapshot={"iteration": iteration},
            available_actions=["SEARCH", "VERIFY", "EXPAND_QUERY", "STOP"],
            selected_action="STOP" if iteration == 3 else "SEARCH",
            action_reasoning=f"reasoning {iteration}",
            reward_signal=1.0,
        )
        # Yield rows for iterations 1 and 2 only (STOP collects nothing), each
        # stamped between this action and the next so the window slicing is
        # exercised deterministically.
        if iteration < 3:
            for k in range(2):
                await SourceRepository(db).create(
                    session_id=session.id,
                    url=f"https://example{iteration}{k}.com/article",
                    title=f"Source {iteration}-{k}",
                    content=None,
                    credibility_score=0.8 if k == 0 else 0.3,
                )
            for k in range(3):
                text = f"claim {k}" if k < 2 else f"claim 0 dup {iteration}"
                await ClaimRepository(db).create(
                    session_id=session.id,
                    claim_text=text,
                    confidence="high" if k == 0 else "medium",
                )
            await db.flush()
    await db.commit()
    return session


async def _stamp_rows(db: AsyncSession, session_id: str, base) -> None:
    """Assign sources/claims to iteration windows via created_at.

    V1 logged a research_action *after* its search completed, so each row must be
    stamped before its iteration's action timestamp (base + iteration minutes) to
    land inside the window the backfill attributes to that action.
    """
    from app.database.models import Claim, Source

    for index, source in enumerate(
        (await db.execute(select(Source).where(Source.session_id == session_id))).scalars()
    ):
        iteration = 1 + index // 2  # two sources per iteration
        source.created_at = base + timedelta(
            minutes=iteration - 1, seconds=50 + index
        )
    for index, claim in enumerate(
        (await db.execute(select(Claim).where(Claim.session_id == session_id))).scalars()
    ):
        iteration = 1 + index // 3  # three claims per iteration
        claim.created_at = base + timedelta(
            minutes=iteration - 1, seconds=55 + index
        )
    await db.commit()


@pytest.mark.asyncio
async def test_backfill_creates_transitions_from_v1_history(db_session: AsyncSession):
    session = await _seed_completed_session(db_session)
    base = utc_now() - timedelta(minutes=9)
    await _stamp_rows(db_session, session.id, base)

    service = TrajectoryService(db_session)
    result = await service.backfill_history()

    assert result["sessions_backfilled"] == 1
    assert result["transitions_created"] == 3

    rows = await TransitionRepository(db_session).get_by_session(session.id)
    assert [row.iteration for row in rows] == [1, 2, 3]
    assert [row.action_type for row in rows] == ["SEARCH", "SEARCH", "STOP"]

    # Per-iteration yields come from research_actions, not guesses.
    assert rows[0].sources_added == 2
    assert rows[0].claims_added == 3
    assert rows[2].sources_added == 0 and rows[2].claims_added == 0

    # The chain is connected: state_after of one step is state_before of the next
    # (same iteration counts and monotone coverage from the cumulative corpus).
    for prev, nxt in pairwise(rows):
        assert prev.state_after["iteration"] == nxt.state_before["iteration"]
        assert nxt.coverage_after >= nxt.coverage_before - 1e-9

    # Every backfilled row is labelled as such — no consumer can mistake it for a
    # measured live step.
    for row in rows:
        assert row.observation.get("backfilled") is True
        assert row.reward_components.get("total") == pytest.approx(row.reward, abs=1e-6)
        assert row.state_hash

    # Only the terminal step is done.
    assert [row.done for row in rows] == [False, False, True]

    # The first step's before-state is the empty corpus (coverage 0), so a
    # replayed JEV sees the run the way it saw it. This is a regression test:
    # a None before_cut once aggregated the whole session into state_before,
    # which showed coverage 0.99 at iteration 0 and broke JEV replay.
    assert rows[0].coverage_before == 0.0
    assert rows[0].state_before["total_sources"] == 0
    assert rows[0].state_before["coverage"] == 0.0
    assert rows[0].coverage_after > 0.0


@pytest.mark.asyncio
async def test_backfill_from_decisions_only(db_session: AsyncSession):
    """Sessions that logged only decisions (no research_actions) still backfill.

    V1's earliest runs never wrote research_actions. The decision timestamps close
    the work of the previous action, and rows older than the first decision are
    V1's unconditional initial search — reconstructed as a synthetic iteration 0.
    """
    session = await _seed_completed_session(db_session, with_actions=False)
    # Stamp the V1 layout directly onto rows: initial search before the first
    # decision, then one work window per decision gap.
    base = utc_now() - timedelta(minutes=9)
    db = db_session
    decisions = DecisionRepository(db)
    for iteration, (action, offset_min) in enumerate(
        [("SEARCH", 2.0), ("VERIFY", 4.0), ("STOP", 6.0)], start=1
    ):
        await decisions.log_decision(
            session.id,
            iteration_number=iteration,
            knowledge_state_snapshot={},
            available_actions=["SEARCH", "VERIFY", "STOP"],
            selected_action=action,
            action_reasoning="reconstructed",
        )
    # Decision rows all carry utc_now(); give them a deterministic spacing.
    from app.database.models import Decision

    rows = (
        await db.execute(
            select(Decision).where(Decision.session_id == session.id)
        )
    ).scalars().all()
    for index, row in enumerate(rows):
        row.created_at = base + timedelta(minutes=2 * (index + 1))
    # Sources/claims: some before the first decision (initial search), some after.
    from app.database.models import Claim, Source

    # _seed_completed_session(with_actions=False) created no rows; add some here.
    for k in range(2):
        await SourceRepository(db).create(
            session_id=session.id,
            url=f"https://initial.com/{k}",
            title=f"Initial {k}",
            content=None,
            credibility_score=0.7,
        )
    await ClaimRepository(db).create(
        session_id=session.id, claim_text="initial claim", confidence="high"
    )
    await db.flush()
    extra_sources = (
        await db.execute(select(Source).where(Source.session_id == session.id))
    ).scalars().all()
    extra_claims = (
        await db.execute(select(Claim).where(Claim.session_id == session.id))
    ).scalars().all()
    for index, row in enumerate(extra_sources):
        if row.url.startswith("https://initial"):
            row.created_at = base + timedelta(minutes=1)  # before decision 1
        else:
            row.created_at = base + timedelta(minutes=3 + index)  # window of iter 1
    for index, row in enumerate(extra_claims):
        if row.claim == "initial claim":
            row.created_at = base + timedelta(minutes=1)
        else:
            row.created_at = base + timedelta(minutes=3 + index)
    await db.commit()

    result = await TrajectoryService(db_session).backfill_history()
    # initial search (iteration 1) + decisions 1 and 2 (iterations 2, 3);
    # the final STOP decision executes nothing and only marks the end.
    assert result["transitions_created"] == 3

    rows = await TransitionRepository(db_session).get_by_session(session.id)
    assert [row.iteration for row in rows] == [1, 2, 3]
    assert rows[0].action_type == "SEARCH"
    assert rows[0].observation["reconstructed_from"] == "initial_search"
    assert rows[1].observation["reconstructed_from"] == "decisions"
    assert [row.action_type for row in rows] == ["SEARCH", "SEARCH", "VERIFY"]
    assert rows[0].sources_added == 2 and rows[0].claims_added == 1
    assert rows[-1].done is True


@pytest.mark.asyncio
async def test_backfill_is_idempotent(db_session: AsyncSession):
    session = await _seed_completed_session(db_session)
    await _stamp_rows(db_session, session.id, utc_now() - timedelta(minutes=9))

    service = TrajectoryService(db_session)
    first = await service.backfill_history()
    second = await service.backfill_history()

    assert first["transitions_created"] == 3
    assert second["transitions_created"] == 0
    rows = await TransitionRepository(db_session).get_by_session(session.id)
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_backfill_skips_sessions_without_actions(db_session: AsyncSession):
    await _seed_completed_session(db_session, with_actions=False)
    result = await TrajectoryService(db_session).backfill_history()
    assert result["sessions_backfilled"] == 0
    assert result["transitions_created"] == 0


@pytest.mark.asyncio
async def test_backfilled_dataset_builds_and_trains(db_session: AsyncSession):
    session = await _seed_completed_session(db_session)
    await _stamp_rows(db_session, session.id, utc_now() - timedelta(minutes=9))

    service = TrajectoryService(db_session)
    await service.backfill_history()

    dataset = await service.build()
    assert isinstance(dataset, TrajectoryDataset)
    assert dataset.stats()["transitions"] == 3
    assert dataset.stats()["sessions"] == 1
    assert dataset.stats()["done_transitions"] == 1
    # No validation issues: the reconstructed chain is well-formed.
    assert dataset.issues == []
    # The exported samples carry the required learning fields.
    sample = dataset.samples[0]
    assert sample["action"] in {"SEARCH", "STOP"}
    assert isinstance(sample["reward"], float)
    assert "state" in sample and "next_state" in sample


@pytest.mark.asyncio
async def test_backfill_via_build_endpoint(db_session: AsyncSession, client):
    """POST /dataset/build with backfill=true trains from V1 history in one call."""
    session = await _seed_completed_session(db_session)
    await _stamp_rows(db_session, session.id, utc_now() - timedelta(minutes=9))

    response = await client.post(
        "/api/evaluation/dataset/build",
        json={"train": True, "backfill": True, "activate": True},
        headers={"X-API-Key": "dev_api_key_jev_ikf_2026"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["trained"] is True
    assert body["policy"] is not None
    assert body["policy"]["samples"] >= 1
    assert body["dataset"]["transitions"] == 3
    assert body["backfill"]["transitions_created"] == 3
