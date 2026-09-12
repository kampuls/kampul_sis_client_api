"""
Pending student registration helpers + auto-cleanup.

When an already-active parent adds a new child, the student row is created with
``status = 2`` (pending review). An App Admin can approve (status -> 1) or reject
it from the admin screen; otherwise, if it is never approved within the grace
window (:data:`GRACE_DAYS`), the background scheduler removes it automatically.

Both the admin "reject" action, parent-registration rejection, and the scheduled
cleanup share :func:`delete_pending_student` / :func:`delete_students_by_ids`, so
a pending child is always torn down the same way (dependent rows, stored files,
and the parent's ``myChilds`` entry when applicable).

Scope for the 7-day auto-cleanup is intentionally limited to children of ACTIVE
parents. Pending *parent* registrations use :func:`delete_students_by_ids` when
an admin rejects the whole registration.
"""

import logging
from typing import Optional, List, Iterable, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

PENDING_STATUS = 2   # students.status for a parent-submitted, not-yet-approved child
GRACE_DAYS = 7       # auto-delete once a pending child is older than this many days

# Dependent rows to remove (per student) before deleting the student itself.
_CHILD_DEPENDENT_DELETES = [
    "DELETE FROM parent_permission_interactions WHERE student_id = :sid",
    "DELETE FROM parent_student_link_requests WHERE student_id = :sid",
    "DELETE FROM pickup_requests WHERE student_id = :sid",
    "DELETE FROM daily_attendance WHERE student_id = :sid",
    "DELETE FROM student_profile_edit_requests WHERE student_id = :sid",
    "DELETE FROM attendance_audit_log WHERE student_id = :sid",
    "DELETE FROM learning WHERE studentid = :sid",
    "DELETE FROM users_resource WHERE user_type = 'student' AND user_id = :sid",
    "DELETE FROM device_tokens WHERE user_type = 'student' AND user_id = :sid",
    "DELETE FROM students WHERE id = :sid",
]


def _get_settings(db: Session, settings=None):
    if settings is not None:
        return settings
    try:
        from ..models.settings import SystemSettings
        return db.query(SystemSettings).first()
    except Exception:
        return None


def collect_student_file_urls(db: Session, student_id: int) -> List[str]:
    """Avatar paths/URLs and pickup audio for a student (read before row delete)."""
    urls: List[str] = []
    try:
        rows = db.execute(
            text(
                "SELECT avatar FROM users_resource "
                "WHERE user_type = 'student' AND user_id = :sid AND avatar IS NOT NULL"
            ),
            {"sid": student_id},
        ).fetchall()
        urls.extend(str(r[0]).strip() for r in rows if r[0])
    except Exception as e:
        logger.warning("Could not load student avatars for #%s: %s", student_id, e)

    try:
        srow = db.execute(
            text("SELECT pickup_audio_url FROM students WHERE id = :sid"),
            {"sid": student_id},
        ).fetchone()
        if srow and srow[0]:
            urls.append(str(srow[0]).strip())
    except Exception as e:
        logger.warning("Could not load pickup audio for student #%s: %s", student_id, e)

    return [u for u in urls if u]


def _teardown_student_rows(db: Session, student_id: int) -> None:
    """Delete dependent rows and the student row. Does not commit or delete files."""
    for sql in _CHILD_DEPENDENT_DELETES:
        try:
            db.execute(text(sql), {"sid": student_id})
        except Exception as e:
            logger.warning("Student delete skipped (%s): %s", e, sql[:90])


def _remove_student_from_parent_my_childs(
    db: Session, student_id: int, parent_id_raw: str
) -> None:
    if not parent_id_raw.isdigit():
        return
    try:
        mrow = db.execute(
            text("SELECT myChilds FROM parents WHERE id = :pid"),
            {"pid": int(parent_id_raw)},
        ).fetchone()
        if mrow and mrow[0]:
            ids = [x.strip() for x in str(mrow[0]).split(",") if x.strip()]
            kept = [x for x in ids if x != str(student_id)]
            if len(kept) != len(ids):
                db.execute(
                    text("UPDATE parents SET myChilds = :mc WHERE id = :pid"),
                    {"mc": ",".join(kept), "pid": int(parent_id_raw)},
                )
    except Exception as e:
        logger.warning(
            "Could not update myChilds after deleting student #%s: %s",
            student_id,
            e,
        )


def _delete_stored_files(urls: Iterable[str], settings=None) -> None:
    from ..services.storage_service import StorageService

    for url in urls:
        if not url:
            continue
        try:
            if StorageService.delete_file(url, settings):
                logger.info("Deleted stored file: %s", url)
            else:
                logger.warning("Stored file not deleted (missing or remote): %s", url)
        except Exception as e:
            logger.warning("Failed to delete stored file %s: %s", url, e)


def delete_students_by_ids(
    db: Session,
    student_ids: List[int],
    *,
    settings=None,
    commit: bool = True,
    update_parent_my_childs: bool = False,
) -> Tuple[int, List[str]]:
    """Delete multiple students, their dependent rows, and stored files.

    Returns ``(deleted_count, file_urls)``. When ``commit`` is False the caller
    must commit the session and delete ``file_urls`` afterward.
    """
    unique_ids = sorted({int(sid) for sid in student_ids if sid})
    if not unique_ids:
        return 0, []

    settings = _get_settings(db, settings)
    file_urls: List[str] = []

    for student_id in unique_ids:
        file_urls.extend(collect_student_file_urls(db, student_id))

        parent_id_raw = ""
        if update_parent_my_childs:
            prow = db.execute(
                text("SELECT TRIM(myparents) FROM students WHERE id = :sid"),
                {"sid": student_id},
            ).fetchone()
            parent_id_raw = str(prow[0]).strip() if prow and prow[0] is not None else ""

        _teardown_student_rows(db, student_id)

        if update_parent_my_childs:
            _remove_student_from_parent_my_childs(db, student_id, parent_id_raw)

    if commit:
        db.commit()
        _delete_stored_files(file_urls, settings)
        try:
            from ..services.query_cache import invalidate_cache
            invalidate_cache("students_list")
        except Exception:
            pass

    return len(unique_ids), file_urls


def delete_pending_student(db: Session, student_id: int, settings=None) -> bool:
    """Delete ONE student: its dependent rows, its avatar file, and its entry in
    the parent's ``myChilds`` list. Commits the transaction. Returns True on
    success. Avatar files are removed only after the DB change is committed.
    """
    delete_students_by_ids(
        db,
        [student_id],
        settings=settings,
        commit=True,
        update_parent_my_childs=True,
    )
    return True


def cleanup_stale_pending_children() -> int:
    """Delete pending children (status=2) of active parents older than
    :data:`GRACE_DAYS`. Returns the number of students removed.

    Runs in its own DB session (invoked from the background scheduler, outside
    any request context).
    """
    from .database import SessionLocal

    db = SessionLocal()
    removed = 0
    try:
        rows = db.execute(
            text(
                f"""
                SELECT s.id
                FROM students s
                JOIN parents p
                  ON p.id = CAST(NULLIF(TRIM(s.myparents), '') AS UNSIGNED)
                WHERE s.status = :pending
                  AND s.submitted_by_parent = 1
                  AND COALESCE(p.status, 0) = 1
                  AND s.created_at IS NOT NULL
                  AND s.created_at <= (NOW() - INTERVAL {GRACE_DAYS} DAY)
                """
            ),
            {"pending": PENDING_STATUS},
        ).fetchall()

        if not rows:
            return 0

        from ..models.settings import SystemSettings
        settings = db.query(SystemSettings).first()

        for row in rows:
            student_id = int(row[0])
            try:
                delete_pending_student(db, student_id, settings=settings)
                removed += 1
                logger.info("Auto-removed stale pending student #%s", student_id)
            except Exception as e:
                db.rollback()
                logger.error("Failed to clean up pending student #%s: %s", student_id, e)

        if removed:
            logger.info("Stale pending-student cleanup removed %s record(s)", removed)
        return removed
    except Exception as e:
        db.rollback()
        logger.error("Pending-student cleanup failed: %s", e)
        return removed
    finally:
        db.close()
