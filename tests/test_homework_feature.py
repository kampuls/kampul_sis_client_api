from io import BytesIO
from pathlib import Path
import zipfile

import pytest
from fastapi import HTTPException

from app.api.v1.homework import _detect_attachment


ROOT = Path(__file__).resolve().parents[1]


def test_homework_routes_are_registered_and_active_year_scoped():
    routes = (ROOT / "app/api/v1/__init__.py").read_text()
    endpoint = (ROOT / "app/api/v1/homework.py").read_text()

    assert "api_router.include_router(homework_router)" in routes
    assert "get_current_academic_id(db)" in endpoint
    assert "schedule.is_active" in endpoint
    assert "notify_parents_homework_published" in endpoint


def test_homework_substitute_requires_explicit_confirmation_and_records_publisher():
    endpoint = (ROOT / "app/api/v1/homework.py").read_text()

    assert "confirm_substitute: bool = Form(False)" in endpoint
    assert "if is_substitute and not confirm_substitute:" in endpoint
    assert "teacher_id=int(current_user.id)" in endpoint


def test_homework_migration_adds_shift_and_attachment_tables():
    migrations = (ROOT / "app/core/migrations.py").read_text()

    assert "_migrate_learning_homework(connection)" in migrations
    assert "ADD COLUMN shift_id INT NULL" in migrations
    assert "CREATE TABLE IF NOT EXISTS learning_homework (" in migrations
    assert "CREATE TABLE IF NOT EXISTS learning_homework_attachments (" in migrations
    assert "REFERENCES learning_class_schedules(id) ON DELETE SET NULL" in migrations
    assert "homework_date DATE NOT NULL" in migrations


def test_homework_parent_notifications_are_exact_class_scoped_and_unique():
    service = (ROOT / "app/services/homework_notification_service.py").read_text()

    assert "SELECT DISTINCT p.id" in service
    assert "FIND_IN_SET" in service
    assert "CHARACTER SET utf8mb4" in service
    assert service.count("COLLATE utf8mb4_unicode_ci") >= 2
    assert "l.academicid = :academic_id" in service
    assert "l.programid = :program_id" in service
    assert "l.shiftid = :shift_id" in service
    assert '"notification_key": f"homework:{homework.id}"' in service


def test_homework_feed_supports_calendar_and_parent_child_filters():
    endpoint = (ROOT / "app/api/v1/homework.py").read_text()

    assert "h.homework_date >= :date_from" in endpoint
    assert "h.homework_date <= :date_to" in endpoint
    assert "(:student_id IS NULL OR l.studentid = :student_id)" in endpoint
    assert "CHARACTER SET utf8mb4" in endpoint
    assert endpoint.count("COLLATE utf8mb4_unicode_ci") >= 2
    assert "h.program_id = :program_id" in endpoint
    assert "h.shift_id = :shift_id" in endpoint


@pytest.mark.parametrize(
    ("payload", "filename", "expected"),
    [
        (b"%PDF-1.7\n", "lesson.pdf", ("application/pdf", ".pdf")),
        (b"\xff\xd8\xff\xe0data", "photo.jpg", ("image/jpeg", ".jpg")),
        (b"hello teacher", "notes.txt", ("text/plain", ".txt")),
    ],
)
def test_homework_attachment_type_is_detected_from_content(payload, filename, expected):
    assert _detect_attachment(payload, filename) == expected


def test_homework_accepts_real_docx_container():
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", "<document />")

    content_type, extension = _detect_attachment(output.getvalue(), "work.docx")
    assert extension == ".docx"
    assert content_type.endswith("wordprocessingml.document")


def test_homework_rejects_disguised_executable():
    with pytest.raises(HTTPException) as exc:
        _detect_attachment(b"MZ\x90\x00binary", "worksheet.pdf")

    assert exc.value.status_code == 400
