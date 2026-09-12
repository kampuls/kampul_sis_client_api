"""
Messages API endpoints for group messaging system.
"""

import logging
from datetime import datetime
import json
import os
import uuid

from fastapi import APIRouter, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect, UploadFile, File
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError
from sqlalchemy import bindparam, text, func, or_
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, cast, Any

from ...core import get_db, settings
from ...schemas import (
    MessageGroupResponse, MessageGroupCreate, MessageGroupMemberResponse,
    MessageResponse, MessageCreate, AutoCreateClassGroupsRequest
)
from ...models import MessageGroup, MessageGroupMember, GroupMessage, User, UserResource, Parent
from ...models.message import UserType
from ...auth.dependencies import (
    PARENT_MEMBER_TYPES,
    STAFF_MEMBER_TYPES,
    STUDENT_MEMBER_TYPES,
    Principal,
    get_current_active_user,
    get_current_principal,
    principal_from_user,
    require_admin,
)
from .market import MARKET_CONVERSATION_TAG
from ...services.notification_service import (
    get_message_group_member_tokens,
    send_notification,
    send_notification_async,
)
from ...services.storage_service import StorageService
from ...services.ws_pubsub import register_handler, publish as _ws_publish
from .websocket import broadcast_to_user
import asyncio

# NOTE: Do NOT cache os.getpid() as _MY_PID at module level.
# With Gunicorn --preload, this runs in the MASTER — all workers would share
# the master's PID. Use os.getpid() inline (called after fork = correct PID).


router = APIRouter()

# WebSocket close code (private-use range): client should not auto-reconnect.
WS_CLOSE_UNAUTHORIZED = 4401


class ConnectionManager:
    """
    Chat group WebSocket manager — fully cross-worker safe.
    - Local connections are served instantly in-memory.
    - Cross-worker delivery goes through ws_broadcast_queue DB pub/sub (~500ms).
    - Registers itself with the shared pub/sub handler registry on __init__.
    """

    def __init__(self):
        # group_id → List[WebSocket]  (local to this worker only)
        self.active_connections: Dict[int, List[WebSocket]] = {}
        # id(websocket) → authenticated user id (typing and other client events)
        self._ws_user_id: Dict[int, int] = {}
        # Auto-register our dispatch handler with the shared pub/sub poll loop
        register_handler(self._dispatch)

    async def connect(self, websocket: WebSocket, group_id: int, user_id: int):
        await websocket.accept()
        await self.attach(websocket, group_id, user_id)

    async def attach(self, websocket: WebSocket, group_id: int, user_id: int):
        """Register an already-accepted WebSocket to this group (after auth)."""
        self._ws_user_id[id(websocket)] = int(user_id)
        if group_id not in self.active_connections:
            self.active_connections[group_id] = []
        self.active_connections[group_id].append(websocket)

    def user_id_for(self, websocket: WebSocket) -> Optional[int]:
        return self._ws_user_id.get(id(websocket))

    def disconnect(self, websocket: WebSocket, group_id: int):
        self._ws_user_id.pop(id(websocket), None)
        if group_id in self.active_connections:
            if websocket in self.active_connections[group_id]:
                self.active_connections[group_id].remove(websocket)
            if not self.active_connections[group_id]:
                del self.active_connections[group_id]

    async def broadcast(self, message: dict, group_id: int):
        """
        Broadcast to a group across ALL workers.
        1. Instantly deliver to this worker's local connections.
        2. Publish to DB queue so other workers deliver to their connections.
        """
        await self._local_broadcast(message, group_id)
        stamped = {**message, "_origin_pid": os.getpid()}
        await _ws_publish(f"group:{group_id}", stamped)

    async def _local_broadcast(self, message: dict, group_id: int):
        """Deliver to WebSocket connections in this group on THIS worker only."""
        if group_id not in self.active_connections:
            return
        for connection in list(self.active_connections[group_id]):
            try:
                await connection.send_json(message)
            except Exception:
                pass

    async def _dispatch(self, channel: str, payload: dict):
        """Called by the pub/sub poll loop. Routes group:{id} messages only."""
        if not channel.startswith("group:"):
            return
        if payload.get("_origin_pid") == os.getpid():  # Skip own-origin (already delivered)
            return
        try:
            group_id = int(channel.split(":", 1)[1])
        except (ValueError, IndexError):
            return
        clean = {k: v for k, v in payload.items() if k != "_origin_pid"}
        await self._local_broadcast(clean, group_id)


manager = ConnectionManager()

_LOG = logging.getLogger(__name__)


def _read_by_json_for_new_message(sender_id: int) -> str:
    """Sender is implicitly 'read' for their own message (fixes unread SQL counting self-sent)."""
    return json.dumps([int(sender_id)])


def _membership_of(
    db: Session, group_id: int, principal: Principal
) -> Optional[MessageGroupMember]:
    """Look up the caller's membership row in a group.

    ``message_group_members.user_id`` points into ``users``, ``parents`` or
    ``students`` depending on ``user_type``. Matching on the ID alone would let
    parent #57 read every group employee #57 belongs to, so the owning table is
    always part of the lookup.
    """
    return (
        db.query(MessageGroupMember)
        .filter(
            MessageGroupMember.group_id == group_id,
            MessageGroupMember.user_id == principal.id,
            MessageGroupMember.user_type.in_(principal.member_types),
        )
        .first()
    )


def _require_membership(
    db: Session, group_id: int, principal: Principal
) -> MessageGroupMember:
    """Same as :func:`_membership_of` but 403s when the caller is not a member."""
    membership = _membership_of(db, group_id, principal)
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group")
    return membership


def _distinct_member_user_ids(db: Session, group_id: int) -> List[int]:
    """One inbox broadcast per user (avoids duplicate rows inflating unread deltas)."""
    rows = (
        db.query(MessageGroupMember.user_id)
        .filter(MessageGroupMember.group_id == group_id)
        .distinct()
        .all()
    )
    return [int(r[0]) for r in rows]


def _coerce_setting_bool(val: Any, default: bool) -> bool:
    """Normalize DB 0/1, strings, or bools for group settings checks."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    try:
        return int(val) != 0
    except (TypeError, ValueError):
        return default


def _member_is_group_admin(membership: MessageGroupMember) -> bool:
    r = getattr(membership, "role", None)
    if r is None:
        return False
    if isinstance(r, str):
        return r.strip().lower() == "admin"
    val = getattr(r, "value", r)
    if isinstance(val, str):
        return val.strip().lower() == "admin"
    return False


def _assert_group_post_allowed(
    db: Session,
    group_id: int,
    principal: Principal,
    membership: MessageGroupMember,
    message_type: str,
) -> None:
    """
    Enforce MessageGroupBan + MessageGroupSettings for every path that creates
    a group message (JSON send, image upload, batch, voice).
    """
    from ...models import MessageGroupBan, MessageGroupSettings

    # Bans are keyed the same way as membership: the ID only means something
    # together with the table it came from.
    active_ban = (
        db.query(MessageGroupBan)
        .filter(
            MessageGroupBan.group_id == group_id,
            MessageGroupBan.user_id == principal.id,
            MessageGroupBan.user_type.in_(principal.member_types),
            MessageGroupBan.is_active == 1,
        )
        .first()
    )
    if active_ban:
        expires_at = getattr(active_ban, "expires_at", None)
        if expires_at is not None and expires_at < datetime.utcnow():
            setattr(active_ban, "is_active", 0)
            db.commit()
        else:
            raise HTTPException(
                status_code=403,
                detail="You are banned from posting in this group",
            )

    settings = (
        db.query(MessageGroupSettings)
        .filter(MessageGroupSettings.group_id == group_id)
        .first()
    )
    if not settings:
        return

    mt = (message_type or "text").strip().lower()

    only_admins = _coerce_setting_bool(
        getattr(settings, "only_admins_can_post", 0), False
    )
    if only_admins and not _member_is_group_admin(membership):
        raise HTTPException(
            status_code=403, detail="Only admins can post in this group"
        )

    can_text = _coerce_setting_bool(getattr(settings, "can_send_text", 1), True)
    can_files = _coerce_setting_bool(getattr(settings, "can_send_files", 1), True)
    can_images = _coerce_setting_bool(getattr(settings, "can_send_images", 1), True)
    can_voice = _coerce_setting_bool(getattr(settings, "can_send_voice", 1), True)

    if mt in ("text", "announcement") and not can_text:
        raise HTTPException(
            status_code=403, detail="Text messages are disabled in this group"
        )
    if mt == "file" and not can_files:
        raise HTTPException(
            status_code=403, detail="File uploads are disabled in this group"
        )
    if mt in ("image", "image_batch") and not can_images:
        raise HTTPException(
            status_code=403, detail="Images are disabled in this group"
        )
    if mt in ("voice", "audio") and not can_voice:
        raise HTTPException(
            status_code=403, detail="Voice messages are disabled in this group"
        )


def _group_unread_counts_for_members(db: Session, group_id: int) -> Dict[int, int]:
    """
    Per-member unread counts for one group (same rules as GET /groups unread subquery).
    Used so inbox WebSocket payloads can set an absolute badge — avoids client +inc stacking
    when multiple duplicate events arrive.
    """
    q = text("""
        SELECT mgm.user_id AS uid,
        (
            SELECT COUNT(*)
            FROM messages m
            WHERE m.group_id = :gid
            AND m.sender_id != mgm.user_id
            AND (m.read_by = '[]' OR m.read_by NOT LIKE CONCAT('%', mgm.user_id, '%'))
            AND m.deleted_at IS NULL
        ) AS unread_n
        FROM message_group_members mgm
        WHERE mgm.group_id = :gid
        GROUP BY mgm.user_id
    """)
    rows = db.execute(q, {"gid": group_id}).fetchall()
    out: Dict[int, int] = {}
    for row in rows:
        m = getattr(row, "_mapping", None)
        if m is not None:
            uid = int(m["uid"])
            n = m["unread_n"]
        else:
            uid = int(row[0])
            n = row[1]
        out[uid] = int(n or 0)
    return out


def _resolve_ws_principal(db: Session, token: Optional[str]) -> Optional[Principal]:
    """
    Validate JWT (same rules as HTTP) and return the caller, or None.
    Parents use parent id; staff use users.id — the two must never be conflated.
    """
    if not token or not str(token).strip():
        return None
    try:
        payload = jwt.decode(
            str(token).strip(),
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        user_id = payload.get("user_id")
        role = payload.get("role")
        token_version = payload.get("token_version")
        username = payload.get("sub")

        if role == "parent":
            parent = None
            if user_id is not None:
                parent = db.query(Parent).filter(Parent.id == user_id).first()
            elif username is not None:
                parent = db.query(Parent).filter(Parent.username == username).first()
            if parent is None:
                return None
            return Principal(int(parent.id), "parent", PARENT_MEMBER_TYPES)

        if role == "student":
            from ...models import Student

            student = None
            if user_id is not None:
                student = db.query(Student).filter(Student.id == user_id).first()
            elif username is not None:
                student = db.query(Student).filter(Student.username == username).first()
            if student is None:
                return None
            return Principal(int(student.id), "student", STUDENT_MEMBER_TYPES)

        # Only employee tokens may be resolved against ``users``. Without this
        # an unknown role would fall through and adopt the employee sharing its ID.
        numeric_employee_role = isinstance(role, int) or (
            isinstance(role, str) and role.isdigit()
        )
        if role not in (None, "teacher", "employee", "admin") and not numeric_employee_role:
            return None

        if user_id is not None:
            user = db.query(User).filter(User.id == user_id).first()
            if user is None:
                return None
            if int(getattr(user, "status", 0) or 0) != 1:
                return None
            db_version = getattr(user, "token_version", 1) or 1
            if token_version is not None:
                if int(token_version) != int(db_version):
                    return None
            else:
                if int(db_version) > 1:
                    return None
            return Principal(int(user_id), "teacher", STAFF_MEMBER_TYPES)

        if username is not None:
            user = db.query(User).filter(User.username == username).first()
            if user is None:
                return None
            if int(getattr(user, "status", 0) or 0) != 1:
                return None
            return Principal(int(user.id), "teacher", STAFF_MEMBER_TYPES)

        return None
    except JWTError:
        return None


def _inbox_preview_text(content: Optional[str], message_type: Optional[str]) -> str:
    if content is None:
        content = ""
    mt = (message_type or "").strip().lower()
    if mt == "image_batch":
        try:
            arr = json.loads(content)
            if isinstance(arr, list):
                n = len(arr)
                return f"{n} photos" if n != 1 else "1 photo"
        except (json.JSONDecodeError, TypeError):
            pass
        return "Photos"
    return content


def _fetch_inbox_preview_row(db: Session, group_id: int) -> Dict[str, Any]:
    """Last visible message row for inbox list (matches get_user_groups semantics)."""
    q = text("""
        SELECT
            msg.content,
            msg.message_type,
            msg.created_at,
            ur.avatar AS sender_image,
            CASE
                WHEN mgm.user_type = 'teacher' OR mgm.user_type = 'employee' OR mgm.id IS NULL
                    THEN COALESCE(NULLIF(TRIM(u.username), ''), NULLIF(TRIM(u.eName), ''), NULLIF(TRIM(u.kName), ''))
                WHEN mgm.user_type = 'parent'
                    THEN COALESCE(NULLIF(TRIM(p.username), ''), NULLIF(TRIM(p.motherName), ''), NULLIF(TRIM(p.fatherName), ''))
                ELSE COALESCE(NULLIF(TRIM(u.username), ''), NULLIF(TRIM(u.eName), ''), NULLIF(TRIM(u.kName), ''))
            END AS sender_name,
            CASE
                WHEN mgm.user_type IN ('teacher', 'employee') OR mgm.id IS NULL THEN u.gender
                ELSE NULL
            END AS sender_gender
        FROM messages msg
        LEFT JOIN message_group_members mgm ON msg.group_id = mgm.group_id AND msg.sender_id = mgm.user_id
        LEFT JOIN users u ON (mgm.user_type IN ('teacher', 'employee') AND msg.sender_id = u.id) OR (mgm.id IS NULL AND msg.sender_id = u.id)
        LEFT JOIN parents p ON (mgm.user_type = 'parent' AND msg.sender_id = p.id)
        LEFT JOIN users_resource ur ON msg.sender_id = ur.user_id
            AND (ur.user_type = mgm.user_type OR (mgm.id IS NULL AND ur.user_type IN ('teacher', 'employee')))
        WHERE msg.group_id = :gid AND msg.deleted_at IS NULL
        ORDER BY msg.created_at DESC
        LIMIT 1
    """)
    row = db.execute(q, {"gid": group_id}).first()
    if not row:
        now = datetime.utcnow()
        return {
            "last_message": "",
            "last_message_time": now.isoformat(),
            "sender_name": None,
            "sender_image": None,
            "sender_gender": None,
            "message_type": "text",
        }
    preview = _inbox_preview_text(getattr(row, "content", None), getattr(row, "message_type", None))
    t = getattr(row, "created_at", None)
    return {
        "last_message": preview,
        "last_message_time": t.isoformat() if t else "",
        "sender_name": getattr(row, "sender_name", None),
        "sender_image": getattr(row, "sender_image", None),
        "sender_gender": getattr(row, "sender_gender", None),
        "message_type": getattr(row, "message_type", None) or "text",
    }


def schedule_inbox_preview_broadcast_for_group(db: Session, group_id: int) -> None:
    """Notify all members' global sockets so inbox preview matches server (e.g. after last msg deleted)."""
    try:
        preview = _fetch_inbox_preview_row(db, group_id)
        unread_map = _group_unread_counts_for_members(db, group_id)
        for uid in _distinct_member_user_ids(db, group_id):
            payload = {
                "group_id": group_id,
                "last_message": preview["last_message"],
                "last_message_time": preview["last_message_time"],
                "sender_name": preview["sender_name"],
                "sender_image": preview["sender_image"],
                "sender_gender": preview["sender_gender"],
                "message_type": preview["message_type"],
                "unread_count_inc": 0,
                "group_unread_count": unread_map.get(uid, 0),
            }
            asyncio.create_task(
                broadcast_to_user(uid, {"type": "inbox_updated", "payload": payload})
            )
    except Exception as e:
        _LOG.error("Error scheduling inbox preview broadcast for group %s: %s", group_id, e)


def schedule_inbox_sync_for_reader(db: Session, group_id: int, user_id: int) -> None:
    """
    Notify the reader's global WebSocket with fresh preview + group_unread_count.
    Without this, mark-read updates the DB but inbox list / bottom-nav badges stay stale until poll.
    """
    try:
        preview = _fetch_inbox_preview_row(db, group_id)
        unread_map = _group_unread_counts_for_members(db, group_id)
        uid = int(user_id)
        payload = {
            "group_id": group_id,
            "last_message": preview["last_message"],
            "last_message_time": preview["last_message_time"],
            "sender_name": preview["sender_name"],
            "sender_image": preview["sender_image"],
            "sender_gender": preview["sender_gender"],
            "message_type": preview["message_type"],
            "unread_count_inc": 0,
            "group_unread_count": unread_map.get(uid, 0),
        }
        asyncio.create_task(
            broadcast_to_user(uid, {"type": "inbox_updated", "payload": payload})
        )
    except Exception as e:
        _LOG.error(
            "Error scheduling inbox sync after read for user %s group %s: %s",
            user_id,
            group_id,
            e,
        )


async def broadcast_group_ws(group_id: int, payload: dict) -> None:
    """Broadcast a JSON payload to all WebSocket clients in this chat group."""
    await manager.broadcast(payload, group_id)


@router.websocket("/ws/{group_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    group_id: int,
    db: Session = Depends(get_db),
):
    token = websocket.query_params.get("token")
    await websocket.accept()
    principal = _resolve_ws_principal(db, token)
    if principal is None:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED, reason="Unauthorized")
        return
    user_id = principal.id
    membership = _membership_of(db, group_id, principal)
    if not membership:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED, reason="Forbidden")
        return

    await manager.attach(websocket, group_id, user_id)
    try:
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    message_data = json.loads(data)
                    if message_data.get("type") == "typing":
                        auth_uid = manager.user_id_for(websocket)
                        if auth_uid is None:
                            continue
                        # Never trust client-supplied userId (spoofing).
                        stamped = {**message_data, "userId": auth_uid}
                        await manager.broadcast(stamped, group_id)
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            pass
    finally:
        manager.disconnect(websocket, group_id)






@router.get("/unread-total")
async def get_total_unread_count(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Get total unread messages count across all school groups (excludes market DMs)."""
    current_user_id = principal.id
    query = text("""
        SELECT COUNT(m.id) as total_unread
        FROM messages m
        JOIN message_group_members mgm ON m.group_id = mgm.group_id
        JOIN message_groups g ON g.id = m.group_id
        WHERE mgm.user_id = :user_id
        AND mgm.user_type IN :member_types
        AND (g.description IS NULL OR g.description != :market_tag)
        AND m.sender_id != :user_id
        AND (m.read_by = '[]' OR m.read_by NOT LIKE :user_pattern)
        AND m.deleted_at IS NULL
    """).bindparams(bindparam("member_types", expanding=True))

    result = db.execute(query, {
        "user_id": current_user_id,
        "member_types": list(principal.member_types),
        "user_pattern": f'%{current_user_id}%',
        "market_tag": MARKET_CONVERSATION_TAG,
    }).first()

    return {"count": result.total_unread if result else 0}


@router.get("/groups", response_model=List[MessageGroupResponse])
async def get_user_groups(
    limit: int = Query(100, ge=1, le=1000),  # Compromise: default 100, max 1000 for Flutter compatibility
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """
    Get all message groups.
    - Admins see ALL groups
    - Non-admins see only groups they're a member of
    Includes member count and unread message count (if applicable).
    """
    current_user_id = principal.id
    # Check if user has admin permissions (AdminViewApp, AdminUpdateApp, or AdminDeleteApp).
    # Only staff IDs index into ``users`` — running this for a parent would grant
    # them the permissions of the employee who happens to share their ID.
    is_admin = False
    if principal.kind == "teacher":
        admin_perms_query = text("""
            SELECT COUNT(*) as perm_count
            FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            JOIN users u ON u.role = rp.role_id
            WHERE u.id = :user_id
            AND p.permission_name IN ('AdminViewApp', 'AdminUpdateApp', 'AdminDeleteApp')
        """)
        perm_result = db.execute(admin_perms_query, {"user_id": current_user_id}).first()
        is_admin = bool(perm_result and perm_result.perm_count > 0)

    if is_admin:
        # Admin: Show ALL groups with joined details AND unread count in one query
        query = text("""
            SELECT 
                g.id, g.name, g.type, g.academic_year_id, g.grade_id,
                g.grade_type_id, g.program_id, g.branch_id,
                g.description, g.group_image, g.created_by, g.created_at, g.updated_at,
                COUNT(DISTINCT m.user_id) as member_count,
                COALESCE(p.short_code, p.program_name) as program_name,
                b.branch_name,
                gt.type_name as grade_type_name,
                (
                    SELECT COUNT(*) 
                    FROM messages msg 
                    WHERE msg.group_id = g.id 
                    AND msg.sender_id != :viewer_id
                    AND (msg.read_by = '[]' OR msg.read_by NOT LIKE :user_pattern)
                    AND msg.deleted_at IS NULL
                ) as unread_count,
                (
                    SELECT content 
                    FROM messages msg 
                    WHERE msg.group_id = g.id AND msg.deleted_at IS NULL
                    ORDER BY created_at DESC LIMIT 1
                ) as last_message,
                (
                    SELECT created_at 
                    FROM messages msg 
                    WHERE msg.group_id = g.id AND msg.deleted_at IS NULL
                    ORDER BY created_at DESC LIMIT 1
                ) as last_message_time,
                (
                    SELECT ur.avatar
                    FROM messages msg 
                    LEFT JOIN message_group_members mgm ON msg.group_id = mgm.group_id AND msg.sender_id = mgm.user_id
                    LEFT JOIN users_resource ur ON msg.sender_id = ur.user_id AND (ur.user_type = mgm.user_type OR (mgm.id IS NULL AND ur.user_type IN ('teacher', 'employee')))
                    WHERE msg.group_id = g.id AND msg.deleted_at IS NULL
                    ORDER BY msg.created_at DESC LIMIT 1
                ) as last_message_sender_image,
                (
                    SELECT 
                        CASE 
                            WHEN mgm.user_type = 'teacher' OR mgm.user_type = 'employee' OR mgm.id IS NULL THEN COALESCE(NULLIF(TRIM(u.username), ''), NULLIF(TRIM(u.eName), ''), NULLIF(TRIM(u.kName), ''))
                            WHEN mgm.user_type = 'parent' THEN COALESCE(NULLIF(TRIM(p.username), ''), NULLIF(TRIM(p.motherName), ''), NULLIF(TRIM(p.fatherName), ''))
                            ELSE COALESCE(NULLIF(TRIM(u.username), ''), NULLIF(TRIM(u.eName), ''), NULLIF(TRIM(u.kName), ''))
                        END
                    FROM messages msg
                    LEFT JOIN message_group_members mgm ON msg.group_id = mgm.group_id AND msg.sender_id = mgm.user_id
                    LEFT JOIN users u ON (mgm.user_type IN ('teacher', 'employee') AND msg.sender_id = u.id) OR (mgm.id IS NULL AND msg.sender_id = u.id)
                    LEFT JOIN parents p ON (mgm.user_type = 'parent' AND msg.sender_id = p.id)
                    WHERE msg.group_id = g.id AND msg.deleted_at IS NULL
                    ORDER BY msg.created_at DESC LIMIT 1
                ) as last_message_sender_name,
                (
                    SELECT 
                        CASE 
                            WHEN mgm.user_type = 'teacher' OR mgm.user_type = 'employee' OR mgm.id IS NULL THEN u.gender
                            ELSE NULL
                        END
                    FROM messages msg
                    LEFT JOIN message_group_members mgm ON msg.group_id = mgm.group_id AND msg.sender_id = mgm.user_id
                    LEFT JOIN users u ON (mgm.user_type IN ('teacher', 'employee') AND msg.sender_id = u.id) OR (mgm.id IS NULL AND msg.sender_id = u.id)
                    WHERE msg.group_id = g.id AND msg.deleted_at IS NULL
                    ORDER BY msg.created_at DESC LIMIT 1
                ) as last_message_sender_gender
            FROM message_groups g
            LEFT JOIN message_group_members m ON g.id = m.group_id
            LEFT JOIN program p ON g.program_id = p.id
            LEFT JOIN branch b ON g.branch_id = b.id
            LEFT JOIN grade_type gt ON g.grade_type_id = gt.id
            WHERE (g.description IS NULL OR g.description != :market_tag)
            GROUP BY g.id, p.short_code, p.program_name, b.branch_name, gt.type_name
            ORDER BY g.updated_at DESC, g.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        result = db.execute(query, {
            "user_pattern": f'%{current_user_id}%',
            "viewer_id": current_user_id,
            "limit": limit,
            "offset": offset,
            "market_tag": MARKET_CONVERSATION_TAG,
        })
    else:
        # Non-admin: Show only groups where user is a member with joined details AND unread count
        query = text("""
            SELECT 
                g.id, g.name, g.type, g.academic_year_id, g.grade_id,
                g.grade_type_id, g.program_id, g.branch_id,
                g.description, g.group_image, g.created_by, g.created_at, g.updated_at,
                COUNT(DISTINCT m.user_id) as member_count,
                COALESCE(p.short_code, p.program_name) as program_name,
                b.branch_name,
                gt.type_name as grade_type_name,
                (
                    SELECT COUNT(*) 
                    FROM messages msg 
                    WHERE msg.group_id = g.id 
                    AND msg.sender_id != :user_id
                    AND (msg.read_by = '[]' OR msg.read_by NOT LIKE :user_pattern)
                    AND msg.deleted_at IS NULL
                ) as unread_count,
                (
                    SELECT content 
                    FROM messages msg 
                    WHERE msg.group_id = g.id AND msg.deleted_at IS NULL
                    ORDER BY created_at DESC LIMIT 1
                ) as last_message,
                (
                    SELECT created_at 
                    FROM messages msg 
                    WHERE msg.group_id = g.id AND msg.deleted_at IS NULL
                    ORDER BY created_at DESC LIMIT 1
                ) as last_message_time,
                (
                    SELECT ur.avatar
                    FROM messages msg 
                    LEFT JOIN message_group_members mgm ON msg.group_id = mgm.group_id AND msg.sender_id = mgm.user_id
                    LEFT JOIN users_resource ur ON msg.sender_id = ur.user_id AND (ur.user_type = mgm.user_type OR (mgm.id IS NULL AND ur.user_type IN ('teacher', 'employee')))
                    WHERE msg.group_id = g.id AND msg.deleted_at IS NULL
                    ORDER BY msg.created_at DESC LIMIT 1
                ) as last_message_sender_image,
                (
                    SELECT 
                        CASE 
                            WHEN mgm.user_type = 'teacher' OR mgm.user_type = 'employee' OR mgm.id IS NULL THEN COALESCE(NULLIF(TRIM(u.username), ''), NULLIF(TRIM(u.eName), ''), NULLIF(TRIM(u.kName), ''))
                            WHEN mgm.user_type = 'parent' THEN COALESCE(NULLIF(TRIM(p.username), ''), NULLIF(TRIM(p.motherName), ''), NULLIF(TRIM(p.fatherName), ''))
                            ELSE COALESCE(NULLIF(TRIM(u.username), ''), NULLIF(TRIM(u.eName), ''), NULLIF(TRIM(u.kName), ''))
                        END
                    FROM messages msg
                    LEFT JOIN message_group_members mgm ON msg.group_id = mgm.group_id AND msg.sender_id = mgm.user_id
                    LEFT JOIN users u ON (mgm.user_type IN ('teacher', 'employee') AND msg.sender_id = u.id) OR (mgm.id IS NULL AND msg.sender_id = u.id)
                    LEFT JOIN parents p ON (mgm.user_type = 'parent' AND msg.sender_id = p.id)
                    WHERE msg.group_id = g.id AND msg.deleted_at IS NULL
                    ORDER BY msg.created_at DESC LIMIT 1
                ) as last_message_sender_name,
                (
                    SELECT 
                        CASE 
                            WHEN mgm.user_type = 'teacher' OR mgm.user_type = 'employee' OR mgm.id IS NULL THEN u.gender
                            ELSE NULL
                        END
                    FROM messages msg
                    LEFT JOIN message_group_members mgm ON msg.group_id = mgm.group_id AND msg.sender_id = mgm.user_id
                    LEFT JOIN users u ON (mgm.user_type IN ('teacher', 'employee') AND msg.sender_id = u.id) OR (mgm.id IS NULL AND msg.sender_id = u.id)
                    WHERE msg.group_id = g.id AND msg.deleted_at IS NULL
                    ORDER BY msg.created_at DESC LIMIT 1
                ) as last_message_sender_gender
            FROM message_groups g
            INNER JOIN message_group_members mgm ON g.id = mgm.group_id
            LEFT JOIN message_group_members m ON g.id = m.group_id
            LEFT JOIN program p ON g.program_id = p.id
            LEFT JOIN branch b ON g.branch_id = b.id
            LEFT JOIN grade_type gt ON g.grade_type_id = gt.id
            WHERE mgm.user_id = :user_id
            AND mgm.user_type IN :member_types
            AND (g.description IS NULL OR g.description != :market_tag)
            GROUP BY g.id, p.short_code, p.program_name, b.branch_name, gt.type_name
            ORDER BY g.updated_at DESC, g.created_at DESC
            LIMIT :limit OFFSET :offset
        """).bindparams(bindparam("member_types", expanding=True))
        result = db.execute(query, {
            "user_id": current_user_id,
            "member_types": list(principal.member_types),
            "user_pattern": f'%{current_user_id}%',
            "limit": limit,
            "offset": offset,
            "market_tag": MARKET_CONVERSATION_TAG,
        })
    groups = []
    
    for row in result:
        groups.append(MessageGroupResponse(
            id=row.id,
            name=row.name,
            type=row.type,
            academic_year_id=row.academic_year_id,
            grade_id=row.grade_id,
            grade_type_id=getattr(row, 'grade_type_id', None),
            program_id=getattr(row, 'program_id', None),
            branch_id=getattr(row, 'branch_id', None),
            description=row.description,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
            member_count=row.member_count,
            unread_count=row.unread_count,  # Already calculated in SQL
            last_message=getattr(row, 'last_message', None),
            last_message_time=getattr(row, 'last_message_time', None),
            last_message_sender_image=getattr(row, 'last_message_sender_image', None),
            last_message_sender_name=getattr(row, 'last_message_sender_name', None),
            program_name=row.program_name,
            branch_name=row.branch_name,
            grade_type_name=row.grade_type_name,
            group_image=getattr(row, 'group_image', None)
        ))
    
    return groups


@router.get("/groups/{group_id}", response_model=MessageGroupResponse)
async def get_group_details(
    group_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Get details of a specific group."""
    current_user_id = principal.id
    # Check if user is a member
    _require_membership(db, group_id, principal)

    group = db.query(MessageGroup).filter(MessageGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Count members
    member_count = db.query(func.count(MessageGroupMember.id)).filter(
        MessageGroupMember.group_id == group_id
    ).scalar()
    
    return MessageGroupResponse(
        id=cast(int, group.id),
        name=cast(str, group.name),
        type=cast(Any, group.type),
        academic_year_id=cast(Optional[int], group.academic_year_id),
        grade_id=cast(Optional[int], group.grade_id),
        description=cast(Optional[str], group.description),
        created_by=cast(int, group.created_by),
        created_at=cast(datetime, group.created_at),
        updated_at=cast(Optional[datetime], group.updated_at),
        member_count=member_count or 0,
        group_image=cast(Optional[str], group.group_image)
    )


@router.post("/groups/{group_id}/image")
async def upload_group_image(
    group_id: int,
    file: UploadFile = File(...),
    current_user: Any = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload or replace a group's cover image. Admin-only."""
    principal = principal_from_user(current_user)
    current_user_id = principal.id

    # Only admins (group or system) can change the image
    membership = _membership_of(db, group_id, principal)
    if not membership or membership.role.lower() != 'admin':
        # Allow system admins too — but only staff IDs index into ``users``.
        perm = None
        if principal.kind == "teacher":
            perm = db.execute(text("""
                SELECT COUNT(*) as c FROM role_permissions rp
                JOIN permissions p ON rp.permission_id = p.id
                JOIN users u ON u.role = rp.role_id
                WHERE u.id = :uid AND p.permission_name IN ('AdminUpdateApp')
            """), {"uid": current_user_id}).first()
        if not perm or perm.c == 0:
            raise HTTPException(status_code=403, detail="Only group admins can change the group image")

    ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/jpg", "application/octet-stream"}
    if file.content_type and file.content_type not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Invalid image type: {file.content_type}")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")

    ext = os.path.splitext(file.filename or "image.jpg")[1] or ".jpg"
    filename = f"group_{group_id}_{uuid.uuid4().hex[:8]}{ext}"

    group = db.query(MessageGroup).filter(MessageGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    old_image_url = getattr(group, "group_image", None)

    image_url = StorageService.upload_file(
        file_data=contents,
        folder="groups",
        filename=filename,
        content_type=file.content_type
    )
    if not image_url:
        raise HTTPException(status_code=500, detail="Failed to upload image")

    if old_image_url:
        from ...models.settings import SystemSettings
        sys_settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
        if sys_settings:
            try:
                StorageService.delete_file(old_image_url, sys_settings)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to delete old group image {old_image_url}: {e}")

    setattr(group, "group_image", image_url)
    setattr(group, "updated_at", datetime.utcnow())
    db.commit()

    return {"group_image": image_url}


@router.post("/groups/{group_id}/messages/upload", response_model=MessageResponse)
async def send_image_message(
    group_id: int,
    file: UploadFile = File(...),
    current_user: Any = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload an image and send it as a message in a group."""
    principal = principal_from_user(current_user)
    current_user_id = principal.id

    membership = _require_membership(db, group_id, principal)

    _assert_group_post_allowed(db, group_id, principal, membership, "image")

    ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/jpg", "application/octet-stream"}
    if file.content_type and file.content_type not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Invalid image type: {file.content_type}")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    ext = os.path.splitext(file.filename or "photo.jpg")[1] or ".jpg"
    filename = f"msg_{group_id}_{uuid.uuid4().hex[:10]}{ext}"

    image_url = StorageService.upload_file(
        file_data=contents,
        folder="messages",
        filename=filename,
        content_type=file.content_type
    )
    if not image_url:
        raise HTTPException(status_code=500, detail="Failed to upload image")

    new_message = GroupMessage(
        group_id=group_id,
        sender_id=current_user_id,
        content=image_url,
        message_type="image",
        read_by=_read_by_json_for_new_message(current_user_id),
        is_hidden=0
    )
    db.add(new_message)
    group = db.query(MessageGroup).filter(MessageGroup.id == group_id).first()
    if group:
        setattr(group, "updated_at", datetime.utcnow())
    db.commit()
    db.refresh(new_message)

    # Sender type comes from the caller's own membership row, already fetched
    # above. Re-reading it by ID alone would label a parent as the employee who
    # shares their ID.
    user_type = membership.user_type or principal.kind
    ur = db.query(UserResource).filter(
        UserResource.user_id == current_user_id,
        UserResource.user_type == user_type
    ).first()
    # Fallback: try employee type if teacher type returns no result
    if not ur and user_type == 'teacher':
        ur = db.query(UserResource).filter(
            UserResource.user_id == current_user_id,
            UserResource.user_type == 'employee'
        ).first()
    sender_image = ur.avatar if ur else None
    user = current_user

    # Broadcast via WebSocket
    await manager.broadcast(
        {
            "id": new_message.id,
            "group_id": new_message.group_id,
            "sender_id": new_message.sender_id,
            "content": new_message.content,
            "message_type": "image",
            "created_at": new_message.created_at.isoformat() if new_message.created_at else None,
            "read_by": new_message.read_by,
            "sender_name": getattr(user, 'username', None),
            "sender_k_name": getattr(user, 'kName', None),
            "sender_e_name": getattr(user, 'eName', None),
            "sender_image": sender_image,
            "sender_gender": getattr(user, 'gender', None),
            "sender_type": user_type,
        },
        group_id
    )

    # Broadcast to all members' global websockets for inbox real-time update
    try:
        inbox_payload = {
            "group_id": group_id,
            "last_message": new_message.content,
            "last_message_time": new_message.created_at.isoformat() if new_message.created_at else datetime.utcnow().isoformat(),
            "sender_name": getattr(user, "username", None) or getattr(user, "kName", None) or getattr(user, "eName", None),
            "sender_image": sender_image,
            "sender_gender": getattr(user, "gender", None),
            "message_type": "image"
        }
        unread_map = _group_unread_counts_for_members(db, group_id)
        sid = int(current_user_id)
        for uid in _distinct_member_user_ids(db, group_id):
            payload = dict(inbox_payload)
            payload["unread_count_inc"] = 0 if int(uid) == sid else 1
            payload["group_unread_count"] = unread_map.get(uid, 0)
            asyncio.create_task(broadcast_to_user(uid, {"type": "inbox_updated", "payload": payload}))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error broadcasting inbox update: {e}")

    # Send push notification to other group members
    group_name = str(getattr(group, "name", "")) if group else ""
    try:
        sender_name = (getattr(user, "kName", None) or getattr(user, "eName", None) or getattr(user, "username", None) or "Someone") if user else "Someone"
        from .messages import send_notification, get_message_group_member_tokens
        member_tokens = get_message_group_member_tokens(db, group_id, current_user_id)
        if member_tokens:
            token_list = member_tokens
            await send_notification_async(
                device_tokens=token_list,
                title=f"New message in {group_name}",
                body=f"📷 {sender_name} sent a photo",
                data={
                    "type": "group_message",
                    "group_id": str(group_id),
                    "message_id": str(new_message.id),
                    "group_name": group_name,
                }
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error sending push notification for image: {e}")

    return MessageResponse(
        id=new_message.id,
        group_id=new_message.group_id,
        sender_id=new_message.sender_id,
        content=new_message.content,
        message_type="image",
        created_at=new_message.created_at,
        read_by=new_message.read_by,
        sender_image=sender_image,
        sender_type=user_type,
    )


@router.post("/groups/{group_id}/messages/upload-batch", response_model=MessageResponse)
async def send_image_batch_message(
    group_id: int,
    files: List[UploadFile] = File(...),
    current_user: Any = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload multiple images and send as one image_batch message."""
    principal = principal_from_user(current_user)
    current_user_id = principal.id

    membership = _require_membership(db, group_id, principal)

    _assert_group_post_allowed(db, group_id, principal, membership, "image_batch")

    if not files:
        raise HTTPException(status_code=400, detail="No image files provided")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Too many images (max 20)")

    ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/jpg", "application/octet-stream"}
    uploaded_urls: List[str] = []
    total_size = 0

    for file in files:
        if file.content_type and file.content_type not in ALLOWED:
            raise HTTPException(status_code=400, detail=f"Invalid image type: {file.content_type}")

        contents = await file.read()
        if not contents:
            continue
        total_size += len(contents)
        if len(contents) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="One of the files is too large (max 10 MB)")
        if total_size > 80 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Total upload size too large (max 80 MB)")

        ext = os.path.splitext(file.filename or "photo.jpg")[1] or ".jpg"
        filename = f"msg_batch_{group_id}_{uuid.uuid4().hex[:10]}{ext}"
        image_url = StorageService.upload_file(
            file_data=contents,
            folder="messages",
            filename=filename,
            content_type=file.content_type
        )
        if not image_url:
            raise HTTPException(status_code=500, detail="Failed to upload one of the images")
        uploaded_urls.append(image_url)

    if not uploaded_urls:
        raise HTTPException(status_code=400, detail="No valid images to upload")

    content_json = json.dumps(uploaded_urls)
    new_message = GroupMessage(
        group_id=group_id,
        sender_id=current_user_id,
        content=content_json,
        message_type="image_batch",
        read_by=_read_by_json_for_new_message(current_user_id),
        is_hidden=0
    )
    db.add(new_message)
    group = db.query(MessageGroup).filter(MessageGroup.id == group_id).first()
    if group:
        setattr(group, "updated_at", datetime.utcnow())
    db.commit()
    db.refresh(new_message)

    # Sender type comes from the caller's own membership row, already fetched above.
    user_type = membership.user_type or principal.kind
    ur = db.query(UserResource).filter(
        UserResource.user_id == current_user_id,
        UserResource.user_type == user_type
    ).first()
    if not ur and user_type == 'teacher':
        ur = db.query(UserResource).filter(
            UserResource.user_id == current_user_id,
            UserResource.user_type == 'employee'
        ).first()
    sender_image = ur.avatar if ur else None
    user = current_user

    await manager.broadcast(
        {
            "id": new_message.id,
            "group_id": new_message.group_id,
            "sender_id": new_message.sender_id,
            "content": new_message.content,
            "message_type": "image_batch",
            "created_at": new_message.created_at.isoformat() if new_message.created_at else None,
            "read_by": new_message.read_by,
            "sender_name": getattr(user, 'username', None),
            "sender_k_name": getattr(user, 'kName', None),
            "sender_e_name": getattr(user, 'eName', None),
            "sender_image": sender_image,
            "sender_gender": getattr(user, 'gender', None),
            "sender_type": user_type,
            "image_count": len(uploaded_urls),
        },
        group_id
    )

    try:
        inbox_payload = {
            "group_id": group_id,
            "last_message": f"{len(uploaded_urls)} photos",
            "last_message_time": new_message.created_at.isoformat() if new_message.created_at else datetime.utcnow().isoformat(),
            "sender_name": getattr(user, "username", None) or getattr(user, "kName", None) or getattr(user, "eName", None),
            "sender_image": sender_image,
            "sender_gender": getattr(user, "gender", None),
            "message_type": "image_batch"
        }
        unread_map = _group_unread_counts_for_members(db, group_id)
        sid = int(current_user_id)
        for uid in _distinct_member_user_ids(db, group_id):
            payload = dict(inbox_payload)
            payload["unread_count_inc"] = 0 if int(uid) == sid else 1
            payload["group_unread_count"] = unread_map.get(uid, 0)
            asyncio.create_task(broadcast_to_user(uid, {"type": "inbox_updated", "payload": payload}))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error broadcasting batch inbox update: {e}")

    group_name = str(getattr(group, "name", "")) if group else ""
    try:
        sender_name = (getattr(user, "kName", None) or getattr(user, "eName", None) or getattr(user, "username", None) or "Someone") if user else "Someone"
        member_tokens = get_message_group_member_tokens(db, group_id, current_user_id)
        if member_tokens:
            token_list = member_tokens
            await send_notification_async(
                device_tokens=token_list,
                title=f"New message in {group_name}",
                body=f"🖼️ {sender_name} sent {len(uploaded_urls)} photos",
                data={
                    "type": "group_message",
                    "group_id": str(group_id),
                    "message_id": str(new_message.id),
                    "group_name": group_name,
                }
            )
    except Exception as e:
        logging.getLogger(__name__).error(f"Error sending push notification for image batch: {e}")

    return MessageResponse(
        id=new_message.id,
        group_id=new_message.group_id,
        sender_id=new_message.sender_id,
        content=new_message.content,
        message_type="image_batch",
        created_at=new_message.created_at,
        read_by=new_message.read_by,
        sender_image=sender_image,
        sender_type=user_type,
    )

@router.post("/groups/{group_id}/messages/upload_voice")
async def send_voice_message(
    group_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user)
):
    """Upload and send a voice message to a group"""
    if not getattr(current_user, "id", None):
        raise HTTPException(status_code=401, detail="Could not determine user ID")
    principal = principal_from_user(current_user)
    current_user_id = principal.id

    membership = _require_membership(db, group_id, principal)

    _assert_group_post_allowed(db, group_id, principal, membership, "voice")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file sent")

    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    ext = os.path.splitext(file.filename or "voice.m4a")[1] or ".m4a"
    filename = f"voice_{group_id}_{uuid.uuid4().hex[:10]}{ext}"

    voice_url = StorageService.upload_file(
        file_data=contents,
        folder="voice_messages",
        filename=filename,
        content_type=file.content_type
    )
    if not voice_url:
        raise HTTPException(status_code=500, detail="Failed to upload voice message")

    new_message = GroupMessage(
        group_id=group_id,
        sender_id=current_user_id,
        content=voice_url,
        message_type="voice",
        read_by=_read_by_json_for_new_message(current_user_id),
        is_hidden=0
    )
    db.add(new_message)
    group = db.query(MessageGroup).filter(MessageGroup.id == group_id).first()
    if group:
        setattr(group, "updated_at", datetime.utcnow())
    db.commit()
    db.refresh(new_message)

    # Get sender info
    # Sender type comes from the caller's own membership row, already fetched above.
    user_type = membership.user_type or principal.kind
    ur = db.query(UserResource).filter(
        UserResource.user_id == current_user_id,
        UserResource.user_type == user_type
    ).first()
    if not ur and user_type == 'teacher':
        ur = db.query(UserResource).filter(
            UserResource.user_id == current_user_id,
            UserResource.user_type == 'employee'
        ).first()
    sender_image = ur.avatar if ur else None
    user = current_user

    # Broadcast via WebSocket
    await manager.broadcast(
        {
            "id": new_message.id,
            "group_id": new_message.group_id,
            "sender_id": new_message.sender_id,
            "content": new_message.content,
            "message_type": "voice",
            "created_at": new_message.created_at.isoformat() if new_message.created_at else None,
            "read_by": new_message.read_by,
            "sender_name": getattr(user, 'username', None),
            "sender_k_name": getattr(user, 'kName', None),
            "sender_e_name": getattr(user, 'eName', None),
            "sender_image": sender_image,
            "sender_gender": getattr(user, 'gender', None),
            "sender_type": user_type,
        },
        group_id
    )

    # Broadcast to all members' global websockets for inbox real-time update
    try:
        inbox_payload = {
            "group_id": group_id,
            "last_message": new_message.content,
            "last_message_time": new_message.created_at.isoformat() if new_message.created_at else datetime.utcnow().isoformat(),
            "sender_name": getattr(user, "username", None) or getattr(user, "kName", None) or getattr(user, "eName", None),
            "sender_image": sender_image,
            "sender_gender": getattr(user, "gender", None),
            "message_type": "voice"
        }
        unread_map = _group_unread_counts_for_members(db, group_id)
        sid = int(current_user_id)
        for uid in _distinct_member_user_ids(db, group_id):
            payload = dict(inbox_payload)
            payload["unread_count_inc"] = 0 if int(uid) == sid else 1
            payload["group_unread_count"] = unread_map.get(uid, 0)
            asyncio.create_task(broadcast_to_user(uid, {"type": "inbox_updated", "payload": payload}))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error broadcasting inbox update: {e}")

    # Send push notification to other group members
    group_name = str(getattr(group, "name", "")) if group else ""
    try:
        sender_name = (getattr(user, "kName", None) or getattr(user, "eName", None) or getattr(user, "username", None) or "Someone") if user else "Someone"
        member_tokens = get_message_group_member_tokens(db, group_id, current_user_id)
        if member_tokens:
            token_list = member_tokens
            await send_notification_async(
                device_tokens=token_list,
                title=f"New message in {group_name}",
                body=f"🎤 {sender_name} sent a voice message",
                data={
                    "type": "group_message",
                    "group_id": str(group_id),
                    "message_id": str(new_message.id),
                    "group_name": group_name,
                }
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error sending push notification for voice: {e}")

    return MessageResponse(
        id=new_message.id,
        group_id=new_message.group_id,
        sender_id=new_message.sender_id,
        content=new_message.content,
        message_type="voice",
        created_at=new_message.created_at,
        read_by=new_message.read_by,
        sender_image=sender_image,
        sender_type=user_type,
    )


@router.get("/groups/{group_id}/members", response_model=List[MessageGroupMemberResponse])
async def get_group_members(
    group_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Get all members of a group with their details."""
    current_user_id = principal.id
    # Check if user is a member
    _require_membership(db, group_id, principal)


    # Get members with user details
    query = text("""
        SELECT 
            mgm.id, mgm.group_id, mgm.user_id, mgm.user_type, mgm.role, mgm.joined_at,
            CASE 
                WHEN mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') THEN u.username
                WHEN mgm.user_type = 'parent' THEN p.username
                WHEN mgm.user_type = 'student' THEN s.username
                ELSE CAST(mgm.user_id AS CHAR)
            END as user_name,
            CASE 
                WHEN mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') THEN u.kName
                WHEN mgm.user_type = 'parent' THEN COALESCE(p.motherName, p.fatherName, '')
                WHEN mgm.user_type = 'student' THEN s.kName
                ELSE ''
            END as user_k_name,
            CASE 
                WHEN mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') THEN u.eName
                WHEN mgm.user_type = 'parent' THEN COALESCE(p.fatherName, p.motherName, '')
                WHEN mgm.user_type = 'student' THEN s.eName
                ELSE ''
            END as user_e_name,
            (
                SELECT ur.avatar 
                FROM users_resource ur 
                WHERE ur.user_id = mgm.user_id 
                  AND (
                      -- staff (teacher/employee/admin/superadmin/user) all live in users table;
                      -- their users_resource rows may be stored as 'teacher' OR 'employee', so match any non-student/non-parent row
                      (mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') AND ur.user_type NOT IN ('student', 'parent'))
                      -- students live in students table; match only student-typed rows
                      OR (mgm.user_type = 'student' AND ur.user_type = 'student')
                      -- parents live in parents table; match only parent-typed rows
                      OR (mgm.user_type = 'parent' AND ur.user_type = 'parent')
                  )
                  AND ur.avatar IS NOT NULL AND ur.avatar != ''
                ORDER BY ur.avatar DESC
                LIMIT 1
            ) as user_image
        FROM message_group_members mgm
        LEFT JOIN users u ON (mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') AND mgm.user_id = u.id)
        LEFT JOIN parents p ON (mgm.user_type = 'parent' AND mgm.user_id = p.id)
        LEFT JOIN students s ON (mgm.user_type = 'student' AND mgm.user_id = s.id)
        WHERE mgm.group_id = :group_id
        ORDER BY mgm.role DESC, mgm.joined_at ASC
    """)
    
    result = db.execute(query, {"group_id": group_id})
    members = []
    
    for row in result:
        members.append(MessageGroupMemberResponse(
            id=row.id,
            group_id=row.group_id,
            user_id=row.user_id,
            user_type=str(row.user_type) if getattr(row, 'user_type', None) is not None else None,
            role=row.role,
            joined_at=row.joined_at,
            user_name=row.user_name,
            user_k_name=row.user_k_name,
            user_e_name=row.user_e_name,
            user_image=row.user_image
        ))
    
    return members


@router.get("/groups/{group_id}/messages", response_model=List[MessageResponse])
async def get_group_messages(
    group_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    after_id: int = Query(None, description="Get messages after this ID (for polling)"),
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Get messages from a group (paginated or polled)."""
    current_user_id = principal.id
    # Check if user is a member
    _require_membership(db, group_id, principal)


    if after_id is not None:
        # Polling: Get messages after a specific ID (newer messages)
        query = text("""
            SELECT 
                m.id, m.group_id, m.sender_id, m.content, m.message_type, m.created_at, m.read_by,
                m.pinned_by, m.pinned_at, m.is_hidden,
                mgm.user_type as sender_type,
                CASE 
                    WHEN mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') THEN u.username
                    WHEN mgm.user_type = 'parent' THEN p.username
                    WHEN mgm.user_type = 'student' THEN s.username
                    ELSE u.username
                END as sender_name,
                CASE 
                    WHEN mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') THEN u.kName
                    WHEN mgm.user_type = 'parent' THEN COALESCE(p.motherName, p.fatherName, '')
                    WHEN mgm.user_type = 'student' THEN s.kName
                    ELSE u.kName
                END as sender_k_name,
                CASE 
                    WHEN mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') THEN u.eName
                    WHEN mgm.user_type = 'parent' THEN COALESCE(p.fatherName, p.motherName, '')
                    WHEN mgm.user_type = 'student' THEN s.eName
                    ELSE u.eName
                END as sender_e_name,
                CASE 
                    WHEN mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') OR mgm.id IS NULL THEN u.gender
                    WHEN mgm.user_type = 'student' THEN s.gender
                    ELSE NULL
                END as sender_gender,
            (
                SELECT ur.avatar 
                FROM users_resource ur 
                WHERE ur.user_id = m.sender_id 
                  AND (
                      (mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') AND ur.user_type NOT IN ('student', 'parent'))
                      OR (mgm.user_type = 'student' AND ur.user_type = 'student')
                      OR (mgm.user_type = 'parent' AND ur.user_type = 'parent')
                      OR (mgm.user_type IS NULL AND ur.user_type NOT IN ('student', 'parent'))
                  )
                  AND ur.avatar IS NOT NULL AND ur.avatar != ''
                ORDER BY ur.avatar DESC
                LIMIT 1
            ) as sender_image
            FROM messages m
            LEFT JOIN message_group_members mgm ON m.group_id = mgm.group_id AND m.sender_id = mgm.user_id
            LEFT JOIN users u ON (mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') AND m.sender_id = u.id) OR (mgm.id IS NULL AND m.sender_id = u.id)
            LEFT JOIN parents p ON (mgm.user_type = 'parent' AND m.sender_id = p.id)
            LEFT JOIN students s ON (mgm.user_type = 'student' AND m.sender_id = s.id)
            WHERE m.group_id = :group_id AND m.id > :after_id
                AND m.deleted_at IS NULL
            ORDER BY m.created_at ASC, m.id ASC
            LIMIT :limit
        """)
        params = {"group_id": group_id, "after_id": after_id, "limit": limit}
    else:
        # Pagination: Get messages with offset (older/history)
        query = text("""
            SELECT 
                m.id, m.group_id, m.sender_id, m.content, m.message_type, m.created_at, m.read_by,
                m.pinned_by, m.pinned_at, m.is_hidden,
                mgm.user_type as sender_type,
                CASE 
                    WHEN mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') THEN u.username
                    WHEN mgm.user_type = 'parent' THEN p.username
                    WHEN mgm.user_type = 'student' THEN s.username
                    ELSE u.username
                END as sender_name,
                CASE 
                    WHEN mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') THEN u.kName
                    WHEN mgm.user_type = 'parent' THEN COALESCE(p.motherName, p.fatherName, '')
                    WHEN mgm.user_type = 'student' THEN s.kName
                    ELSE u.kName
                END as sender_k_name,
                CASE 
                    WHEN mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') THEN u.eName
                    WHEN mgm.user_type = 'parent' THEN COALESCE(p.fatherName, p.motherName, '')
                    WHEN mgm.user_type = 'student' THEN s.eName
                    ELSE u.eName
                END as sender_e_name,
                CASE 
                    WHEN mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') OR mgm.id IS NULL THEN u.gender
                    WHEN mgm.user_type = 'student' THEN s.gender
                    ELSE NULL
                END as sender_gender,
            (
                SELECT ur.avatar 
                FROM users_resource ur 
                WHERE ur.user_id = m.sender_id 
                  AND (
                      (mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') AND ur.user_type NOT IN ('student', 'parent'))
                      OR (mgm.user_type = 'student' AND ur.user_type = 'student')
                      OR (mgm.user_type = 'parent' AND ur.user_type = 'parent')
                      OR (mgm.user_type IS NULL AND ur.user_type NOT IN ('student', 'parent'))
                  )
                  AND ur.avatar IS NOT NULL AND ur.avatar != ''
                ORDER BY ur.avatar DESC
                LIMIT 1
            ) as sender_image
            FROM messages m
            LEFT JOIN message_group_members mgm ON m.group_id = mgm.group_id AND m.sender_id = mgm.user_id
            LEFT JOIN users u ON (mgm.user_type IN ('teacher', 'employee', 'admin', 'superadmin', 'user') AND m.sender_id = u.id) OR (mgm.id IS NULL AND m.sender_id = u.id)
            LEFT JOIN parents p ON (mgm.user_type = 'parent' AND m.sender_id = p.id)
            LEFT JOIN students s ON (mgm.user_type = 'student' AND m.sender_id = s.id)
            WHERE m.group_id = :group_id
                AND m.deleted_at IS NULL
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT :limit OFFSET :offset
        """)
        params = {"group_id": group_id, "limit": limit, "offset": offset}
    
    result = db.execute(query, params)
    messages = []
    
    for row in result:
        messages.append(MessageResponse(
            id=row.id,
            group_id=row.group_id,
            sender_id=row.sender_id,
            content=row.content,
            message_type=row.message_type,
            created_at=row.created_at,
            read_by=row.read_by,
            sender_name=row.sender_name,
            sender_k_name=row.sender_k_name,
            sender_e_name=row.sender_e_name,
            sender_image=row.sender_image,
            sender_gender=row.sender_gender,
            sender_type=str(row.sender_type) if getattr(row, 'sender_type', None) is not None else None,
            pinned_by=row.pinned_by,
            pinned_at=row.pinned_at,
            is_hidden=row.is_hidden
        ))
    
    return messages


@router.post("/groups/{group_id}/messages", response_model=MessageResponse)
async def send_message(
    group_id: int,
    message_data: MessageCreate,
    current_user: Any = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Send a message to a group."""
    principal = principal_from_user(current_user)
    current_user_id = principal.id

    # Determine user_type for avatars
    from .user_resource import _resolve_user_type
    user_type = _resolve_user_type(current_user)

    # Check if user is a member
    membership = _require_membership(db, group_id, principal)

    _assert_group_post_allowed(
        db, group_id, principal, membership, message_data.message_type
    )

    # Create message
    new_message = GroupMessage(
        group_id=group_id,
        sender_id=current_user_id,
        content=message_data.content,
        message_type=message_data.message_type,
        read_by=_read_by_json_for_new_message(current_user_id),
        is_hidden=0  # Not hidden by default
    )
    
    db.add(new_message)
    
    # Update group's updated_at
    group = db.query(MessageGroup).filter(MessageGroup.id == group_id).first()
    if group:
        setattr(group, "updated_at", datetime.utcnow())
    
    db.commit()
    db.refresh(new_message)
    
    # Get sender details from Current User Active Session
    ur = db.query(UserResource).filter(UserResource.user_id == current_user_id, UserResource.user_type == user_type).first()
    sender_image = ur.avatar if ur else None
    user = current_user

    


    # Broadcast new message to connected clients
    await manager.broadcast(
        {
            "id": new_message.id,
            "group_id": new_message.group_id,
            "sender_id": new_message.sender_id,
            "content": new_message.content,
            "message_type": new_message.message_type,
            "created_at": new_message.created_at.isoformat(),
            "read_by": new_message.read_by,
            "sender_name": getattr(user, "username", None),
            "sender_k_name": getattr(user, "kName", None),
            "sender_e_name": getattr(user, "eName", None),
            "sender_image": sender_image,
            "sender_type": user_type
        },
        group_id
    )

    # Broadcast to all members' global websockets for inbox real-time update
    try:
        inbox_payload = {
            "group_id": group_id,
            "last_message": new_message.content,
            "last_message_time": new_message.created_at.isoformat(),
            "sender_name": getattr(user, "username", None) or getattr(user, "kName", None) or getattr(user, "eName", None),
            "sender_image": sender_image,
            "sender_gender": getattr(user, "gender", None),
            "message_type": new_message.message_type
        }
        unread_map = _group_unread_counts_for_members(db, group_id)
        sid = int(current_user_id)
        for uid in _distinct_member_user_ids(db, group_id):
            payload = dict(inbox_payload)
            payload["unread_count_inc"] = 0 if int(uid) == sid else 1
            payload["group_unread_count"] = unread_map.get(uid, 0)
            asyncio.create_task(broadcast_to_user(uid, {"type": "inbox_updated", "payload": payload}))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error broadcasting inbox update: {e}")

    # Send push notification to other group members when requested (like hot events)
    do_send_push = getattr(message_data, "send_notification", True)
    if do_send_push:
        group_name = str(getattr(group, "name", "")) if group else ""
        try:
            sender_name = (getattr(user, "kName", None) or getattr(user, "eName", None) or getattr(user, "username", None) or "Someone") if user else "Someone"
            content_str = str(new_message.content or "")
            content_preview = content_str[:80]
            if len(content_str) > 80:
                content_preview += "..."
            member_tokens = get_message_group_member_tokens(db, group_id, current_user_id)
            if not member_tokens:
                logging.getLogger(__name__).info(
                    "Group message notification: no device tokens for group_id=%s (other members must open the app and be logged in to register FCM)",
                    group_id,
                )
            else:
                token_list = member_tokens
                is_market = bool(
                    group and getattr(group, "description", "") == "market:buyer-seller"
                )
                push_data = {
                    "type": "group_message",
                    "group_id": str(group_id),
                    "message_id": str(new_message.id),
                    "group_name": group_name,
                    "title": f"New message in {group_name}",
                    "body": f"{sender_name}: {content_preview}",
                    "is_market": "true" if is_market else "false",
                }
                if is_market:
                    push_data["deep_link"] = (
                        f"pamais://market/chat/{group_id}?messageId={new_message.id}"
                    )
                # Push only: let Android/iOS show system notification when app
                # Let FCM show a system notification on Android/iOS when the
                # app is not active (so tapping it can launch the app and
                # provide an initialMessage with data for navigation). We are
                # NOT saving to the notifications table.
                ok = await send_notification_async(
                    device_tokens=token_list,
                    title=f"New message in {group_name}",
                    body=f"{sender_name}: {content_preview}",
                    data=push_data,
                    channel_id="message_channel",
                    android_show_system_notification=True,
                )
                logging.getLogger(__name__).info(
                    "Group message notification: sent to %s device(s), success=%s",
                    len(token_list),
                    ok,
                )
        except Exception as e:
            logging.getLogger(__name__).exception("Group message notification failed: %s", e)

    return MessageResponse(
        id=cast(int, new_message.id),
        group_id=cast(int, new_message.group_id),
        sender_id=cast(int, new_message.sender_id),
        content=cast(str, new_message.content),
        message_type=cast(Any, new_message.message_type),
        created_at=cast(datetime, new_message.created_at),
        read_by=cast(Optional[str], new_message.read_by),
        sender_name=cast(Optional[str], getattr(user, "username", None)),
        sender_k_name=cast(Optional[str], getattr(user, "kName", None)),
        sender_e_name=cast(Optional[str], getattr(user, "eName", None)),
        sender_image=sender_image,
        sender_type=user_type
    )

@router.post("/groups/{group_id}/read")
async def mark_messages_read(
    group_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Mark all messages in a group as read by the current user."""
    current_user_id = principal.id
    # Check if user is a member
    _require_membership(db, group_id, principal)

    # Get all unread messages for this user in this group
    # Note: This is an inefficient implementation for large groups but matches current schema
    # A better approach would be to track last_read_message_id in member table
    messages = db.query(GroupMessage).filter(GroupMessage.group_id == group_id).all()
    
    updated_count = 0
    for message in messages:
        try:
            raw = getattr(message, "read_by", None)
            read_by_list = json.loads(str(raw) if raw else "[]")
            if current_user_id not in read_by_list:
                read_by_list.append(current_user_id)
                setattr(message, "read_by", json.dumps(read_by_list))
                updated_count += 1
        except json.JSONDecodeError:
            setattr(message, "read_by", json.dumps([current_user_id]))
            updated_count += 1
            
    if updated_count > 0:
        db.commit()

    # Real-time badge sync for this user (inbox row + home tab total via same WS event).
    schedule_inbox_sync_for_reader(db, group_id, current_user_id)

    return {"status": "success", "updated_count": updated_count}


@router.post("/groups/auto-create-class-groups")
async def auto_create_class_groups(
    request_data: AutoCreateClassGroupsRequest,
    current_user_id: int = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    [ADMIN ONLY] Auto-create message groups for all grades in the specified academic year.
    - Creates one group per grade/class
    - Adds homeroom teacher as admin
    - Adds all parents of students in that grade as members
    """
    try:
        # Get current academic year if not specified
        academic_year_id = request_data.academic_year_id
        if not academic_year_id:
            query = text("SELECT id FROM academic WHERE status = 1 ORDER BY id DESC LIMIT 1")
            result = db.execute(query).first()
            if not result:
                raise HTTPException(status_code=404, detail="No active academic year found")
            academic_year_id = result.id
        
        # Get academic year details
        year_query = text("SELECT academic_us_name FROM academic WHERE id = :id")
        year_result = db.execute(year_query, {"id": academic_year_id}).first()
        if not year_result:
            raise HTTPException(status_code=404, detail="Academic year not found")
        year_name = year_result.academic_us_name
        
        
        # Get all class assignments (class_teachers) for this academic year
        grades_query = text("""
            SELECT DISTINCT
                ct.grade_id as id,
                g.grade_name as myclass,
                ct.teacher_id,
                ct.grade_type_id,
                gt.type_name as grade_type,
                ct.branch_id,
                b.branch_name,
                ct.program_id,
                p.program_name
            FROM class_teachers ct
            JOIN grade g ON ct.grade_id = g.id
            LEFT JOIN grade_type gt ON ct.grade_type_id = gt.id
            LEFT JOIN branch b ON ct.branch_id = b.id
            LEFT JOIN program p ON ct.program_id = p.id
            WHERE ct.academic_id = :academic_year_id
            ORDER BY b.branch_name, p.program_name, g.grade_name, gt.type_name
        """)
        grades = db.execute(grades_query, {"academic_year_id": academic_year_id}).fetchall()
        
        created_groups = []
        
        for grade in grades:
            grade_id = grade.id
            teacher_id = grade.teacher_id
            class_name = grade.myclass
            grade_type_id = grade.grade_type_id
            grade_type = grade.grade_type or ""
            branch_id = grade.branch_id
            branch_name = grade.branch_name or ""
            program_id = grade.program_id
            program_name = grade.program_name or ""
            
            # Create simplified group name: "Class Name - Grade Type" (no branch)
            name_parts = [class_name]
            if grade_type:
                name_parts.append(f"- {grade_type}")

            group_name = " ".join(name_parts)
            
            # Check if group already exists (strict uniqueness check)
            # A group is unique by: academic_year + branch + program + grade + grade_type
            query_filters = [
                MessageGroup.grade_id == grade_id,
                MessageGroup.academic_year_id == academic_year_id,
                MessageGroup.type == 'class'
            ]
            
            # Add all optional filters for exact matching
            if grade_type_id:
                query_filters.append(MessageGroup.grade_type_id == grade_type_id)
            if program_id:
                query_filters.append(MessageGroup.program_id == program_id)
            if branch_id:
                query_filters.append(MessageGroup.branch_id == branch_id)
            
            existing_group = db.query(MessageGroup).filter(*query_filters).first()
            
            if existing_group:
                print(f"Group '{group_name}' already exists, skipping...")
                continue
            
            # Create the group with all details stored in separate columns
            new_group = MessageGroup(
                name=group_name,
                type='class',
                academic_year_id=academic_year_id,
                grade_id=grade_id,
                grade_type_id=grade_type_id,
                program_id=program_id,
                branch_id=branch_id,
                description=f"{class_name} [{grade_type}] [{program_name}] [{branch_name}] - {year_name}",
                created_by=current_user_id
            )
            db.add(new_group)
            db.flush()  # Get the ID
            
            # Add the requesting admin as admin of the group (current user is from users table)
            admin_member = MessageGroupMember(
                group_id=new_group.id,
                user_id=current_user_id,
                user_type=UserType.TEACHER,  # Admins are in users table
                role='admin'
            )
            db.add(admin_member)
            
            # Add homeroom teacher as admin (if exists and different from requesting admin)
            if teacher_id and teacher_id != current_user_id:
                teacher_member = MessageGroupMember(
                    group_id=new_group.id,
                    user_id=teacher_id,
                    user_type=UserType.TEACHER,  # Teachers are in users table
                    role='admin'
                )
                db.add(teacher_member)
            
            # Add users with admin permissions as group admins
            admin_permissions_query = text("""
                SELECT DISTINCT u.id
                FROM users u
                INNER JOIN role_permissions rp ON u.role = rp.role_id
                INNER JOIN permissions p ON rp.permission_id = p.id
                WHERE p.permission_name IN ('AdminViewApp', 'AdminUpdateApp', 'AdminDeleteApp')
                AND u.status = 1
            """)
            admin_users = db.execute(admin_permissions_query).fetchall()
            
            for admin_user in admin_users:
                admin_user_id = admin_user.id
                # Skip if already added (requesting admin or homeroom teacher)
                if admin_user_id != current_user_id and admin_user_id != teacher_id:
                    permission_admin_member = MessageGroupMember(
                        group_id=new_group.id,
                        user_id=admin_user_id,
                        user_type=UserType.TEACHER,  # Permission admins are in users table
                        role='admin'
                    )
                    db.add(permission_admin_member)
            
            # Get all students in this grade and their parents
            students_query = text("""
                SELECT DISTINCT s.myparents
                FROM students s
                INNER JOIN learning l ON s.id = l.studentid
                WHERE l.gradeid = :grade_id
                AND l.academicid = :academic_year_id
                AND s.status = 1
                AND s.myparents IS NOT NULL
            """)
            students = db.execute(students_query, {"grade_id": grade_id, "academic_year_id": academic_year_id}).fetchall()
            
            # Add parents as members
            for student in students:
                parent_id = student.myparents
                if parent_id:
                    try:
                        parent_member = MessageGroupMember(
                            group_id=new_group.id,
                            user_id=int(parent_id),
                            user_type=UserType.PARENT,  # Parents are in parents table
                            role='member'
                        )
                        db.add(parent_member)
                    except Exception as e:
                        print(f"Error adding parent {parent_id}: {e}")
            
            created_groups.append({
                "id": new_group.id,
                "name": group_name,
                "class_name": class_name,
                "grade_type": grade_type,
                "program_name": program_name,
                "branch_name": branch_name,
                "academic_year": year_name,
                "member_count": 1 if current_user_id else 0  # Admin added
            })
        
        db.commit()
        
        # Return detailed statistics
        total_possible = len(grades)
        created_count = len(created_groups)
        skipped_count = total_possible - created_count
        
        return {
            "success": True,
            "message": f"Created {created_count} groups, skipped {skipped_count} existing groups",
            "statistics": {
                "total_classes": total_possible,
                "created_count": created_count,
                "skipped_count": skipped_count,
                "success_rate": round((created_count / total_possible * 100) if total_possible > 0 else 0, 1)
            },
            "created_groups": created_groups
        }
        
    except Exception as e:
        db.rollback()
        print(f"Error creating class groups: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
