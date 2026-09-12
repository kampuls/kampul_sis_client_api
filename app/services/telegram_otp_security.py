"""Security helpers for Telegram OTP sends and registration hand-off.

The OTP endpoints are public, so sends need a dedicated per-phone and per-IP
throttle.  A successful Telegram verification also returns an opaque,
single-use proof; registration consumes that proof in the same database
transaction that creates the pending account.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core import settings

logger = logging.getLogger(__name__)

_PREFIX = "telegram_otp_throttle"
_memory_lock = threading.Lock()
_memory: Dict[str, List[float]] = {}
_last_sweep = 0.0


def _redis():
    try:
        from .cache import RedisCache, redis_client

        if not RedisCache._redis_available:
            return None
        return redis_client
    except Exception:
        return None


def _enabled() -> bool:
    return bool(getattr(settings, "telegram_otp_throttle_enabled", True))


def _window() -> int:
    return max(
        int(getattr(settings, "telegram_otp_window_seconds", 900) or 900),
        60,
    )


def _phone_limit() -> int:
    return max(int(getattr(settings, "telegram_otp_max_sends_per_phone", 5) or 5), 1)


def _ip_limit() -> int:
    return max(int(getattr(settings, "telegram_otp_max_sends_per_ip", 30) or 30), 1)


def _bucket_keys(phone: str, ip: Optional[str]) -> List[Tuple[str, int]]:
    phone_digest = hashlib.sha256(phone.encode("utf-8")).hexdigest()
    keys = [(f"{_PREFIX}:phone:{phone_digest}", _phone_limit())]
    if ip and ip.strip():
        ip_digest = hashlib.sha256(ip.strip().encode("utf-8")).hexdigest()
        keys.append((f"{_PREFIX}:ip:{ip_digest}", _ip_limit()))
    return keys


def _sweep_memory(now: float, window: int) -> None:
    global _last_sweep
    if now - _last_sweep < 60:
        return
    _last_sweep = now
    cutoff = now - window
    for key in [key for key, values in _memory.items() if not values or values[-1] <= cutoff]:
        _memory.pop(key, None)


def _memory_check_and_add(key: str, limit: int, now: float, window: int) -> bool:
    with _memory_lock:
        _sweep_memory(now, window)
        values = [value for value in _memory.get(key, []) if value > now - window]
        if len(values) >= limit:
            _memory[key] = values
            return False
        values.append(now)
        _memory[key] = values
        return True


def allow_send(phone: str, ip: Optional[str]) -> bool:
    """Count one send request and return whether all buckets allow it.

    Redis shares the counters across workers.  If Redis is unavailable, a
    bounded in-process fallback still limits accidental or single-worker abuse.
    A throttle failure degrades open so an infrastructure problem cannot lock
    every family out of registration.
    """
    if not _enabled():
        return True

    now = time.time()
    window = _window()
    client = _redis()
    try:
        for key, limit in _bucket_keys(phone, ip):
            if client is not None:
                try:
                    pipe = client.pipeline()
                    pipe.incr(key, 1)
                    pipe.expire(key, window)
                    count, _ = pipe.execute()
                    if int(count) > limit:
                        return False
                    continue
                except Exception:
                    pass
            if not _memory_check_and_add(key, limit, now, window):
                return False
        return True
    except Exception as exc:
        logger.error("Telegram OTP throttle failed open: %s", exc)
        return True


def retry_after_seconds() -> int:
    return _window()


def reset_throttle_for_tests() -> None:
    global _last_sweep
    with _memory_lock:
        _memory.clear()
        _last_sweep = 0.0


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_registration_proof(
    db: Session,
    *,
    session_id: int,
    ttl_seconds: Optional[int] = None,
) -> str:
    """Attach a short-lived opaque registration proof to one verified session."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    configured_ttl = int(
        ttl_seconds
        if ttl_seconds is not None
        else getattr(settings, "telegram_registration_proof_ttl_seconds", 1800)
    )
    expires_at = now + timedelta(seconds=max(configured_ttl, 60))
    result = db.execute(
        text(
            """
            UPDATE telegram_otp_sessions
            SET registration_token_hash = :token_hash,
                registration_expires_at = :expires_at,
                registration_used_at = NULL
            WHERE id = :session_id
              AND used_at IS NOT NULL
            """
        ),
        {
            "token_hash": _token_digest(token),
            "expires_at": expires_at,
            "session_id": session_id,
        },
    )
    if result.rowcount != 1:
        raise RuntimeError("Verified Telegram session could not issue registration proof")
    return token


def claim_registration_proof(
    db: Session,
    *,
    phone: str,
    token: Optional[str],
) -> bool:
    """Atomically reserve a proof for the pending-account transaction.

    This method deliberately does not commit.  The staff/parent creation helper
    commits the account and proof consumption together; its rollback makes the
    proof retryable when saving the account fails.
    """
    value = (token or "").strip()
    if not value:
        return False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = db.execute(
        text(
            """
            UPDATE telegram_otp_sessions
            SET registration_used_at = :now
            WHERE phone = :phone
              AND registration_token_hash = :token_hash
              AND registration_expires_at > :now
              AND registration_used_at IS NULL
              AND used_at IS NOT NULL
            """
        ),
        {
            "now": now,
            "phone": phone,
            "token_hash": _token_digest(value),
        },
    )
    return result.rowcount == 1


def bearer_value(authorization: Optional[str]) -> Optional[str]:
    value = (authorization or "").strip()
    if not value:
        return None
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value or None
