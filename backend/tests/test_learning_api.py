"""Learning API (V2 2.9 / 2.12): trajectory, state, evaluation and memory endpoints.

Behaviour through the real surface: seeded rows in, HTTP in, JSON out — including the
error envelope, because a client cannot be expected to handle two error shapes.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import (
    DecisionRepository,
    PolicyRepository,
    PredictionRepository,
    SessionRepository,
    TransitionRepository,
)
from app.services.rl import TabularPolicy
from tests.conftest import make_state, make_transition

HEADERS = {"X-API-Key": "dev_api_key_jev_ikf_2026"}


async def _seed_session(db: AsyncSession, question: str = "Is hydrogen viable?"):
    session = await SessionRepository(db).create(question=question, depth="shallow")
    await db.commit()
    return session


async def _seed_trajectory(db: AsyncSession, session_id: str, count: int = 3):
    repo = TransitionRepository(db)
    for index in range(count):
        state_before = make_state(
            session_id=session_id, iteration=index, coverage=0.3 + index * 0.1
        )
        state_after = make_state(
            session_id=session_id,
            iteration=index + 1,
            coverage=0.35 + index * 0.1,
            previous_action="SEARCH",
        )
        await repo.upsert(
            session_id=session_id,
            iteration=index + 1,
            state_before=state_before.to_dict(),
            state_after=state_after.to_dict(),
            action_type="SEARCH",
            action_parameters={"query": f"q{index}"},
            observation={"sources_added": 1, "claims_added": 2},
            reward=1.0 + index,
            reward_components={
                "information_gain_reward": 0.8,
                "unnecessary_action_penalty": 0.05,
                "total": 1.0 + index,
            },
            information_gain=0.4,
            coverage_before=state_before.coverage,
            coverage_after=state_after.coverage,
            contradictions_before=0,
            contradictions_after=0,
            sources_added=1,
            claims_added=2,
            execution_time=10.0,
            policy_source="JEV",
            done=index == count - 1,
            state_hash=state_after.state_hash(),
            state_bytes=state_after.state_size(),
        )
    await db.commit()


async def _seed_policy(db: AsyncSession, *, active: bool = True):
    records = [
        make_transition(
            index + 1,
            id=f"train-{index}",
            action="VERIFY",
            reward=3.0,
            done=index == 5,
            state_before=make_state(iteration=index, coverage=0.3).to_dict(),
            state_after=make_state(iteration=index + 1, coverage=0.35).to_dict(),
        )
        for index in range(6)
    ]
    policy = TabularPolicy.train(records, min_samples=1)
    row = await PolicyRepository(db).create(
        name="api-test-policy",
        algorithm=policy.to_dict()["algorithm"],
        payload=policy.to_dict(),
        samples=policy.samples,
        sessions=1,
        active=False,
    )
    if active:
        await PolicyRepository(db).set_active(row.id)
    await db.commit()
    return row


# ─── trajectory, decisions and state ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_trajectory_endpoint_returns_ordered_transitions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    session = await _seed_session(db_session)
    await _seed_trajectory(db_session, session.id, count=3)

    response = await client.get(
        f"/api/research/{session.id}/trajectory", headers=HEADERS
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["complete"] is True
    assert payload["policies"] == {"JEV": 3}
    assert [row["iteration"] for row in payload["transitions"]] == [1, 2, 3]
    assert payload["transitions"][0]["reward_components"]["information_gain_reward"] == 0.8
    assert payload["transitions"][0]["state_bytes"] > 0


@pytest.mark.asyncio
async def test_trajectory_endpoint_404s_unknown_sessions(client: AsyncClient) -> None:
    response = await client.get("/api/research/nope/trajectory", headers=HEADERS)

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "SessionNotFoundError"
    assert body["error"]["details"]["session_id"] == "nope"


@pytest.mark.asyncio
async def test_decision_inspector_joins_state_actions_reward_and_shadow(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    session = await _seed_session(db_session)
    await _seed_trajectory(db_session, session.id, count=2)
    await DecisionRepository(db_session).log_decision(
        session_id=session.id,
        iteration_number=1,
        knowledge_state_snapshot={"iteration": 1, "coverage_estimate": 0.35},
        available_actions=["SEARCH", "VERIFY", "EXPAND_QUERY", "STOP"],
        selected_action="SEARCH",
        action_reasoning="coverage below threshold",
        reward_signal=1.2,
    )
    await PredictionRepository(db_session).create(
        session_id=session.id,
        iteration=1,
        state_key="coverage=very_low",
        jev_action="SEARCH",
        rl_action="VERIFY",
        rl_expected_value=2.5,
        rl_scores={"VERIFY": 2.5},
        rl_support=4,
        disagreement=True,
    )
    await db_session.commit()

    response = await client.get(
        f"/api/research/{session.id}/decisions", headers=HEADERS
    )

    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["jev_action"] == "SEARCH"
    assert entry["rl_action"] == "VERIFY"
    assert entry["disagreement"] is True
    assert entry["actual_action"] == "SEARCH"
    assert entry["reward"] == 1.0
    assert entry["available_actions"] == ["SEARCH", "VERIFY", "EXPAND_QUERY", "STOP"]
    # The reward is explained component by component, not just totalled.
    assert {row["component"] for row in entry["reward_explanation"]} == {
        "information_gain_reward",
        "unnecessary_action_penalty",
    }


@pytest.mark.asyncio
async def test_state_endpoint_reports_the_recorded_state(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    session = await _seed_session(db_session)
    await _seed_trajectory(db_session, session.id, count=2)

    response = await client.get(f"/api/research/{session.id}/state", headers=HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "trajectory"
    assert payload["state"]["iteration"] == 2
    assert payload["state_hash"]
    assert "coverage=" in payload["state_key"]
    assert set(payload["features"]) == {
        "coverage",
        "gain",
        "contradictions",
        "gaps",
        "facets",
        "budget",
        "phase",
        "previous",
    }


@pytest.mark.asyncio
async def test_state_endpoint_reconstructs_for_runs_without_transitions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    session = await _seed_session(db_session)

    response = await client.get(f"/api/research/{session.id}/state", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["source"] == "reconstructed"


@pytest.mark.asyncio
async def test_predictions_endpoint_counts_agreement(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    session = await _seed_session(db_session)
    repo = PredictionRepository(db_session)
    await repo.create(
        session_id=session.id,
        iteration=1,
        state_key="k",
        jev_action="SEARCH",
        rl_action="SEARCH",
        disagreement=False,
    )
    await repo.create(
        session_id=session.id,
        iteration=2,
        state_key="k",
        jev_action="SEARCH",
        rl_action="VERIFY",
        disagreement=True,
    )
    await db_session.commit()

    response = await client.get(
        f"/api/research/{session.id}/predictions", headers=HEADERS
    )

    payload = response.json()
    assert payload["total"] == 2
    assert payload["agreements"] == 1
    assert payload["disagreements"] == 1


# ─── dataset ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dataset_stats_endpoint_works_on_an_empty_store(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/evaluation/dataset/stats", headers=HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["transitions"] == 0
    assert payload["sessions"] == 0
    assert payload["recorded_transitions"] == 0


@pytest.mark.asyncio
async def test_dataset_endpoint_exports_valid_samples(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    session = await _seed_session(db_session)
    await _seed_trajectory(db_session, session.id, count=2)

    response = await client.get("/api/evaluation/dataset", headers=HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["transitions"] == 2
    assert payload["session_ids"] == [session.id]
    assert set(payload["samples"][0]) == {
        "state",
        "action",
        "reward",
        "next_state",
        "done",
    }
    assert payload["dataset_hash"]


@pytest.mark.asyncio
async def test_dataset_export_is_jsonl(client: AsyncClient, db_session: AsyncSession) -> None:
    session = await _seed_session(db_session)
    await _seed_trajectory(db_session, session.id, count=2)

    response = await client.get("/api/evaluation/dataset/export", headers=HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [line for line in response.text.splitlines() if line]
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_dataset_build_trains_a_policy_and_evaluation_compares_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    session = await _seed_session(db_session)
    await _seed_trajectory(db_session, session.id, count=3)

    build = await client.post(
        "/api/evaluation/dataset/build",
        headers=HEADERS,
        json={"train": True, "activate": True, "policy_name": "api-run"},
    )

    assert build.status_code == 200
    payload = build.json()
    assert payload["dataset"]["transitions"] == 3
    assert payload["trained"] is True
    assert payload["policy"]["active"] is True
    assert payload["policy_metrics"]["is_deep_rl"] is False

    run = await client.post(
        "/api/evaluation/run",
        headers=HEADERS,
        json={"policy": "rl", "baseline": "jev", "max_steps": 3},
    )

    assert run.status_code == 200
    report = run.json()
    assert report["dataset_size"] == 3
    assert report["policy"] == "rl"
    assert report["metrics"]["steps"] == 3
    assert report["baseline_metrics"]["steps"] == 3
    assert "agreement_rate" in report["comparison"]
    assert report["notes"]
    assert report["run_id"]

    results = await client.get("/api/evaluation/results", headers=HEADERS)
    assert results.status_code == 200
    assert results.json()["total"] == 1

    detail = await client.get(
        f"/api/evaluation/results/{report['run_id']}", headers=HEADERS
    )
    assert detail.status_code == 200
    scopes = {row["scope"] for row in detail.json()["results"]}
    assert scopes == {"overall", "session", "action"}


@pytest.mark.asyncio
async def test_jev_evaluation_needs_no_policy(client: AsyncClient, db_session: AsyncSession) -> None:
    session = await _seed_session(db_session)
    await _seed_trajectory(db_session, session.id, count=2)

    response = await client.post(
        "/api/evaluation/run", headers=HEADERS, json={"policy": "jev"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["policy"] == "jev"
    assert payload["metrics"]["observed_steps"] == 2


@pytest.mark.asyncio
async def test_rl_evaluation_without_a_policy_says_so_instead_of_failing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    session = await _seed_session(db_session)
    await _seed_trajectory(db_session, session.id, count=2)

    response = await client.post(
        "/api/evaluation/run", headers=HEADERS, json={"policy": "rl"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["policy"] == "jev"
    assert any("No trained policy is active" in note for note in payload["notes"])


@pytest.mark.asyncio
async def test_unsupported_dataset_version_is_rejected_with_the_envelope(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/evaluation/run",
        headers=HEADERS,
        json={"policy": "jev", "dataset_version": "v0"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "EvaluationOptionsError"
    assert "v2.0" in body["error"]["details"]["supported"]


@pytest.mark.asyncio
async def test_policy_listing_and_activation(client: AsyncClient, db_session: AsyncSession) -> None:
    row = await _seed_policy(db_session, active=False)

    listed = await client.get("/api/evaluation/policies", headers=HEADERS)
    assert listed.status_code == 200
    assert listed.json()["policies"][0]["name"] == "api-test-policy"

    activated = await client.post(
        f"/api/evaluation/policies/{row.id}/activate", headers=HEADERS
    )
    assert activated.status_code == 200
    assert activated.json()["policy"]["active"] is True
    assert "JEV continues" in activated.json()["message"]

    missing = await client.post(
        "/api/evaluation/policies/nope/activate", headers=HEADERS
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "EvaluationOptionsError"


@pytest.mark.asyncio
async def test_reward_formula_endpoint_documents_the_calculation(client: AsyncClient) -> None:
    response = await client.get("/api/evaluation/reward-formula", headers=HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["reward"]["total"] == "sum(positive) - sum(penalties)"
    assert payload["actions"]["executable"] == [
        "VERIFY",
        "EXPAND_QUERY",
        "SEARCH",
        "STOP",
    ]
    assert payload["production_policy"] == "JEV"


@pytest.mark.asyncio
async def test_learning_endpoints_require_the_api_key_in_production(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The new surface follows the same auth rule as the existing one."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "API_KEY", "a-real-key")

    unauthenticated: Any = await client.get("/api/evaluation/dataset/stats")
    wrong = await client.get(
        "/api/evaluation/dataset/stats", headers={"X-API-Key": "nope"}
    )
    accepted = await client.get(
        "/api/evaluation/dataset/stats", headers={"X-API-Key": "a-real-key"}
    )

    assert unauthenticated.status_code == 401
    assert wrong.status_code == 401
    assert accepted.status_code == 200


# ─── memory surface ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_search_session_conflicts_and_promote(
    client: AsyncClient, db_session: AsyncSession, memory_bound_to_test_db: None
) -> None:
    from app.services.memory import ClaimVersionRecord, LongTermMemory

    session = await _seed_session(db_session, question="Is hydrogen viable?")
    memory = LongTermMemory()
    await memory.remember_claim_versions(
        [
            {
                "subject": "hydrogen cost",
                "predicate": "equals",
                "versions": [
                    ClaimVersionRecord(
                        value="$4/kg",
                        text="Hydrogen cost was $4/kg in 2024.",
                        valid_from=2024,
                        valid_to=2024,
                        session_id=session.id,
                        sources=["https://a.example"],
                    ),
                    ClaimVersionRecord(
                        value="$2/kg",
                        text="Hydrogen cost is $2/kg in 2026.",
                        valid_from=2026,
                        valid_to=2026,
                        session_id=session.id,
                        sources=["https://b.example"],
                    ),
                ],
            }
        ],
        session_id=session.id,
    )

    search = await client.get("/api/memory/search?q=hydrogen", headers=HEADERS)
    assert search.status_code == 200
    assert search.json()["total"] >= 1

    for_session = await client.get(
        f"/api/memory/session/{session.id}", headers=HEADERS
    )
    assert for_session.status_code == 200
    assert for_session.json()["total"] >= 1
    assert for_session.json()["items"][0]["provenance"]["session_id"] == session.id

    conflicts = await client.get("/api/memory/conflicts", headers=HEADERS)
    assert conflicts.status_code == 200
    payload = conflicts.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["status"] == "superseded"
    statuses = {version["status"] for version in item["versions"]}
    assert statuses == {"active", "superseded"}
    assert item["versions"][0]["sources"]

    unknown_status = await client.get(
        "/api/memory/conflicts?status=made_up", headers=HEADERS
    )
    assert unknown_status.status_code == 422

    promote = await client.post(
        "/api/memory/promote",
        headers=HEADERS,
        json={"session_id": session.id},
    )
    assert promote.status_code == 200
    assert promote.json()["session_id"] == session.id

    missing = await client.post(
        "/api/memory/promote", headers=HEADERS, json={"session_id": "nope"}
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SessionNotFoundError"
