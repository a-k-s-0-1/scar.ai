"""Tests for the unified error envelope and startup session reconciliation."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import SessionRepository
from app.services.session_manager import SessionManager

API_HEADERS = {"X-API-Key": "dev_api_key_jev_ikf_2026"}


@pytest.mark.asyncio
async def test_validation_error_uses_standard_envelope(client: AsyncClient) -> None:
    """Request validation failures share the app's error shape, not FastAPI's."""
    res = await client.post(
        "/api/research/start",
        headers={**API_HEADERS, "X-Request-ID": "trace-validation"},
        json={
            "question": "Does an out-of-range timeout still fail cleanly today?",
            "depth": "deep",
            "max_research_time_minutes": 20,
        },
    )
    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "ValidationError"
    assert body["error"]["message"] == "Request payload failed validation."
    assert body["error"]["request_id"] == "trace-validation"
    assert body["error"]["path"] == "/api/research/start"

    issues = body["error"]["details"]["issues"]
    assert any(
        issue["loc"][-1] == "max_research_time_minutes" for issue in issues
    ), f"expected the offending field in the issue list, got {issues}"


@pytest.mark.asyncio
async def test_reconcile_interrupted_sessions_marks_only_active_ones(
    db_session: AsyncSession,
) -> None:
    """A restart turns phantom 'running' sessions into errors, leaving others alone."""
    repo = SessionRepository(db_session)
    running = await repo.create(question="Session interrupted mid flight.")
    initializing = await repo.create(question="Session that never started.")
    finished = await repo.create(question="Session that already completed.")
    await repo.update_status(running.id, "running")
    await repo.update_status(finished.id, "completed")
    assert initializing.status == "initializing"
    await db_session.commit()

    reconciled = await SessionManager.reconcile_interrupted_sessions(db_session)

    assert reconciled == 2
    for session_id in (running.id, initializing.id):
        refreshed = await repo.get_by_id(session_id)
        assert refreshed is not None
        assert refreshed.status == "error"
        assert refreshed.error_message == "Interrupted by server restart."
        assert refreshed.completed_at is not None

    untouched = await repo.get_by_id(finished.id)
    assert untouched is not None
    assert untouched.status == "completed"
