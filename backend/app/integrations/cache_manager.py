"""Cache manager supporting Redis with automatic in-memory fallback."""

import json
import time
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()


class CacheManager:
    """Provides async caching with Redis if reachable, falling back to local memory."""

    def __init__(self) -> None:
        self.redis_client: aioredis.Redis | None = None
        self._memory_cache: dict[str, tuple[str, float]] = {}
        self._redis_available: bool = False

    async def initialize(self) -> None:
        """Attempt to connect to Redis."""
        try:
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await client.ping()
            self.redis_client = client
            self._redis_available = True
            logger.info("Connected to Redis cache successfully.")
        except Exception as e:
            self._redis_available = False
            logger.info(f"Redis not available ({e}). Using in-memory cache.")

    async def get(self, key: str) -> Any | None:
        """Retrieve cached value by key."""
        if self._redis_available and self.redis_client:
            try:
                val = await self.redis_client.get(key)
                if val:
                    return json.loads(val)
                return None
            except Exception as e:
                logger.warning(f"Redis get error, falling back to memory: {e}")

        # Check in-memory cache
        item = self._memory_cache.get(key)
        if item:
            val_str, expiry = item
            if expiry == 0 or expiry > time.time():
                return json.loads(val_str)
            else:
                del self._memory_cache[key]
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Store value in cache with TTL."""
        val_str = json.dumps(value)

        if self._redis_available and self.redis_client:
            try:
                await self.redis_client.set(key, val_str, ex=ttl_seconds)
                return
            except Exception as e:
                logger.warning(f"Redis set error, falling back to memory: {e}")

        # In-memory storage
        expiry = time.time() + ttl_seconds if ttl_seconds > 0 else 0
        self._memory_cache[key] = (val_str, expiry)


cache_manager = CacheManager()
