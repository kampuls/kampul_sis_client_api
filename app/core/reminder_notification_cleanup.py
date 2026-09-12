"""
Auto-cleanup for reminder and wish notifications.

Reminder notifications (attendance check-in/out reminders and class schedule
reminders) are only relevant at the moment they fire, so the nightly job at
23:50 Cambodia time deletes every one of them — they are never kept past the
day they were sent.

Birthday/anniversary wish notifications are kept a little longer so the
recipient can still see who wished them, then removed once they are older
than :data:`WISH_RETENTION_DAYS`.

Rows are matched on the JSON ``data`` column (``"type": "attendance_reminder"``
etc.); all other notification types are untouched.
"""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# data JSON "type" values written by the reminder services.
REMINDER_TYPES = ("attendance_reminder", "schedule_reminder")

# data JSON "type" values written by the wish endpoints (users.py).
WISH_TYPES = ("birthday_wish", "anniversary_wish")
WISH_RETENTION_DAYS = 3


def cleanup_reminder_and_wish_notifications() -> int:
    """Delete all reminder notifications and wish notifications older than
    :data:`WISH_RETENTION_DAYS`.

    Returns the total number of rows removed. Runs in its own DB session
    (invoked from the background scheduler, outside any request context).
    """
    from .database import SessionLocal

    db: Session = SessionLocal()
    deleted_reminders = 0
    deleted_wishes = 0
    try:
        # Reminders: moment-relevant only — wipe them all every night.
        result = db.execute(
            text(
                """
                DELETE FROM notifications
                WHERE (data LIKE :type0 OR data LIKE :type1)
                """
            ),
            {
                "type0": f'%"{REMINDER_TYPES[0]}"%',
                "type1": f'%"{REMINDER_TYPES[1]}"%',
            },
        )
        deleted_reminders = result.rowcount or 0

        # Wishes: keep a short window, then remove.
        result = db.execute(
            text(
                f"""
                DELETE FROM notifications
                WHERE (data LIKE :type0 OR data LIKE :type1)
                  AND created_at IS NOT NULL
                  AND created_at <= (NOW() - INTERVAL {WISH_RETENTION_DAYS} DAY)
                """
            ),
            {
                "type0": f'%"{WISH_TYPES[0]}"%',
                "type1": f'%"{WISH_TYPES[1]}"%',
            },
        )
        deleted_wishes = result.rowcount or 0

        db.commit()
        if deleted_reminders or deleted_wishes:
            logger.info(
                "Reminder/wish notification cleanup removed %s reminder row(s) "
                "and %s wish row(s) (wishes older than %s days)",
                deleted_reminders,
                deleted_wishes,
                WISH_RETENTION_DAYS,
            )
        return deleted_reminders + deleted_wishes
    except Exception as e:
        db.rollback()
        logger.error("Reminder/wish notification cleanup failed: %s", e)
        return deleted_reminders + deleted_wishes
    finally:
        db.close()
