"""
Per-user check-in rate limits, blocked attempts, and anomaly signals.

- Hard limit: too many check-in-out POSTs per user → HTTP 429 + DB row.
- Security blocks: mock GPS, missing GPS/device signal, unauthorized network,
  branch, or workplace → DB row.
- Soft signals: logged only (many users on one IP = normal school Wi‑Fi;
  one user from many IPs in a short window = possible VPN / travel / abuse).
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import threading
import time
from collections import defaultdict
from typing import Any, List, Optional, Tuple

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from ..models.check_in_security_event import CheckInSecurityEvent
from ..models.telegram_attendance_settings import TelegramAttendanceSettings
from ..models.user import User
from ..core.config import settings
from .attendance_security_alert_policy import (
    should_send_attendance_security_telegram,
)
from .telegram_branch_routing import resolve_attendance_notification_chat_id
from .telegram_notification_service import TelegramNotificationService

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()

# --- Per-user POST /check-in-out rate (any action) ---
_USER_WINDOW_SEC = 60.0
_USER_MAX_REQUESTS = 25  # generous for flaky networks; still stops scripts

# --- User-requested Telegram support reports ---
# This has its own small limit so reporting a problem never consumes the
# employee's check-in allowance and repeated taps cannot flood Telegram.
_SUPPORT_REPORT_WINDOW_SEC = 60.0
_SUPPORT_REPORT_MAX_REQUESTS = 3

# --- One user, many IPs (check_in only) — warning, throttled ---
_MULTI_IP_WINDOW_SEC = 30 * 60
_MULTI_IP_UNIQUE_THRESHOLD = 4
_MULTI_IP_LOG_COOLDOWN_SEC = 30 * 60

# --- One public IP, many different users — info, throttled (school NAT) ---
_NAT_WINDOW_SEC = 10 * 60
_NAT_UNIQUE_USERS_THRESHOLD = 15
_NAT_LOG_COOLDOWN_SEC = 5 * 60

_user_req_ts: dict[int, List[float]] = defaultdict(list)
_support_report_req_ts: dict[int, List[float]] = defaultdict(list)
_user_checkin_ip_ts: dict[int, List[Tuple[float, str]]] = defaultdict(list)
_ip_user_ts: dict[str, List[Tuple[float, int]]] = defaultdict(list)
_nat_log_until: dict[str, float] = {}
_multi_ip_log_until: dict[int, float] = {}
_event_log_until: dict[tuple[int, str, str], float] = {}


def _mono() -> float:
    return time.monotonic()


def _prune_floats(ts: List[float], window: float) -> None:
    cutoff = _mono() - window
    ts[:] = [value for value in ts if value >= cutoff]


def _prune_tuples(entries: List[Tuple[float, Any]], window: float) -> None:
    cutoff = _mono() - window
    entries[:] = [(stamp, value) for stamp, value in entries if stamp >= cutoff]


def _client_ip(request: Request) -> str:
    peer_ip = (
        str(request.client.host).strip()
        if request.client and request.client.host
        else ""
    )
    if not peer_ip:
        return ""

    # Forwarded headers are attacker-controlled unless the direct peer is a
    # proxy explicitly trusted by deployment configuration.
    peer_is_trusted_proxy = False
    try:
        peer = ipaddress.ip_address(peer_ip)
        for raw in str(settings.trusted_proxy_ranges or "").split(","):
            entry = raw.strip()
            if not entry:
                continue
            network = ipaddress.ip_network(
                entry if "/" in entry else f"{entry}/{peer.max_prefixlen}",
                strict=False,
            )
            if peer in network:
                peer_is_trusted_proxy = True
                break
    except ValueError:
        peer_is_trusted_proxy = False

    if peer_is_trusted_proxy:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            try:
                ipaddress.ip_address(candidate)
                return candidate[:64]
            except ValueError:
                pass
    return peer_ip[:64]


def _ua(request: Request) -> Optional[str]:
    ua = request.headers.get("User-Agent")
    if not ua:
        return None
    return ua[:500]


def _persist_event(
    db: Session,
    *,
    user_id: Optional[int],
    client_ip: str,
    event_type: str,
    severity: str,
    message: str,
    detail: Optional[dict[str, Any]] = None,
    user_agent: Optional[str] = None,
) -> bool:
    try:
        row = CheckInSecurityEvent(
            user_id=user_id,
            client_ip=client_ip or None,
            event_type=event_type,
            severity=severity,
            message=message,
            detail_json=json.dumps(detail) if detail else None,
            user_agent=user_agent,
        )
        db.add(row)
        db.commit()
        if should_send_attendance_security_telegram(event_type, severity):
            _queue_telegram_security_alert(
                db,
                user_id=user_id,
                client_ip=client_ip,
                event_type=event_type,
                severity=severity,
                message=message,
            )
        return True
    except Exception as e:
        db.rollback()
        logger.warning("check_in_security: failed to persist event: %s", e)
        return False


def _queue_telegram_security_alert(
    db: Session,
    *,
    user_id: Optional[int],
    client_ip: str,
    event_type: str,
    severity: str,
    message: str,
) -> None:
    """Dispatch a persisted security event without delaying attendance."""
    if user_id is None:
        return
    try:
        telegram_settings = db.query(TelegramAttendanceSettings).first()
        if (
            telegram_settings is None
            or not telegram_settings.enabled
            or not telegram_settings.bot_token
        ):
            return
        user = db.query(User).filter(User.id == int(user_id)).first()
        chat_id = resolve_attendance_notification_chat_id(
            telegram_settings,
            db=db,
            branch_id=getattr(user, "workplace", None),
        )
        if not chat_id:
            return

        employee_name = (
            getattr(user, "eName", None)
            or getattr(user, "kName", None)
            or getattr(user, "username", None)
            or f"User #{int(user_id)}"
        )
        username = str(getattr(user, "username", None) or "unknown")
        bot_token = str(telegram_settings.bot_token)
    except Exception as exc:
        logger.warning(
            "check_in_security: could not prepare Telegram alert: %s",
            exc,
        )
        return

    async def send_alerts() -> None:
        await TelegramNotificationService.send_checkin_security_alert(
            bot_token=bot_token,
            chat_id=chat_id,
            employee_name=str(employee_name),
            username=username,
            user_id=int(user_id),
            event_type=event_type,
            severity=severity,
            message=message,
            client_ip=client_ip or None,
        )

    try:
        asyncio.get_running_loop().create_task(send_alerts())
    except RuntimeError:
        threading.Thread(
            target=lambda: asyncio.run(send_alerts()),
            name="attendance-security-telegram",
            daemon=True,
        ).start()


def record_checkin_security_event(
    db: Session,
    *,
    user_id: int,
    client_ip: str,
    event_type: str,
    severity: str,
    message: str,
    detail: Optional[dict[str, Any]] = None,
    user_agent: Optional[str] = None,
    cooldown_seconds: float = 60.0,
) -> None:
    """Persist a blocked/anomalous attempt without flooding repeated retries."""
    now = _mono()
    key = (int(user_id), event_type, client_ip or "")
    if now < _event_log_until.get(key, 0.0):
        return
    _event_log_until[key] = now + max(0.0, cooldown_seconds)
    _persist_event(
        db,
        user_id=user_id,
        client_ip=client_ip,
        event_type=event_type,
        severity=severity,
        message=message,
        detail=detail,
        user_agent=user_agent,
    )


async def enforce_checkin_rate_limit(
    request: Request,
    db: Session,
    user_id: int,
) -> str:
    """
    Call at the start of POST /check-in-out. Returns client_ip.
    Raises HTTPException 429 if per-user burst is exceeded.
    """
    ip = _client_ip(request)
    ua = _ua(request)
    blocked = False
    async with _lock:
        ts = _user_req_ts[user_id]
        _prune_floats(ts, _USER_WINDOW_SEC)
        if len(ts) >= _USER_MAX_REQUESTS:
            blocked = True
        else:
            ts.append(_mono())
    if blocked:
        record_checkin_security_event(
            db,
            user_id=user_id,
            client_ip=ip,
            event_type="rate_limit_user",
            severity="critical",
            message="Check-in API rate limit exceeded for this user (burst).",
            detail={"window_sec": _USER_WINDOW_SEC, "max": _USER_MAX_REQUESTS},
            user_agent=ua,
            cooldown_seconds=_USER_WINDOW_SEC,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many check-in requests. Please wait a minute and try again.",
        )
    return ip


async def enforce_attendance_support_report_rate_limit(
    request: Request,
    db: Session,
    user_id: int,
) -> str:
    """Limit Telegram reports without affecting attendance mutations."""
    ip = _client_ip(request)
    blocked = False
    async with _lock:
        timestamps = _support_report_req_ts[user_id]
        _prune_floats(timestamps, _SUPPORT_REPORT_WINDOW_SEC)
        if len(timestamps) >= _SUPPORT_REPORT_MAX_REQUESTS:
            blocked = True
        else:
            timestamps.append(_mono())
    if blocked:
        record_checkin_security_event(
            db,
            user_id=user_id,
            client_ip=ip,
            event_type="support_report_rate_limit",
            severity="warning",
            message="Attendance support report rate limit exceeded.",
            detail={
                "window_sec": _SUPPORT_REPORT_WINDOW_SEC,
                "max": _SUPPORT_REPORT_MAX_REQUESTS,
            },
            user_agent=_ua(request),
            cooldown_seconds=_SUPPORT_REPORT_WINDOW_SEC,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many attendance reports. Please wait a minute and retry.",
        )
    return ip


async def observe_successful_check_in(
    db: Session,
    *,
    user_id: int,
    client_ip: str,
    user_agent: Optional[str],
) -> None:
    """After a successful check-in (not check-out): update IP heuristics and maybe log."""
    if not client_ip:
        return

    log_multi: Optional[dict[str, Any]] = None
    log_nat: Optional[dict[str, Any]] = None

    async with _lock:
        now = _mono()
        ulist = _user_checkin_ip_ts[user_id]
        _prune_tuples(ulist, _MULTI_IP_WINDOW_SEC)
        ulist.append((now, client_ip))
        unique_ips = {ip for _, ip in ulist}

        ilist = _ip_user_ts[client_ip]
        _prune_tuples(ilist, _NAT_WINDOW_SEC)
        ilist.append((now, user_id))
        unique_users = {uid for _, uid in ilist}
        if len(unique_ips) >= _MULTI_IP_UNIQUE_THRESHOLD:
            if now >= _multi_ip_log_until.get(user_id, 0.0):
                _multi_ip_log_until[user_id] = now + _MULTI_IP_LOG_COOLDOWN_SEC
                log_multi = {
                    "unique_ip_count": len(unique_ips),
                    "window_minutes": int(_MULTI_IP_WINDOW_SEC // 60),
                }

        if len(unique_users) >= _NAT_UNIQUE_USERS_THRESHOLD:
            if now >= _nat_log_until.get(client_ip, 0.0):
                _nat_log_until[client_ip] = now + _NAT_LOG_COOLDOWN_SEC
                log_nat = {
                    "unique_user_count": len(unique_users),
                    "window_minutes": int(_NAT_WINDOW_SEC // 60),
                }

    if log_multi is not None:
        _persist_event(
            db,
            user_id=user_id,
            client_ip=client_ip,
            event_type="multi_ip_user",
            severity="warning",
            message=(
                "This user checked in from several different public IPs within "
                "30 minutes (VPN, mobile data switching, travel, or unusual activity)."
            ),
            detail=log_multi,
            user_agent=user_agent,
        )

    if log_nat is not None:
        _persist_event(
            db,
            user_id=user_id,
            client_ip=client_ip,
            event_type="shared_nat_burst",
            severity="info",
            message=(
                "Many different users checked in from the same public IP within "
                "a few minutes — usually school or office Wi‑Fi (shared internet), not an attack."
            ),
            detail=log_nat,
            user_agent=None,
        )
