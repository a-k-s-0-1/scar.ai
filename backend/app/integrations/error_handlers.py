"""Retry policies, circuit breakers, and external API error wrappers."""

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


def create_api_retry_decorator(
    max_attempts: int = 3, min_wait: float = 1.0, max_wait: float = 10.0
):
    """Standard retry decorator for network/HTTP operations."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(
            (httpx.RequestError, httpx.HTTPStatusError, TimeoutError, ConnectionError)
        ),
        reraise=True,
    )
