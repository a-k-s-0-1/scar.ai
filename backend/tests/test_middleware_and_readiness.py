"""Tests for request middleware, readiness probing, and background task tracking."""

import asyncio

import pytest
from httpx import AsyncClient

API_HEADERS = {"X-API-Key": "dev_api_key_jev_ikf_2026"}


@pytest.mark.asyncio
async def test_request_id_is_generated_and_echoed(client: AsyncClient) -> None:
    """Every response carries a correlation ID and a timing header."""
    generated = await client.get("/health/ready")
    assert generated.status_code == 200
    assert generated.headers.get("X-Request-ID")
    assert generated.headers.get("X-Response-Time-Ms")

    echoed = await client.get("/health/ready", headers={"X-Request-ID": "trace-123"})
    assert echoed.headers["X-Request-ID"] == "trace-123"


@pytest.mark.asyncio
async def test_error_envelope_carries_request_id(client: AsyncClient) -> None:
    """A failed request is traceable: the error body repeats the correlation ID."""
    res = await client.get(
        "/api/research/does-not-exist",
        headers={**API_HEADERS, "X-Request-ID": "trace-err"},
    )
    assert res.status_code == 404
    body = res.json()
    assert body["error"]["code"] == "SessionNotFoundError"
    assert body["error"]["request_id"] == "trace-err"
    assert body["error"]["path"] == "/api/research/does-not-exist"


@pytest.mark.asyncio
async def test_readiness_reports_database(client: AsyncClient) -> None:
    """The readiness probe verifies the database answers, not just the process."""
    res = await client.get("/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert body["timestamp"]


@pytest.mark.asyncio
async def test_duplicate_launch_returns_existing_task() -> None:
    """While a session is running, a second launch is ignored, not duplicated."""
    from app.services import research_orchestrator as orchestrator_module

    async def _hang() -> None:
        await asyncio.sleep(60)

    task = asyncio.create_task(_hang())
    orchestrator_module._running_tasks["sess-guard"] = task
    try:
        assert orchestrator_module.launch_research_task("sess-guard") is task
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        orchestrator_module._running_tasks.pop("sess-guard", None)


@pytest.mark.asyncio
async def test_finished_task_is_released_and_session_can_relaunch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed run releases its slot, so the same session can be relaunched."""
    from app.services import research_orchestrator as orchestrator_module

    class _StubOrchestrator:
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id

        async def run(self) -> None:
            return None

    monkeypatch.setattr(orchestrator_module, "ResearchOrchestrator", _StubOrchestrator)

    first = orchestrator_module.launch_research_task("sess-relaunch")
    assert first is not None
    await first
    await asyncio.sleep(0)
    assert "sess-relaunch" not in orchestrator_module._running_tasks

    second = orchestrator_module.launch_research_task("sess-relaunch")
    assert second is not None and second is not first
    await second
