"""Integration tests for FastAPI REST API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    """Verify health endpoint returns 200 and ok status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "environment" in data


@pytest.mark.asyncio
async def test_start_research_validation(client: AsyncClient) -> None:
    """Verify question validation rejects too-short questions."""
    headers = {"X-API-Key": "dev_api_key_jev_ikf_2026"}
    res = await client.post(
        "/api/research/start", json={"question": "short"}, headers=headers
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_session_lifecycle_api(client: AsyncClient) -> None:
    """Verify session start, lookup, stop, and list endpoints."""
    headers = {"X-API-Key": "dev_api_key_jev_ikf_2026"}

    # Start session
    payload = {
        "question": "What is the status of room temperature superconductivity research?",
        "depth": "standard",
    }
    start_res = await client.post("/api/research/start", json=payload, headers=headers)
    assert start_res.status_code == 201
    session_data = start_res.json()
    session_id = session_data["id"]
    assert session_data["status"] == "initializing"

    # Get session
    get_res = await client.get(f"/api/research/{session_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == session_id

    # Stop session
    stop_res = await client.post(f"/api/research/{session_id}/stop", headers=headers)
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "stopped"

    # List sessions
    list_res = await client.get("/api/sessions", headers=headers)
    assert list_res.status_code == 200
    sessions_list = list_res.json()["sessions"]
    assert any(s["id"] == session_id for s in sessions_list)
