"""Pytest fixtures with in-memory SQLite database and test API client."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.rate_limit import reset_rate_limiters
from app.database.models import Base
from app.database.session import get_db
from app.main import app
from app.services import event_recorder
from app.services.memory import NullEmbeddings

# Test database engine using SQLite in-memory
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

test_async_session_maker = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(autouse=True)
def clean_rate_limit_windows() -> None:
    """Rate limits are process state; every test starts with an empty window."""
    reset_rate_limiters()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def recorder_bound_to_test_db(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bind the durable event recorder to the in-memory test database.

    Autouse on purpose: a test that broadcasts without this writes its events into the
    real development database. Depends on ``db_session`` so the schema exists before
    the recorder writes.
    """
    monkeypatch.setattr(event_recorder, "_session_factory", test_async_session_maker)
    yield


@pytest_asyncio.fixture(scope="function", autouse=True)
async def memory_bound_to_test_db(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bind long-term memory to the in-memory test database.

    Autouse because the research loop now *recalls* before its first search: a test
    that lets memory reach the development database does not just pollute it, it is
    polluted *by* it: recalled dead ends from an earlier run change which query the
    loop picks, so the suite stops being reproducible run-to-run. Depends on
    ``db_session`` so the schema exists first.
    """
    from app.services.memory import service as memory_service

    monkeypatch.setattr(memory_service, "_session_factory", test_async_session_maker)
    # Force the lexical provider. A real key in the environment would otherwise make
    # every memory write in a test hit the embedding API — slow, flaky and paid for.
    monkeypatch.setattr(
        memory_service, "get_embedding_provider", lambda *a, **k: NullEmbeddings()
    )
    yield


@pytest_asyncio.fixture(scope="function", autouse=True)
async def learning_bound_to_test_db(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bind the trajectory recorder to the in-memory test database.

    The live loop writes a transition every iteration; without this the suite would
    create rows for fictional sessions in the real database (and fail once the dev
    file has not been upgraded yet). Depends on ``db_session`` so the schema exists.
    """
    from app.services.rl import recorder as rl_recorder

    monkeypatch.setattr(rl_recorder, "_session_factory", test_async_session_maker)
    yield


# ─── shared builders for the V2 learning tests ───────────────────────────────
# Module-level (not fixtures) so a test can build a state or a transition inline
# without importing three modules to do it.


def make_state(**overrides: object):
    """A valid ``ResearchState`` with sensible research-run defaults."""
    from app.services.rl import build_research_state

    payload: dict = {
        "session_id": "session-1",
        "question": "Is solar green hydrogen viable at utility scale?",
        "iteration": 1,
        "depth": "standard",
        "max_iterations": 5,
        "total_sources": 4,
        "total_claims": 6,
        "total_nodes": 3,
        "total_edges": 2,
        "information_gain": 0.4,
        "coverage": 0.5,
        "unresolved_contradictions": 0,
        "resolved_contradictions": 0,
        "gaps": ["economic"],
        "facet_coverage": 0.45,
        "source_quality": 0.72,
        "source_diversity": 3,
        "confidence_distribution": {"high": 3, "medium": 3, "low": 0},
        "duplicate_count": 0,
        "time_elapsed": 45.0,
        "remaining_time": 255.0,
        "remaining_search_budget": 25,
        "remaining_llm_budget": 140,
        "previous_action": "SEARCH",
        "previous_reward": 1.2,
    }
    payload.update(overrides)
    return build_research_state(**payload)


_UNSET = object()


def make_transition(iteration: int = 1, **overrides: object):
    """A valid ``TransitionRecord`` shaped like one the recorder would persist.

    ``state_before``/``state_after`` may be passed explicitly — including ``None``, which
    is how the validation tests build a deliberately broken transition. Omitted, they
    are generated for the record's own session so the chain is consistent.
    """
    from app.services.rl import TransitionRecord

    session_id = str(overrides.get("session_id", "session-1"))
    before_override = overrides.pop("state_before", _UNSET)
    after_override = overrides.pop("state_after", _UNSET)
    action = str(overrides.get("action", "SEARCH"))

    before = (
        make_state(
            session_id=session_id, iteration=iteration - 1, previous_action=None
        ).to_dict()
        if before_override is _UNSET
        else before_override
    )
    after = (
        make_state(
            session_id=session_id, iteration=iteration, previous_action=action
        ).to_dict()
        if after_override is _UNSET
        else after_override
    )
    payload: dict = {
        "id": f"transition-{iteration}",
        "session_id": session_id,
        "iteration": iteration,
        "state_before": before,
        "action": action,
        "action_parameters": {"query": "query text"},
        "observation": {"sources_added": 2, "claims_added": 3},
        "reward": 1.5,
        "reward_components": {"information_gain_reward": 0.8},
        "information_gain": 0.4,
        "coverage_before": float((before or {}).get("coverage", 0.0)) if isinstance(before, dict) else 0.0,
        "coverage_after": float((after or {}).get("coverage", 0.0)),
        "contradictions_before": 0,
        "contradictions_after": 0,
        "sources_added": 2,
        "claims_added": 3,
        "execution_time": 12.0,
        "state_after": after,
        "policy_source": "JEV",
        "done": False,
    }
    payload.update(overrides)
    return TransitionRecord(**payload)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean, isolated database session per test function."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_async_session_maker() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTP test client with database dependency override."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
