"""Custom exceptions and HTTP exception handlers."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.middleware import request_id_var


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        # Response headers that must travel with the error (e.g. Retry-After).
        self.headers = headers or {}


class SessionNotFoundError(AppException):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            message=f"Research session '{session_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"session_id": session_id},
        )


class InvalidQuestionError(AppException):
    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Invalid research question: {reason}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"reason": reason},
        )


class RateLimitExceededError(AppException):
    def __init__(self, service: str, retry_after: int = 60) -> None:
        super().__init__(
            message=f"Rate limit exceeded for {service}. Please try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"service": service, "retry_after": retry_after},
        )


class TooManyRequestsError(AppException):
    """Raised when a caller exceeds a configured request budget for a scope."""

    def __init__(
        self,
        scope: str,
        limit: int,
        window_seconds: float,
        retry_after: int,
        identifier: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=(
                f"Rate limit exceeded for {scope}: at most {limit} request(s) per "
                f"{int(window_seconds)}s. Retry in {retry_after}s."
            ),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={
                "scope": scope,
                "limit": limit,
                "window_seconds": window_seconds,
                "retry_after": retry_after,
                "identifier": identifier,
                **(context or {}),
            },
            headers={"Retry-After": str(retry_after)},
        )


class SessionBudgetExceededError(AppException):
    """Raised when a session spends its allotted LLM calls or context budget."""

    def __init__(
        self, session_id: str, resource: str, limit: int, used: int
    ) -> None:
        super().__init__(
            message=(
                f"Session {session_id} exhausted its LLM {resource} budget "
                f"({used} of {limit})."
            ),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={
                "session_id": session_id,
                "resource": resource,
                "limit": limit,
                "used": used,
            },
        )


class SynthesisNotRetryableError(AppException):
    """Raised when a report cannot be re-synthesised right now."""

    def __init__(self, session_id: str, reason: str) -> None:
        super().__init__(
            message=(
                f"Cannot re-synthesize the report for session '{session_id}': "
                f"{reason}."
            ),
            status_code=status.HTTP_409_CONFLICT,
            details={"session_id": session_id, "reason": reason},
        )


class DatasetNotReadyError(AppException):
    """Raised when an offline dataset cannot be built or trained on yet."""

    def __init__(self, reason: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=f"Research trajectory dataset is not ready: {reason}",
            status_code=status.HTTP_409_CONFLICT,
            details={"reason": reason, **(details or {})},
        )


class EvaluationOptionsError(AppException):
    """Raised when an evaluation or policy request names something that does not exist."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details or {},
        )


class ExternalAPIError(AppException):
    def __init__(self, service: str, error: str) -> None:
        super().__init__(
            message=f"External service '{service}' error: {error}",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={"service": service, "error": error},
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Register uniform JSON error handlers for all exceptions."""

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.__class__.__name__,
                    "message": exc.message,
                    "details": exc.details,
                    "path": str(request.url.path),
                    "request_id": request_id_var.get(),
                }
            },
            headers=exc.headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return the standard error envelope for request validation failures.

        Without this, FastAPI emits its own `{"detail": [...]}` shape, so clients
        (and the frontend's message extraction) had to handle two error formats.
        """
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "ValidationError",
                    "message": "Request payload failed validation.",
                    "details": {"issues": jsonable_encoder(exc.errors())},
                    "path": str(request.url.path),
                    "request_id": request_id_var.get(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "InternalServerError",
                    "message": "An unexpected error occurred. Please check logs.",
                    "details": {"error_type": type(exc).__name__, "detail": str(exc)},
                    "path": str(request.url.path),
                    "request_id": request_id_var.get(),
                }
            },
        )
