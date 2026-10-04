"""Request-scoped middleware: correlation IDs, timing, and access logging.

FastAPI equivalent of the Express correlation-ID + access-log middleware pair:
one identifier flows from the client, through logs, into error envelopes, so a
failed call is traceable without guesswork.
"""

import time
import uuid
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.utils.logger import logger

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Liveness/readiness probes are polled; keep them out of the access log.
_PROBE_PREFIXES = ("/health",)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request and log its outcome."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - start) * 1000:.0f}"
            return response
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            request_id_var.reset(token)
            if not request.url.path.startswith(_PROBE_PREFIXES):
                logger.info(
                    f"{request.method} {request.url.path} -> {status_code} "
                    f"in {elapsed_ms:.0f}ms [request_id={request_id}]"
                )

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)
