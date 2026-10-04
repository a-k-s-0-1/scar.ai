"""Tests for per-session LLM call, context and concurrency budgets."""

import asyncio

import pytest

from app.api.errors import SessionBudgetExceededError
from app.integrations import llm_router as router_module
from app.integrations.llm_router import LLMRouter, TaskType


@pytest.fixture
def router() -> LLMRouter:
    """A router with no leftover session budgets from other tests."""
    instance = LLMRouter()
    instance.reset()
    return instance


@pytest.mark.asyncio
async def test_session_call_budget_blocks_further_calls(
    router: LLMRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One session cannot spend more calls than its ceiling."""
    monkeypatch.setattr(router_module.settings, "LLM_MAX_CALLS_PER_SESSION", 2)

    async def fake_call(task: TaskType, prompt: str, system: str | None, temp: float) -> str:
        return "ok"

    monkeypatch.setattr(router, "_generate_with_retry", fake_call)

    assert await router.generate(TaskType.CLASSIFY, "prompt", session_id="s-1") == "ok"
    assert await router.generate(TaskType.CLASSIFY, "prompt", session_id="s-1") == "ok"

    with pytest.raises(SessionBudgetExceededError) as excinfo:
        await router.generate(TaskType.CLASSIFY, "prompt", session_id="s-1")

    assert excinfo.value.details["resource"] == "call"
    assert excinfo.value.details["session_id"] == "s-1"
    assert router.usage("s-1")["calls"] == 2

    # Another session keeps its own, untouched budget.
    assert await router.generate(TaskType.CLASSIFY, "prompt", session_id="s-2") == "ok"
    assert router.usage("s-2")["calls"] == 1


@pytest.mark.asyncio
async def test_context_budget_counts_prompts_and_completions(
    router: LLMRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Context spend is prompt + completion characters against the session allowance."""
    monkeypatch.setattr(router_module.settings, "LLM_CONTEXT_CHAR_BUDGET", 20)

    async def fake_call(task: TaskType, prompt: str, system: str | None, temp: float) -> str:
        return "0123456789"

    monkeypatch.setattr(router, "_generate_with_retry", fake_call)

    await router.generate(TaskType.CLASSIFY, "0123456789", session_id="s-3")
    assert router.usage("s-3")["context_chars"] == 20

    with pytest.raises(SessionBudgetExceededError) as excinfo:
        await router.generate(TaskType.CLASSIFY, "x", session_id="s-3")

    assert excinfo.value.details["resource"] == "context"
    assert excinfo.value.details["used"] == 20


@pytest.mark.asyncio
async def test_session_gate_serializes_one_sessions_calls(
    router: LLMRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrency is capped per session even when the global gate is wider."""
    monkeypatch.setattr(router_module.settings, "LLM_MAX_CONCURRENT_CALLS_PER_SESSION", 1)
    router._gate = asyncio.Semaphore(4)

    peak = {"current": 0, "max": 0}

    async def fake_call(task: TaskType, prompt: str, system: str | None, temp: float) -> str:
        peak["current"] += 1
        peak["max"] = max(peak["max"], peak["current"])
        await asyncio.sleep(0.02)
        peak["current"] -= 1
        return "ok"

    monkeypatch.setattr(router, "_generate_with_retry", fake_call)

    results = await asyncio.gather(
        *(router.generate(TaskType.CLASSIFY, "prompt", session_id="s-4") for _ in range(4))
    )

    assert results == ["ok"] * 4
    assert peak["max"] == 1
    assert router.usage("s-4")["calls"] == 4


@pytest.mark.asyncio
async def test_release_session_forgets_budget(
    router: LLMRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finishing a session clears its counters so the registry stays small."""
    monkeypatch.setattr(router_module.settings, "LLM_MAX_CALLS_PER_SESSION", 1)

    async def fake_call(task: TaskType, prompt: str, system: str | None, temp: float) -> str:
        return "ok"

    monkeypatch.setattr(router, "_generate_with_retry", fake_call)

    await router.generate(TaskType.CLASSIFY, "prompt", session_id="s-5")
    with pytest.raises(SessionBudgetExceededError):
        await router.generate(TaskType.CLASSIFY, "prompt", session_id="s-5")

    router.release_session("s-5")

    assert router.usage("s-5")["calls"] == 0
    assert await router.generate(TaskType.CLASSIFY, "prompt", session_id="s-5") == "ok"


@pytest.mark.asyncio
async def test_calls_without_a_session_skip_session_budget(
    router: LLMRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sessionless calls (health probes, one-off tasks) keep the old behaviour."""
    monkeypatch.setattr(router_module.settings, "LLM_MAX_CALLS_PER_SESSION", 1)

    async def fake_call(task: TaskType, prompt: str, system: str | None, temp: float) -> str:
        return "ok"

    monkeypatch.setattr(router, "_generate_with_retry", fake_call)

    assert await router.generate(TaskType.CLASSIFY, "prompt") == "ok"
    assert await router.generate(TaskType.CLASSIFY, "prompt") == "ok"
