"""
DB-based WebSocket Pub/Sub
==========================
Free alternative to Redis pub/sub for cross-worker WebSocket broadcasting.

How it works:
  - Any worker wanting to broadcast inserts a row into ws_broadcast_queue
  - Each worker runs a single async polling loop every 500ms
  - All registered handlers are called for each new message
  - Rows older than 10 seconds are auto-cleaned

Latency: ~500ms max (vs ~1ms with Redis) — perfectly fine for a school app.

Usage:
    # In any module:
    from .ws_pubsub import register_handler, publish

    # Register a dispatch handler (done once at module load)
    register_handler(my_async_dispatch_fn)  # async def fn(channel, payload)

    # Publish a message to all workers
    await publish("user:5", {"type": "...", "_origin_pid": MY_PID})
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Callable, List

from sqlalchemy import text

from ..core import SessionLocal

logger = logging.getLogger(__name__)

# ── Handler registry ───────────────────────────────────────────────────────────
# Each worker module (websocket.py, messages.py) registers its own dispatch fn.
# The poll loop calls ALL registered handlers for every new queue row.
_handlers: List[Callable] = []


def register_handler(fn: Callable) -> None:
    """
    Register an async dispatch function.
    Signature: async def fn(channel: str, payload: dict) -> None
    Safe to call multiple times with the same fn (deduplicates).
    """
    if fn not in _handlers:
        _handlers.append(fn)
        logger.debug(f"[WS-PubSub] Registered handler: {fn.__qualname__}")


# ── Global last-seen ID tracker ────────────────────────────────────────────────
_last_processed_id: int = 0
_initialized: bool = False

# Polling interval and row TTL
POLL_INTERVAL = 0.5      # 500ms
ROW_TTL_SECONDS = 10


async def _init_last_id() -> None:
    """Set _last_processed_id to current max so we don't replay old history on startup."""
    global _last_processed_id, _initialized
    if _initialized:
        return
    try:
        db = SessionLocal()
        try:
            row = db.execute(
                text("SELECT COALESCE(MAX(id), 0) FROM ws_broadcast_queue")
            ).fetchone()
            _last_processed_id = int(row[0]) if row else 0
            _initialized = True
            logger.info(f"[WS-PubSub] Initialised, last_id={_last_processed_id}")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[WS-PubSub] Init error: {e}")


def publish_sync(channel: str, payload: dict) -> None:
    """
    Thread-safe publish for sync HTTP handlers (no asyncio loop required).
    Inserts into ws_broadcast_queue; worker poll loops deliver within ~500ms.
    """
    try:
        db = SessionLocal()
        try:
            db.execute(
                text("""
                    INSERT INTO ws_broadcast_queue (channel, payload)
                    VALUES (:channel, :payload)
                """),
                {"channel": channel, "payload": json.dumps(payload)},
            )
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[WS-PubSub] Sync publish error channel={channel}: {e}")


async def publish(channel: str, payload: dict) -> None:
    """
    Publish a message to all workers via DB queue.
    Always include _origin_pid in payload to prevent double-delivery.

    Channel formats:
      "user:{user_id}"   → specific user
      "room:{room_id}"   → specific room
      "group:{group_id}" → chat group
      "all"              → every connected user
    """
    try:
        db = SessionLocal()
        try:
            db.execute(
                text("""
                    INSERT INTO ws_broadcast_queue (channel, payload)
                    VALUES (:channel, :payload)
                """),
                {"channel": channel, "payload": json.dumps(payload)},
            )
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[WS-PubSub] Publish error channel={channel}: {e}")


async def _cleanup_old_rows(db) -> None:
    """Delete rows older than ROW_TTL_SECONDS to keep the table small."""
    cutoff = datetime.utcnow() - timedelta(seconds=ROW_TTL_SECONDS)
    try:
        db.execute(
            text("DELETE FROM ws_broadcast_queue WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[WS-PubSub] Cleanup error: {e}")


async def poll_loop() -> None:
    """
    Single async loop per worker.
    Polls the DB every POLL_INTERVAL seconds and calls ALL registered handlers.
    Started once per worker in app lifespan (main.py).
    """
    global _last_processed_id

    await _init_last_id()
    cleanup_counter = 0

    logger.info(f"[WS-PubSub] Poll loop started (handlers: {len(_handlers)})")

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)

            if not _handlers:
                continue  # No handlers registered yet, keep waiting

            db = SessionLocal()
            try:
                rows = db.execute(
                    text("""
                        SELECT id, channel, payload
                        FROM ws_broadcast_queue
                        WHERE id > :last_id
                        ORDER BY id ASC
                        LIMIT 200
                    """),
                    {"last_id": _last_processed_id},
                ).fetchall()

                for row in rows:
                    row_id, channel, raw_payload = row[0], row[1], row[2]
                    try:
                        payload = (
                            json.loads(raw_payload)
                            if isinstance(raw_payload, str)
                            else raw_payload
                        )
                        # Call ALL registered handlers
                        for handler in list(_handlers):
                            try:
                                await handler(channel, payload)
                            except Exception as he:
                                logger.error(
                                    f"[WS-PubSub] Handler {handler.__qualname__} "
                                    f"error on channel={channel}: {he}"
                                )
                    except Exception as e:
                        logger.error(f"[WS-PubSub] Row {row_id} error: {e}")
                    finally:
                        _last_processed_id = max(_last_processed_id, row_id)

                # Cleanup every ~30s (60 × 0.5s)
                cleanup_counter += 1
                if cleanup_counter >= 60:
                    await _cleanup_old_rows(db)
                    cleanup_counter = 0

            finally:
                db.close()

        except asyncio.CancelledError:
            logger.info("[WS-PubSub] Poll loop cancelled gracefully")
            break
        except Exception as e:
            logger.error(f"[WS-PubSub] Poll error: {e}")
            await asyncio.sleep(2)  # Back off on error
