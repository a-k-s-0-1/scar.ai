"""Main FastAPI Application Entrypoint.

Initializes middleware, routers, exception handlers, and lifespan lifecycle.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DbSession
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.routes.evaluation import router as evaluation_router
from app.api.routes.evidence import router as evidence_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.memory import router as memory_router
from app.api.routes.reports import router as reports_router
from app.api.routes.research import router as research_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.trajectory import router as trajectory_router
from app.config import get_settings
from app.database.session import async_session_maker, init_db
from app.integrations.cache_manager import cache_manager
from app.services.event_recorder import record_session_event
from app.services.session_manager import SessionManager
from app.utils.logger import logger
from app.ws.managers import ws_manager

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup and shutdown events."""
    logger.info(
        f"Starting Self-Correcting Agent for Research - SCAR Backend [{settings.ENVIRONMENT}]"
    )

    # 1. Initialize database tables
    try:
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    # 2. Make every broadcast durable so finished sessions can be replayed
    ws_manager.set_event_recorder(record_session_event)

    # 3. Reconcile sessions interrupted by a previous process
    try:
        async with async_session_maker() as startup_db:
            await SessionManager.reconcile_interrupted_sessions(startup_db)
    except SQLAlchemyError as e:
        logger.warning(f"Session reconciliation warning: {e}")

    # 4. Initialize cache
    try:
        await cache_manager.initialize()
    except Exception as e:
        logger.warning(f"Cache initialization warning: {e}")

    yield

    logger.info("Shutting down Self-Correcting Agent for Research - SCAR Backend...")


app = FastAPI(
    title="Self-Correcting Agent for Research - SCAR API",
    version="1.0.0",
    description="Backend orchestrator powering SCAR: autonomous iterative search, claim extraction (IKF), and judgment evaluation (JEV).",
    lifespan=lifespan,
)

# Exception handlers
register_exception_handlers(app)

# Request correlation IDs, timing, and access logging
app.add_middleware(RequestContextMiddleware)

# CORS Configuration (registered last so it wraps every response, including errors)
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["*"]
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(research_router)
app.include_router(sessions_router)
app.include_router(knowledge_router)
app.include_router(evidence_router)
app.include_router(reports_router)
app.include_router(memory_router)
# V2 offline learning: trajectories, decision inspector and evaluation lab.
app.include_router(trajectory_router)
app.include_router(evaluation_router)


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """Liveness probe verifying API availability."""
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check(db: DbSession) -> JSONResponse:
    """Readiness probe: verifies the database answers before traffic is routed."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Readiness probe failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unreachable"},
        )
    return JSONResponse(
        status_code=200,
        content={
            "status": "ready",
            "database": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
