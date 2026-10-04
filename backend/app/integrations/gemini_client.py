"""Google Gemini API client using standard HTTP REST interface."""

from typing import Any

import httpx

from app.api.errors import ExternalAPIError, RateLimitExceededError
from app.config import get_settings
from app.integrations.error_handlers import create_api_retry_decorator
from app.utils.logger import logger

settings = get_settings()


class GeminiClient:
    """Client for Google Gemini REST API (gemini-1.5-flash / gemini-2.0-flash)."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.timeout = httpx.Timeout(45.0, connect=10.0)

    @create_api_retry_decorator(max_attempts=2, min_wait=2.0, max_wait=8.0)
    async def embed(
        self, text: str, model: str | None = None
    ) -> list[float]:
        """Return an embedding vector for ``text`` via ``:embedContent``.

        Used by long-term memory. Callers must treat a failure as "no vector" rather
        than an error: retrieval has a lexical path, and a memory write must never be
        the reason a research run dies.
        """
        if not self.api_key:
            raise ExternalAPIError("Gemini", "GEMINI_API_KEY is not configured.")

        target = model or settings.GEMINI_EMBEDDING_MODEL
        url = f"{self.BASE_URL}/{target}:embedContent?key={self.api_key}"
        payload: dict[str, Any] = {
            "model": f"models/{target}",
            "content": {"parts": [{"text": text}]},
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload)
                if response.status_code == 429:
                    raise RateLimitExceededError("Gemini Embeddings", retry_after=60)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                raise ExternalAPIError(
                    "Gemini",
                    f"embed HTTP {e.response.status_code}: {e.response.text}",
                ) from e
            except httpx.RequestError as e:
                raise ExternalAPIError("Gemini", str(e)) from e

        values = data.get("embedding", {}).get("values")
        if not values:
            return []
        return [float(value) for value in values]

    @create_api_retry_decorator(max_attempts=3, min_wait=2.0, max_wait=10.0)
    async def generate(
        self,
        prompt: str,
        model: str = "gemini-3.8-flash",
        temperature: float = 0.2,
        system_instruction: str | None = None,
    ) -> str:
        """Generate content using Gemini model via REST."""
        if not self.api_key:
            raise ExternalAPIError("Gemini", "GEMINI_API_KEY is not configured.")

        url = f"{self.BASE_URL}/{model}:generateContent?key={self.api_key}"

        contents = [{"parts": [{"text": prompt}]}]
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload)
                if response.status_code == 429:
                    logger.warning("Gemini API rate limit exceeded.")
                    raise RateLimitExceededError("Gemini API", retry_after=60)

                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Gemini HTTP {e.response.status_code}: {e.response.text}")
                raise ExternalAPIError(
                    "Gemini", f"HTTP {e.response.status_code}: {e.response.text}"
                ) from e
            except httpx.RequestError as e:
                logger.error(f"Gemini connection error: {e}")
                raise ExternalAPIError("Gemini", str(e)) from e

        # Extract text from response candidates
        candidates = data.get("candidates", [])
        if not candidates:
            return ""

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return ""

        return parts[0].get("text", "")
