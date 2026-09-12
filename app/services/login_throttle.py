"""Slow down password guessing against the login endpoints.

The global rate limiter allows 10,000 requests a minute per IP, which is ~166
password guesses a second, and it buckets on a header an attacker controls. This
adds a throttle keyed on **the account being attempted**, which no amount of IP
rotation can dodge, plus a secondary per-IP bucket.

Two properties this must have, in priority order:

1. Never lock out a legitimate user because of a bug or an outage here. Every
   failure path returns "allowed" — a throttle that breaks logins is worse than
   the guessing it prevents.
2. Only failures count, and a success clears the counter, so somebody typing one
   wrong password then the right one is never affected.

Counters live in Redis when it is reachable so all workers share them, and fall
back to a per-process dict otherwise (weaker, but still far better than nothing).
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

from ..core import settings

logger = logging.getLogger(__name__)

_PREFIX = "login_throttle"

_lock = threading.Lock()
_memory: Dict[str, List[float]] = {}
_last_sweep = 0.0


def _redis():
    """The shared Redis client, or None when it is unavailable."""
    try:
        from .cache import RedisCache, redis_client

        if not RedisCache._redis_available:
            return None
        return redis_client
    except Exception:
        return None


def _window() -> int:
    return max(int(getattr(settings, "login_attempt_window_seconds", 900) or 900), 30)


def _max_attempts() -> int:
    return max(int(getattr(settings, "login_max_failed_attempts", 10) or 10), 1)


def _enabled() -> bool:
    return bool(getattr(settings, "login_throttle_enabled", True))


def _sweep_memory(now: float, window: int) -> None:
    """Drop stale in-memory buckets so this cannot grow without bound."""
    global _last_sweep
    if now - _last_sweep < 60:
        return
    _last_sweep = now
    cutoff = now - window
    for key in [k for k, v in _memory.items() if not v or v[-1] < cutoff]:
        _memory.pop(key, None)


def _memory_count(key: str, now: float, window: int) -> int:
    with _lock:
        _sweep_memory(now, window)
        kept = [t for t in _memory.get(key, []) if t > now - window]
        _memory[key] = kept
        return len(kept)


def _memory_add(key: str, now: float, window: int) -> None:
    with _lock:
        _sweep_memory(now, window)
        kept = [t for t in _memory.get(key, []) if t > now - window]
        kept.append(now)
        _memory[key] = kept


def _keys(username: Optional[str], ip: Optional[str]) -> List[Tuple[str, str]]:
    """(label, key) pairs to check. Username is the one that actually matters."""
    out: List[Tuple[str, str]] = []
    if username and username.strip():
        out.append(("account", f"{_PREFIX}:acct:{username.strip().lower()[:80]}"))
    if ip and ip.strip():
        out.append(("ip", f"{_PREFIX}:ip:{ip.strip()[:64]}"))
    return out


def failures_for(username: Optional[str], ip: Optional[str]) -> int:
    """Highest recent failure count across the account and IP buckets."""
    if not _enabled():
        return 0
    now = time.time()
    window = _window()
    highest = 0
    client = _redis()
    for _label, key in _keys(username, ip):
        count = 0
        if client is not None:
            try:
                raw = client.get(key)
                count = int(raw) if raw else 0
            except Exception:
                count = _memory_count(key, now, window)
        else:
            count = _memory_count(key, now, window)
        highest = max(highest, count)
    return highest


def is_locked(username: Optional[str], ip: Optional[str]) -> bool:
    """True when this account (or IP) has failed too often recently."""
    try:
        if not _enabled():
            return False
        return failures_for(username, ip) >= _max_attempts()
    except Exception as e:
        # Degrade open: never block a real login because the throttle broke.
        logger.error("Login throttle check failed, allowing request: %s", e)
        return False


def record_failure(username: Optional[str], ip: Optional[str]) -> None:
    """Count one failed password attempt."""
    try:
        if not _enabled():
            return
        now = time.time()
        window = _window()
        client = _redis()
        for _label, key in _keys(username, ip):
            if client is not None:
                try:
                    pipe = client.pipeline()
                    pipe.incr(key, 1)
                    pipe.expire(key, window)
                    pipe.execute()
                    continue
                except Exception:
                    pass
            _memory_add(key, now, window)
    except Exception as e:
        logger.error("Login throttle could not record a failure: %s", e)


def clear(username: Optional[str], ip: Optional[str]) -> None:
    """Forget the failures after a successful sign-in."""
    try:
        if not _enabled():
            return
        client = _redis()
        for _label, key in _keys(username, ip):
            if client is not None:
                try:
                    client.delete(key)
                except Exception:
                    pass
            with _lock:
                _memory.pop(key, None)
    except Exception as e:
        logger.error("Login throttle could not clear counters: %s", e)


def retry_after_seconds() -> int:
    return _window()


def reset_all_for_tests() -> None:
    """Test helper — drops every counter, in-process AND in Redis.

    Redis counters outlive the process, so clearing only the local dict left
    stale counts behind and made tests pass once and fail on the next run.
    """
    global _last_sweep
    with _lock:
        _memory.clear()
        _last_sweep = 0.0
    client = _redis()
    if client is not None:
        try:
            keys = list(client.scan_iter(match=f"{_PREFIX}:*", count=500))
            if keys:
                client.delete(*keys)
        except Exception as e:
            logger.debug("Could not clear Redis throttle counters: %s", e)
