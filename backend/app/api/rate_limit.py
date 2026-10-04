"""In-process sliding-window rate limiting for the research endpoints.

Deliberately simple: one process serves the API, so an in-memory window per key is
the cheapest correct limiter and needs no Redis. The goal is to stop runaway
clients, double-submits and search storms — not to meter normal use — so limits are
generous and configurable through settings.

Every limit is keyed by scope plus caller identity, and refusals carry the scope,
the configured limit, the remaining wait and any request context (session id,
endpoint) so a client can react without guessing.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from app.api.errors import TooManyRequestsError
from app.config import get_settings

settings = get_settings()


@dataclass(frozen=True)
class RateLimitDecision:
    """Outcome of a single limiter probe."""

    allowed: bool
    remaining: int
    retry_after: int


class SlidingWindowLimiter:
    """Counts hits per key inside a rolling time window."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, now: float | None = None) -> RateLimitDecision:
        """Record a hit for ``key`` and report whether it is allowed."""
        moment = time.monotonic() if now is None else now
        hits = self._hits[key]

        # Drop hits that fell out of the window.
        cutoff = moment - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= self.limit:
            oldest = hits[0]
            retry_after = max(1, int(self.window_seconds - (moment - oldest)) + 1)
            return RateLimitDecision(allowed=False, remaining=0, retry_after=retry_after)

        hits.append(moment)
        return RateLimitDecision(
            allowed=True, remaining=self.limit - len(hits), retry_after=0
        )

    def reset(self, key: str | None = None) -> None:
        """Forget one key's history (or all of it)."""
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


_limiters: dict[str, SlidingWindowLimiter] = {}


def get_limiter(scope: str, limit: int, window_seconds: float = 60.0) -> SlidingWindowLimiter:
    """Return the limiter for a scope, rebuilding it when its limit changes.

    Limits come from settings, which tests and operators can change at runtime;
    rebuilding on a limit change keeps the file honest without a restart.
    """
    limiter = _limiters.get(scope)
    if limiter is None or limiter.limit != limit:
        limiter = SlidingWindowLimiter(limit=limit, window_seconds=window_seconds)
        _limiters[scope] = limiter
    return limiter


def reset_rate_limiters() -> None:
    """Clear every limiter (used by tests and after config reloads)."""
    _limiters.clear()


def enforce_rate_limit(
    scope: str,
    identifier: str,
    limit: int,
    *,
    window_seconds: float = 60.0,
    context: dict[str, Any] | None = None,
) -> RateLimitDecision:
    """Raise :class:`TooManyRequestsError` when ``identifier`` is over budget."""
    if not settings.HTTP_RATE_LIMIT_ENABLED:
        return RateLimitDecision(allowed=True, remaining=limit, retry_after=0)

    decision = get_limiter(scope, limit, window_seconds).check(identifier)
    if not decision.allowed:
        raise TooManyRequestsError(
            scope=scope,
            limit=limit,
            window_seconds=window_seconds,
            retry_after=decision.retry_after,
            identifier=identifier,
            context=context,
        )
    return decision
