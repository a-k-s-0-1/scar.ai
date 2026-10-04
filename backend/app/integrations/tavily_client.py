"""Tavily Search API integration client with retry handling and structure mapping."""

from typing import Any

import httpx

from app.api.errors import ExternalAPIError, RateLimitExceededError
from app.config import get_settings
from app.integrations.error_handlers import create_api_retry_decorator
from app.utils.logger import logger

settings = get_settings()


class TavilyClient:
    """Client for Tavily Search API (https://tavily.com)."""

    BASE_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.TAVILY_API_KEY
        self.timeout = httpx.Timeout(20.0, connect=10.0)

    @create_api_retry_decorator(max_attempts=3, min_wait=2.0, max_wait=8.0)
    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "advanced",
        include_raw_content: bool = True,
    ) -> list[dict[str, Any]]:
        """Execute web search via Tavily API.

        Returns:
            List of dicts: [{"url": ..., "title": ..., "content": ..., "score": ..., "published_date": ...}]
        """
        if not self.api_key:
            logger.warning("TAVILY_API_KEY is not configured.")
            raise ExternalAPIError(
                "Tavily", "TAVILY_API_KEY is not configured in environment variables."
            )

        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_raw_content": False,  # Clean content is cleaner for claim extraction
            "include_answer": False,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(self.BASE_URL, json=payload)
                if response.status_code == 429:
                    logger.warning("Tavily API rate limit exceeded.")
                    raise RateLimitExceededError("Tavily Search", retry_after=60)

                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Tavily HTTP error {e.response.status_code}: {e.response.text}"
                )
                raise ExternalAPIError(
                    "Tavily", f"HTTP {e.response.status_code}"
                ) from e
            except httpx.RequestError as e:
                logger.error(f"Tavily network error: {e}")
                raise ExternalAPIError("Tavily", str(e)) from e

        results = data.get("results", [])
        formatted: list[dict[str, Any]] = []

        for item in results:
            url = item.get("url")
            if not url:
                continue
            formatted.append(
                {
                    "url": url,
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "score": float(item.get("score", 0.7)),
                    "published_date": item.get("published_date"),
                }
            )

        logger.info(
            f"Tavily search returned {len(formatted)} results for query: '{query}'"
        )
        return formatted
