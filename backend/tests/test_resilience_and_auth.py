"""Tests for LLM rate-limit resilience, WebSocket auth, and pair de-duplication."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.errors import RateLimitExceededError
from app.database.repository import (
    ClaimRepository,
    ContradictionRepository,
    SessionRepository,
)
from app.integrations import llm_router as llm_module
from app.main import app
from app.services.contradiction_detector import ContradictionDetector

API_KEY = "dev_api_key_jev_ikf_2026"


def _fast_router() -> llm_module.LLMRouter:
    """Fresh router with backoff disabled so tests do not sleep."""
    router = llm_module.LLMRouter()
    router._retry_base_delay = 0.0
    return router


@pytest.mark.asyncio
async def test_rate_limited_task_is_retried_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A throttled task backs off and retries instead of failing the iteration."""
    router = _fast_router()
    calls = {"count": 0}

    async def flaky(*args: object, **kwargs: object) -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise RateLimitExceededError("Groq")
        return "synthesized"

    monkeypatch.setattr(router, "_dispatch", flaky)

    assert await router.generate(llm_module.TaskType.REPORT, "prompt") == "synthesized"
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_non_rate_limit_errors_are_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only rate limits are retried; other failures surface immediately."""
    router = _fast_router()
    calls = {"count": 0}

    async def boom(*args: object, **kwargs: object) -> str:
        calls["count"] += 1
        raise ValueError("prompt rejected")

    monkeypatch.setattr(router, "_dispatch", boom)

    with pytest.raises(ValueError):
        await router.generate(llm_module.TaskType.EXTRACT, "prompt")
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_concurrent_calls_are_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Concurrent sessions cannot stampede a free-tier provider key."""
    router = _fast_router()
    router._gate = asyncio.Semaphore(2)
    state = {"active": 0, "peak": 0}

    async def slow(*args: object, **kwargs: object) -> str:
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.01)
        state["active"] -= 1
        return "ok"

    monkeypatch.setattr(router, "_dispatch", slow)

    await asyncio.gather(
        *[router.generate(llm_module.TaskType.SUMMARIZE, f"p{i}") for i in range(6)]
    )
    assert state["peak"] == 2


def test_websocket_rejects_incorrect_key() -> None:
    """A browser socket without the right key is refused before acceptance."""
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/research/ws/session-1?api_key=wrong"):
            pass


def test_websocket_accepts_matching_key() -> None:
    """With the configured key the live stream works as before."""
    client = TestClient(app)
    with client.websocket_connect(
        f"/api/research/ws/session-2?api_key={API_KEY}"
    ) as websocket:
        websocket.send_text("ping")
        assert websocket.receive_text() == "pong"


@pytest.mark.asyncio
async def test_already_judged_pairs_skip_the_llm(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contradiction pairs verified earlier are not re-billed to the provider."""
    s_repo = SessionRepository(db_session)
    claim_repo = ClaimRepository(db_session)
    contra_repo = ContradictionRepository(db_session)

    session = await s_repo.create(question="Do cells and storage systems agree?")
    a1 = await claim_repo.create(
        session_id=session.id,
        claim_text="Alpha cells last 3000 cycles.",
        subject="alpha cells",
    )
    a2 = await claim_repo.create(
        session_id=session.id,
        claim_text="Alpha cells fail after 500 cycles.",
        subject="alpha cells",
    )
    b1 = await claim_repo.create(
        session_id=session.id,
        claim_text="Beta grids store 4 hours of energy.",
        subject="beta grids",
    )
    b2 = await claim_repo.create(
        session_id=session.id,
        claim_text="Beta grids store under 1 hour of energy.",
        subject="beta grids",
    )
    await contra_repo.create(
        session.id, a1.id, a2.id, severity="high", resolution_note="cycle disparity"
    )
    await db_session.commit()

    evaluated_prompts: list[str] = []

    async def fake_generate(
            task: object,
            prompt: str,
            system_instruction: str | None = None,
            temperature: float = 0.2,
            session_id: str | None = None,
        ) -> str:
            evaluated_prompts.append(prompt)
            return '{"contradicts": false}'

    monkeypatch.setattr(llm_module.llm_router, "generate", fake_generate)

    detected = await ContradictionDetector(session.id).detect_contradictions(db=db_session)

    assert detected == []
    assert len(evaluated_prompts) == 1, "the judged pair must not be re-evaluated"
    assert "Beta grids" in evaluated_prompts[0]
    assert "Alpha cells" not in evaluated_prompts[0]
