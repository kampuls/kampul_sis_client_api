"""
Migrate branch.director_signature and branch.stamp (MEDIUMBLOB) into
signature_url and stamp_url via StorageService (local / cloud per settings).

- Converts each blob to PNG (preserves transparency for stamps/signatures).
- If signature_url / stamp_url already exists, deletes the old file and replaces it.
- Uses the same upload folders as the certificate API:
    branches/signatures, branches/stamps

Examples:
  cd pama_api
  python scripts/migrate_branch_blob_to_urls.py --dry-run
  python scripts/migrate_branch_blob_to_urls.py
  python scripts/migrate_branch_blob_to_urls.py --branch-id 3
  python scripts/migrate_branch_blob_to_urls.py --clear-blob
"""

from __future__ import annotations

import argparse
import io
import sys
import uuid
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models.organization import Branch
from app.models.settings import SystemSettings
from app.services.storage_service import StorageService


@dataclass
class Counters:
    scanned: int = 0
    signature_migrated: int = 0
    stamp_migrated: int = 0
    skipped_no_signature_blob: int = 0
    skipped_no_stamp_blob: int = 0
    failed_invalid_signature: int = 0
    failed_invalid_stamp: int = 0
    failed_upload_signature: int = 0
    failed_upload_stamp: int = 0
    failed_other: int = 0


def blob_to_png(blob: bytes) -> bytes:
    """Decode image bytes and re-encode as PNG (keeps alpha when present)."""
    with Image.open(io.BytesIO(blob)) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
        elif img.mode != "RGB":
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()


def _has_blob(blob: Optional[bytes]) -> bool:
    return bool(blob) and len(blob) > 0


def upload_branch_asset(
    db: Session,
    branch: Branch,
    *,
    blob: bytes,
    url_attr: str,
    folder: str,
    filename_prefix: str,
    sys_settings: Optional[SystemSettings],
    dry_run: bool,
) -> Optional[str]:
    """Delete old URL file (if any), upload PNG, return new URL."""
    old_url = getattr(branch, url_attr)
    if old_url and not dry_run:
        StorageService.delete_file(old_url, sys_settings)

    if dry_run:
        return f"/uploads/{folder}/{filename_prefix}_{branch.id}_dryrun.png"

    filename = f"{filename_prefix}_{branch.id}_{uuid.uuid4().hex[:10]}.png"
    url = StorageService.upload_file(
        file_data=blob,
        folder=folder,
        filename=filename,
        content_type="image/png",
    )
    if not url:
        return None
    setattr(branch, url_attr, url)
    return url


def migrate_signature(
    db: Session,
    branch: Branch,
    sys_settings: Optional[SystemSettings],
    *,
    dry_run: bool,
    clear_blob: bool,
    counters: Counters,
) -> None:
    if not _has_blob(branch.director_signature):
        counters.skipped_no_signature_blob += 1
        return

    try:
        png_bytes = blob_to_png(branch.director_signature)
    except UnidentifiedImageError:
        counters.failed_invalid_signature += 1
        print(f"  branch {branch.id}: invalid director_signature image")
        return
    except Exception as e:
        counters.failed_other += 1
        print(f"  branch {branch.id}: signature convert error: {e}")
        return

    url = upload_branch_asset(
        db,
        branch,
        blob=png_bytes,
        url_attr="signature_url",
        folder="branches/signatures",
        filename_prefix="branch_signature",
        sys_settings=sys_settings,
        dry_run=dry_run,
    )
    if not url:
        counters.failed_upload_signature += 1
        print(f"  branch {branch.id}: signature upload failed")
        return

    if clear_blob and not dry_run:
        branch.director_signature = None

    counters.signature_migrated += 1
    print(f"  branch {branch.id} ({branch.branch_name}): signature_url -> {url}")


def migrate_stamp(
    db: Session,
    branch: Branch,
    sys_settings: Optional[SystemSettings],
    *,
    dry_run: bool,
    clear_blob: bool,
    counters: Counters,
) -> None:
    if not _has_blob(branch.stamp):
        counters.skipped_no_stamp_blob += 1
        return

    try:
        png_bytes = blob_to_png(branch.stamp)
    except UnidentifiedImageError:
        counters.failed_invalid_stamp += 1
        print(f"  branch {branch.id}: invalid stamp image")
        return
    except Exception as e:
        counters.failed_other += 1
        print(f"  branch {branch.id}: stamp convert error: {e}")
        return

    url = upload_branch_asset(
        db,
        branch,
        blob=png_bytes,
        url_attr="stamp_url",
        folder="branches/stamps",
        filename_prefix="branch_stamp",
        sys_settings=sys_settings,
        dry_run=dry_run,
    )
    if not url:
        counters.failed_upload_stamp += 1
        print(f"  branch {branch.id}: stamp upload failed")
        return

    if clear_blob and not dry_run:
        branch.stamp = None

    counters.stamp_migrated += 1
    print(f"  branch {branch.id} ({branch.branch_name}): stamp_url -> {url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate branch BLOBs to signature_url and stamp_url (PNG via StorageService)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate only; no DB or storage writes.",
    )
    parser.add_argument(
        "--clear-blob",
        action="store_true",
        help="After success, set director_signature / stamp to NULL.",
    )
    parser.add_argument(
        "--branch-id",
        type=int,
        default=None,
        help="Process a single branch id only.",
    )
    parser.add_argument(
        "--signature-only",
        action="store_true",
        help="Migrate director_signature only.",
    )
    parser.add_argument(
        "--stamp-only",
        action="store_true",
        help="Migrate stamp only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.signature_only and args.stamp_only:
        print("Use at most one of --signature-only and --stamp-only.")
        sys.exit(1)

    migrate_sig = not args.stamp_only
    migrate_stmp = not args.signature_only

    counters = Counters()
    db: Session = SessionLocal()
    try:
        q = db.query(Branch).order_by(Branch.id.asc())
        if args.branch_id is not None:
            q = q.filter(Branch.id == args.branch_id)
        branches = q.all()

        if args.branch_id is not None and not branches:
            print(f"No branch found with id={args.branch_id}")
            sys.exit(1)

        print(f"Found {len(branches)} branch(es).")
        if args.dry_run:
            print("DRY-RUN: no files or database changes will be saved.")

        sys_settings = db.query(SystemSettings).first()

        for branch in branches:
            counters.scanned += 1
            print(f"Processing branch {branch.id} ({branch.branch_name})...")
            try:
                if migrate_sig:
                    migrate_signature(
                        db,
                        branch,
                        sys_settings,
                        dry_run=args.dry_run,
                        clear_blob=args.clear_blob,
                        counters=counters,
                    )
                if migrate_stmp:
                    migrate_stamp(
                        db,
                        branch,
                        sys_settings,
                        dry_run=args.dry_run,
                        clear_blob=args.clear_blob,
                        counters=counters,
                    )
            except Exception as e:
                counters.failed_other += 1
                db.rollback()
                print(f"  branch {branch.id}: unexpected error: {e}")
                continue

        if not args.dry_run:
            db.commit()
            print("Committed database changes.")
        else:
            db.rollback()

    finally:
        db.close()

    print("")
    print("Migration summary")
    print("-----------------")
    print(f"Branches scanned:              {counters.scanned}")
    print(f"Signatures migrated:             {counters.signature_migrated}")
    print(f"Stamps migrated:                 {counters.stamp_migrated}")
    print(f"Skipped (no signature blob):   {counters.skipped_no_signature_blob}")
    print(f"Skipped (no stamp blob):         {counters.skipped_no_stamp_blob}")
    print(f"Failed (invalid signature):    {counters.failed_invalid_signature}")
    print(f"Failed (invalid stamp):          {counters.failed_invalid_stamp}")
    print(f"Failed (signature upload):     {counters.failed_upload_signature}")
    print(f"Failed (stamp upload):           {counters.failed_upload_stamp}")
    print(f"Failed (other):                  {counters.failed_other}")


if __name__ == "__main__":
    main()
