"""Groq API client (llama-3.1-70b-versatile / llama-3.3-70b-versatile) via OpenAI-compatible REST API."""

import httpx

from app.api.errors import ExternalAPIError, RateLimitExceededError
from app.config import get_settings
from app.integrations.error_handlers import create_api_retry_decorator
from app.utils.logger import logger

settings = get_settings()


class GroqClient:
    """Client for Groq cloud API (ultra-fast inference for 70B models)."""

    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.GROQ_API_KEY
        self.timeout = httpx.Timeout(45.0, connect=10.0)

    @create_api_retry_decorator(max_attempts=3, min_wait=2.0, max_wait=10.0)
    async def generate(
        self,
        prompt: str,
        model: str = "openai/gpt-oss-120b",
        temperature: float = 0.2,
        system_prompt: str | None = None,
    ) -> str:
        """Call Groq chat completion endpoint."""
        if not self.api_key:
            raise ExternalAPIError("Groq", "GROQ_API_KEY is not configured.")

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    self.BASE_URL, json=payload, headers=headers
                )
                if response.status_code == 429:
                    logger.warning("Groq API rate limit exceeded.")
                    raise RateLimitExceededError("Groq API", retry_after=60)

                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Groq HTTP error {e.response.status_code}: {e.response.text}"
                )
                raise ExternalAPIError(
                    "Groq", f"HTTP {e.response.status_code}: {e.response.text}"
                ) from e
            except httpx.RequestError as e:
                logger.error(f"Groq network error: {e}")
                raise ExternalAPIError("Groq", str(e)) from e

        choices = data.get("choices", [])
        if not choices:
            return ""

        return choices[0].get("message", {}).get("content", "")
