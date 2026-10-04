"""FastAPI dependency injection utilities."""

from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DEV_DEFAULT_API_KEY, Settings, get_settings
from app.database.session import get_db

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: Annotated[str | None, Security(api_key_header)] = None,
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate X-API-Key header against configured application key.

    Development tolerates the shipped default key (and a missing header) so a fresh
    clone runs with no setup. Any other environment enforces the key exactly, so
    an unconfigured deployment cannot silently serve unauthenticated requests.
    """
    if settings.ENVIRONMENT == "development" and (
        not settings.API_KEY or settings.API_KEY == DEV_DEFAULT_API_KEY
    ):
        return api_key or "dev_key"

    if not api_key or api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key


# Type aliases for clean endpoint dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
ApiKeyAuth = Annotated[str, Depends(verify_api_key)]
AppSettings = Annotated[Settings, Depends(get_settings)]
