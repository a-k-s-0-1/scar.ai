"""Tests for request budgets on the research endpoints."""

import pytest
from httpx import AsyncClient

from app.api.errors import TooManyRequestsError
from app.api.rate_limit import (
    SlidingWindowLimiter,
    enforce_rate_limit,
    reset_rate_limiters,
)
from app.config import get_settings

API_HEADERS = {"X-API-Key": "dev_api_key_jev_ikf_2026"}


def test_sliding_window_allows_limit_then_refuses() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)

    assert limiter.check("caller", now=100.0).allowed
    assert limiter.check("caller", now=100.5).allowed

    blocked = limiter.check("caller", now=101.0)
    assert not blocked.allowed
    assert blocked.remaining == 0
    assert blocked.retry_after >= 1

    # Once the oldest hit leaves the window the caller is welcome again.
    assert limiter.check("caller", now=161.0).allowed


def test_limits_are_isolated_per_key() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)

    assert limiter.check("alpha", now=1.0).allowed
    assert not limiter.check("alpha", now=2.0).allowed
    assert limiter.check("beta", now=2.0).allowed


def test_enforce_rate_limit_reports_context_and_retry_after() -> None:
    with pytest.raises(TooManyRequestsError) as excinfo:
        for _ in range(2):
            enforce_rate_limit(
                "test:scope",
                "caller",
                1,
                window_seconds=30,
                context={"session_id": "s-1"},
            )

    error = excinfo.value
    assert error.status_code == 429
    assert error.headers["Retry-After"].isdigit()
    assert error.details["scope"] == "test:scope"
    assert error.details["session_id"] == "s-1"
    assert error.details["limit"] == 1


@pytest.mark.asyncio
async def test_start_endpoint_is_rate_limited_per_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A key that starts too many sessions in a minute gets a 429 with context."""
    monkeypatch.setattr(get_settings(), "HTTP_RATE_LIMIT_STARTS_PER_MINUTE", 2)
    # Never launch a real research loop from a rate limit test.
    monkeypatch.setattr(
        "app.api.routes.research.launch_research_task", lambda session_id: None
    )
    reset_rate_limiters()

    payload = {
        "question": "Does the limiter refuse repeated research starts today?",
        "depth": "shallow",
    }

    for _ in range(2):
        res = await client.post("/api/research/start", json=payload, headers=API_HEADERS)
        assert res.status_code == 201

    blocked = await client.post("/api/research/start", json=payload, headers=API_HEADERS)
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]

    body = blocked.json()
    assert body["error"]["code"] == "TooManyRequestsError"
    assert body["error"]["details"]["scope"] == "research:start"
    assert body["error"]["details"]["limit"] == 2
    assert body["error"]["details"]["endpoint"] == "POST /api/research/start"


@pytest.mark.asyncio
async def test_read_endpoints_use_a_separate_budget(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reads are limited independently of starts, so browsing history is cheap."""
    monkeypatch.setattr(get_settings(), "HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE", 3)
    reset_rate_limiters()

    codes = [
        (await client.get("/api/research/missing-session", headers=API_HEADERS)).status_code
        for _ in range(4)
    ]
    assert codes[:3] == [404, 404, 404]
    assert codes[3] == 429
