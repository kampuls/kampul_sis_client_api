from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, cast

from ...core.database import get_db
from ...core.security import get_current_active_user
from ...models.user import User
from ...schemas.certificate import DemoCertStudentResponse

import logging
logger = logging.getLogger(__name__)

# This will be injected into certificates.py
@router.get("/public/{student_id}", response_model=List[DemoCertStudentResponse])
async def get_public_certificates(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all public certificates for a specific student.
    Allowed for:
    - Admin
    - The student themselves
    - A parent who has the student in their myChilds list
    """
    is_admin = getattr(current_user, "role", 0) == 1
    if not is_admin:
        perm_check = text("""
            SELECT COUNT(*) FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            WHERE rp.role_id = :role_id
            AND p.permission_name IN ('AdminViewApp', 'AdminUpdateApp')
        """)
        perm_count = db.execute(perm_check, {"role_id": getattr(current_user, "role", 0)}).scalar()
        is_admin = bool(perm_count and perm_count > 0)

    is_allowed = is_admin
    
    if not is_allowed:
        user_id = cast(int, getattr(current_user, "id", 0))
        role_name = getattr(current_user, "role_name", "") or ""
        
        if role_name == "student" and user_id == student_id:
            is_allowed = True
        elif role_name == "parent":
            parent_row = db.execute(
                text("SELECT myChilds FROM parents WHERE id = :pid"),
                {"pid": user_id}
            ).fetchone()
            if parent_row and parent_row[0]:
                child_ids = [int(x.strip()) for x in str(parent_row[0]).split(",") if x.strip()]
                if student_id in child_ids:
                    is_allowed = True
                    
    if not is_allowed:
        raise HTTPException(status_code=403, detail="Not authorized to view these certificates")

    # Fetch issued and public certificates only
    sql = text("""
        SELECT
            dc.id,
            s.id                       AS student_id,
            dc.cer_id,
            dc.cer_model,
            dc.academic_id,
            dc.program_id,
            dc.grade_id,
            dc.grade_type_id,
            dc.nittes_id,
            dc.created_at,
            dc.updated_at,
            COALESCE(dc.is_public, 0) AS is_public,

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
            ) AS teacher_ename

        FROM demo_cert dc
        JOIN students s ON dc.student_id = s.id
        LEFT JOIN academic a ON a.id = dc.academic_id
        LEFT JOIN program p  ON p.id = dc.program_id
        LEFT JOIN grade g    ON g.id = dc.grade_id
        LEFT JOIN grade_scale gs ON gs.academic_id = dc.academic_id
                                AND gs.grade_group_id = g.group_Id
                                AND gs.id = (
                                    SELECT id FROM grade_scale
                                    WHERE academic_id    = dc.academic_id
                                      AND grade_group_id = g.group_Id
                                    LIMIT 1
                                )
        LEFT JOIN branch b ON b.id = s.branch
        WHERE dc.student_id = :student_id AND dc.is_public = 1
        ORDER BY dc.created_at DESC
    """)

    try:
        rows = db.execute(sql, {"student_id": student_id}).mappings().all()

        # Build response manually, reusing existing logic if we had background_certs.
        # But wait! For parents we should ALREADY be using the snapshots!
        # Because the certificate was already issued. So we don't strictly need to resolve live background_cert, 
        # unless it doesn't have a snapshot (which happens for old certs).
        
        # Let's fetch background_certs just in case to fallback if snapshot_background_url is missing
        bg_sql = "SELECT academic_id, program_id, cer_model, grade_group_ids, grade_ids, background_url, orientation, updated_at FROM background_cert"
        bg_rows = db.execute(text(bg_sql)).mappings().all()
        
        import json
        
        def _get_live_bg(academic_id, program_id, cer_model, grade_id, grade_group_id):
            best = None
            best_weight = -1
            for bg in bg_rows:
                if bg["academic_id"] == academic_id and bg["program_id"] == program_id and bg["cer_model"] == cer_model:
                    w = 0
                    if bg["grade_ids"]:
                        try:
                            g_ids = json.loads(bg["grade_ids"])
                            if grade_id in g_ids: w = 3
                        except: pass
                    if w == 0 and bg["grade_group_ids"]:
                        try:
                            gg_ids = json.loads(bg["grade_group_ids"])
                            if grade_group_id in gg_ids: w = 2
                        except: pass
                    if w == 0 and not bg["grade_ids"] and not bg["grade_group_ids"]:
                        w = 1
                    
                    if w > best_weight:
                        best = bg
                        best_weight = w
            return best

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
        logger.error(f"Error fetching public certs for student {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch certificates")

