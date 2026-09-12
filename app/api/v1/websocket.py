"""
WebSocket endpoint for real-time updates (Facebook-like architecture)

Multi-worker safe:
  - Each worker broadcasts messages to its own local connections (fast, in-memory).
  - Cross-worker messages go through ws_broadcast_queue (DB pub/sub, no Redis needed).
  - Each worker polls the DB every 500ms and delivers pending messages to local connections.
"""
import os
import json
import logging
import asyncio
from typing import Dict, Optional, Set

# NOTE: Do NOT cache os.getpid() at module level.
# With Gunicorn --preload, modules load in the MASTER process.
# os.getpid() must be called INLINE at broadcast time (after fork)
# so each worker stamps its own PID, not the master's PID.
from fastapi import WebSocket, WebSocketDisconnect, Query, HTTPException, status
from sqlalchemy.orm import Session
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError

from ...core import get_db, settings
from ...core.database import SessionLocal
from ...models import User, Parent
from ...services.ws_pubsub import publish, publish_sync, poll_loop, register_handler

logger = logging.getLogger(__name__)

_main_loop: Optional[asyncio.AbstractEventLoop] = None


def bind_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called once per worker at startup so sync routes can wake local sockets."""
    global _main_loop
    _main_loop = loop


def _parent_as_user(parent: Parent):
    """Adapter so Parent can be used where User is expected."""
    return type("ParentAsUser", (), {
        "id": parent.id,
        "username": parent.username or str(parent.id),
        "role": "parent",
        "is_parent": True,
    })()


def _can_join_room(user, room_id: str) -> bool:
    """Enforce sensitive room boundaries in addition to HTTP authorization."""
    if room_id.startswith("pickup_admin_"):
        return not (
            bool(getattr(user, "is_parent", False))
            or str(getattr(user, "role", "")).lower() == "parent"
        )
    return True

# ── Per-worker in-memory connection maps ──────────────────────────────────────
# These are LOCAL to this worker process only.
# Cross-worker delivery is handled by the DB pub/sub poll loop below.
active_connections: Dict[int, Set[WebSocket]] = {}
room_connections: Dict[str, Set[WebSocket]] = {}
connections_lock = asyncio.Lock()


# ── DB Pub/Sub dispatch ───────────────────────────────────────────────────────

async def _dispatch(channel: str, payload: dict) -> None:
    """
    Called by the polling loop for every new message in ws_broadcast_queue.
    Skips messages that originated from THIS worker (already delivered via fast path).
    """
    # Prevent double-delivery: skip messages stamped with THIS worker's PID
    if payload.get("_origin_pid") == os.getpid():
        return

    # Strip internal field before sending to client
    clean = {k: v for k, v in payload.items() if k != "_origin_pid"}

    if channel == "all":
        for user_id in list(active_connections.keys()):
            await _local_broadcast_to_user(user_id, clean)

    elif channel.startswith("user:"):
        try:
            user_id = int(channel.split(":", 1)[1])
            await _local_broadcast_to_user(user_id, clean)
        except (ValueError, IndexError):
            pass

    elif channel.startswith("room:"):
        room_id = channel.split(":", 1)[1]
        await _local_broadcast_to_room(room_id, clean)


async def start_poll_loop() -> asyncio.Task:
    """
    Register this module's dispatch handler and start the shared DB poll loop.
    Called once per worker from app lifespan (main.py).
    messages.py's ConnectionManager also registers its own handler automatically.
    """
    register_handler(_dispatch)
    return asyncio.create_task(poll_loop())


# ── Local (single-worker) broadcast helpers ───────────────────────────────────

async def _local_broadcast_to_user(user_id: int, message: dict) -> None:
    """Send message to all connections of a user IN THIS WORKER."""
    async with connections_lock:
        connections = list(active_connections.get(user_id, set()))

    if not connections:
        return

    disconnected: Set[WebSocket] = set()
    for connection in connections:
        try:
            await connection.send_json(message)
        except Exception:
            disconnected.add(connection)

    if disconnected:
        async with connections_lock:
            current = active_connections.get(user_id)
            if current:
                current.difference_update(disconnected)
                if not current:
                    active_connections.pop(user_id, None)


async def _local_broadcast_to_room(room_id: str, message: dict) -> None:
    """Send message to all connections in a room IN THIS WORKER."""
    async with connections_lock:
        connections = list(room_connections.get(room_id, set()))

    if not connections:
        return

    disconnected: Set[WebSocket] = set()
    for connection in connections:
        try:
            await connection.send_json(message)
        except Exception:
            disconnected.add(connection)

    if disconnected:
        async with connections_lock:
            current = room_connections.get(room_id)
            if current:
                current.difference_update(disconnected)
                if not current:
                    room_connections.pop(room_id, None)


# ── Public broadcast API (cross-worker safe) ──────────────────────────────────

async def broadcast_to_user(user_id: int, message: dict) -> None:
    """
    Broadcast to a specific user — reaches ALL workers via DB pub/sub.
    Also delivers immediately to this worker's local connections.
    """
    await _local_broadcast_to_user(user_id, message)   # Fast path: this worker
    stamped = {**message, "_origin_pid": os.getpid()}
    await publish(f"user:{user_id}", stamped)           # Cross-worker: DB queue


async def broadcast_to_room(room_id: str, message: dict) -> None:
    """
    Broadcast to a room — reaches ALL workers via DB pub/sub.
    """
    await _local_broadcast_to_room(room_id, message)   # Fast path: this worker
    stamped = {**message, "_origin_pid": os.getpid()}
    await publish(f"room:{room_id}", stamped)           # Cross-worker: DB queue


async def broadcast_attendance_update(
    academic_id: int,
    attendance_date: str,
    student_id: int,
    program_id: int = None,
    grade_id: int = None,
    grade_type_id: int = None,
    shift_id: int = None,
    status: str = None
):
    """Broadcast attendance update event to all workers."""
    message = {
        "type": "attendance_updated",
        "payload": {
            "academic_id": academic_id,
            "attendance_date": attendance_date,
            "student_id": student_id,
            "program_id": program_id,
            "grade_id": grade_id,
            "grade_type_id": grade_type_id,
            "shift_id": shift_id,
            "status": status
        }
    }
    # Fast path: deliver immediately to this worker's own connections
    for user_id in list(active_connections.keys()):
        await _local_broadcast_to_user(user_id, message)
    room_id = f"academic_{academic_id}"
    await _local_broadcast_to_room(room_id, message)
    # Cross-worker: DB pub/sub delivers to other workers
    # _origin_pid prevents double-delivery back to this worker
    stamped = {**message, "_origin_pid": os.getpid()}
    await publish("all", stamped)


async def broadcast_class_update(
    academic_id: int,
    class_id: int = None,
    action: str = "updated"
):
    """Broadcast class update event."""
    message = {
        "type": "class_updated",
        "payload": {
            "academic_id": academic_id,
            "class_id": class_id,
            "action": action
        }
    }
    for user_id in list(active_connections.keys()):
        await _local_broadcast_to_user(user_id, message)
    stamped = {**message, "_origin_pid": os.getpid()}
    await publish("all", stamped)
    room_id = f"academic_{academic_id}"
    await _local_broadcast_to_room(room_id, message)
    await publish(f"room:{room_id}", stamped)


async def broadcast_schedule_update(
    academic_id: int,
    branch_id: int = None,
    grade_group_id: int = None,
    action: str = "updated"
):
    """Broadcast schedule update event."""
    message = {
        "type": "schedule_updated",
        "payload": {
            "academic_id": academic_id,
            "branch_id": branch_id,
            "grade_group_id": grade_group_id,
            "action": action
        }
    }
    for user_id in list(active_connections.keys()):
        await _local_broadcast_to_user(user_id, message)
    stamped = {**message, "_origin_pid": os.getpid()}
    await publish("all", stamped)
    room_id = f"academic_{academic_id}"
    await _local_broadcast_to_room(room_id, message)
    await publish(f"room:{room_id}", stamped)


async def broadcast_public_data_update(domain: str):
    """Broadcast public data updated event."""
    message = {
        "type": "public_data_updated",
        "payload": {"domain": domain}
    }
    for user_id in list(active_connections.keys()):
        await _local_broadcast_to_user(user_id, message)
    stamped = {**message, "_origin_pid": os.getpid()}
    await publish("all", stamped)


async def _broadcast_public_data_local(domain: str) -> None:
    message = {
        "type": "public_data_updated",
        "payload": {"domain": domain},
    }
    for user_id in list(active_connections.keys()):
        await _local_broadcast_to_user(user_id, message)


def notify_public_data_from_sync(domain: str) -> None:
    """
    Notify all clients from a sync HTTP handler.
    Inserts into DB pub/sub (other workers) and schedules immediate local delivery.
    """
    message = {
        "type": "public_data_updated",
        "payload": {"domain": domain},
    }
    publish_sync("all", message)
    loop = _main_loop
    if loop is not None and loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(
                _broadcast_public_data_local(domain), loop
            )
        except Exception:
            logger.debug("local public data broadcast skipped", exc_info=True)


# ── Connection lifecycle ───────────────────────────────────────────────────────

def verify_token(token: str, db: Session):
    """Verify JWT token and return user (User or Parent adapter)."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm]
        )
        user_id = payload.get("user_id")
        username = payload.get("sub")
        role = payload.get("role")

        if user_id is not None and role == "parent":
            parent = db.query(Parent).filter(Parent.id == user_id).first()
            if parent is not None:
                return _parent_as_user(parent)

        if user_id is not None:
            user = db.query(User).filter(User.id == user_id).first()
            if user is not None:
                return user
        if username is not None:
            user = db.query(User).filter(User.username == username).first()
            if user is not None:
                return user

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}"
        )


async def connect_websocket(websocket: WebSocket, user):
    """Register a new WebSocket connection."""
    await websocket.accept()

    async with connections_lock:
        if user.id not in active_connections:
            active_connections[user.id] = set()
        active_connections[user.id].add(websocket)

    logger.info(f"WebSocket connected: User {user.id} ({user.username})")

    await websocket.send_json({
        "type": "connection",
        "status": "connected",
        "user_id": user.id
    })


async def disconnect_websocket(websocket: WebSocket, user):
    """Unregister a WebSocket connection."""
    async with connections_lock:
        if user.id in active_connections:
            active_connections[user.id].discard(websocket)
            if not active_connections[user.id]:
                del active_connections[user.id]

        for room_id in list(room_connections.keys()):
            connections = room_connections.get(room_id)
            if not connections:
                continue
            connections.discard(websocket)
            if not connections:
                room_connections.pop(room_id, None)

    logger.info(f"WebSocket disconnected: User {user.id} ({user.username})")


async def join_room(websocket: WebSocket, room_id: str):
    """Add a connection to a room."""
    async with connections_lock:
        if room_id not in room_connections:
            room_connections[room_id] = set()
        room_connections[room_id].add(websocket)


async def leave_room(websocket: WebSocket, room_id: str):
    """Remove a connection from a room."""
    async with connections_lock:
        if room_id in room_connections:
            room_connections[room_id].discard(websocket)
            if not room_connections[room_id]:
                del room_connections[room_id]


async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    """
    WebSocket endpoint for real-time updates.
    Now cross-worker safe via DB pub/sub (no Redis needed).
    """
    user = None
    db: Session = SessionLocal()

    try:
        user = verify_token(token, db)
        await connect_websocket(websocket, user)

        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)

                message_type = message.get("type")
                payload = message.get("payload", {})

                if message_type == "subscribe":
                    await websocket.send_json({
                        "type": "subscribed",
                        "event": payload.get("event"),
                        "status": "success"
                    })

                elif message_type == "join_room":
                    room_id = payload.get("room_id")
                    if room_id:
                        if not _can_join_room(user, str(room_id)):
                            await websocket.send_json({
                                "type": "error",
                                "message": "Not authorized to join this room",
                            })
                            continue
                        await join_room(websocket, room_id)
                        await websocket.send_json({
                            "type": "room_joined",
                            "room_id": room_id,
                            "status": "success"
                        })

                elif message_type == "leave_room":
                    room_id = payload.get("room_id")
                    if room_id:
                        await leave_room(websocket, room_id)
                        await websocket.send_json({
                            "type": "room_left",
                            "room_id": room_id,
                            "status": "success"
                        })

                elif message_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": payload.get("timestamp")
                    })

            except json.JSONDecodeError:
                try:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON format"})
                except Exception:
                    break
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                try:
                    await websocket.send_json({"type": "error", "message": str(e)})
                except Exception:
                    break

    except WebSocketDisconnect:
        if user:
            await disconnect_websocket(websocket, user)
    except HTTPException as e:
        logger.error(f"WebSocket authentication failed: {e.detail}")
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if user:
            await disconnect_websocket(websocket, user)
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        if user:
            try:
                await disconnect_websocket(websocket, user)
            except Exception:
                pass
        db.close()


# Export broadcast functions for use in other modules
__all__ = [
    "broadcast_attendance_update",
    "broadcast_class_update",
    "broadcast_schedule_update",
    "broadcast_public_data_update",
    "notify_public_data_from_sync",
    "bind_event_loop",
    "broadcast_to_user",
    "broadcast_to_room",
    "websocket_endpoint",
    "start_poll_loop",
]
