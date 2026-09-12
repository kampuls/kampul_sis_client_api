"""
Query result caching decorator for high-traffic endpoints.
Reduces database load by caching frequently accessed data.
"""
import functools
import hashlib
import json
import time
import asyncio
from typing import Any, Optional, Callable
from fastapi import Request
from starlette.responses import Response, JSONResponse
import logging

logger = logging.getLogger(__name__)


class QueryCache:
    """Simple in-memory query result cache with TTL"""
    
    def __init__(self, default_ttl: int = 60):
        self._cache: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, expires_at = self._cache[key]
            if time.time() < expires_at:
                return value
            del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expires_at = time.time() + (ttl or self._default_ttl)
        self._cache[key] = (value, expires_at)
    
    def delete(self, key: str) -> None:
        self._cache.pop(key, None)
    
    def clear(self) -> None:
        self._cache.clear()
    
    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count of removed items."""
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if exp <= now]
        for key in expired:
            del self._cache[key]
        return len(expired)
    
    def stats(self) -> dict:
        """Return cache statistics"""
        now = time.time()
        active = sum(1 for _, exp in self._cache.values() if exp > now)
        return {
            "total_entries": len(self._cache),
            "active_entries": active,
            "expired_entries": len(self._cache) - active,
        }


# Global cache instance
query_cache = QueryCache(default_ttl=60)


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a unique cache key from arguments"""
    key_data = {
        "prefix": prefix,
        "args": args,
        "kwargs": kwargs,
    }
    key_string = json.dumps(key_data, sort_keys=True, default=str)
    key_hash = hashlib.md5(key_string.encode()).hexdigest()
    return f"{prefix}:{key_hash}"


def cache_query_result(
    prefix: str,
    ttl: int = 60,
    cache_none: bool = False,
    key_func: Optional[Callable] = None,
):
    """
    Decorator to cache query results.
    
    Args:
        prefix: Cache key prefix (e.g., "auth_me", "app_branding")
        ttl: Time to live in seconds
        cache_none: Whether to cache None results
        key_func: Optional function to generate custom cache key
    
    Usage:
        @router.get("/me")
        @cache_query_result("auth_me", ttl=30)
        async def get_current_user(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = generate_cache_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_result = query_cache.get(cache_key)
            if cached_result is not None or (cached_result is None and cache_none):
                logger.debug(f"Cache HIT for {cache_key}")
                return cached_result
            
            # Execute function and cache result
            logger.debug(f"Cache MISS for {cache_key}, executing query...")
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            # Cache the result (even if None, if allowed)
            if result is not None or cache_none:
                query_cache.set(cache_key, result, ttl)
                logger.debug(f"Cached result for {cache_key} (TTL={ttl}s)")
            
            return result
        
        wrapper.cache_key = cache_key  # type: ignore
        return wrapper
    
    return decorator


def invalidate_cache(pattern: str) -> int:
    """
    Invalidate cache entries matching a pattern.
    Returns count of invalidated entries.
    """
    keys_to_delete = [k for k in query_cache._cache.keys() if pattern in k]
    for key in keys_to_delete:
        del query_cache._cache[key]
    logger.info(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}'")
    return len(keys_to_delete)


def get_cache_stats() -> dict:
    """Get cache statistics"""
    return query_cache.stats()

