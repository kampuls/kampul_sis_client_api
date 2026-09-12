"""
Auto-cleanup for saved parent attendance notifications.

When a teacher marks attendance, parents receive a push and an in-app inbox row
(``notifications`` table, ``redirect_route = 'attendance'``). Rows older than
:data:`RETENTION_DAYS` are removed by the background scheduler so the inbox
does not grow indefinitely.

Other parent notifications (link requests, account approval, etc.) use different
``redirect_route`` values and are not affected.
"""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

RETENTION_DAYS = 7


def cleanup_old_parent_attendance_notifications() -> int:
    """Delete parent attendance inbox rows older than :data:`RETENTION_DAYS`.

    Returns the number of rows removed. Runs in its own DB session (invoked from
    the background scheduler, outside any request context).
    """
    from .database import SessionLocal

    db: Session = SessionLocal()
    deleted = 0
    try:
        result = db.execute(
            text(
                f"""
                DELETE FROM notifications
                WHERE user_type = 'parent'
                  AND redirect_route = 'attendance'
                  AND created_at IS NOT NULL
                  AND created_at <= (NOW() - INTERVAL {RETENTION_DAYS} DAY)
                """
            )
        )
        deleted = result.rowcount or 0
        db.commit()
        if deleted:
            logger.info(
                "Parent attendance notification cleanup removed %s row(s) "
                "(older than %s days)",
                deleted,
                RETENTION_DAYS,
            )
        return deleted
    except Exception as e:
        db.rollback()
        logger.error("Parent attendance notification cleanup failed: %s", e)
        return deleted
    finally:
        db.close()
