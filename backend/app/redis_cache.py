"""
Redis Caching Helper with In-Memory Fallback.
Provides caching functionality for high-performance enterprise operations.
If Redis is unconfigured or unavailable, automatically falls back to standard in-memory storage.
"""
import time
import json
import logging
from typing import Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self):
        self._redis_client = None
        self._memory_cache = {}  # key -> (value, expire_timestamp)
        self._is_redis = False

        if settings.redis_url:
            try:
                import redis
                self._redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
                self._redis_client.ping()
                self._is_redis = True
                logger.info("Connected to Redis cache at %s", settings.redis_url)
            except Exception as err:
                logger.warning("Failed to connect to Redis (%s). Using in-memory cache fallback.", err)
                self._redis_client = None
                self._is_redis = False

    def get(self, key: str) -> Optional[Any]:
        if self._is_redis and self._redis_client:
            try:
                val = self._redis_client.get(key)
                if val:
                    return json.loads(val)
                return None
            except Exception as err:
                logger.error("Redis get error for key %s: %s", key, err)
                return None
        else:
            # Memory cache fallback check
            item = self._memory_cache.get(key)
            if not item:
                return None
            val, exp = item
            if exp and time.time() > exp:
                del self._memory_cache[key]
                return None
            return val

    def set(self, key: str, value: Any, expire_seconds: int = 300) -> bool:
        serialized = json.dumps(value)
        if self._is_redis and self._redis_client:
            try:
                self._redis_client.set(key, serialized, ex=expire_seconds)
                return True
            except Exception as err:
                logger.error("Redis set error for key %s: %s", key, err)
                return False
        else:
            exp = time.time() + expire_seconds if expire_seconds else None
            self._memory_cache[key] = (value, exp)
            return True

    def delete(self, key: str) -> bool:
        if self._is_redis and self._redis_client:
            try:
                self._redis_client.delete(key)
                return True
            except Exception:
                return False
        else:
            self._memory_cache.pop(key, None)
            return True

    def status(self) -> dict:
        return {
            "type": "redis" if self._is_redis else "in_memory",
            "active": True,
            "redis_url": settings.redis_url if self._is_redis else None
        }

cache_service = CacheService()
