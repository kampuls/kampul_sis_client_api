"""
Migrate students.image (MEDIUMBLOB) into users_resource.avatar.

What this script does:
1) Reads each student image blob.
2) Converts/compresses to JPEG (social-style profile compression).
3) Uploads using StorageService (local/cloud based on system settings).
4) Creates/updates users_resource row for user_type='student'.

Examples:
  python scripts/migrate_student_blob_to_user_resource.py --dry-run
  python scripts/migrate_student_blob_to_user_resource.py
  python scripts/migrate_student_blob_to_user_resource.py --force
  python scripts/migrate_student_blob_to_user_resource.py --force --clear-blob
"""

from __future__ import annotations

import argparse
import io
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

# Ensure project root is importable when running as:
#   python3 scripts/migrate_student_blob_to_user_resource.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models import Student, UserResource
from app.services.storage_service import StorageService


@dataclass
class Counters:
    scanned: int = 0
    migrated: int = 0
    skipped_no_blob: int = 0
    skipped_existing_avatar: int = 0
    failed_invalid_image: int = 0
    failed_upload: int = 0
    failed_other: int = 0


def compress_to_jpeg(
    blob: bytes,
    quality: int = 60,
    max_width: int = 1080,
    max_height: int = 1080,
) -> bytes:
    """
    Convert any incoming image bytes to compressed JPEG.
    Similar intent to mobile profile compression helper:
    - aggressive quality compression
    - constrained dimensions
    """
    with Image.open(io.BytesIO(blob)) as img:
        # Respect EXIF orientation first.
        img = ImageOps.exif_transpose(img)

        # JPEG does not support alpha channel, flatten transparent pixels to white.
        if img.mode in ("RGBA", "LA", "P"):
            converted = img.convert("RGBA")
            background = Image.new("RGBA", converted.size, (255, 255, 255, 255))
            img = Image.alpha_composite(background, converted).convert("RGB")
        else:
            img = img.convert("RGB")

        # Match profile-style size constraints.
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        out = io.BytesIO()
        img.save(
            out,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
        return out.getvalue()


def get_or_create_user_resource(db: Session, student_id: int) -> UserResource:
    resource = (
        db.query(UserResource)
        .filter(
            UserResource.user_id == student_id,
            UserResource.user_type == "student",
        )
        .first()
    )
    if resource is None:
        resource = UserResource(
            user_id=student_id,
            user_type="student",
            status=1,
        )
        db.add(resource)
        db.flush()
    return resource


def migrate_student(
    db: Session,
    student: Student,
    *,
    force: bool,
    clear_blob: bool,
    dry_run: bool,
    quality: int,
    max_width: int,
    max_height: int,
    counters: Counters,
) -> None:
    counters.scanned += 1

    if not student.image:
        counters.skipped_no_blob += 1
        return

    resource = get_or_create_user_resource(db, student.id)
    if resource.avatar:
        if not force:
            counters.skipped_existing_avatar += 1
            return
        elif not dry_run:
            # User requested: delete the file not just the path
            try:
                StorageService.delete_file(resource.avatar)
            except Exception as e:
                print(f"Failed to delete old avatar {resource.avatar}: {e}")

    try:
        compressed = compress_to_jpeg(
            student.image,
            quality=quality,
            max_width=max_width,
            max_height=max_height,
        )
    except UnidentifiedImageError:
        counters.failed_invalid_image += 1
        return
    except Exception as e:
        print(f"Failed to compress image for student {student.id}: {e}")
        counters.failed_other += 1
        return

    if dry_run:
        counters.migrated += 1
        return

    filename = f"student_avatar_{student.id}_{uuid.uuid4().hex[:10]}.jpg"
    avatar_url: Optional[str] = StorageService.upload_file(
        file_data=compressed,
        folder="avatars",
        filename=filename,
        content_type="image/jpeg",
    )
    if not avatar_url:
        counters.failed_upload += 1
        return

    resource.avatar = avatar_url
    if clear_blob:
        student.image = None

    counters.migrated += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate students.image blob to users_resource.avatar"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without writing DB/file changes.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing users_resource.avatar values.",
    )
    parser.add_argument(
        "--clear-blob",
        action="store_true",
        help="After successful migration, set students.image to NULL.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="How many students to process before commit (default: 100).",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=60,
        help="JPEG quality (default: 60).",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=1080,
        help="Maximum output width (default: 1080).",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        default=1080,
        help="Maximum output height (default: 1080).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    counters = Counters()

    db: Session = SessionLocal()
    try:
        students = db.query(Student).order_by(Student.id.asc()).all()
        print(f"Found {len(students)} students.")
        if args.dry_run:
            print("Running in DRY-RUN mode (no DB or file writes).")

        for idx, student in enumerate(students, start=1):
            try:
                migrate_student(
                    db,
                    student,
                    force=args.force,
                    clear_blob=args.clear_blob,
                    dry_run=args.dry_run,
                    quality=args.quality,
                    max_width=args.max_width,
                    max_height=args.max_height,
                    counters=counters,
                )
            except Exception as e:
                print(f"Failed to migrate student {student.id}: {e}")
                counters.failed_other += 1
                db.rollback()
                continue

            if not args.dry_run and idx % args.batch_size == 0:
                try:
                    db.commit()
                except Exception as e:
                    print(f"Batch commit failed at idx {idx}: {e}")
                    db.rollback()

        if not args.dry_run:
            try:
                db.commit()
            except Exception as e:
                print(f"Final commit failed: {e}")
                db.rollback()

    finally:
        db.close()

    print("")
    print("Migration summary")
    print("-----------------")
    print(f"Scanned students:           {counters.scanned}")
    print(f"Migrated avatars:           {counters.migrated}")
    print(f"Skipped (no blob):          {counters.skipped_no_blob}")
    print(f"Skipped (already avatar):   {counters.skipped_existing_avatar}")
    print(f"Failed (invalid image):     {counters.failed_invalid_image}")
    print(f"Failed (upload):            {counters.failed_upload}")
    print(f"Failed (other):             {counters.failed_other}")


if __name__ == "__main__":
    main()
