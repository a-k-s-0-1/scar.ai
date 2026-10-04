"""Tests for the durable session event log and its replay endpoint."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import SessionEventRepository, SessionRepository
from app.services import event_recorder
from app.ws.managers import ConnectionManager

API_HEADERS = {"X-API-Key": "dev_api_key_jev_ikf_2026"}


class FakeSocket:
    """Minimal stand-in for a connected WebSocket."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, message: dict[str, Any]) -> None:
        self.sent.append(message)


@pytest.mark.asyncio
async def test_events_are_sequenced_per_session(db_session: AsyncSession) -> None:
    """Sequences are monotonic within a session and independent across sessions."""
    sessions = SessionRepository(db_session)
    first = await sessions.create(question="Do event logs outlive a finished run?", depth="shallow")
    second = await sessions.create(question="Are sequence numbers isolated per session?", depth="shallow")
    await db_session.commit()

    events = SessionEventRepository(db_session)
    assert await events.append(first.id, {"type": "initialized"}) == 1
    assert await events.append(first.id, {"type": "search_started", "iteration": 1}) == 2
    assert await events.append(second.id, {"type": "initialized"}) == 1
    await db_session.commit()

    stored = await events.list_events(first.id)
    assert [event.seq for event in stored] == [1, 2]
    assert [event.event_type for event in stored] == ["initialized", "search_started"]
    assert stored[1].iteration == 1
    assert stored[0].iteration is None

    resumed = await events.list_events(first.id, after_seq=1)
    assert [event.event_type for event in resumed] == ["search_started"]
    assert await events.count(first.id) == 2


@pytest.mark.asyncio
async def test_broadcast_persists_then_stamps_sequence() -> None:
    """The live message carries the stored seq so replays can skip duplicates."""
    manager = ConnectionManager()
    recorded: list[tuple[str, str]] = []

    async def recorder(session_id: str, message: dict[str, Any]) -> int:
        recorded.append((session_id, str(message["type"])))
        return 7

    manager.set_event_recorder(recorder)
    socket = FakeSocket()
    manager.active_connections["s-1"].append(socket)

    await manager.broadcast("s-1", {"type": "sources_found", "count": 3})

    assert recorded == [("s-1", "sources_found")]
    assert socket.sent == [{"type": "sources_found", "count": 3, "seq": 7}]


@pytest.mark.asyncio
async def test_broadcast_records_without_listeners() -> None:
    """A run nobody watched must still leave a timeline behind."""
    manager = ConnectionManager()
    recorded: list[str] = []

    async def recorder(session_id: str, message: dict[str, Any]) -> int | None:
        recorded.append(str(message["type"]))
        return None

    manager.set_event_recorder(recorder)

    await manager.broadcast("s-2", {"type": "completed"})

    assert recorded == ["completed"]


@pytest.mark.asyncio
async def test_recorder_skips_non_progress_messages(
    recorder_bound_to_test_db: None,
) -> None:
    """Only research progress is persisted; ad-hoc chatter is not."""
    assert await event_recorder.record_session_event("s-3", {"type": "ping"}) is None
    assert await event_recorder.record_session_event("s-3", {"type": "initialized"}) == 1


@pytest.mark.asyncio
async def test_ikf_updated_is_persisted_for_replay(
    recorder_bound_to_test_db: None,
) -> None:
    """IKF telemetry must survive the run, not only stream past a live listener.

    The recorder keeps an allow-list of progress events; a new broadcast type that is
    missing from it looks fine while watching a run and is silently gone on replay.
    """
    assert (
        await event_recorder.record_session_event(
            "s-ikf",
            {
                "type": "ikf_updated",
                "iteration": 2,
                "evidence": {"claims": 12, "mean_strength": 0.41},
                "versions": {"versioned": 1},
            },
        )
        == 1
    )


@pytest.mark.asyncio
async def test_events_endpoint_replays_and_resumes(
    client: AsyncClient,
    db_session: AsyncSession,
    recorder_bound_to_test_db: None,
) -> None:
    """The endpoint returns the timeline in order and honours the resume cursor."""
    sessions = SessionRepository(db_session)
    session = await sessions.create(question="Can a finished run be replayed?", depth="shallow")
    await db_session.commit()

    await event_recorder.record_session_event(
        session.id, {"type": "initialized", "question": session.question}
    )
    await event_recorder.record_session_event(
        session.id, {"type": "completed", "total_claims": 3, "total_sources": 2}
    )

    res = await client.get(f"/api/research/{session.id}/events", headers=API_HEADERS)
    assert res.status_code == 200
    body = res.json()
    assert [event["type"] for event in body["events"]] == ["initialized", "completed"]
    assert body["latest_seq"] == 2
    assert body["total"] == 2
    assert body["events"][1]["payload"]["total_claims"] == 3

    resumed = await client.get(
        f"/api/research/{session.id}/events?after_seq=1", headers=API_HEADERS
    )
    assert [event["type"] for event in resumed.json()["events"]] == ["completed"]


@pytest.mark.asyncio
async def test_events_endpoint_rejects_unknown_session(client: AsyncClient) -> None:
    res = await client.get("/api/research/missing-session/events", headers=API_HEADERS)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "SessionNotFoundError"
