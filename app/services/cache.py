import time
import json
import os
import redis
from typing import Any, Optional

# Connect to the Redis container using environment variables or fallback to local IP
# (Fixes 15-second DNS freeze when running natively on Mac without docker)
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

# Standard Redis connection pool
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True,
    socket_timeout=2
)

class RedisCache:
    """Thread-safe, multi-worker Redis cache with seamless JSON serialization."""
    
    _redis_available = True
    
    def __init__(self, prefix: str, ttl_seconds: int = 300):
        self._prefix = prefix
        self._ttl = ttl_seconds

    def _format_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def get(self, key: str) -> Optional[Any]:
        if not RedisCache._redis_available:
            return None
            
        try:
            val = redis_client.get(self._format_key(key))
            if val is not None:
                return json.loads(val)
        except Exception as e:
            # Circuit breaker: if Redis is down, disable it globally for this worker
            # to prevent 2-5 second timeouts on every cache operation
            RedisCache._redis_available = False
        return None

    def set(self, key: str, value: Any) -> None:
        if not RedisCache._redis_available:
            return
            
        try:
            encoded_val = json.dumps(value)
            redis_client.setex(self._format_key(key), self._ttl, encoded_val)
        except Exception:
            RedisCache._redis_available = False

    def delete(self, key: str) -> None:
        if not RedisCache._redis_available:
            return
        try:
            redis_client.delete(self._format_key(key))
        except Exception:
            RedisCache._redis_available = False

    def clear(self) -> None:
        if not RedisCache._redis_available:
            return
        try:
            # Clear all keys matching specific instance prefix
            keys = redis_client.keys(f"{self._prefix}:*")
            if keys:
                redis_client.delete(*keys)
        except Exception:
            RedisCache._redis_available = False
    
    def cleanup_expired(self) -> int:
        """Redis natively auto-expires TTLs, so this method is mostly obsolete but preserved for signature compatibility."""
        return 0


permissions_cache = RedisCache(prefix="perms", ttl_seconds=300)
social_links_cache = RedisCache(prefix="social", ttl_seconds=300)
settings_cache = RedisCache(prefix="settings", ttl_seconds=300)

