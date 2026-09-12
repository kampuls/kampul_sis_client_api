"""
Leave Notification Service.

Background-task entry points fired by the leave-management API:
- new request      → push + in-app to all eligible approvers (+ Telegram)
- review reminder  → push + in-app to eligible approvers who can decide
- decision         → requester notified; other approvers told who decided (+ Telegram)
- cancellation     → approvers notified (and requester when cancelled by admin)

Each entry point opens its own DB session because it runs after the request
lifecycle. All functions are sync (FastAPI runs them in a worker thread);
the async Telegram client is driven with asyncio.run().
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session

from ..core.config import settings as app_settings
from ..core.database import SessionLocal
from ..models import (
    LeaveApprover,
    LeaveBalanceAdjustment,
    LeaveRequest,
    LeaveType,
    TelegramAttendanceSettings,
    User,
)
from .notification_service import send_notification
from .leave_approval_policy import approval_day_limit_allows
from .telegram_leave_routing import resolve_leave_notification_chat_id

logger = logging.getLogger(__name__)

CAMBODIA_TZ = timezone(timedelta(hours=7))

# Route ids understood by the Flutter app (NavigationUtils.navigateToFeature).
ROUTE_APPROVER_INBOX = "leave_requests"
ROUTE_MY_LEAVE = "employee_leave"


@dataclass(frozen=True)
class _TelegramTreeNode:
    label: str
    children: tuple["_TelegramTreeNode", ...] = ()


def _display_name(user: Optional[User]) -> str:
    if user is None:
        return "Unknown"
    for attr in ("eName", "kName", "username"):
        value = getattr(user, attr, None)
        if value:
            return str(value)
    return f"User #{getattr(user, 'id', '?')}"


def _fmt_date(value) -> str:
    try:
        return value.strftime("%d/%m/%Y")
    except Exception:
        return str(value)


def _fmt_days_summary(request: LeaveRequest) -> str:
    """Return each leave scope/session directly below its date."""
    parts: List[str] = []
    for day in sorted(request.days, key=lambda d: d.leave_date):
        if day.scope == "sessions" and day.session_indexes:
            sessions = ", ".join(f"S{i}" for i in day.session_indexes)
            window = (
                f" · {day.time_from}–{day.time_to}"
                if day.time_from and day.time_to
                else ""
            )
            detail = f"{sessions}{window}"
        else:
            detail = "Full day"
        parts.extend([_fmt_date(day.leave_date), f"   └ {detail}"])
    return "\n".join(parts)


def _leave_dates_tree(request: LeaveRequest) -> _TelegramTreeNode:
    date_nodes: List[_TelegramTreeNode] = []
    for day in sorted(request.days, key=lambda d: d.leave_date):
        if day.scope == "sessions" and day.session_indexes:
            sessions = ", ".join(f"S{i}" for i in day.session_indexes)
            window = (
                f" · {day.time_from}–{day.time_to}"
                if day.time_from and day.time_to
                else ""
            )
            detail = f"{sessions}{window}"
        else:
            detail = "Full day"
        date_nodes.append(
            _TelegramTreeNode(
                _escape_html(_fmt_date(day.leave_date)),
                (_TelegramTreeNode(_escape_html(detail)),),
            )
        )
    return _TelegramTreeNode("🗓️ Leave dates", tuple(date_nodes))


def _eligible_approvers(
    db: Session,
    requester: User,
    request_days: Optional[float] = None,
) -> List[LeaveApprover]:
    approvers = (
        db.query(LeaveApprover)
        .filter(LeaveApprover.is_active == True)  # noqa: E712
        .all()
    )
    matched: List[LeaveApprover] = []
    for approver in approvers:
        if not approval_day_limit_allows(
            approver.max_days_can_approve,
            request_days,
        ):
            continue
        if bool(approver.can_approve_all):
            matched.append(approver)
            continue
        if approver.department_id is None and approver.branch_id is None:
            # Empty scope may be used with can_view_all_requests for a
            # read-only reviewer. It is never a decision/notification scope.
            continue
        if (
            approver.department_id is not None
            and getattr(requester, "departmentId", None) != approver.department_id
        ):
            continue
        if (
            approver.branch_id is not None
            and getattr(requester, "workplace", None) != approver.branch_id
        ):
            continue
        matched.append(approver)
    return matched


def _push_to_users(
    db: Session,
    user_ids: List[int],
    title: str,
    body: str,
    redirect_route: str,
    request_id: int,
    *,
    notification_type: str = "leave_request",
    data_key: str = "request_id",
) -> None:
    ids = sorted({int(u) for u in user_ids if u})
    if ids:
        users = db.query(User).filter(User.id.in_(ids), User.status == 1).all()
        active_ids = {int(user.id) for user in users}
        ids = [user_id for user_id in ids if user_id in active_ids]
    if not ids:
        return
    try:
        send_notification(
            device_tokens=[],
            title=title,
            body=body,
            # redirect_route rides in the push payload too, so tapping the
            # system notification can route: 'leave_requests' → approver
            # inbox, 'employee_leave' → the requester's My Leave screen.
            data={
                "type": notification_type,
                data_key: str(request_id),
                "redirect_route": redirect_route,
            },
            db=db,
            user_ids=[{"id": uid, "user_type": "teacher"} for uid in ids],
            redirect_route=redirect_route,
            redirect_args={data_key: request_id},
        )
    except Exception as exc:
        logger.error(f"Leave push notification failed: {exc}")


def _telegram_settings(db: Session) -> Optional[TelegramAttendanceSettings]:
    try:
        settings = db.query(TelegramAttendanceSettings).first()
    except Exception:
        return None
    if (
        not settings
        or not settings.bot_token
        or not resolve_leave_notification_chat_id(settings)
    ):
        return None
    return settings


def _leave_chat_id(
    settings: TelegramAttendanceSettings,
    db: Session,
    requester: Optional[User],
) -> str:
    """Return a usable destination after _telegram_settings validation."""
    return str(
        resolve_leave_notification_chat_id(
            settings,
            db=db,
            branch_id=getattr(requester, "workplace", None),
        )
        or ""
    )


def _configured_app_link_base_url() -> Optional[str]:
    """Resolve a valid public app-link origin from deployment configuration."""
    candidates = [
        os.environ.get("PAMA_APP_LINK_BASE_URL", ""),
        os.environ.get("PUBLIC_API_BASE_URL", ""),
    ]
    # In development, Settings may read config/.env. In production, require an
    # actual deployment variable so a developer's LAN URL can never leak into
    # a Telegram button.
    if not app_settings.is_production:
        candidates.extend(
            [
                app_settings.pama_app_link_base_url,
                app_settings.public_api_base_url,
            ]
        )
    for candidate in candidates:
        raw = str(candidate or "").strip().rstrip("/")
        if not raw:
            continue
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            logger.warning("Ignoring invalid public app-link base URL: %s", raw)
            continue
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    return None


def _leave_request_link(request_id: int) -> Optional[str]:
    base_url = _configured_app_link_base_url()
    if not base_url:
        logger.warning(
            "Leave Telegram link omitted: configure PAMA_APP_LINK_BASE_URL "
            "or PUBLIC_API_BASE_URL"
        )
        return None
    return f"{base_url}/leave/{int(request_id)}"


def _send_telegram(
    bot_token: str,
    chat_id: str,
    message: str,
    *,
    action_url: Optional[str] = None,
) -> None:
    async def _post() -> None:
        import httpx

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        if action_url:
            payload["reply_markup"] = {
                "inline_keyboard": [[{
                    "text": "📱 View leave request",
                    "url": action_url,
                }]],
            }
        async with httpx.AsyncClient(timeout=10.0) as client:
            last_error = ""
            for attempt in range(3):
                try:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        return
                    last_error = f"{response.status_code} - {response.text}"
                except Exception as exc:
                    last_error = str(exc)
                if attempt < 2:
                    await asyncio.sleep(0.4 * (2**attempt))
            logger.error(
                "Telegram leave notification failed after 3 attempts: %s",
                last_error,
            )

    try:
        asyncio.run(_post())
    except Exception as exc:
        logger.error(f"Telegram leave notification error: {exc}")


def _escape_html(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _telegram_message(
    header: str,
    rows: List[Union[str, _TelegramTreeNode]],
    footer: Optional[str] = None,
) -> str:
    tree_rows: List[_TelegramTreeNode] = []
    for row in rows:
        if isinstance(row, _TelegramTreeNode):
            tree_rows.append(row)
            continue
        row_lines = [line for line in str(row).splitlines() if line.strip()]
        if row_lines:
            tree_rows.append(
                _TelegramTreeNode(
                    row_lines[0],
                    tuple(_TelegramTreeNode(line) for line in row_lines[1:]),
                )
            )

    body_lines: List[str] = []

    def append_node(
        node: _TelegramTreeNode,
        *,
        ancestor_prefix: str,
        is_last: bool,
    ) -> None:
        connector = "└" if is_last else "├"
        body_lines.append(f"{ancestor_prefix}{connector} {node.label}")
        child_prefix = ancestor_prefix + ("   " if is_last else "│  ")
        for child_index, child in enumerate(node.children):
            append_node(
                child,
                ancestor_prefix=child_prefix,
                is_last=child_index == len(node.children) - 1,
            )

    for row_index, row in enumerate(tree_rows):
        append_node(
            row,
            ancestor_prefix="",
            is_last=row_index == len(tree_rows) - 1,
        )

    message = f"<b>{header}</b>\n" + "\n".join(body_lines)
    if footer:
        message += f"\n\n<b>📌 Note</b>\n└ {_escape_html(footer)}"
    message += (
        "\n\n<i>━━━━━━━━━━━━━━━━━━━━</i>\n"
        f"<i>{app_settings.mobile_app_title} Attendance System</i>"
    )
    return message


def _load_request(db: Session, request_id: int):
    request = db.query(LeaveRequest).filter(LeaveRequest.id == request_id).first()
    if not request:
        return None, None, None
    requester = db.query(User).filter(User.id == request.user_id).first()
    leave_type = db.query(LeaveType).filter(LeaveType.id == request.leave_type_id).first()
    return request, requester, leave_type


def _replacement_user(db: Session, request: LeaveRequest) -> Optional[User]:
    if not getattr(request, "replacement_user_id", None):
        return None
    return db.query(User).filter(User.id == request.replacement_user_id).first()


def _notify_replacement_assigned(
    db: Session,
    request: LeaveRequest,
    requester_name: str,
    type_name: str,
    date_range: str,
    approver_name: str,
) -> None:
    """Tell the covering colleague: who is on leave, for how long, approved by whom."""
    if not getattr(request, "replacement_user_id", None):
        return
    total = float(request.total_days or 0)
    body = (
        f"{requester_name} is on {type_name} for {total:g} day(s) ({date_range}). "
        f"You will cover their work. Approved by {approver_name}."
    )
    rep_note = (getattr(request, "replacement_note", None) or "").strip()
    if rep_note:
        body += f" Note: {rep_note}"

    _push_to_users(
        db,
        [int(request.replacement_user_id)],
        title="You Are Assigned to Cover 👥",
        body=body,
        redirect_route=ROUTE_MY_LEAVE,
        request_id=int(request.id),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Entry points
# ═══════════════════════════════════════════════════════════════════════════


def notify_leave_request_created(request_id: int) -> None:
    db = SessionLocal()
    try:
        request, requester, leave_type = _load_request(db, request_id)
        if request is None or requester is None:
            return
        requester_name = _display_name(requester)
        type_name = str(leave_type.name) if leave_type else "Leave"
        total = float(request.total_days or 0)
        date_range = (
            _fmt_date(request.start_date)
            if request.start_date == request.end_date
            else f"{_fmt_date(request.start_date)} → {_fmt_date(request.end_date)}"
        )

        approval_days = total if request.status == "pending" else None
        approver_ids = [
            int(a.user_id)
            for a in _eligible_approvers(db, requester, approval_days)
            if int(a.user_id) != int(request.user_id)
        ]
        if request.status == "pending":
            _push_to_users(
                db,
                approver_ids,
                title="New Leave Request",
                body=f"{requester_name} asks {total:g} day(s) {type_name} · {date_range}",
                redirect_route=ROUTE_APPROVER_INBOX,
                request_id=int(request.id),
            )
        else:
            # Auto-approved type (requires_approval = false) → inform approvers.
            _push_to_users(
                db,
                approver_ids,
                title="Leave Auto-Approved",
                body=f"{requester_name} took {total:g} day(s) {type_name} · {date_range}",
                redirect_route=ROUTE_APPROVER_INBOX,
                request_id=int(request.id),
            )
            # No decision step will follow — tell the covering colleague now.
            _notify_replacement_assigned(
                db, request, requester_name, type_name, date_range, "auto-approval"
            )

        replacement = _replacement_user(db, request)
        settings = _telegram_settings(db)
        if settings is not None and bool(settings.notify_leave_requests):
            header = "📝 Leave Request" if request.status == "pending" else "📝 Leave (Auto-Approved)"
            rows = [
                f"Name: {_escape_html(requester_name)}",
                f"Type: {_escape_html(type_name)}",
                f"Days: {total:g}",
                _leave_dates_tree(request),
            ]
            if replacement is not None:
                rows.append(f"Replacement: {_escape_html(_display_name(replacement))}")
            _send_telegram(
                str(settings.bot_token),
                _leave_chat_id(settings, db, requester),
                _telegram_message(header, rows, footer=request.reason),
                action_url=_leave_request_link(int(request.id)),
            )
    except Exception as exc:
        logger.error(f"notify_leave_request_created({request_id}) failed: {exc}")
    finally:
        db.close()


def notify_leave_review_reminder(
    request_id: int,
    sent_by_id: int,
    recipient_ids: List[int],
) -> None:
    """Send a concise follow-up with a secure route to the exact request."""
    db = SessionLocal()
    try:
        request, requester, leave_type = _load_request(db, request_id)
        if (
            request is None
            or requester is None
            or str(request.status) != "pending"
        ):
            return
        sender = db.query(User).filter(User.id == sent_by_id).first()
        requester_name = _display_name(requester)
        sender_name = _display_name(sender)
        type_name = str(leave_type.name) if leave_type else "leave"
        total = float(request.total_days or 0)
        date_range = (
            _fmt_date(request.start_date)
            if request.start_date == request.end_date
            else f"{_fmt_date(request.start_date)}–{_fmt_date(request.end_date)}"
        )
        sent_by_requester = int(sent_by_id) == int(request.user_id)
        if sent_by_requester:
            title = "Pending Leave Request — Decision Needed"
            body = (
                f"{requester_name} has a pending {total:g}-day {type_name} "
                f"request ({date_range}) and is waiting for your "
                "decision. Tap to review and approve or reject."
            )
        else:
            title = "Leave Request Awaiting Your Decision"
            body = (
                f"{sender_name} is following up on {requester_name}'s "
                f"{total:g}-day {type_name} request ({date_range}). "
                "Tap to review and decide."
            )
        _push_to_users(
            db,
            recipient_ids,
            title=title,
            body=body,
            redirect_route=ROUTE_APPROVER_INBOX,
            request_id=int(request.id),
            notification_type="leave_request",
        )
    except Exception as exc:
        logger.error(
            f"notify_leave_review_reminder({request_id}) failed: {exc}"
        )
    finally:
        db.close()


def notify_manual_leave_created(request_ids: List[int], created_by_id: int) -> None:
    """Tell each employee that an approver recorded approved leave for them."""
    db = SessionLocal()
    try:
        creator = db.query(User).filter(User.id == created_by_id).first()
        creator_name = _display_name(creator)
        settings = _telegram_settings(db)
        for request_id in sorted({int(value) for value in request_ids if value}):
            request, requester, leave_type = _load_request(db, request_id)
            if request is None or requester is None:
                continue
            requester_name = _display_name(requester)
            type_name = str(leave_type.name) if leave_type else "Leave"
            total = float(request.total_days or 0)
            date_range = (
                _fmt_date(request.start_date)
                if request.start_date == request.end_date
                else f"{_fmt_date(request.start_date)} → {_fmt_date(request.end_date)}"
            )
            _push_to_users(
                db,
                [int(request.user_id)],
                title="Leave Recorded",
                body=(
                    f"{creator_name} recorded {total:g} day(s) {type_name} "
                    f"for you ({date_range}). Your leave balance was updated."
                ),
                redirect_route=ROUTE_MY_LEAVE,
                request_id=int(request.id),
            )
            if settings is not None and bool(settings.notify_leave_decisions):
                rows = [
                    f"Name: {_escape_html(requester_name)}",
                    f"Type: {_escape_html(type_name)}",
                    f"Days: {total:g}",
                    _leave_dates_tree(request),
                    f"Recorded by: {_escape_html(creator_name)}",
                ]
                _send_telegram(
                    str(settings.bot_token),
                    _leave_chat_id(settings, db, requester),
                    _telegram_message(
                        "✅ Manual Leave Recorded",
                        rows,
                        footer=request.reason,
                    ),
                    action_url=_leave_request_link(int(request.id)),
                )
    except Exception as exc:
        logger.error(f"notify_manual_leave_created({request_ids}) failed: {exc}")
    finally:
        db.close()


def notify_leave_balance_adjusted(
    adjustment_ids: List[int], created_by_id: int
) -> None:
    """Tell employees exactly why an allowance was reduced by policy."""
    db = SessionLocal()
    try:
        creator = db.query(User).filter(User.id == created_by_id).first()
        creator_name = _display_name(creator)
        settings = _telegram_settings(db)
        for adjustment_id in sorted({int(value) for value in adjustment_ids if value}):
            adjustment = (
                db.query(LeaveBalanceAdjustment)
                .filter(LeaveBalanceAdjustment.id == adjustment_id)
                .first()
            )
            if adjustment is None:
                continue
            target = db.query(User).filter(User.id == adjustment.user_id).first()
            leave_type = (
                db.query(LeaveType)
                .filter(LeaveType.id == adjustment.leave_type_id)
                .first()
            )
            if target is None:
                continue
            type_name = str(leave_type.name) if leave_type else "Leave"
            amount = float(adjustment.amount_days or 0)
            _push_to_users(
                db,
                [int(adjustment.user_id)],
                title="Leave Balance Updated",
                body=(
                    f"{amount:g} day(s) were deducted from your {type_name} "
                    f"allowance by {creator_name}. Reason: {adjustment.reason}"
                ),
                redirect_route=ROUTE_MY_LEAVE,
                request_id=int(adjustment.id),
                notification_type="leave_balance_adjustment",
                data_key="adjustment_id",
            )
            if settings is not None and bool(settings.notify_leave_decisions):
                _send_telegram(
                    str(settings.bot_token),
                    _leave_chat_id(settings, db, target),
                    _telegram_message(
                        "⚖️ Leave Balance Deducted",
                        [
                            f"Name: {_escape_html(_display_name(target))}",
                            f"Type: {_escape_html(type_name)}",
                            f"Days: {amount:g}",
                            f"Deducted by: {_escape_html(creator_name)}",
                        ],
                        footer=str(adjustment.reason or ""),
                    ),
                )
    except Exception as exc:
        logger.error(f"notify_leave_balance_adjusted({adjustment_ids}) failed: {exc}")
    finally:
        db.close()


def notify_leave_balance_adjustment_voided(
    adjustment_id: int, voided_by_id: int
) -> None:
    """Tell the employee when a policy deduction is reversed/restored."""
    db = SessionLocal()
    try:
        adjustment = (
            db.query(LeaveBalanceAdjustment)
            .filter(LeaveBalanceAdjustment.id == adjustment_id)
            .first()
        )
        if adjustment is None:
            return
        actor = db.query(User).filter(User.id == voided_by_id).first()
        leave_type = (
            db.query(LeaveType)
            .filter(LeaveType.id == adjustment.leave_type_id)
            .first()
        )
        type_name = str(leave_type.name) if leave_type else "Leave"
        amount = float(adjustment.amount_days or 0)
        _push_to_users(
            db,
            [int(adjustment.user_id)],
            title="Leave Balance Restored",
            body=(
                f"{amount:g} day(s) were restored to your {type_name} allowance "
                f"by {_display_name(actor)}. Reason: {adjustment.void_reason}"
            ),
            redirect_route=ROUTE_MY_LEAVE,
            request_id=int(adjustment.id),
            notification_type="leave_balance_adjustment",
            data_key="adjustment_id",
        )
    except Exception as exc:
        logger.error(
            f"notify_leave_balance_adjustment_voided({adjustment_id}) failed: {exc}"
        )
    finally:
        db.close()


def notify_leave_request_decided(request_id: int, decided_by_id: int) -> None:
    db = SessionLocal()
    try:
        request, requester, leave_type = _load_request(db, request_id)
        if request is None or requester is None:
            return
        decider = db.query(User).filter(User.id == decided_by_id).first()
        decider_name = _display_name(decider)
        requester_name = _display_name(requester)
        type_name = str(leave_type.name) if leave_type else "Leave"
        total = float(request.total_days or 0)
        approved = request.status == "approved"
        date_range = (
            _fmt_date(request.start_date)
            if request.start_date == request.end_date
            else f"{_fmt_date(request.start_date)} → {_fmt_date(request.end_date)}"
        )

        # 1) Requester
        if approved:
            body = f"Your {total:g} day(s) {type_name} ({date_range}) was approved by {decider_name}"
        else:
            note = (request.rejection_reason or "").strip()
            body = f"Your {total:g} day(s) {type_name} ({date_range}) was rejected by {decider_name}"
            if note:
                body += f" — {note}"
        _push_to_users(
            db,
            [int(request.user_id)],
            title="Leave Approved ✅" if approved else "Leave Rejected ❌",
            body=body,
            redirect_route=ROUTE_MY_LEAVE,
            request_id=int(request.id),
        )

        # 2) Other approvers — let them know it is already handled.
        other_ids = [
            int(a.user_id)
            for a in _eligible_approvers(db, requester, total)
            if int(a.user_id) not in (int(decided_by_id), int(request.user_id))
        ]
        _push_to_users(
            db,
            other_ids,
            title="Leave Request Handled",
            body=(
                f"{requester_name}'s {type_name} request was already "
                f"{'approved' if approved else 'rejected'} by {decider_name}"
            ),
            redirect_route=ROUTE_APPROVER_INBOX,
            request_id=int(request.id),
        )

        # 3) The covering colleague — only when the leave is actually approved.
        if approved:
            _notify_replacement_assigned(
                db, request, requester_name, type_name, date_range, decider_name
            )

        replacement = _replacement_user(db, request)
        settings = _telegram_settings(db)
        if settings is not None and bool(settings.notify_leave_decisions):
            header = "✅ Leave Approved" if approved else "❌ Leave Rejected"
            rows = [
                f"Name: {_escape_html(requester_name)}",
                f"Type: {_escape_html(type_name)}",
                f"Days: {total:g}",
                _leave_dates_tree(request),
                f"By: {_escape_html(decider_name)}",
            ]
            if approved and replacement is not None:
                rows.append(f"Replacement: {_escape_html(_display_name(replacement))}")
            _send_telegram(
                str(settings.bot_token),
                _leave_chat_id(settings, db, requester),
                _telegram_message(header, rows, footer=request.rejection_reason),
                action_url=_leave_request_link(int(request.id)),
            )
    except Exception as exc:
        logger.error(f"notify_leave_request_decided({request_id}) failed: {exc}")
    finally:
        db.close()


def notify_leave_request_cancelled(request_id: int, cancelled_by_id: int) -> None:
    db = SessionLocal()
    try:
        request, requester, leave_type = _load_request(db, request_id)
        if request is None or requester is None:
            return
        canceller = db.query(User).filter(User.id == cancelled_by_id).first()
        canceller_name = _display_name(canceller)
        requester_name = _display_name(requester)
        type_name = str(leave_type.name) if leave_type else "Leave"
        total = float(request.total_days or 0)
        cancelled_by_owner = int(cancelled_by_id) == int(request.user_id)

        # Approvers always hear about cancellations of pending/approved leave.
        approver_ids = [
            int(a.user_id)
            for a in _eligible_approvers(db, requester, total)
            if int(a.user_id) not in (int(cancelled_by_id), int(request.user_id))
        ]
        _push_to_users(
            db,
            approver_ids,
            title="Leave Request Cancelled",
            body=(
                f"{requester_name} cancelled their {total:g} day(s) {type_name} request"
                if cancelled_by_owner
                else f"{canceller_name} cancelled {requester_name}'s {total:g} day(s) {type_name} request"
            ),
            redirect_route=ROUTE_APPROVER_INBOX,
            request_id=int(request.id),
        )

        # If an approver/admin closed someone else's leave, tell the owner too.
        if not cancelled_by_owner:
            _push_to_users(
                db,
                [int(request.user_id)],
                title="Leave Cancelled",
                body=f"Your {total:g} day(s) {type_name} request was cancelled by {canceller_name}",
                redirect_route=ROUTE_MY_LEAVE,
                request_id=int(request.id),
            )

        # The covering colleague no longer needs to stand in.
        if getattr(request, "replacement_user_id", None) and int(
            request.replacement_user_id
        ) != int(cancelled_by_id):
            _push_to_users(
                db,
                [int(request.replacement_user_id)],
                title="Cover Assignment Cancelled",
                body=(
                    f"{requester_name}'s {total:g} day(s) {type_name} leave was cancelled — "
                    "you no longer need to cover their work."
                ),
                redirect_route=ROUTE_MY_LEAVE,
                request_id=int(request.id),
            )

        settings = _telegram_settings(db)
        if settings is not None and bool(settings.notify_leave_decisions):
            rows = [
                f"Name: {_escape_html(requester_name)}",
                f"Type: {_escape_html(type_name)}",
                f"Days: {total:g}",
                _leave_dates_tree(request),
                f"Cancelled by: {_escape_html(canceller_name)}",
            ]
            _send_telegram(
                str(settings.bot_token),
                _leave_chat_id(settings, db, requester),
                _telegram_message(
                    "🚫 Leave Request Cancelled",
                    rows,
                    footer=request.cancel_reason,
                ),
                action_url=_leave_request_link(int(request.id)),
            )
    except Exception as exc:
        logger.error(f"notify_leave_request_cancelled({request_id}) failed: {exc}")
    finally:
        db.close()
