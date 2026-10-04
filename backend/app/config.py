"""Configuration management using pydantic-settings."""

import json
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Shipped default key. Development tolerates it (and a missing header) so a fresh
# clone runs without setup; any other environment requires an exact match.
DEV_DEFAULT_API_KEY = "dev_api_key_jev_ikf_2026"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Security
    API_KEY: str = Field(
        default=DEV_DEFAULT_API_KEY,
        description="API Key for X-API-Key header verification",
    )
    ENVIRONMENT: str = Field(
        default="development",
        description="Runtime environment: development, staging, production",
    )
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Research Limits
    MAX_RESEARCH_TIME_MINUTES: int = Field(
        default=10, description="Max session run time before timeout"
    )
    MAX_QUERIES_PER_SESSION: int = Field(
        default=50, description="Max search queries per session"
    )

    # Search API
    TAVILY_API_KEY: str = Field(default="", description="Tavily Search API key")

    # LLM Router Resilience
    LLM_MAX_CONCURRENT_CALLS: int = Field(
        default=2,
        ge=1,
        le=16,
        description="Shared ceiling on simultaneous LLM calls across sessions",
    )
    LLM_RETRY_ATTEMPTS: int = Field(
        default=3,
        ge=1,
        le=6,
        description="Attempts per LLM task when providers report rate limits",
    )

    # Per-session LLM budget. A runaway loop is expensive on free tiers, so each
    # session gets its own call ceiling, concurrency slot and context allowance
    # on top of the global gate.
    LLM_MAX_CALLS_PER_SESSION: int = Field(
        default=150,
        ge=1,
        le=5000,
        description="Hard ceiling on LLM calls one session may spend",
    )
    LLM_MAX_CONCURRENT_CALLS_PER_SESSION: int = Field(
        default=1,
        ge=1,
        le=8,
        description="Simultaneous LLM calls allowed for a single session",
    )
    LLM_CONTEXT_CHAR_BUDGET: int = Field(
        default=600_000,
        ge=10_000,
        description="Approximate prompt+completion characters one session may send",
    )

    # HTTP request budgets per API key (in-process sliding window).
    HTTP_RATE_LIMIT_ENABLED: bool = Field(
        default=True, description="Enable request rate limiting on research endpoints"
    )
    HTTP_RATE_LIMIT_STARTS_PER_MINUTE: int = Field(
        default=6,
        ge=1,
        description="New research sessions a single key may start per minute",
    )
    HTTP_RATE_LIMIT_REQUESTS_PER_MINUTE: int = Field(
        default=120,
        ge=1,
        description="Read/stop requests a single key may make per minute",
    )

    # LLM Router Settings
    GEMINI_API_KEY: str = Field(
        default="", description="Google AI Studio Gemini API key (Tier 2/3)"
    )
    GROQ_API_KEY: str = Field(
        default="", description="Groq API key (Tier 3 reasoning & reports)"
    )
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434", description="Local Ollama base URL (Tier 1)"
    )
    OLLAMA_MODEL: str = Field(
        default="phi3:mini", description="Local Ollama model name"
    )

    # Long-term memory (V2 2.1). Cross-session knowledge is what lets a later run
    # start from what earlier runs learned instead of from nothing.
    MEMORY_ENABLED: bool = Field(
        default=True, description="Persist and recall knowledge across sessions"
    )
    MEMORY_MAX_ITEMS: int = Field(
        default=2000,
        ge=10,
        le=100_000,
        description="Cap on stored memory items; the lowest-weight ones are forgotten first",
    )
    MEMORY_RECALL_LIMIT: int = Field(
        default=8, ge=1, le=50, description="Items recalled per query"
    )
    MEMORY_HALF_LIFE_DAYS: int = Field(
        default=180,
        ge=1,
        description="Half-life of a memory item's weight while it is never reused",
    )
    MEMORY_MIN_WEIGHT: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Weight below which an unused item is forgotten",
    )
    MEMORY_EMBEDDINGS_ENABLED: bool = Field(
        default=True,
        description="Use remote embeddings for semantic recall; lexical scoring is the fallback",
    )
    GEMINI_EMBEDDING_MODEL: str = Field(
        default="gemini-embedding-001",
        description="Gemini embedding model used for memory recall",
    )

    # Offline learning (V2 2.3 – 2.9). JEV remains the production decision maker
    # throughout V2; these flags only govern data collection and whether the learned
    # policy is *asked* what it would have done (never executed).
    RL_TRAJECTORY_ENABLED: bool = Field(
        default=True,
        description="Persist one state/action/reward/next-state transition per iteration",
    )
    RL_SHADOW_ENABLED: bool = Field(
        default=True,
        description="Record what the offline policy would have done, without executing it",
    )
    RL_POLICY_MIN_SAMPLES: int = Field(
        default=10,
        ge=1,
        description="Transitions below which the offline policy defers to JEV",
    )
    RL_POLICY_SHRINKAGE: float = Field(
        default=2.0,
        ge=0.0,
        le=100.0,
        description="Bayesian pseudo-count pulling context estimates toward the global mean",
    )
    RL_DATASET_MAX_TRANSITIONS: int = Field(
        default=5000,
        ge=10,
        le=200_000,
        description="Ceiling on transitions loaded into one offline dataset",
    )

    # Database & Cache
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./research_agent.db",
        description="Async database connection string",
    )
    REDIS_URL: str = Field(
        default="redis://localhost:6379", description="Redis connection string"
    )

    # CORS
    CORS_ORIGINS: list[str] | str = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except Exception:
                return [s.strip() for s in v.split(",") if s.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
