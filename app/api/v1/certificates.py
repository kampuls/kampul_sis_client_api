"""
Certificate management API endpoints.

Mirrors the legacy C# ControlCertificate / CertificateModelsList / CertificateSettings forms.

Endpoints:
  GET    /certificates/backgrounds              — list background_cert (filter: academic_id, program_id, cer_model)
  POST   /certificates/backgrounds              — create new background_cert record
  POST   /certificates/backgrounds/{id}/image   — upload background image, store URL
  PUT    /certificates/backgrounds/{id}          — update record fields
  DELETE /certificates/backgrounds/{id}          — delete record

  GET    /certificates/settings/{academic_id}   — get cert number settings for academic year
  POST   /certificates/settings                 — upsert cert settings

  GET    /certificates/students                 — list demo_cert students (filter: academic, branch, program, grade)
  POST   /certificates/generate-id              — generate next cer_id without saving (preview)
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core import get_db
from ...auth.dependencies import require_admin, get_current_active_user
from ...models.certificate import BackgroundCert, CertificateSettings, DemoCert
from ...models.organization import Branch
from ...models.student import Student
from ...models.user import User
from ...schemas.certificate import (
    BackgroundCertCreate,
    BackgroundCertResponse,
    BackgroundCertUpdate,
    BranchCertAssetResponse,
    CertIdGenerateRequest,
    CertIdGenerateResponse,
    CertIssueRequest,
    CertIssueResponse,
    CertIssueResultItem,
    CertificateSettingsResponse,
    CertificateSettingsUpsert,
    DemoCertStudentResponse,
)
from ...core.push_assets import (
    CERTIFICATE_PUSH_IMAGE_RELATIVE,
    ensure_certificate_push_image_for_push,
)
from ...services.storage_service import StorageService

router = APIRouter(prefix="/certificates", tags=["certificates"])


# ─────────────────────────────────────────────────────────────────────────────
# Lookup endpoints: Academic Years, Programs, Grades
# These query the REAL lookup tables (`academic`, `program`, `grade`)
# exactly as the C# ControlCertificate.cs does — not the content-management
# `academic_programs` table which is a different concept.
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/academics")
async def list_cert_academics(db: Session = Depends(get_db),
                              current_user: User = Depends(get_current_active_user)):
    """
    Return all academic years from the `academic` table, newest first.
    Mirrors C# LoadAllAcademics():
      SELECT id, academic_us_name FROM academic ORDER BY id DESC
    """
    rows = db.execute(text(
        "SELECT id, academic_name, academic_us_name, status FROM academic ORDER BY id DESC"
    )).mappings().all()
    return [{"id": r["id"], "name": r["academic_us_name"] or r["academic_name"], "is_active": r["status"] == 1} for r in rows]


@router.get("/programs")
async def list_cert_programs(db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_active_user)):
    """
    Return all programs from the `program` table.
    Mirrors C# LoadAllPrograms():
      SELECT id, program_name FROM program ORDER BY program_name ASC
    """
    rows = db.execute(text(
        "SELECT id, program_name, program_name_us, short_code FROM program ORDER BY program_name ASC"
    )).mappings().all()
    return [{"id": r["id"], "name": r["program_name_us"] or r["program_name"], "short_code": r.get("short_code")} for r in rows]


@router.get("/grades")
async def list_cert_grades(
    academic_id: Optional[int] = Query(None),
    program_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return grades filtered by academic/program/branch, using the learning table join.
    Mirrors C# LoadAllGradesWithDetails():
      SELECT DISTINCT g.id, g.grade_name, g.grade_type_id,
             l.academicid, l.programid, l.gradeid, s.branch
      FROM grade g
      LEFT JOIN learning l ON g.id = l.gradeid
      LEFT JOIN students s ON l.studentid = s.id
      ORDER BY g.grade_name ASC
    Also returns grade_group_id so Flutter can use it for background_cert grouping.
    """
    conditions = []
    params: dict = {}

    if academic_id is not None:
        conditions.append("l.academicid = :academic_id")
        params["academic_id"] = academic_id
    if program_id is not None:
        conditions.append("l.programid = :program_id")
        params["program_id"] = program_id
    if branch_id is not None:
        conditions.append("s.branch = :branch_id")
        params["branch_id"] = branch_id

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = text(f"""
        SELECT DISTINCT
            g.id,
            g.grade_name,
            g.group_Id AS grade_group_id,
            g.grade_type_id,
            b.id   AS branch_id,
            b.branch_name
        FROM grade g
        LEFT JOIN learning l ON g.id = l.gradeid
        LEFT JOIN students s ON l.studentid = s.id
        LEFT JOIN branch  b ON s.branch = b.id
        {where}
        ORDER BY b.branch_name ASC, g.grade_name ASC
    """)

    rows = db.execute(sql, params).mappings().all()
    # Use (grade_id, branch_id) as unique key so same-name grades in different branches show separately
    seen = set()
    result = []
    for r in rows:
        key = (r["id"], r["branch_id"])
        if key not in seen:
            seen.add(key)
            result.append({
                "id": r["id"],
                "name": r["grade_name"],
                "grade_group_id": r["grade_group_id"],
                "grade_type_id": r["grade_type_id"],
                "branch_id": r["branch_id"] or 0,
                "branch_name": r["branch_name"] or "Unknown Branch",
            })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Helper: generate next cer_id using certificate_settings logic
# (mirrors AddStudentsCertificate.cs L517-542)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_cer_id(academic_id: int, db: Session) -> str:
    """
    Auto-generate the next certificate number following the same algorithm
    as the C# desktop app.

    Algorithm:
      1. Load certificate_settings for the academic year
      2. Get last cer_id from demo_cert ORDER BY id DESC LIMIT 1
      3. Parse the sequence number (digits before the first '/')
      4. Increment by 1
      5. Build:  prefix + zeroPad(seq, digit) + year(2-digit) + surfix
    """
    settings = (
        db.query(CertificateSettings)
        .filter(CertificateSettings.academic_id == academic_id)
        .first()
    )

    prefix = settings.prefix if settings else ""
    surfix = settings.surfix if settings else "/PAMAIS"
    digit  = settings.digit  if settings else 4
    year   = settings.year   if settings else None

    # Get last cer_id
    last = db.query(DemoCert).order_by(DemoCert.id.desc()).first()
    seq = 1
    if last and last.cer_id:
        try:
            # The sequence number is always the leading digits (before the separator)
            raw_num = last.cer_id.split("/")[0]
            # Strip any non-digit prefix
            num_str = "".join(c for c in raw_num if c.isdigit())
            if num_str:
                seq = int(num_str) + 1
        except Exception:
            seq = 1

    year_str = str(year)[-2:] if year else ""
    cer_id = f"{prefix}{str(seq).zfill(digit)}{year_str}{surfix}"
    return cer_id



@router.post("/upload-image")
async def upload_certificate_image(
    file: UploadFile = File(...),
    type: str = Form("custom"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Upload an ad-hoc image (signature/stamp) for certificate generation.
    Returns the URL directly without saving to any specific database record.
    """
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, and WebP are allowed.",
        )

    contents = await file.read()
    
    import os
    import uuid
    ext = os.path.splitext(file.filename)[1]
    if not ext:
        if file.content_type == "image/png": ext = ".png"
        elif file.content_type == "image/webp": ext = ".webp"
        else: ext = ".jpg"
        
    filename = f"custom_{type}_{uuid.uuid4().hex}{ext}"

    image_url = StorageService.upload_file(
        file_data=contents,
        folder=f"certificates/custom_{type}s",
        filename=filename,
        content_type=file.content_type,
    )

    if not image_url:
        raise HTTPException(status_code=500, detail="Failed to upload image")

    return {"url": image_url}

# ─────────────────────────────────────────────────────────────────────────────
# Background Cert Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/backgrounds", response_model=List[BackgroundCertResponse])
async def list_backgrounds(
    academic_id: Optional[int] = Query(None),
    program_id: Optional[int] = Query(None),
    cer_model: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    List background_cert records with optional filters.
    Joined with program and academic tables for display names.
    """
    # Use raw SQL to get the joined data (program_name + academic_name)
    conditions = ["1=1"]
    params: dict = {}

    if academic_id:
        conditions.append("bg.academic_id = :academic_id")
        params["academic_id"] = academic_id
    if program_id:
        conditions.append("bg.program_id = :program_id")
        params["program_id"] = program_id
    if cer_model:
        conditions.append("bg.cer_model = :cer_model")
        params["cer_model"] = cer_model

    where = " AND ".join(conditions)
    sql = text(f"""
        SELECT
            bg.id,
            bg.program_id,
            bg.academic_id,
            bg.cer_model,
            bg.grade_group_ids,
            bg.grade_ids,
            bg.background_url,
            bg.signature_url,
            bg.stamp_url,
            bg.updated_at,
            bg.orientation,
            p.program_name,
            a.academic_name
        FROM background_cert bg
        LEFT JOIN program p ON bg.program_id = p.id
        LEFT JOIN academic a ON bg.academic_id = a.id
        WHERE {where}
        ORDER BY bg.academic_id DESC, bg.program_id ASC, bg.cer_model ASC
    """)

    rows = db.execute(sql, params).mappings().all()
    result = []
    for row in rows:
        import json as _json
        def _parse_ids(val):
            if not val:
                return None
            try:
                return _json.loads(val)
            except Exception:
                return None
        result.append(BackgroundCertResponse(
            id=row["id"],
            program_id=row["program_id"],
            academic_id=row["academic_id"],
            cer_model=row["cer_model"],
            grade_group_ids=_parse_ids(row["grade_group_ids"]),
            grade_ids=_parse_ids(row["grade_ids"]),
            background_url=row["background_url"],
            signature_url=row["signature_url"],
            stamp_url=row["stamp_url"],
            orientation=row["orientation"],
            updated_at=row["updated_at"],
            program_name=row["program_name"],
            academic_name=row["academic_name"],
        ))
    return result


@router.post(
    "/backgrounds",
    response_model=BackgroundCertResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_background(
    body: BackgroundCertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new background_cert record."""
    import json as _json

    # Serialize lists to JSON strings for DB storage
    grade_group_ids_str = _json.dumps(body.grade_group_ids) if body.grade_group_ids else None
    grade_ids_str = _json.dumps(body.grade_ids) if body.grade_ids else None

    # Allow multiple backgrounds per model (differentiated by grade_group_ids or grade_ids)

    try:
        record = BackgroundCert(
            program_id=body.program_id,
            academic_id=body.academic_id,
            cer_model=body.cer_model,
            grade_group_ids=grade_group_ids_str,
            grade_ids=grade_ids_str,
            orientation=body.orientation,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        def _parse_ids(val):
            if not val:
                return None
            try:
                return _json.loads(val)
            except Exception:
                return None

        return BackgroundCertResponse(
            id=record.id,
            program_id=record.program_id,
            academic_id=record.academic_id,
            cer_model=record.cer_model,
            grade_group_ids=_parse_ids(record.grade_group_ids),
            grade_ids=_parse_ids(record.grade_ids),
            background_url=record.background_url,
            orientation=record.orientation,
            updated_at=record.updated_at,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database Error: {str(e)}"
        )


@router.post("/backgrounds/{background_id}/image", response_model=BackgroundCertResponse)
async def upload_background_image(
    background_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Upload a background image for a certificate design.
    Stores the file via StorageService and saves the URL to `background_url`.
    Follows the same upload pattern as splash_ads.py.
    """
    record = db.query(BackgroundCert).filter(BackgroundCert.id == background_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Background cert record not found")

    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, and WebP are allowed.",
        )

    contents = await file.read()
    
    import os
    ext = os.path.splitext(file.filename)[1]
    if not ext:
        if file.content_type == "image/png": ext = ".png"
        elif file.content_type == "image/webp": ext = ".webp"
        else: ext = ".jpg"
        
    if record.background_url:
        # Extract existing filename to overwrite it and keep the same URL
        filename_to_use = record.background_url.split('/')[-1]
        # Remove any query parameters (like ?alt=media in Firebase)
        filename_to_use = filename_to_use.split('?')[0]
    else:
        filename_to_use = f"bg_model_{record.id}{ext}"

    image_url = StorageService.upload_file(
        file_data=contents,
        folder="certificates/backgrounds",
        filename=filename_to_use,
        content_type=file.content_type,
    )

    if not image_url:
        raise HTTPException(status_code=500, detail="Failed to upload background image")

    # Only delete the old file if the URL actually changed (e.g. first time upload or provider change)
    if record.background_url and record.background_url != image_url:
        from ...models.settings import SystemSettings
        sys_settings = db.query(SystemSettings).first()
        StorageService.delete_file(record.background_url, sys_settings)

    record.background_url = image_url
    db.commit()
    db.refresh(record)

    return BackgroundCertResponse(
        id=record.id,
        program_id=record.program_id,
        academic_id=record.academic_id,
        cer_model=record.cer_model,
        background_url=record.background_url,
        orientation=record.orientation,
        updated_at=record.updated_at,
    )


@router.post("/backgrounds/{background_id}/stamp", response_model=BackgroundCertResponse)
async def upload_background_stamp(
    background_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Upload a stamp image for a certificate design (Model).
    Stores the file via StorageService and saves the URL to `stamp_url`.
    """
    record = db.query(BackgroundCert).filter(BackgroundCert.id == background_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Background cert record not found")

    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, and WebP are allowed.",
        )

    contents = await file.read()
    
    import os
    ext = os.path.splitext(file.filename)[1]
    if not ext:
        if file.content_type == "image/png": ext = ".png"
        elif file.content_type == "image/webp": ext = ".webp"
        else: ext = ".jpg"
        
    if record.stamp_url:
        filename_to_use = record.stamp_url.split('/')[-1].split('?')[0]
    else:
        filename_to_use = f"bg_model_stamp_{record.id}{ext}"

    image_url = StorageService.upload_file(
        file_data=contents,
        folder="certificates/stamps",
        filename=filename_to_use,
        content_type=file.content_type,
    )

    if not image_url:
        raise HTTPException(status_code=500, detail="Failed to upload stamp image")

    if record.stamp_url and record.stamp_url != image_url:
        from ...models.settings import SystemSettings
        sys_settings = db.query(SystemSettings).first()
        StorageService.delete_file(record.stamp_url, sys_settings)

    record.stamp_url = image_url
    db.commit()
    db.refresh(record)

    return BackgroundCertResponse.model_validate(record)


@router.post("/backgrounds/{background_id}/signature", response_model=BackgroundCertResponse)
async def upload_background_signature(
    background_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Upload a signature image for a certificate design (Model).
    Stores the file via StorageService and saves the URL to `signature_url`.
    """
    record = db.query(BackgroundCert).filter(BackgroundCert.id == background_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Background cert record not found")

    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, and WebP are allowed.",
        )

    contents = await file.read()
    
    import os
    ext = os.path.splitext(file.filename)[1]
    if not ext:
        if file.content_type == "image/png": ext = ".png"
        elif file.content_type == "image/webp": ext = ".webp"
        else: ext = ".jpg"
        
    if record.signature_url:
        filename_to_use = record.signature_url.split('/')[-1].split('?')[0]
    else:
        filename_to_use = f"bg_model_signature_{record.id}{ext}"

    image_url = StorageService.upload_file(
        file_data=contents,
        folder="certificates/signatures",
        filename=filename_to_use,
        content_type=file.content_type,
    )

    if not image_url:
        raise HTTPException(status_code=500, detail="Failed to upload signature image")

    if record.signature_url and record.signature_url != image_url:
        from ...models.settings import SystemSettings
        sys_settings = db.query(SystemSettings).first()
        StorageService.delete_file(record.signature_url, sys_settings)

    record.signature_url = image_url
    db.commit()
    db.refresh(record)

    return BackgroundCertResponse.model_validate(record)


@router.put("/backgrounds/{background_id}", response_model=BackgroundCertResponse)
async def update_background(
    background_id: int,
    body: BackgroundCertUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update metadata fields of a background_cert record."""
    import json as _json
    record = db.query(BackgroundCert).filter(BackgroundCert.id == background_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    update_data = body.model_dump(exclude_unset=True)
    # Convert list fields to JSON strings
    if "grade_group_ids" in update_data:
        update_data["grade_group_ids"] = _json.dumps(update_data["grade_group_ids"]) if update_data["grade_group_ids"] else None
    if "grade_ids" in update_data:
        update_data["grade_ids"] = _json.dumps(update_data["grade_ids"]) if update_data["grade_ids"] else None

    for key, val in update_data.items():
        setattr(record, key, val)

    db.commit()
    db.refresh(record)

    def _parse_ids(val):
        if not val:
            return None
        try:
            return _json.loads(val)
        except Exception:
            return None

    return BackgroundCertResponse(
        id=record.id,
        program_id=record.program_id,
        academic_id=record.academic_id,
        cer_model=record.cer_model,
        grade_group_ids=_parse_ids(record.grade_group_ids),
        grade_ids=_parse_ids(record.grade_ids),
        background_url=record.background_url,
        orientation=record.orientation,
        updated_at=record.updated_at,
    )


@router.delete("/backgrounds/{background_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_background(
    background_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a background_cert record and its uploaded image file."""
    record = db.query(BackgroundCert).filter(BackgroundCert.id == background_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if record.background_url:
        from ...models.settings import SystemSettings
        sys_settings = db.query(SystemSettings).first()
        StorageService.delete_file(record.background_url, sys_settings)

    db.delete(record)
    db.commit()
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Certificate Settings Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/settings/{academic_id}", response_model=CertificateSettingsResponse)
async def get_cert_settings(
    academic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get certificate number format settings for a specific academic year."""
    obj = (
        db.query(CertificateSettings)
        .filter(CertificateSettings.academic_id == academic_id)
        .first()
    )
    if not obj:
        # Return defaults if not configured yet
        return CertificateSettingsResponse(
            id=0,
            academic_id=academic_id,
            prefix="",
            surfix="/PAMAIS",
            digit=4,
            year=None,
            sample_id="0000/PAMAIS",
        )
    return CertificateSettingsResponse.from_orm_with_sample(obj)


@router.post("/settings", response_model=CertificateSettingsResponse)
async def upsert_cert_settings(
    body: CertificateSettingsUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create or update certificate number format settings for one academic year."""
    obj = (
        db.query(CertificateSettings)
        .filter(CertificateSettings.academic_id == body.academic_id)
        .first()
    )
    if obj:
        obj.prefix = body.prefix
        obj.surfix = body.surfix
        obj.digit  = body.digit
        obj.year   = body.year
    else:
        obj = CertificateSettings(**body.model_dump())
        db.add(obj)

    db.commit()
    db.refresh(obj)
    return CertificateSettingsResponse.from_orm_with_sample(obj)


# ─────────────────────────────────────────────────────────────────────────────
# Demo Cert Student Listing
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/students", response_model=List[DemoCertStudentResponse])
async def list_cert_students(
    academic_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    program_id: Optional[int] = Query(None),
    grade_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    List students eligible for certificates, with their certificate status.
    Queries the `learning` table (enrolled students) and LEFT JOINs `demo_cert`.
    """
    import logging
    logger = logging.getLogger(__name__)

    # ── Filters for the inner DISTINCT subquery (learning table, no alias) ──
    inner = ["academicid IS NOT NULL"]
    params: dict = {}

    if academic_id:
        inner.append("academicid = :academic_id")
        params["academic_id"] = academic_id
    if program_id:
        inner.append("programid = :program_id")
        params["program_id"] = program_id
    if grade_id:
        inner.append("gradeid = :grade_id")
        params["grade_id"] = grade_id

    inner_where = " AND ".join(inner)

    # ── Filters for the outer query (joined students table available) ──
    # Historical years include now-inactive students (past enrollees who
    # have since left must still be certifiable).
    from ...utils.academic_year import is_historical_academic_year

    params["historical"] = (
        1 if academic_id and is_historical_academic_year(db, academic_id) else 0
    )
    outer = ["(s.status = 1 OR :historical = 1)"]
    if branch_id:
        outer.append("s.branch = :branch_id")
        params["branch_id"] = branch_id

    outer_where = " AND ".join(outer)

    sql = text(f"""
        SELECT
            COALESCE(dc.id, 0)        AS id,
            s.id                       AS student_id,
            dc.cer_id,
            dc.cer_model               AS cer_model,
            COALESCE(dc.is_public, 0)  AS is_public,
            lb.academicid              AS academic_id,
            lb.programid               AS program_id,
            lb.gradeid                 AS grade_id,
            dc.grade_type_id,
            dc.nittes_id,
            dc.created_at,
            dc.updated_at,

            s.studentid,
            s.kName   AS k_name,
            s.eName   AS e_name,
            s.gender,
            s.dob,
            (
                SELECT ur.avatar
                FROM users_resource ur
                WHERE ur.user_id = s.id
                  AND ur.user_type = 'student'
                  AND ur.avatar IS NOT NULL
                  AND ur.avatar != ''
                LIMIT 1
            )                 AS image,
            s.branch  AS branch_id,

            a.academic_name,
            a.academic_us_name,
            p.program_name,
            p.program_name_us,
            p.short_code AS program_short_code,
            g.grade_name,
            g.grade_name_us,
            g.group_Id AS grade_group_id,
            gs.us_grade,
            gs.kh_grade,

            b.branch_name,
            b.address_english,
            b.director_kName AS director_kname,
            b.director_eName AS director_ename,
            b.director_signature_path,
            b.stamp_path,
            b.signature_url,
            b.stamp_url,

            dc.snapshot_background_url,
            dc.snapshot_signature_url,
            dc.snapshot_stamp_url,
            dc.snapshot_cert_date,
            dc.snapshot_director_kname,
            dc.snapshot_director_ename,
            dc.snapshot_principal_label,
            dc.snapshot_address_prefix,
            dc.snapshot_date_format,

            (
                SELECT u.kName
                FROM class_teachers ct2
                JOIN users u ON ct2.teacher_id = u.id
                WHERE ct2.academic_id = lb.academicid
                  AND ct2.program_id  = lb.programid
                  AND ct2.grade_id    = lb.gradeid
                LIMIT 1
            ) AS teacher_kname,
            (
                SELECT u.eName
                FROM class_teachers ct2
                JOIN users u ON ct2.teacher_id = u.id
                WHERE ct2.academic_id = lb.academicid
                  AND ct2.program_id  = lb.programid
                  AND ct2.grade_id    = lb.gradeid
                LIMIT 1
            ) AS teacher_ename

        FROM (
            SELECT DISTINCT studentid, academicid, programid, gradeid
            FROM learning
            WHERE {inner_where}
        ) lb
        JOIN students s              ON s.id           = lb.studentid
        LEFT JOIN academic a         ON a.id           = lb.academicid
        LEFT JOIN program p          ON p.id           = lb.programid
        LEFT JOIN grade g            ON g.id           = lb.gradeid
        JOIN demo_cert dc
               ON dc.student_id  = s.id
              AND dc.academic_id = lb.academicid
              AND dc.program_id  = lb.programid
              AND dc.grade_id    = lb.gradeid
        LEFT JOIN grade_scale gs     ON gs.id = dc.nittes_id
        LEFT JOIN branch b           ON b.id           = s.branch
        WHERE {outer_where}
        ORDER BY s.kName, s.eName
    """)

    import json
    try:
        rows = db.execute(sql, params).mappings().all()

        # Fetch background certs to resolve Priority (Grade > Group > Default)
        bg_where = []
        bg_params = {}
        if academic_id:
            bg_where.append("academic_id = :academic_id")
            bg_params["academic_id"] = academic_id
        if program_id:
            bg_where.append("program_id = :program_id")
            bg_params["program_id"] = program_id
        
        bg_sql = "SELECT academic_id, program_id, cer_model, grade_group_ids, grade_ids, background_url, signature_url, stamp_url, orientation, updated_at FROM background_cert"
        if bg_where:
            bg_sql += " WHERE " + " AND ".join(bg_where)
        bg_sql += " ORDER BY updated_at DESC"
            
        bg_rows = db.execute(text(bg_sql), bg_params).mappings().all()
        
        bg_cache = []
        for bg in bg_rows:
            try:
                g_groups = json.loads(bg["grade_group_ids"]) if bg["grade_group_ids"] else []
            except Exception:
                g_groups = []
            try:
                g_ids = json.loads(bg["grade_ids"]) if bg["grade_ids"] else []
            except Exception:
                g_ids = []
            bg_cache.append({
                "academic_id": bg["academic_id"],
                "program_id": bg["program_id"],
                "cer_model": bg["cer_model"],
                "grade_group_ids": g_groups,
                "grade_ids": g_ids,
                "background_url": bg["background_url"],
                "signature_url": bg["signature_url"],
                "stamp_url": bg["stamp_url"],
                "orientation": bg["orientation"] or "landscape"
            })

        def find_best_bg(acid, proid, model, gid, ggroupid):
            possible = [b for b in bg_cache if b["academic_id"] == acid and b["program_id"] == proid and b["cer_model"] == model]
                
            # Priority 1: Exact grade match
            for b in possible:
                if b["grade_ids"] and gid in b["grade_ids"]:
                    return b
            # Priority 2: Grade Group match
            for b in possible:
                if b["grade_group_ids"] and ggroupid in b["grade_group_ids"]:
                    return b
            # Priority 3: Default (no grade_ids AND no grade_group_ids)
            for b in possible:
                if not b["grade_ids"] and not b["grade_group_ids"]:
                    return b
            return None

        results = []
        for r in rows:
            r_dict = dict(r)
            r_dict["is_public"] = bool(r_dict.get("is_public"))
            
            bg = find_best_bg(
                r_dict["academic_id"], 
                r_dict["program_id"], 
                r_dict.get("cer_model") or 1,
                r_dict["grade_id"], 
                r_dict["grade_group_id"]
            )
            
            # Use the matched background design parameters
            if bg:
                r_dict["cer_model"] = bg["cer_model"]
                r_dict["background_url"] = bg["background_url"]
                r_dict["orientation"] = bg["orientation"]
                # Override branch signature and stamp with model signature and stamp if present
                if bg.get("signature_url"):
                    r_dict["signature_url"] = bg["signature_url"]
                if bg.get("stamp_url"):
                    r_dict["stamp_url"] = bg["stamp_url"]
            else:
                if not r_dict.get("cer_model"):
                    r_dict["cer_model"] = 1
                r_dict["background_url"] = None
                r_dict["orientation"] = "landscape"
            
            results.append(DemoCertStudentResponse(**r_dict))
            
        return results
    except Exception as exc:
        logger.error("list_cert_students SQL error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {exc}",
        )



# ─────────────────────────────────────────────────────────────────────────────
# Certificate ID Generation (preview — does NOT save)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/generate-id", response_model=CertIdGenerateResponse)
async def generate_cert_id(
    body: CertIdGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Generate the next certificate number without saving.
    Useful for previewing what the ID will be before the admin confirms.
    """
    cer_id = _generate_cer_id(body.academic_id, db)
    return CertIdGenerateResponse(cer_id=cer_id)


# ─────────────────────────────────────────────────────────────────────────────
# Branch Certificate Assets (signature + stamp URL upload)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/branches", response_model=List[BranchCertAssetResponse])
async def list_cert_branches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all branches with their current signature/stamp URLs."""
    branches = db.query(Branch).order_by(Branch.branch_name).all()
    return [
        BranchCertAssetResponse(
            branch_id=b.id,
            branch_name=b.branch_name,
            signature_url=b.signature_url,
            stamp_url=b.stamp_url,
            director_kname=b.director_kName,
            director_ename=b.director_eName,
        )
        for b in branches
    ]


@router.post("/branches/{branch_id}/signature", response_model=BranchCertAssetResponse)
async def upload_branch_signature(
    branch_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Upload a director signature image for a branch.
    Stores via StorageService and saves the URL to branch.signature_url.
    """
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    allowed = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WebP images are accepted")

    contents = await file.read()
    url = StorageService.upload_file(
        file_data=contents,
        folder="branches/signatures",
        filename=file.filename,
        content_type=file.content_type,
    )
    if not url:
        raise HTTPException(status_code=500, detail="Upload failed")

    # We intentionally do NOT delete the old file so that historically issued certificates
    # (which saved a snapshot of the old URL) do not break.
    

    branch.signature_url = url
    db.commit()
    db.refresh(branch)
    return BranchCertAssetResponse(
        branch_id=branch.id,
        branch_name=branch.branch_name,
        signature_url=branch.signature_url,
        stamp_url=branch.stamp_url,
        director_kname=branch.director_kName,
        director_ename=branch.director_eName,
    )


@router.delete("/branches/{branch_id}/signature", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch_signature(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Remove the signature image for a branch."""
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    if branch.signature_url:
        from ...models.settings import SystemSettings
        sys = db.query(SystemSettings).first()
        StorageService.delete_file(branch.signature_url, sys)
    branch.signature_url = None
    db.commit()
    return None


@router.post("/branches/{branch_id}/stamp", response_model=BranchCertAssetResponse)
async def upload_branch_stamp(
    branch_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Upload a school stamp image for a branch.
    Stores via StorageService and saves the URL to branch.stamp_url.
    """
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    allowed = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WebP images are accepted")

    contents = await file.read()
    url = StorageService.upload_file(
        file_data=contents,
        folder="branches/stamps",
        filename=file.filename,
        content_type=file.content_type,
    )
    if not url:
        raise HTTPException(status_code=500, detail="Upload failed")

    # We intentionally do NOT delete the old file so that historically issued certificates
    # (which saved a snapshot of the old URL) do not break.
    

    branch.stamp_url = url
    db.commit()
    db.refresh(branch)
    return BranchCertAssetResponse(
        branch_id=branch.id,
        branch_name=branch.branch_name,
        signature_url=branch.signature_url,
        stamp_url=branch.stamp_url,
        director_kname=branch.director_kName,
        director_ename=branch.director_eName,
    )


@router.delete("/branches/{branch_id}/stamp", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch_stamp(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Remove the stamp image for a branch."""
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    if branch.stamp_url:
        from ...models.settings import SystemSettings
        sys = db.query(SystemSettings).first()
        StorageService.delete_file(branch.stamp_url, sys)
    branch.stamp_url = None
    db.commit()
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Certificate Issue / Re-Issue
# ─────────────────────────────────────────────────────────────────────────────


def _student_display_name(student: Student) -> str:
    k = (student.kName or "").strip()
    e = (student.eName or "").strip()
    if k and e:
        return f"{k} ({e})"
    return k or e or "Your child"


def _send_certificate_push_notifications_task(
    issued_items: List[dict],
) -> None:
    """
    Notify parents when a public certificate is issued.
    Runs in a background task after POST /certificates/issue completes.
    """
    import logging

    from ...core.database import SessionLocal
    from ...services.notification_service import (
        get_parent_device_tokens,
        send_app_rich_push_notification,
    )

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    ensure_certificate_push_image_for_push()
    try:
        for item in issued_items:
            if not item.get("is_public"):
                continue
            student_id = int(item["student_id"])
            cer_id = (item.get("cer_id") or "").strip()
            student = db.query(Student).filter(Student.id == student_id).first()
            name = _student_display_name(student) if student else "Your child"

            tokens = get_parent_device_tokens(db, student_id)
            if not tokens:
                logger.info(
                    "[Certificates] No parent tokens for student %s", student_id
                )
                continue

            title = "New certificate from school"
            body = f"{name} has a new certificate. Tap to view."
            payload = {
                "type": "student_certificate",
                "student_id": str(student_id),
                "cer_id": cer_id,
                "title": title,
                "body": body,
                "image_url": CERTIFICATE_PUSH_IMAGE_RELATIVE,
            }
            try:
                # Data-only: parent app shows one rich local notification with the
                # certificate artwork (not a separate FCM text/icon tray).
                send_app_rich_push_notification(
                    device_tokens=tokens,
                    title=title,
                    body=body,
                    data=payload,
                    db=db,
                )
                logger.info(
                    "[Certificates] Sent student_certificate push for student %s (%s tokens)",
                    student_id,
                    len(tokens),
                )
            except Exception as exc:
                logger.warning(
                    "[Certificates] Push failed for student %s: %s",
                    student_id,
                    exc,
                )
    except Exception as exc:
        logger.exception("[Certificates] Background certificate push failed: %s", exc)
    finally:
        db.close()


@router.post("/issue", response_model=CertIssueResponse)
async def issue_certificates(
    body: CertIssueRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Issue or re-issue certificates for a batch of students.

    - If no demo_cert row exists for (student, academic, program, grade),
      a new one is created with a fresh cer_id.
    - If a row already exists (re-issue), the snapshot data is updated
      and the cer_id is KEPT (cert number stays the same).
    - All snapshot fields are saved so the certificate always
      reproduces exactly what was shown when first generated.
    """
    import logging
    logger = logging.getLogger(__name__)

    results: list[CertIssueResultItem] = []

    for item in body.students:
        try:
            existing = (
                db.query(DemoCert)
                .filter(
                    DemoCert.student_id  == item.student_id,
                    DemoCert.academic_id == item.academic_id,
                    DemoCert.program_id  == item.program_id,
                    DemoCert.grade_id    == item.grade_id,
                )
                .first()
            )

            was_reissued = existing is not None

            if existing:
                # Re-issue: keep existing cer_id, update snapshot
                existing.cer_model              = item.cer_model
                existing.grade_type_id          = item.grade_type_id
                existing.nittes_id              = item.nittes_id
                existing.snapshot_background_url = item.snapshot_background_url
                existing.snapshot_signature_url  = item.snapshot_signature_url
                existing.snapshot_stamp_url      = item.snapshot_stamp_url
                existing.is_public              = 1 if item.is_public else 0
                if item.snapshot_cert_date is not None:
                    existing.snapshot_cert_date = item.snapshot_cert_date
                if item.snapshot_director_kname is not None:
                    existing.snapshot_director_kname = item.snapshot_director_kname
                if item.snapshot_director_ename is not None:
                    existing.snapshot_director_ename = item.snapshot_director_ename
                if item.snapshot_principal_label is not None:
                    existing.snapshot_principal_label = item.snapshot_principal_label
                if item.snapshot_address_prefix is not None:
                    existing.snapshot_address_prefix = item.snapshot_address_prefix
                if item.snapshot_date_format is not None:
                    existing.snapshot_date_format = item.snapshot_date_format
                db.flush()
                record = existing
            else:
                # First issue: generate a new cer_id
                cer_id = _generate_cer_id(body.academic_id, db)
                record = DemoCert(
                    student_id              = item.student_id,
                    cer_id                  = cer_id,
                    cer_model               = item.cer_model,
                    academic_id             = item.academic_id,
                    program_id              = item.program_id,
                    grade_id                = item.grade_id,
                    grade_type_id           = item.grade_type_id,
                    nittes_id               = item.nittes_id,
                    is_public               = 1 if item.is_public else 0,
                    snapshot_background_url = item.snapshot_background_url,
                    snapshot_signature_url  = item.snapshot_signature_url,
                    snapshot_stamp_url      = item.snapshot_stamp_url,
                    snapshot_cert_date      = item.snapshot_cert_date,
                    snapshot_director_kname = item.snapshot_director_kname,
                    snapshot_director_ename = item.snapshot_director_ename,
                    snapshot_principal_label= item.snapshot_principal_label,
                    snapshot_address_prefix = item.snapshot_address_prefix,
                    snapshot_date_format    = item.snapshot_date_format,
                )
                db.add(record)
                db.flush()  # get ID without committing

            results.append(CertIssueResultItem(
                student_id   = item.student_id,
                cer_id       = record.cer_id or "",
                demo_cert_id = record.id,
                was_reissued = was_reissued,
                is_public    = bool(record.is_public),
            ))

        except Exception as exc:
            logger.error("issue_certificates error for student %s: %s",
                         item.student_id, exc, exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to issue cert for student {item.student_id}: {exc}",
            )

    db.commit()

    if body.send_push_notification and results:
        push_items = [
            {
                "student_id": r.student_id,
                "cer_id": r.cer_id,
                "is_public": r.is_public,
            }
            for r in results
        ]
        background_tasks.add_task(
            _send_certificate_push_notifications_task,
            push_items,
        )

    return CertIssueResponse(issued=results, total=len(results))


# ─────────────────────────────────────────────────────────────────────────────
# Public Certificates (For Parents/Students)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/public/{student_id}", response_model=List[DemoCertStudentResponse])
async def get_public_certificates(
    student_id: int,
    academic_id: Optional[int] = Query(
        None,
        gt=0,
        description="Optional academic year; omit to return every academic year",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get public certificates for a specific student across every academic year.
    Pass ``academic_id`` only when the caller wants to view one year.
    Matches the student by kName, eName, and dob to ensure past certificates
    are fetched even if the student was assigned a new ID.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Check permissions: Admin, the student themselves, or the student's parent
    user_role = getattr(current_user, "role", None)
    user_id   = getattr(current_user, "id", None)
    logger.info(
        "[public-certs] student_id=%s  caller_id=%s  caller_role=%s",
        student_id, user_id, user_role,
    )

    is_admin = user_role == 1
    if not is_admin:
        perm_check = text("""
            SELECT COUNT(*) FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            WHERE rp.role_id = :role_id
            AND p.permission_name IN ('AdminViewApp', 'AdminUpdateApp')
        """)
        perm_count = db.execute(perm_check, {"role_id": user_role or 0}).scalar()
        if perm_count and perm_count > 0:
            is_admin = True
            logger.info("[public-certs] caller has admin permission via role_permissions")

    is_allowed = is_admin
    if is_admin:
        logger.info("[public-certs] caller is admin — allowed")

    if not is_allowed and user_role == "student":
        if user_id == student_id:
            is_allowed = True
            logger.info("[public-certs] caller is the student themselves — allowed")

    if not is_allowed and user_role == "parent":
        # Check if student is in parent's myChilds
        parent_row = db.execute(
            text("SELECT myChilds FROM parents WHERE id = :uid LIMIT 1"),
            {"uid": user_id}
        ).fetchone()

        if parent_row:
            my_childs_raw = parent_row[0]
            logger.info("[public-certs] parent id=%s myChilds=%r", user_id, my_childs_raw)
            if my_childs_raw:
                child_ids = [cid.strip() for cid in my_childs_raw.split(',') if cid.strip()]
                logger.info("[public-certs] parsed child_ids=%s  checking for student_id=%s", child_ids, student_id)
                if str(student_id) in child_ids:
                    is_allowed = True
                    logger.info("[public-certs] student_id=%s is in parent's myChilds — allowed", student_id)
                else:
                    logger.warning("[public-certs] student_id=%s NOT in parent's myChilds=%s", student_id, child_ids)
            else:
                logger.warning("[public-certs] parent id=%s has empty myChilds", user_id)
        else:
            logger.warning("[public-certs] no parent row found for id=%s", user_id)

    if not is_allowed:
        logger.warning(
            "[public-certs] DENIED student_id=%s caller_id=%s role=%s",
            student_id, user_id, user_role,
        )
        raise HTTPException(status_code=403, detail="Not authorized to view these certificates")

    try:
        academic_filter = ""
        params = {"student_id": student_id}
        if academic_id is not None:
            academic_filter = "AND dc.academic_id = :academic_id"
            params["academic_id"] = academic_id

        sql = text(f"""
            SELECT
                dc.id,
                s.id                       AS student_id,
                dc.cer_id,
                dc.cer_model,
                dc.academic_id,
                dc.program_id,
                dc.grade_type_id,
                dc.grade_id,
                dc.nittes_id,
                s.studentid,
                s.kName                    AS k_name,
                s.eName                    AS e_name,
                s.gender,
                s.dob,
                (
                    SELECT ur.avatar
                    FROM users_resource ur
                    WHERE ur.user_id = s.id
                      AND ur.user_type = 'student'
                      AND ur.avatar IS NOT NULL
                      AND ur.avatar != ''
                    LIMIT 1
                )                          AS image,
                b.id                       AS branch_id,
                b.branch_name,
                b.address_english,
                b.director_kName           AS director_kname,
                b.director_eName           AS director_ename,
                b.director_signature_path,
                b.stamp_path,
                b.signature_url,
                b.stamp_url,
                a.academic_name,
                a.academic_us_name,
                p.program_name,
                p.program_name_us,
                p.short_code AS program_short_code,
                g.grade_name,
                g.grade_name_us,
                g.group_Id AS grade_group_id,
                gs.us_grade,
                gs.kh_grade,
                
                dc.snapshot_background_url,
                dc.snapshot_signature_url,
                dc.snapshot_stamp_url,
                dc.snapshot_cert_date,
                dc.snapshot_director_kname,
                dc.snapshot_director_ename,
                dc.snapshot_principal_label,
                dc.snapshot_address_prefix,
                dc.snapshot_date_format,
                
                (
                    SELECT u.kName
                    FROM class_teachers ct2
                    JOIN users u ON ct2.teacher_id = u.id
                    WHERE ct2.academic_id = dc.academic_id
                      AND ct2.program_id  = dc.program_id
                      AND ct2.grade_id    = dc.grade_id
                    LIMIT 1
                ) AS teacher_kname,
                (
                    SELECT u.eName
                    FROM class_teachers ct2
                    JOIN users u ON ct2.teacher_id = u.id
                    WHERE ct2.academic_id = dc.academic_id
                      AND ct2.program_id  = dc.program_id
                      AND ct2.grade_id    = dc.grade_id
                    LIMIT 1
                ) AS teacher_ename,
                dc.is_public,
                dc.created_at,
                dc.updated_at
            FROM demo_cert dc
            JOIN students s ON dc.student_id = s.id
            JOIN students target ON target.id = :student_id
            LEFT JOIN academic a ON a.id = dc.academic_id
            LEFT JOIN program p  ON p.id = dc.program_id
            LEFT JOIN grade g    ON g.id = dc.grade_id
            LEFT JOIN grade_scale gs ON gs.id = dc.nittes_id
            LEFT JOIN branch b ON b.id = s.branch
            WHERE 1=1
              AND s.kName <=> target.kName
              AND s.eName <=> target.eName
              AND s.dob <=> target.dob
              {academic_filter}
            ORDER BY dc.created_at DESC
        """)

        rows = db.execute(sql, params).mappings().all()

        bg_sql = "SELECT academic_id, program_id, cer_model, grade_group_ids, grade_ids, background_url, orientation, updated_at FROM background_cert"
        bg_rows = db.execute(text(bg_sql)).mappings().all()
        
        bg_cache = []
        import json
        for bg in bg_rows:
            g_groups = []
            g_ids = []
            try:
                g_groups = json.loads(bg["grade_group_ids"]) if bg["grade_group_ids"] else []
            except:
                pass
            try:
                g_ids = json.loads(bg["grade_ids"]) if bg["grade_ids"] else []
            except:
                pass
            bg_cache.append({
                "academic_id": bg["academic_id"],
                "program_id": bg["program_id"],
                "cer_model": bg["cer_model"],
                "grade_group_ids": g_groups,
                "grade_ids": g_ids,
                "background_url": bg["background_url"],
                "orientation": bg["orientation"] or "landscape"
            })

        def _get_live_bg(acid, proid, model, gid, ggroupid):
            possible = [b for b in bg_cache if b["academic_id"] == acid and b["program_id"] == proid and b["cer_model"] == model]
            for b in possible:
                if b["grade_ids"] and gid in b["grade_ids"]:
                    return b
            for b in possible:
                if b["grade_group_ids"] and ggroupid in b["grade_group_ids"]:
                    return b
            for b in possible:
                if not b["grade_ids"] and not b["grade_group_ids"]:
                    return b
            return None

        results = []
        for r in rows:
            d = dict(r)
            bg = _get_live_bg(d["academic_id"], d["program_id"], d["cer_model"], d["grade_id"], d["grade_group_id"])
            if bg:
                if not d.get("snapshot_background_url"):
                    d["background_url"] = bg["background_url"]
                d["orientation"] = bg["orientation"]
            else:
                d["orientation"] = "landscape"
            
            d["is_public"] = bool(d["is_public"])
            results.append(d)

        return results

    except Exception as e:
        import traceback
        logger.error(f"Error fetching public certificates: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to fetch public certificates")
