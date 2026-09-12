"""Reliable parent notification delivery for newly published homework."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models.homework import LearningHomework
from . import notification_service


logger = logging.getLogger(__name__)


def get_homework_parent_targets(
    db: Session,
    homework: LearningHomework,
) -> List[Dict[str, Any]]:
    """Return each active linked parent once for the homework's exact class."""
    grade_filter = "l.gradeid = :grade_id"
    params: Dict[str, Any] = {
        "academic_id": int(homework.academic_id),
        "program_id": int(homework.program_id),
        "shift_id": int(homework.shift_id),
        "grade_id": homework.grade_id,
        "grade_group_id": int(homework.grade_group_id),
        "grade_type_id": homework.grade_type_id,
    }
    if homework.grade_id is None:
        grade_filter = "g.group_id = :grade_group_id"

    grade_type_filter = ""
    if homework.grade_type_id is not None:
        grade_type_filter = "AND (l.grade_type_id <=> :grade_type_id)"

    rows = db.execute(
        text(f"""
            SELECT DISTINCT p.id
            FROM parents p
            JOIN learning l
              ON FIND_IN_SET(
                   CAST(l.studentid AS CHAR CHARACTER SET utf8mb4)
                     COLLATE utf8mb4_unicode_ci,
                   REPLACE(COALESCE(p.myChilds, ''), ' ', '')
                     COLLATE utf8mb4_unicode_ci
                 ) > 0
            JOIN grade g ON g.id = l.gradeid
            WHERE p.status = 1
              AND l.academicid = :academic_id
              AND l.programid = :program_id
              AND l.shiftid = :shift_id
              AND {grade_filter}
              {grade_type_filter}
        """),
        params,
    ).fetchall()
    return [{"id": int(row[0]), "user_type": "parent"} for row in rows]


def _due_label(value: date | None) -> str:
    return value.strftime("%d %b %Y") if value else "No due date"


def notify_parents_homework_published(homework_id: int) -> None:
    """Persist one inbox item per parent and send one push per installation."""
    db = SessionLocal()
    try:
        homework = (
            db.query(LearningHomework)
            .filter(
                LearningHomework.id == int(homework_id),
                LearningHomework.is_active == True,  # noqa: E712
            )
            .first()
        )
        if homework is None:
            logger.warning("Homework notification skipped; item %s not found", homework_id)
            return

        labels = db.execute(
            text("""
                SELECT
                    COALESCE(NULLIF(s.subject_name_us, ''), s.subject_name) AS subject_name,
                    COALESCE(g.grade_name, gg.group_name) AS grade_name,
                    gt.type_name AS grade_type_name,
                    sh.shift_name,
                    COALESCE(NULLIF(u.eName, ''), NULLIF(u.kName, ''), u.username) AS teacher_name
                FROM learning_homework h
                JOIN subjects s ON s.id = h.subject_id
                JOIN grade_group gg ON gg.id = h.grade_group_id
                LEFT JOIN grade g ON g.id = h.grade_id
                LEFT JOIN grade_type gt ON gt.id = h.grade_type_id
                LEFT JOIN shift sh ON sh.id = h.shift_id
                JOIN users u ON u.id = h.teacher_id
                WHERE h.id = :homework_id
                LIMIT 1
            """),
            {"homework_id": int(homework.id)},
        ).fetchone()
        subject_name = str(labels[0] or "Subject") if labels else "Subject"
        class_parts = [
            str(labels[1] or "Class") if labels else "Class",
            str(labels[2] or "").strip() if labels else "",
            str(labels[3] or "").strip() if labels else "",
        ]
        class_name = " · ".join(part for part in class_parts if part)
        teacher_name = str(labels[4] or "Teacher") if labels else "Teacher"

        targets = get_homework_parent_targets(db, homework)
        if not targets:
            logger.info("Homework %s has no linked parent recipients", homework.id)
            return

        tokens = notification_service.resolve_device_tokens_for_users(db, targets)
        delivered = notification_service.send_notification(
            device_tokens=tokens,
            title=f"New Homework: {subject_name}",
            body=(
                f"{teacher_name} posted homework for {class_name}. "
                f"Due: {_due_label(homework.due_date)}."
            ),
            data={
                "type": "homework_published",
                "homework_id": str(homework.id),
                **(
                    {"class_schedule_id": str(homework.class_schedule_id)}
                    if homework.class_schedule_id is not None
                    else {}
                ),
                "subject_id": str(homework.subject_id),
                "academic_id": str(homework.academic_id),
                "notification_key": f"homework:{homework.id}",
            },
            channel_id="message_channel",
            android_show_system_notification=True,
            db=db,
            user_ids=targets,
            redirect_route="assignments",
            redirect_args={"homework_id": int(homework.id)},
        )
        logger.info(
            "Homework notification: homework_id=%s parents=%s tokens=%s delivered=%s",
            homework.id,
            len(targets),
            len(tokens),
            delivered,
        )
    except Exception:
        logger.exception("Failed to notify parents about homework %s", homework_id)
    finally:
        db.close()
