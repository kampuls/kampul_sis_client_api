"""Teacher homework publishing and class-scoped homework feeds."""

from __future__ import annotations

import re
import uuid
import zipfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...auth.dependencies import get_current_active_employee
from ...core import get_db
from ...models import Parent, Student, User
from ...models.homework import LearningHomework, LearningHomeworkAttachment
from ...models.learning import LearningClassSchedule
from ...services.homework_notification_service import notify_parents_homework_published
from ...services.storage_service import StorageService
from ...utils.academic_year import get_current_academic_id
from .notifications import get_user_info_from_token


router = APIRouter(prefix="/homework", tags=["homework"])

MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_DESCRIPTION_LENGTH = 20_000


class HomeworkAttachmentOut(BaseModel):
    id: int
    file_url: str
    original_name: str
    content_type: str
    file_size: int


class HomeworkOut(BaseModel):
    id: int
    academic_id: int
    class_schedule_id: Optional[int]
    branch_id: int
    program_id: int
    grade_group_id: int
    grade_id: Optional[int]
    grade_type_id: Optional[int]
    shift_id: int
    subject_id: int
    teacher_id: int
    title: str
    description: str
    homework_date: date
    due_date: Optional[date]
    created_at: datetime
    subject_name: str
    class_name: str
    grade_name: str
    grade_type_name: Optional[str]
    shift_name: Optional[str]
    program_name: Optional[str]
    teacher_name: str
    attachments: List[HomeworkAttachmentOut]


def _validate_principal(db: Session, principal: Dict[str, Any]) -> Tuple[str, int]:
    user_type = str(principal.get("user_type") or "").lower()
    user_id = int(principal.get("id") or 0)
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    if user_type == "parent":
        row = db.query(Parent).filter(Parent.id == user_id, Parent.status == 1).first()
    elif user_type == "student":
        row = db.query(Student).filter(Student.id == user_id, Student.status == 1).first()
    else:
        user_type = "teacher"
        row = db.query(User).filter(User.id == user_id, User.status == 1).first()
    if row is None:
        raise HTTPException(status_code=403, detail="Active account required")
    if user_type == "teacher":
        db_version = int(getattr(row, "token_version", 1) or 1)
        token_version = principal.get("token_version")
        if token_version is not None and int(token_version) != db_version:
            raise HTTPException(status_code=401, detail="Token has been revoked")
        if token_version is None and db_version > 1:
            raise HTTPException(status_code=401, detail="Token has been revoked")
    return user_type, user_id


def _detect_attachment(data: bytes, original_name: str) -> Tuple[str, str]:
    """Return a trusted (content type, extension), rejecting disguised files."""
    suffix = Path(original_name or "").suffix.lower()
    if data.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") and suffix == ".doc":
        return "application/msword", ".doc"
    if data.startswith(b"PK\x03\x04") and suffix == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    return (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        ".docx",
                    )
        except (zipfile.BadZipFile, OSError):
            pass
    if suffix == ".txt" and b"\x00" not in data:
        try:
            data.decode("utf-8")
            return "text/plain", ".txt"
        except UnicodeDecodeError:
            pass
    raise HTTPException(
        status_code=400,
        detail="Attachments must be PDF, JPG, PNG, WebP, DOC, DOCX, or UTF-8 TXT files",
    )


def _safe_original_name(value: str, extension: str) -> str:
    name = Path(value or f"attachment{extension}").name
    name = re.sub(r"[^A-Za-z0-9._()\- ]+", "_", name).strip(" .")
    if not name:
        name = f"attachment{extension}"
    return name[:255]


def _resolve_schedule_shift(db: Session, schedule: LearningClassSchedule) -> int:
    if schedule.shift_id is not None:
        return int(schedule.shift_id)

    scoped_shift = db.execute(
        text("""
            SELECT DISTINCT shift_id
            FROM learning_time_slot_scopes
            WHERE time_slot_id = :time_slot_id
              AND shift_id IS NOT NULL
              AND (
                    (scope_type = 'grade' AND scope_id = :grade_id)
                    OR
                    (scope_type = 'grade_group' AND scope_id = :grade_group_id)
              )
            LIMIT 2
        """),
        {
            "time_slot_id": int(schedule.time_slot_id),
            "grade_id": schedule.grade_id,
            "grade_group_id": int(schedule.grade_group_id),
        },
    ).fetchall()
    shifts = {int(row[0]) for row in scoped_shift if row[0] is not None}

    if len(shifts) != 1:
        grade_filter = "l.gradeid = :grade_id" if schedule.grade_id else "g.group_id = :grade_group_id"
        grade_type_filter = ""
        if schedule.grade_type_id is not None:
            grade_type_filter = "AND (l.grade_type_id <=> :grade_type_id)"
        rows = db.execute(
            text(f"""
                SELECT DISTINCT l.shiftid
                FROM learning l
                JOIN grade g ON g.id = l.gradeid
                WHERE l.academicid = :academic_id
                  AND l.programid = :program_id
                  AND g.branch_id = :branch_id
                  AND {grade_filter}
                  {grade_type_filter}
                  AND l.shiftid IS NOT NULL
                LIMIT 2
            """),
            {
                "academic_id": int(schedule.academic_id),
                "program_id": int(schedule.program_id),
                "branch_id": int(schedule.branch_id),
                "grade_id": schedule.grade_id,
                "grade_group_id": int(schedule.grade_group_id),
                "grade_type_id": schedule.grade_type_id,
            },
        ).fetchall()
        shifts = {int(row[0]) for row in rows if row[0] is not None}

    if len(shifts) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This teaching schedule does not identify one class shift. "
                "Ask an administrator to open the class schedule and save its shift."
            ),
        )
    shift_id = shifts.pop()
    schedule.shift_id = shift_id
    return shift_id


def _homework_rows(
    db: Session,
    *,
    user_type: str,
    user_id: int,
    academic_id: int,
    homework_id: Optional[int],
    class_schedule_id: Optional[int],
    program_id: Optional[int],
    grade_id: Optional[int],
    grade_type_id: Optional[int],
    shift_id: Optional[int],
    date_from: Optional[date],
    date_to: Optional[date],
    student_id: Optional[int],
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"academic_id": academic_id, "user_id": user_id}
    filters = ["h.academic_id = :academic_id", "h.is_active = TRUE"]
    if user_type == "teacher":
        filters.append("h.teacher_id = :user_id")
    elif user_type == "parent":
        params["student_id"] = student_id
        filters.append("""
            EXISTS (
                SELECT 1
                FROM parents parent_scope
                JOIN learning l
                  ON FIND_IN_SET(
                       CAST(l.studentid AS CHAR CHARACTER SET utf8mb4)
                         COLLATE utf8mb4_unicode_ci,
                       REPLACE(COALESCE(parent_scope.myChilds, ''), ' ', '')
                         COLLATE utf8mb4_unicode_ci
                     ) > 0
                JOIN grade enrolled_grade ON enrolled_grade.id = l.gradeid
                WHERE parent_scope.id = :user_id
                  AND parent_scope.status = 1
                  AND (:student_id IS NULL OR l.studentid = :student_id)
                  AND l.academicid = h.academic_id
                  AND l.programid = h.program_id
                  AND l.shiftid = h.shift_id
                  AND (h.grade_id IS NULL OR l.gradeid = h.grade_id)
                  AND (h.grade_id IS NOT NULL OR enrolled_grade.group_id = h.grade_group_id)
                  AND (h.grade_type_id IS NULL OR l.grade_type_id <=> h.grade_type_id)
            )
        """)
    else:
        filters.append("""
            EXISTS (
                SELECT 1
                FROM learning l
                JOIN grade enrolled_grade ON enrolled_grade.id = l.gradeid
                WHERE l.studentid = :user_id
                  AND l.academicid = h.academic_id
                  AND l.programid = h.program_id
                  AND l.shiftid = h.shift_id
                  AND (h.grade_id IS NULL OR l.gradeid = h.grade_id)
                  AND (h.grade_id IS NOT NULL OR enrolled_grade.group_id = h.grade_group_id)
                  AND (h.grade_type_id IS NULL OR l.grade_type_id <=> h.grade_type_id)
            )
        """)
    if homework_id is not None:
        filters.append("h.id = :homework_id")
        params["homework_id"] = homework_id
    if class_schedule_id is not None:
        filters.append("h.class_schedule_id = :class_schedule_id")
        params["class_schedule_id"] = class_schedule_id
    if program_id is not None:
        filters.append("h.program_id = :program_id")
        params["program_id"] = program_id
    if grade_id is not None:
        filters.append("h.grade_id = :grade_id")
        params["grade_id"] = grade_id
    if grade_type_id is not None:
        filters.append("(h.grade_type_id <=> :grade_type_id)")
        params["grade_type_id"] = grade_type_id
    if shift_id is not None:
        filters.append("h.shift_id = :shift_id")
        params["shift_id"] = shift_id
    if date_from is not None:
        filters.append("h.homework_date >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        filters.append("h.homework_date <= :date_to")
        params["date_to"] = date_to

    rows = db.execute(
        text(f"""
            SELECT
                h.id, h.academic_id, h.class_schedule_id, h.branch_id,
                h.program_id, h.grade_group_id, h.grade_id,
                h.grade_type_id, h.shift_id, h.subject_id, h.teacher_id,
                h.title, h.description, h.homework_date, h.due_date, h.created_at,
                COALESCE(NULLIF(s.subject_name_us, ''), s.subject_name) AS subject_name,
                COALESCE(g.grade_name, gg.group_name) AS grade_name,
                gt.type_name AS grade_type_name,
                sh.shift_name,
                p.program_name,
                COALESCE(NULLIF(u.eName, ''), NULLIF(u.kName, ''), u.username) AS teacher_name
            FROM learning_homework h
            JOIN subjects s ON s.id = h.subject_id
            JOIN grade_group gg ON gg.id = h.grade_group_id
            LEFT JOIN grade g ON g.id = h.grade_id
            LEFT JOIN grade_type gt ON gt.id = h.grade_type_id
            LEFT JOIN shift sh ON sh.id = h.shift_id
            LEFT JOIN program p ON p.id = h.program_id
            JOIN users u ON u.id = h.teacher_id
            WHERE {' AND '.join(filters)}
            ORDER BY h.created_at DESC, h.id DESC
            LIMIT 1000
        """),
        params,
    ).fetchall()
    items = [dict(row._mapping) for row in rows]
    if not items:
        return []

    ids = [int(item["id"]) for item in items]
    attachments = (
        db.query(LearningHomeworkAttachment)
        .filter(LearningHomeworkAttachment.homework_id.in_(ids))
        .order_by(LearningHomeworkAttachment.id.asc())
        .all()
    )
    by_homework: Dict[int, List[Dict[str, Any]]] = {item_id: [] for item_id in ids}
    for attachment in attachments:
        by_homework[int(attachment.homework_id)].append(
            {
                "id": int(attachment.id),
                "file_url": attachment.file_url,
                "original_name": attachment.original_name,
                "content_type": attachment.content_type,
                "file_size": int(attachment.file_size),
            }
        )
    for item in items:
        class_parts = [
            str(item.get("grade_name") or "Class"),
            str(item.get("grade_type_name") or "").strip(),
            str(item.get("shift_name") or "").strip(),
        ]
        item["class_name"] = " · ".join(part for part in class_parts if part)
        item["attachments"] = by_homework[int(item["id"])]
    return items


@router.get("", response_model=List[HomeworkOut])
def list_homework(
    homework_id: Optional[int] = Query(None),
    class_schedule_id: Optional[int] = Query(None),
    program_id: Optional[int] = Query(None),
    grade_id: Optional[int] = Query(None),
    grade_type_id: Optional[int] = Query(None),
    shift_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    student_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    principal: Dict[str, Any] = Depends(get_user_info_from_token),
):
    """Current-year homework visible to this teacher, parent, or student."""
    user_type, user_id = _validate_principal(db, principal)
    return _homework_rows(
        db,
        user_type=user_type,
        user_id=user_id,
        academic_id=get_current_academic_id(db),
        homework_id=homework_id,
        class_schedule_id=class_schedule_id,
        program_id=program_id,
        grade_id=grade_id,
        grade_type_id=grade_type_id,
        shift_id=shift_id,
        date_from=date_from,
        date_to=date_to,
        student_id=student_id,
    )


@router.post("", response_model=HomeworkOut, status_code=status.HTTP_201_CREATED)
async def publish_homework(
    background_tasks: BackgroundTasks,
    class_schedule_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    homework_date: Optional[date] = Form(None),
    due_date: Optional[date] = Form(None),
    confirm_substitute: bool = Form(False),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Publish homework for an active-year class subject, including confirmed replacement teaching."""
    clean_title = title.strip()
    clean_description = description.strip()
    if not clean_title or len(clean_title) > 255:
        raise HTTPException(status_code=400, detail="Homework title must be 1 to 255 characters")
    if not clean_description or len(clean_description) > MAX_DESCRIPTION_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Homework description must be 1 to {MAX_DESCRIPTION_LENGTH} characters",
        )
    effective_homework_date = homework_date or date.today()
    if due_date is not None and due_date < effective_homework_date:
        raise HTTPException(status_code=400, detail="Due date cannot be before the homework date")

    active_academic_id = get_current_academic_id(db)
    schedule = (
        db.query(LearningClassSchedule)
        .filter(LearningClassSchedule.id == int(class_schedule_id))
        .first()
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="Teaching schedule not found")
    if not bool(schedule.is_active) or int(schedule.academic_id) != active_academic_id:
        raise HTTPException(
            status_code=409,
            detail="Homework can only be published from an active current-year teaching schedule",
        )

    shift_id = _resolve_schedule_shift(db, schedule)
    is_substitute = int(schedule.teacher_id) != int(current_user.id)
    if is_substitute and not confirm_substitute:
        raise HTTPException(
            status_code=409,
            detail="Confirm that you are replacing the assigned subject teacher before publishing",
        )

    uploads = [file for file in (files or []) if file.filename]
    if len(uploads) > MAX_ATTACHMENTS:
        raise HTTPException(status_code=400, detail=f"A maximum of {MAX_ATTACHMENTS} attachments is allowed")

    homework = LearningHomework(
        academic_id=active_academic_id,
        class_schedule_id=int(schedule.id),
        branch_id=int(schedule.branch_id),
        program_id=int(schedule.program_id),
        grade_group_id=int(schedule.grade_group_id),
        grade_id=schedule.grade_id,
        grade_type_id=schedule.grade_type_id,
        shift_id=shift_id,
        subject_id=int(schedule.subject_id),
        teacher_id=int(current_user.id),
        title=clean_title,
        description=clean_description,
        homework_date=effective_homework_date,
        due_date=due_date,
        is_active=True,
    )
    db.add(homework)
    db.flush()

    uploaded_urls: List[str] = []
    try:
        for upload in uploads:
            data = await upload.read()
            if not data:
                raise HTTPException(status_code=400, detail=f"{upload.filename}: file is empty")
            if len(data) > MAX_ATTACHMENT_BYTES:
                raise HTTPException(status_code=400, detail=f"{upload.filename}: file must be 10 MB or smaller")
            content_type, extension = _detect_attachment(data, upload.filename or "")
            original_name = _safe_original_name(upload.filename or "", extension)
            stored_name = f"h{int(homework.id)}_{uuid.uuid4().hex}{extension}"
            file_url = StorageService.upload_file(
                data,
                f"homework/{active_academic_id}",
                stored_name,
                content_type,
            )
            if not file_url:
                raise HTTPException(status_code=500, detail=f"Could not upload {original_name}")
            uploaded_urls.append(file_url)
            db.add(
                LearningHomeworkAttachment(
                    homework_id=int(homework.id),
                    file_url=file_url,
                    original_name=original_name,
                    content_type=content_type,
                    file_size=len(data),
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        for file_url in uploaded_urls:
            StorageService.delete_file(file_url)
        raise

    background_tasks.add_task(notify_parents_homework_published, int(homework.id))
    rows = _homework_rows(
        db,
        user_type="teacher",
        user_id=int(current_user.id),
        academic_id=active_academic_id,
        homework_id=int(homework.id),
        class_schedule_id=None,
        program_id=None,
        grade_id=None,
        grade_type_id=None,
        shift_id=None,
        date_from=None,
        date_to=None,
        student_id=None,
    )
    if not rows:
        raise HTTPException(status_code=500, detail="Homework was saved but could not be reloaded")
    return rows[0]


@router.delete("/{homework_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_homework(
    homework_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Hide a homework item; only its publishing teacher may remove it."""
    item = db.query(LearningHomework).filter(LearningHomework.id == homework_id).first()
    if item is None or not bool(item.is_active):
        raise HTTPException(status_code=404, detail="Homework not found")
    if int(item.teacher_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="You can only remove your own homework")
    if int(item.academic_id) != get_current_academic_id(db):
        raise HTTPException(status_code=409, detail="Only current-year homework can be changed")
    item.is_active = False
    db.commit()
    return None
