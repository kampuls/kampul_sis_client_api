"""
Price list API – public endpoints for fee schedules by academic year.
Uses raw SQL (no ORM model for price_list).
"""
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Any

from ...core import get_db

router = APIRouter()


# ─── Auto-create price_visibility_settings table ────────────────────────────
_VISIBILITY_TABLE_CREATED = False

def _ensure_visibility_table(db: Session):
    global _VISIBILITY_TABLE_CREATED
    if _VISIBILITY_TABLE_CREATED:
        return
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS price_visibility_settings (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                branch_id  INT NULL COMMENT 'NULL = all branches',
                program_id INT NULL COMMENT 'NULL = all programs',
                show_monthly   TINYINT(1) NOT NULL DEFAULT 1,
                show_quarter   TINYINT(1) NOT NULL DEFAULT 1,
                show_semester  TINYINT(1) NOT NULL DEFAULT 1,
                show_oneyear   TINYINT(1) NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """))
        db.commit()
        _VISIBILITY_TABLE_CREATED = True
    except Exception:
        pass


def _resolve_visibility(db: Session, branch_id, program_id) -> dict:
    """Return the most-specific matching visibility row, or all-visible defaults."""
    _ensure_visibility_table(db)
    # Priority: exact match > branch-only > program-only > global
    candidates = [
        (branch_id, program_id),
        (branch_id, None),
        (None, program_id),
        (None, None),
    ]
    for b, p in candidates:
        where = []
        params = {}
        if b is not None:
            where.append("branch_id = :b")
            params["b"] = b
        else:
            where.append("branch_id IS NULL")
        if p is not None:
            where.append("program_id = :p")
            params["p"] = p
        else:
            where.append("program_id IS NULL")
        row = db.execute(
            text("SELECT id, show_monthly, show_quarter, show_semester, show_oneyear FROM price_visibility_settings WHERE " + " AND ".join(where)),
            params,
        ).fetchone()
        if row:
            return {
                "id": row[0],
                "show_monthly": bool(row[1]),
                "show_quarter": bool(row[2]),
                "show_semester": bool(row[3]),
                "show_oneyear": bool(row[4]),
            }
    return {"id": None, "show_monthly": True, "show_quarter": True, "show_semester": True, "show_oneyear": True}


# ─── Visibility endpoints ────────────────────────────────────────────────────

@router.get("/visibility")
async def get_visibility(
    branch_id: Optional[int] = Query(None),
    program_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Resolve effective show/hide flags for a given branch + program combo."""
    return _resolve_visibility(db, branch_id, program_id)


@router.get("/visibility/all")
async def get_visibility_all(db: Session = Depends(get_db)):
    """Admin: return every row in price_visibility_settings."""
    _ensure_visibility_table(db)
    rows = db.execute(text(
        "SELECT id, branch_id, program_id, show_monthly, show_quarter, show_semester, show_oneyear, created_at, updated_at FROM price_visibility_settings ORDER BY id"
    )).fetchall()
    return [
        {
            "id": r[0],
            "branch_id": r[1],
            "program_id": r[2],
            "show_monthly": bool(r[3]),
            "show_quarter": bool(r[4]),
            "show_semester": bool(r[5]),
            "show_oneyear": bool(r[6]),
        }
        for r in rows
    ]


from pydantic import BaseModel

class VisibilityUpsert(BaseModel):
    branch_id: Optional[int] = None
    program_id: Optional[int] = None
    show_monthly: bool = True
    show_quarter: bool = True
    show_semester: bool = True
    show_oneyear: bool = True


@router.put("/visibility")
async def upsert_visibility(body: VisibilityUpsert, db: Session = Depends(get_db)):
    """Admin: insert or update a visibility rule for a branch/program combo."""
    _ensure_visibility_table(db)
    # Check if a matching row exists
    where_parts = []
    params: dict = {}
    if body.branch_id is not None:
        where_parts.append("branch_id = :branch_id")
        params["branch_id"] = body.branch_id
    else:
        where_parts.append("branch_id IS NULL")
    if body.program_id is not None:
        where_parts.append("program_id = :program_id")
        params["program_id"] = body.program_id
    else:
        where_parts.append("program_id IS NULL")

    existing = db.execute(
        text("SELECT id FROM price_visibility_settings WHERE " + " AND ".join(where_parts)),
        params,
    ).fetchone()

    params.update({
        "show_monthly": int(body.show_monthly),
        "show_quarter": int(body.show_quarter),
        "show_semester": int(body.show_semester),
        "show_oneyear": int(body.show_oneyear),
    })

    if existing:
        db.execute(text(
            "UPDATE price_visibility_settings SET show_monthly=:show_monthly, show_quarter=:show_quarter, show_semester=:show_semester, show_oneyear=:show_oneyear WHERE id=:id"
        ), {**params, "id": existing[0]})
        db.commit()
        return {"id": existing[0], "action": "updated"}
    else:
        result = db.execute(text(
            "INSERT INTO price_visibility_settings (branch_id, program_id, show_monthly, show_quarter, show_semester, show_oneyear) VALUES (:branch_id, :program_id, :show_monthly, :show_quarter, :show_semester, :show_oneyear)"
        ), {
            "branch_id": body.branch_id,
            "program_id": body.program_id,
            **params,
        })
        db.commit()
        return {"id": result.lastrowid, "action": "created"}


@router.delete("/visibility/{rule_id}")
async def delete_visibility(rule_id: int, db: Session = Depends(get_db)):
    """Admin: delete a visibility rule by ID."""
    _ensure_visibility_table(db)
    db.execute(text("DELETE FROM price_visibility_settings WHERE id = :id"), {"id": rule_id})
    db.commit()
    return {"deleted": rule_id}




def _decimal_to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


@router.get("/academic-years")
async def get_academic_years(db: Session = Depends(get_db)):
    """
    Get all academic years from the academic table for the fee schedule selector.
    Returns id, academic_name, academic_us_name, start/end dates, ordered by id DESC.
    """
    try:
        query = text("""
            SELECT id, academic_name, academic_us_name, academic_start, academic_end,
                   quarter_one_start, quarter_one_end, quarter_two_start, quarter_two_end,
                   quarter_three_start, quarter_three_end, quarter_four_start, quarter_four_end,
                   semester_one_start, semester_one_end, semester_two_start, semester_two_end
            FROM academic
            ORDER BY id DESC
        """)
        rows = db.execute(query).fetchall()
        return [
            {
                "id": r[0],
                "academic_name": r[1] or "",
                "academic_us_name": r[2] or r[1] or "",
                "academic_start": r[3].isoformat() if r[3] else None,
                "academic_end": r[4].isoformat() if r[4] else None,
                "quarter_one_start": r[5].isoformat() if r[5] else None,
                "quarter_one_end": r[6].isoformat() if r[6] else None,
                "quarter_two_start": r[7].isoformat() if r[7] else None,
                "quarter_two_end": r[8].isoformat() if r[8] else None,
                "quarter_three_start": r[9].isoformat() if r[9] else None,
                "quarter_three_end": r[10].isoformat() if r[10] else None,
                "quarter_four_start": r[11].isoformat() if r[11] else None,
                "quarter_four_end": r[12].isoformat() if r[12] else None,
                "semester_one_start": r[13].isoformat() if r[13] else None,
                "semester_one_end": r[14].isoformat() if r[14] else None,
                "semester_two_start": r[15].isoformat() if r[15] else None,
                "semester_two_end": r[16].isoformat() if r[16] else None,
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def get_price_list(
    academic_id: int = Query(..., description="Academic year ID"),
    branch_id: Optional[int] = Query(None),
    program_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Get price_list rows for the given academic year only.
    Filter is strictly by price_list.academicid = academic_id.
    Optionally filter by branch_id and/or program_id.
    """
    try:
        academic_id = int(academic_id)
        conditions = ["pl.academicid = :academic_id"]
        params = {"academic_id": academic_id}
        if branch_id is not None:
            conditions.append("pl.branch_id = :branch_id")
            params["branch_id"] = branch_id
        if program_id is not None:
            conditions.append("pl.program_id = :program_id")
            params["program_id"] = program_id

        query = text("""
            SELECT pl.id, pl.program_id, pl.grade_id,
                   pl.monthly, pl.quarter, pl.semester, pl.oneyear,
                   pl.academicid, pl.branch_id, pl.note,
                   p.program_name, p.short_code,
                   g.grade_name
            FROM price_list pl
            LEFT JOIN program p ON pl.program_id = p.id
            LEFT JOIN grade g ON pl.grade_id = g.id
            WHERE """ + " AND ".join(conditions) + """
            ORDER BY p.program_name, g.id ASC
        """)
        try:
            rows = db.execute(query, params).fetchall()
        except Exception as col_err:
            err_msg = str(col_err).lower()
            if "academicid" in err_msg or "unknown column" in err_msg or "academic_id" in err_msg:
                # Try column name academic_id (snake_case) if academicid fails
                conditions_alt = ["pl.academic_id = :academic_id"]
                params_alt = {"academic_id": academic_id}
                if branch_id is not None:
                    conditions_alt.append("pl.branch_id = :branch_id")
                    params_alt["branch_id"] = branch_id
                if program_id is not None:
                    conditions_alt.append("pl.program_id = :program_id")
                    params_alt["program_id"] = program_id
                query_alt = text("""
                    SELECT pl.id, pl.program_id, pl.grade_id,
                           pl.monthly, pl.quarter, pl.semester, pl.oneyear,
                           pl.academic_id, pl.branch_id, pl.note,
                           p.program_name, p.short_code,
                           g.grade_name
                    FROM price_list pl
                    LEFT JOIN program p ON pl.program_id = p.id
                    LEFT JOIN grade g ON pl.grade_id = g.id
                    WHERE """ + " AND ".join(conditions_alt) + """
                    ORDER BY p.program_name, g.id ASC
                """)
                rows = db.execute(query_alt, params_alt).fetchall()
            else:
                raise
        # Strict filter: only return rows whose academicid matches the requested academic_id
        out = []
        for r in rows:
            row_academicid = r[7]
            if row_academicid is None:
                continue
            try:
                rid = int(row_academicid)
            except (TypeError, ValueError):
                continue
            if rid != academic_id:
                continue
            grade_id_val = r[2]
            grade_name_val = r[12]
            if isinstance(grade_name_val, str) and grade_name_val.strip():
                grade_name_out = grade_name_val.strip()
            elif grade_id_val is not None:
                try:
                    gid = int(grade_id_val)
                    grade_name_out = f"Grade {gid}"
                except (TypeError, ValueError):
                    grade_name_out = None
            else:
                grade_name_out = None
            out.append({
                "id": r[0],
                "program_id": r[1],
                "grade_id": r[2],
                "monthly": _decimal_to_float(r[3]),
                "quarter": _decimal_to_float(r[4]),
                "semester": _decimal_to_float(r[5]),
                "oneyear": _decimal_to_float(r[6]),
                "academicid": rid,
                "branch_id": r[8],
                "note": r[9],
                "program_name": r[10] or f"Program {r[1]}",
                "program_short_code": r[11] if r[11] else None,
                "grade_name": grade_name_out,
            })
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fee-services")
async def get_fee_services(
    academic_id: int = Query(..., description="Academic year ID"),
    branch_id: Optional[int] = Query(None),
    program_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Get fee service rows for the given academic year.
    Supports optional branch/program filters when those columns exist.
    """
    try:
        academic_id = int(academic_id)

        # Preferred shape: fee_services has academic_id, branch_id and program_id.
        base_conditions = ["fs.academic_id = :academic_id"]
        params = {"academic_id": academic_id}
        if branch_id is not None:
            base_conditions.append("fs.branch_id = :branch_id")
            params["branch_id"] = branch_id
        if program_id is not None:
            base_conditions.append("fs.program_id = :program_id")
            params["program_id"] = program_id

        query = text(
            """
            SELECT
                fs.id,
                fs.service_name,
                fs.amount,
                fs.branch_id,
                fs.academic_id,
                fs.program_id,
                fs.special
            FROM fee_services fs
            WHERE """
            + " AND ".join(base_conditions)
            + """
            ORDER BY fs.id ASC
            """
        )

        try:
            rows = db.execute(query, params).fetchall()
        except Exception as col_err:
            # Backward compatibility: some DBs may not have program_id yet.
            msg = str(col_err).lower()
            if "program_id" not in msg and "unknown column" not in msg:
                raise

            fallback_conditions = ["fs.academic_id = :academic_id"]
            fallback_params = {"academic_id": academic_id}
            if branch_id is not None:
                fallback_conditions.append("fs.branch_id = :branch_id")
                fallback_params["branch_id"] = branch_id

            fallback_query = text(
                """
                SELECT
                    fs.id,
                    fs.service_name,
                    fs.amount,
                    fs.branch_id,
                    fs.academic_id,
                    NULL AS program_id,
                    fs.special
                FROM fee_services fs
                WHERE """
                + " AND ".join(fallback_conditions)
                + """
                ORDER BY fs.id ASC
                """
            )
            rows = db.execute(fallback_query, fallback_params).fetchall()

            # If client requested a specific program but DB has no program_id column,
            # we cannot apply that filter server-side, so return empty to avoid wrong mapping.
            if program_id is not None:
                return []

        return [
            {
                "id": r[0],
                "service_name": r[1] or "",
                "amount": _decimal_to_float(r[2]) or 0.0,
                "branch_id": r[3],
                "academic_id": r[4],
                "program_id": r[5],
                "special": r[6],
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
