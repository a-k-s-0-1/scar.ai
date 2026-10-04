"""Hybrid Multi-Provider Model Router.

Routes tasks dynamically across Tier 1 (Local), Tier 2 (Gemini Flash),
and Tier 3 (Groq 70B / Gemini Pro) with automatic fallback.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum

from app.api.errors import RateLimitExceededError, SessionBudgetExceededError
from app.config import get_settings
from app.integrations.gemini_client import GeminiClient
from app.integrations.groq_client import GroqClient
from app.integrations.ollama_client import OllamaClient
from app.utils.logger import logger

settings = get_settings()

# Base delay for exponential backoff between retries of a rate-limited call.
RETRY_BASE_DELAY_SECONDS = 2.0


class TaskType(str, Enum):
    """Categorization of LLM tasks for cost and complexity routing."""

    CLASSIFY = "classify"  # Query routing, action classification, heuristics
    EXTRACT = "extract"  # Structured claim and entity extraction
    SUMMARIZE = "summarize"  # Evidence and source summarization
    CONTRADICTION = "contradiction"  # Contradiction and gap detection
    REASON = "reason"  # Self-correction and decision evaluation
    REPORT = "report"  # Final executive summary and report compilation


@dataclass
class SessionUsage:
    """Model calls and context characters spent by one research session."""

    calls: int = 0
    context_chars: int = 0


@dataclass
class _SessionState:
    """Per-session concurrency slot plus its budget counters."""

    gate: asyncio.Semaphore
    usage: SessionUsage = field(default_factory=SessionUsage)


class LLMRouter:
    """Intelligent router dispatching prompts to the optimal free-tier LLM provider."""

    def __init__(self) -> None:
        self.ollama = OllamaClient()
        self.gemini = GeminiClient()
        self.groq = GroqClient()
        # Free-tier providers rate limit per key, so concurrent sessions must not
        # stampede them; every call passes through this shared gate.
        self._gate = asyncio.Semaphore(settings.LLM_MAX_CONCURRENT_CALLS)
        self._retry_attempts = settings.LLM_RETRY_ATTEMPTS
        self._retry_base_delay = RETRY_BASE_DELAY_SECONDS
        # Per-session budgets on top of the shared gate: a single runaway loop
        # cannot drain the provider quota other sessions are waiting on.
        self._sessions: dict[str, _SessionState] = {}

    def _session_state(self, session_id: str) -> _SessionState:
        state = self._sessions.get(session_id)
        if state is None:
            state = _SessionState(
                gate=asyncio.Semaphore(settings.LLM_MAX_CONCURRENT_CALLS_PER_SESSION)
            )
            self._sessions[session_id] = state
        return state

    def _reserve(
        self, session_id: str, prompt: str, system_instruction: str | None
    ) -> _SessionState:
        """Refuse a call that would exceed the session's call or context budget."""
        state = self._session_state(session_id)
        if state.usage.calls >= settings.LLM_MAX_CALLS_PER_SESSION:
            raise SessionBudgetExceededError(
                session_id,
                "call",
                settings.LLM_MAX_CALLS_PER_SESSION,
                state.usage.calls,
            )

        requested = len(prompt) + len(system_instruction or "")
        if state.usage.context_chars + requested > settings.LLM_CONTEXT_CHAR_BUDGET:
            raise SessionBudgetExceededError(
                session_id,
                "context",
                settings.LLM_CONTEXT_CHAR_BUDGET,
                state.usage.context_chars,
            )
        return state

    def usage(self, session_id: str) -> dict[str, int]:
        """Return a session's spend against its budget (for telemetry and logs)."""
        usage = self._sessions[session_id].usage if session_id in self._sessions else SessionUsage()
        return {
            "calls": usage.calls,
            "context_chars": usage.context_chars,
            "max_calls": settings.LLM_MAX_CALLS_PER_SESSION,
            "max_context_chars": settings.LLM_CONTEXT_CHAR_BUDGET,
        }

    def release_session(self, session_id: str) -> None:
        """Forget a finished session's budget so the registry does not grow forever."""
        self._sessions.pop(session_id, None)

    def reset(self) -> None:
        """Drop every session budget (tests, config changes)."""
        self._sessions.clear()

    async def generate(
        self,
        task: TaskType,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        session_id: str | None = None,
    ) -> str:
        """Serialize provider access, then retry rate-limited tasks with backoff.

        With a ``session_id`` the call additionally passes that session's own gate
        and budget, so an over-budget session fails fast with a clear error instead
        of queueing behind every other session.
        """
        if session_id is None:
            async with self._gate:
                return await self._generate_with_retry(
                    task, prompt, system_instruction, temperature
                )

        state = self._session_state(session_id)
        async with state.gate:
            # Budget checks stay inside the session gate so concurrent tasks of one
            # session cannot both pass the last available slot.
            self._reserve(session_id, prompt, system_instruction)
            async with self._gate:
                result = await self._generate_with_retry(
                    task, prompt, system_instruction, temperature
                )
            state.usage.calls += 1
            state.usage.context_chars += (
                len(prompt) + len(system_instruction or "") + len(result)
            )
            return result

    async def _generate_with_retry(
        self,
        task: TaskType,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
    ) -> str:
        """Retry only on provider rate limits; other failures surface immediately.

        Every tier already falls back to the next provider internally, so a rate
        limit reaching this point means all tiers were throttled: back off and try
        the cascade again rather than failing the whole research iteration.
        """
        last_error: RateLimitExceededError | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await self._dispatch(task, prompt, system_instruction, temperature)
            except RateLimitExceededError as e:
                last_error = e
                if attempt >= self._retry_attempts:
                    break
                delay = self._retry_base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"Providers rate limited on '{task.value}' "
                    f"(attempt {attempt}/{self._retry_attempts}); retrying in {delay:.0f}s. {e.message}"
                )
                await asyncio.sleep(delay)

        assert last_error is not None
        raise last_error

    async def _dispatch(
        self,
        task: TaskType,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Route prompt based on task type with cascading provider fallback."""

        # TIER 1: Lightweight tasks (classify, query routing)
        if task == TaskType.CLASSIFY:
            # Try Ollama first if available
            if await self.ollama.is_available():
                try:
                    logger.info(
                        f"Routing '{task.value}' to Tier 1: Local Ollama ({settings.OLLAMA_MODEL})"
                    )
                    return await self.ollama.generate(prompt, system=system_instruction)
                except Exception as e:
                    logger.warning(
                        f"Tier 1 (Ollama) failed: {e}. Falling back to Tier 2 (Gemini Flash)."
                    )

            # Fallback to Tier 2 (Gemini Flash)
            return await self._call_tier_2(prompt, system_instruction, temperature)

        # TIER 2: Medium complexity (claim extraction, summarization)
        elif task in (TaskType.EXTRACT, TaskType.SUMMARIZE):
            try:
                logger.info(f"Routing '{task.value}' to Tier 2: Gemini Flash")
                return await self._call_tier_2(prompt, system_instruction, temperature)
            except Exception as e:
                logger.warning(
                    f"Tier 2 (Gemini Flash) failed: {e}. Falling back to Tier 3 (Groq)."
                )
                return await self._call_tier_3(prompt, system_instruction, temperature)

        # TIER 3: Complex reasoning (contradictions, report, deep self-correction)
        else:
            try:
                # Try Groq first for fast 70B inference
                if settings.GROQ_API_KEY:
                    logger.info(
                        f"Routing '{task.value}' to Tier 3: Groq (llama-3.1-70b)"
                    )
                    return await self._call_tier_3(
                        prompt, system_instruction, temperature
                    )
                else:
                    # Use Gemini if Groq key not provided
                    logger.info(f"Routing '{task.value}' to Tier 3: Gemini Flash/Pro")
                    return await self._call_tier_2(
                        prompt, system_instruction, temperature
                    )
            except Exception as e:
                logger.warning(
                    f"Primary Tier 3 failed: {e}. Falling back to Gemini Flash."
                )
                return await self._call_tier_2(prompt, system_instruction, temperature)

    async def _call_tier_2(
        self, prompt: str, system_instruction: str | None, temperature: float
    ) -> str:
        """Call Gemini Flash."""
        if not settings.GEMINI_API_KEY:
            # If no API key configured, check if Groq is available as backup
            if settings.GROQ_API_KEY:
                return await self.groq.generate(
                    prompt, temperature=temperature, system_prompt=system_instruction
                )
            raise ValueError(
                "Neither GEMINI_API_KEY nor GROQ_API_KEY is configured in .env"
            )

        return await self.gemini.generate(
            prompt,
            model="gemini-3.8-flash",
            temperature=temperature,
            system_instruction=system_instruction,
        )

    async def _call_tier_3(
        self, prompt: str, system_instruction: str | None, temperature: float
    ) -> str:
        """Call Groq 120B / Fast Inference."""
        return await self.groq.generate(
            prompt,
            model="openai/gpt-oss-120b",
            temperature=temperature,
            system_prompt=system_instruction,
        )


llm_router = LLMRouter()
