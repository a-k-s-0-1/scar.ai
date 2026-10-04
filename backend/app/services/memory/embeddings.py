"""Embedding provider for memory recall — semantic when possible, lexical when not.

The owner chose remote embeddings (Gemini) for retrieval. This module is what makes
that choice safe in a system that must keep working: the provider is a thin protocol,
the Gemini implementation **never raises**, and an unavailable or invalid key simply
yields no vectors, which downgrades recall to lexical scoring instead of failing a run.

That is not a theoretical concern. A key can be revoked, quota can run out, and the
provider can be unreachable — in all three cases the research run must still finish.
"""

from __future__ import annotations

from typing import Protocol

from app.config import get_settings
from app.integrations.gemini_client import GeminiClient
from app.utils.logger import logger


class EmbeddingProvider(Protocol):
    """Minimal contract: turn text into a vector, or admit you cannot."""

    name: str

    async def embed(self, text: str) -> list[float] | None:
        """Return a vector, or ``None`` when embeddings are unavailable."""


class NullEmbeddings:
    """Stand-in used when embeddings are disabled or no key is configured."""

    name = "none"

    async def embed(self, text: str) -> list[float] | None:
        return None


class GeminiEmbeddings:
    """Gemini embeddings behind a never-raising interface.

    Failures are logged **once per process** at warning level and then at debug: a
    revoked key would otherwise print the same 400 on every memory write for the whole
    run and bury everything else in the log.
    """

    name = "gemini"

    def __init__(self, client: GeminiClient | None = None) -> None:
        self._client = client or GeminiClient()
        self._warned = False

    async def embed(self, text: str) -> list[float] | None:
        if not (text or "").strip():
            return None
        try:
            vector = await self._client.embed(text)
        except Exception as exc:  # noqa: BLE001 — retrieval must never break a run
            if not self._warned:
                logger.warning(
                    f"Embeddings unavailable ({type(exc).__name__}: {exc}). "
                    "Memory recall falls back to lexical scoring for the rest of this process."
                )
                self._warned = True
            else:
                logger.debug(f"Embeddings still unavailable: {exc}")
            return None
        if not vector:
            return None
        return vector


def get_embedding_provider(settings=None) -> EmbeddingProvider:
    """Pick a provider for this process, based on configuration and available keys."""
    settings = settings or get_settings()
    if not settings.MEMORY_EMBEDDINGS_ENABLED:
        return NullEmbeddings()
    if not settings.GEMINI_API_KEY:
        logger.info(
            "MEMORY_EMBEDDINGS_ENABLED is set but GEMINI_API_KEY is empty; "
            "memory recall will use lexical scoring."
        )
        return NullEmbeddings()
    return GeminiEmbeddings()


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    """Cosine similarity in ``[0, 1]``; ``0.0`` when either vector is missing.

    Vectors of different length are not comparable (a model change between runs), and
    are treated as no similarity rather than as an error. Negative similarity is
    clamped: for retrieval, "unrelated" and "opposite" are equally unhelpful.
    """
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right, strict=False):
        dot += a * b
        left_norm += a * a
        right_norm += b * b

    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    similarity = dot / ((left_norm**0.5) * (right_norm**0.5))
    return max(0.0, min(1.0, similarity))
