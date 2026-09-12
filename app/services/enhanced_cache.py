"""
Enhanced caching for connection-efficient operation.
Caches more endpoints to reduce database connections.
"""
from functools import wraps
import hashlib
import json
import time
import asyncio
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class EnhancedCache:
    """In-memory cache with TTL and size limits"""
    
    def __init__(self, default_ttl: int = 300, max_size: int = 1000):
        self._cache: dict = {}
        self._max_size = max_size
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
        
        # Evict oldest if over capacity
        while len(self._cache) > self._max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
    
    def delete(self, key: str) -> None:
        self._cache.pop(key, None)
    
    def clear(self) -> None:
        self._cache.clear()
    
    def stats(self) -> dict:
        now = time.time()
        active = sum(1 for _, exp in self._cache.values() if exp > now)
        return {
            "total_entries": len(self._cache),
            "active_entries": active,
            "expired_entries": len(self._cache) - active,
            "max_size": self._max_size,
        }


# Global cache instances with different TTLs
# Long TTL (10 minutes) - rarely changes
long_cache = EnhancedCache(default_ttl=600, max_size=500)

# Medium TTL (5 minutes) - changes occasionally  
medium_cache = EnhancedCache(default_ttl=300, max_size=1000)

# Short TTL (1-2 minutes) - changes frequently
short_cache = EnhancedCache(default_ttl=120, max_size=2000)


def cache_result(cache_instance, key_prefix: str, ttl: Optional[int] = None):
    """Decorator to cache function results"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key
            key_data = {"prefix": key_prefix, "func": func.__name__, "args": args, "kwargs": kwargs}
            key = hashlib.md5(json.dumps(key_data, sort_keys=True, default=str).encode()).hexdigest()
            
            # Try cache
            cached = cache_instance.get(key)
            if cached is not None:
                logger.debug(f"Cache HIT: {key_prefix}:{key[:8]}")
                return cached
            
            # Execute and cache
            logger.debug(f"Cache MISS: {key_prefix}:{key[:8]}")
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            if result is not None:
                cache_instance.set(key, result, ttl)
            
            return result
        return async_wrapper
    
    def sync_wrapper(*args, **kwargs):
        # Generate cache key
        key_data = {"prefix": key_prefix, "func": func.__name__, "args": args, "kwargs": kwargs}
        key = hashlib.md5(json.dumps(key_data, sort_keys=True, default=str).encode()).hexdigest()
        
        # Try cache
        cached = cache_instance.get(key)
        if cached is not None:
            logger.debug(f"Cache HIT: {key_prefix}:{key[:8]}")
            return cached
        
        # Execute and cache
        logger.debug(f"Cache MISS: {key_prefix}:{key[:8]}")
        result = func(*args, **kwargs)
        
        if result is not None:
            cache_instance.set(key, result, ttl)
        
        return result
    
    def decorator_inner(func):
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator_inner


# Helper functions for specific use cases
def cache_branches(ttl: int = 600):
    """Cache branch list for 10 minutes"""
    return cache_result(long_cache, "branches", ttl)


def cache_settings(ttl: int = 600):
    """Cache settings for 10 minutes"""
    return cache_result(long_cache, "settings", ttl)


def cache_permissions(ttl: int = 600):
    """Cache permissions for 10 minutes"""
    return cache_result(long_cache, "permissions", ttl)


def cache_student_list(ttl: int = 120):
    """Cache student list for 2 minutes"""
    return cache_result(medium_cache, "students", ttl)


def cache_teacher_list(ttl: int = 120):
    """Cache teacher list for 2 minutes"""
    return cache_result(medium_cache, "teachers", ttl)


def cache_attendance(ttl: int = 120):
    """Cache attendance data for 2 minutes"""
    return cache_result(short_cache, "attendance", ttl)


def get_cache_stats() -> dict:
    """Get stats for all caches"""
    return {
        "long_cache": long_cache.stats(),
        "medium_cache": medium_cache.stats(),
        "short_cache": short_cache.stats(),
    }


def invalidate_pattern(pattern: str) -> int:
    """Invalidate cache entries matching pattern"""
    count = 0
    for cache in [long_cache, medium_cache, short_cache]:
        keys_to_delete = [k for k in cache._cache.keys() if pattern in k]
        for key in keys_to_delete:
            del cache._cache[key]
            count += 1
    logger.info(f"Invalidated {count} cache entries matching '{pattern}'")
    return count
