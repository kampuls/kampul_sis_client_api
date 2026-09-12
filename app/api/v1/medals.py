from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Optional

from ...core import get_db
from ...schemas.medal import (
    StudentMedalResponse,
    StudentMedalSummary,
    AcademicYearOption,
    StudentMedalDetail,
    GradeProgramMedalReport,
    StudentCompetitionMedalRow,
    OverallMedalSummary,
    EnrollmentProgramOption,
)

router = APIRouter()


def _branch_params(branch_id: Optional[int]) -> dict:
    """Query params for branch filters (numeric id on learning + string on students.branch)."""
    if branch_id is None:
        return {}
    return {"branch_id": branch_id, "branch_id_str": str(branch_id)}


def _branch_scope_sql(branch_id: Optional[int], learning_branch_col: str) -> str:
    """
    Restrict rows to a campus/branch.

    Many `learning.branch_id` values are NULL in legacy data; `students.branch` then
    holds the campus id as a string (same convention as public medals). Match either.
    """
    if branch_id is None:
        return ""
    return (
        f" AND ({learning_branch_col} = :branch_id OR ({learning_branch_col} IS NULL "
        "AND TRIM(CAST(s.branch AS CHAR)) = TRIM(:branch_id_str)))"
    )


def _learning_join_one_row_per_student_sql(
    academic_id: Optional[int],
    branch_id: Optional[int],
    enrollment_program_id: Optional[int] = None,
) -> tuple[str, str, str]:
    """
    Learning can have many rows per student per academic year (programs/shifts/etc.).
    Joining medals directly to `learning` without deduping multiplies each medal row and
    inflates SUM/COUNT. Pick one enrollment row per student (latest learning.id) and
    optionally filter medals to the same academic year on `medals.academic_id`.

    When enrollment_program_id is set, only rows with learning.programid = that id are
    considered, so grade reflects that curriculum program and medals are not duplicated
    across multiple enrollments for the same student.

    Branch is NOT applied inside the MAX(id) subquery: NULL branch_id rows would be
    excluded there. Instead, expose `learning_branch_id` on the join and apply
    `_branch_scope_sql` in the outer WHERE (see callers).
    """
    prog_inner = " AND programid = :enrollment_program_id" if enrollment_program_id is not None else ""
    if academic_id is None:
        prog_outer = " AND l.programid = :enrollment_program_id" if enrollment_program_id is not None else ""
        join_sql = f"JOIN learning l ON s.id = l.studentid{prog_outer}"
        branch_scope = _branch_scope_sql(branch_id, "l.branch_id")
        return (join_sql, "", branch_scope)
    join_sql = f"""
        JOIN (
            SELECT l1.studentid, l1.gradeid, l1.grade_type_id, l1.branch_id AS learning_branch_id
            FROM learning l1
            INNER JOIN (
                SELECT studentid, MAX(id) AS max_id
                FROM learning
                WHERE academicid = :academic_id{prog_inner}
                GROUP BY studentid
            ) lm ON l1.id = lm.max_id
        ) l ON s.id = l.studentid
    """
    medal_sql = "AND m.academic_id = :academic_id"
    branch_scope = _branch_scope_sql(branch_id, "l.learning_branch_id")
    return (join_sql, medal_sql, branch_scope)


def _enrollment_program_params(enrollment_program_id: Optional[int]) -> dict:
    if enrollment_program_id is not None:
        return {"enrollment_program_id": enrollment_program_id}
    return {}


def _get_active_academic_id(db: Session) -> Optional[int]:
    """Current academic year via the canonical resolver
    (status=1 -> settings.academicid -> newest)."""
    from ...utils.academic_year import get_current_academic_id

    return get_current_academic_id(db)


@router.get("/public/academic-years", response_model=List[AcademicYearOption])
def get_public_academic_years(db: Session = Depends(get_db)):
    """List all academic years for the medal filter dropdown."""
    rows = db.execute(
        text("SELECT id, academic_name, academic_us_name, status FROM academic ORDER BY id DESC")
    ).fetchall()
    result = []
    for row in rows:
        result.append(AcademicYearOption(
            id=row[0],
            name_kh=row[1] or "",
            name_en=row[2] or "",
            is_active=bool(row[3] == 1),
        ))
    return result


@router.get("/public/medals", response_model=List[StudentMedalResponse])
def get_public_medals(
    db: Session = Depends(get_db),
    limit: int = Query(10, description="Max students to return"),
    skip: int = Query(0, description="Pagination skip"),
    top_only: bool = Query(True, description="Sort by highest medals"),
    academic_id: Optional[int] = Query(None, description="Filter by academic year. Defaults to active year."),
    branch_id: Optional[int] = Query(None, description="Filter by branch ID."),
):
    """
    Get aggregated students with medals for the public UI.
    Filtered by academic year (defaults to the currently active year) and branch.
    Uses the same avatar source as Top Students (users_resource table).
    """
    # Resolve academic id
    if academic_id is None:
        academic_id = _get_active_academic_id(db)

    # Build the WHERE clause based on filters
    academic_filter = "AND m.academic_id = :academic_id" if academic_id is not None else ""
    branch_filter = "AND s.branch = :branch_id_str" if branch_id is not None else ""

    sql = text(f"""
        SELECT
            s.id,
            s.kName,
            s.eName,
            s.gender,
            ur.avatar,
            mp.name_kh,
            mp.name_us,
            m.medal_type
        FROM medals m
        JOIN students s ON m.student_id = s.id
        JOIN medal_price mp ON m.medal_price_id = mp.id
        LEFT JOIN users_resource ur ON ur.user_id = s.id AND ur.user_type = 'student'
        WHERE 1=1 {academic_filter} {branch_filter}
    """)

    params = {}
    if academic_id is not None:
        params["academic_id"] = academic_id
    if branch_id is not None:
        params["branch_id_str"] = str(branch_id)

    rows = db.execute(sql, params).fetchall()

    # 2) Aggregate by student
    student_aggregates = {}
    for row in rows:
        s_id, k_name, e_name, gender, avatar, price_kh, price_us, medal_type = row

        str_id = str(s_id)
        if str_id not in student_aggregates:
            student_aggregates[str_id] = {
                "student_id": s_id,
                "kName": k_name,
                "eName": e_name,
                "gender": gender,
                "avatar": avatar,
                "summary": StudentMedalSummary(),
                "rank_score": 0
            }

        summ = student_aggregates[str_id]["summary"]
        summ.total_medals += 1

        is_school = (medal_type == "មេដាយកម្រិតសាលា")
        is_national = (medal_type == "មេដាយកម្រិតជាតិ")

        score_add = 0
        if price_kh == "មាស":
            score_add = 1000
            if is_school:
                summ.school_gold += 1
            elif is_national:
                summ.national_gold += 1
            else:
                summ.international_gold += 1
            summ.total_gold += 1
        elif price_kh == "ប្រាក់":
            score_add = 100
            if is_school:
                summ.school_silver += 1
            elif is_national:
                summ.national_silver += 1
            else:
                summ.international_silver += 1
            summ.total_silver += 1
        elif price_kh == "សំរិទ្ធ":
            score_add = 10
            if is_school:
                summ.school_bronze += 1
            elif is_national:
                summ.national_bronze += 1
            else:
                summ.international_bronze += 1
            summ.total_bronze += 1
        elif price_kh == "ពេជ្រ":
            score_add = 10000
            if is_school:
                summ.school_diamond += 1
            elif is_national:
                summ.national_diamond += 1
            else:
                summ.international_diamond += 1
            summ.total_diamond += 1

        if not is_school:
            score_add *= 2

        student_aggregates[str_id]["rank_score"] += score_add

    # Sort
    agg_list = list(student_aggregates.values())
    agg_list.sort(key=lambda x: x["rank_score"], reverse=True)

    # Pagination
    paginated = agg_list[skip: skip + limit]

    response = []
    current_rank = skip + 1
    for agg in paginated:
        response.append(
            StudentMedalResponse(
                student_id=agg["student_id"],
                student_ename=agg["eName"] or "",
                student_kname=agg["kName"],
                student_gender=agg["gender"],
                student_image=agg["avatar"],
                rank=current_rank,
                medals_summary=agg["summary"]
            )
        )
        current_rank += 1

    return response

@router.get("/public/medals/student/{student_id}", response_model=List[StudentMedalDetail])
def get_public_student_medals(
    student_id: int,
    db: Session = Depends(get_db),
    academic_id: Optional[int] = Query(None, description="Filter by academic year. Defaults to active year."),
):
    """Get the detailed list of medals for a specific student."""
    if academic_id is None:
        academic_id = _get_active_academic_id(db)

    academic_filter = "AND m.academic_id = :academic_id" if academic_id is not None else ""

    sql = text(f"""
        SELECT 
            m.medal_name,
            m.medal_type,
            mp.name_kh as price_name_kh,
            mp.name_us as price_name_us,
            a.academic_name as academic_kh,
            a.academic_us_name as academic_en,
            m.created_at
        FROM medals m
        JOIN medal_price mp ON m.medal_price_id = mp.id
        LEFT JOIN academic a ON m.academic_id = a.id
        WHERE m.student_id = :student_id {academic_filter}
        ORDER BY m.created_at DESC
    """)

    params = {"student_id": student_id}
    if academic_id is not None:
        params["academic_id"] = academic_id

    rows = db.execute(sql, params).fetchall()

    result = []
    for row in rows:
        medal_name, medal_type, price_kh, price_us, acad_kh, acad_en, created_at = row
        result.append(StudentMedalDetail(
            medal_name=medal_name or "",
            medal_type=medal_type or "",
            price_name_kh=price_kh or "",
            price_name_us=price_us or "",
            academic_kh=acad_kh or "",
            academic_en=acad_en or "",
            created_at=str(created_at) if created_at else None
        ))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Admin Medal Report Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/admin/medals/report", response_model=List[GradeProgramMedalReport])
def get_medal_report_by_grade_and_program(
    db: Session = Depends(get_db),
    academic_id: Optional[int] = Query(None, description="Filter by academic year"),
    branch_id: Optional[int] = Query(None, description="Filter by branch"),
    enrollment_program_id: Optional[int] = Query(
        None,
        description="Curriculum program id (learning.programid). Omit for all programs; "
        "then one latest enrollment row per student (any program) to avoid duplicate medal counts.",
    ),
    grade: Optional[str] = Query(None, description="Filter by grade name"),
    program: Optional[str] = Query(None, description="Filter by competition name (medals.medal_name)"),
):
    """
    Get medal statistics grouped by grade and program.
    
    This endpoint aggregates medal data by:
    - Grade (from learning.gradeid -> grade.grade_name)
    - Program (from medals.medal_name field, which contains competition/program name)
    
    Returns medal counts (gold, silver, bronze, diamond) for each grade-program combination.
    """
    # Resolve academic_id if not provided
    if academic_id is None:
        academic_id = _get_active_academic_id(db)
    
    # Build filters
    learning_join, medal_academic_sql, branch_scope_sql = _learning_join_one_row_per_student_sql(
        academic_id, branch_id, enrollment_program_id
    )
    grade_filter = "AND g.grade_name = :grade" if grade is not None and grade else ""
    program_filter = "AND m.medal_name = :program" if program is not None and program else ""
    
    # Join medals -> students -> one learning row per student -> grade
    sql = text(f"""
        SELECT 
            COALESCE(g.grade_name, 'Unknown') as grade_name,
            COALESCE(m.medal_name, 'Unknown') as program_name,
            SUM(CASE WHEN mp.name_kh = 'មាស' THEN 1 ELSE 0 END) as total_gold,
            SUM(CASE WHEN mp.name_kh = 'ប្រាក់' THEN 1 ELSE 0 END) as total_silver,
            SUM(CASE WHEN mp.name_kh = 'សំរិទ្ធ' THEN 1 ELSE 0 END) as total_bronze,
            SUM(CASE WHEN mp.name_kh = 'ពេជ្រ' THEN 1 ELSE 0 END) as total_diamond,
            COUNT(m.id) as total_medals
        FROM medals m
        JOIN students s ON m.student_id = s.id
        JOIN medal_price mp ON m.medal_price_id = mp.id
        {learning_join}
        JOIN grade g ON l.gradeid = g.id
        LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
        WHERE 1=1 {medal_academic_sql} {grade_filter} {program_filter}{branch_scope_sql}
        GROUP BY g.grade_name, m.medal_name
        ORDER BY g.grade_name, total_medals DESC
    """)
    
    params = {}
    if academic_id is not None:
        params["academic_id"] = academic_id
    params.update(_branch_params(branch_id))
    params.update(_enrollment_program_params(enrollment_program_id))
    if grade is not None and grade:
        params["grade"] = grade
    if program is not None and program:
        params["program"] = program
    
    try:
        rows = db.execute(sql, params).fetchall()
        
        result = []
        for row in rows:
            grade_name, program_name, gold, silver, bronze, diamond, total = row
            result.append(GradeProgramMedalReport(
                grade_name=grade_name or "Unknown",
                program_name=program_name or "Unknown",
                total_gold=gold or 0,
                total_silver=silver or 0,
                total_bronze=bronze or 0,
                total_diamond=diamond or 0,
                total_medals=total or 0,
            ))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get(
    "/admin/medals/report/student-competition-rows",
    response_model=List[StudentCompetitionMedalRow],
)
def get_medal_report_student_competition_rows(
    db: Session = Depends(get_db),
    academic_id: Optional[int] = Query(None, description="Filter by academic year"),
    branch_id: Optional[int] = Query(None, description="Filter by branch"),
    enrollment_program_id: Optional[int] = Query(
        None,
        description="Curriculum program id (learning.programid); same semantics as main report.",
    ),
    grade: Optional[str] = Query(None, description="Filter by grade name"),
    program: Optional[str] = Query(None, description="Filter by competition name (medals.medal_name)"),
):
    """
    Flat rows: one row per (student, grade, competition) with gold/silver/bronze/diamond counts.
    Used for Excel pivot (students × competitions).
    """
    if academic_id is None:
        academic_id = _get_active_academic_id(db)

    learning_join, medal_academic_sql, branch_scope_sql = _learning_join_one_row_per_student_sql(
        academic_id, branch_id, enrollment_program_id
    )
    grade_filter = "AND g.grade_name = :grade" if grade is not None and grade else ""
    program_filter = "AND m.medal_name = :program" if program is not None and program else ""

    sql = text(f"""
        SELECT
            s.id AS student_id,
            MAX(COALESCE(
                NULLIF(TRIM(s.eName), ''),
                NULLIF(TRIM(s.kName), ''),
                CONCAT('Student ', s.id)
            )) AS student_name,
            MAX(COALESCE(NULLIF(TRIM(s.kName), ''), '')) AS student_name_kh,
            MAX(COALESCE(NULLIF(TRIM(s.eName), ''), '')) AS student_name_en,
            MAX(COALESCE(NULLIF(TRIM(s.gender), ''), '')) AS gender,
            COALESCE(g.grade_name, 'Unknown') AS grade_name,
            COALESCE(gt.type_name, '') AS grade_type_name,
            COALESCE(m.medal_type, 'Unknown') AS medal_type,
            COALESCE(m.medal_name, 'Unknown') AS program_name,
            SUM(CASE WHEN mp.name_kh = 'មាស' THEN 1 ELSE 0 END) AS total_gold,
            SUM(CASE WHEN mp.name_kh = 'ប្រាក់' THEN 1 ELSE 0 END) AS total_silver,
            SUM(CASE WHEN mp.name_kh = 'សំរិទ្ធ' THEN 1 ELSE 0 END) AS total_bronze,
            SUM(CASE WHEN mp.name_kh = 'ពេជ្រ' THEN 1 ELSE 0 END) AS total_diamond,
            COUNT(m.id) AS total_medals
        FROM medals m
        JOIN students s ON m.student_id = s.id
        JOIN medal_price mp ON m.medal_price_id = mp.id
        {learning_join}
        JOIN grade g ON l.gradeid = g.id
        LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
        WHERE 1=1 {medal_academic_sql} {grade_filter} {program_filter}{branch_scope_sql}
        GROUP BY s.id, g.grade_name, gt.type_name, m.medal_type, m.medal_name
        HAVING COUNT(m.id) > 0
        ORDER BY grade_name, grade_type_name, student_name, medal_type, program_name
    """)

    params: dict = {}
    if academic_id is not None:
        params["academic_id"] = academic_id
    params.update(_branch_params(branch_id))
    params.update(_enrollment_program_params(enrollment_program_id))
    if grade is not None and grade:
        params["grade"] = grade
    if program is not None and program:
        params["program"] = program

    try:
        rows = db.execute(sql, params).fetchall()
        out: List[StudentCompetitionMedalRow] = []
        for row in rows:
            (
                sid,
                sname,
                sname_kh,
                sname_en,
                gender,
                gname,
                gtype,
                mtype,
                pname,
                gold,
                silver,
                bronze,
                diamond,
                total,
            ) = row
            out.append(
                StudentCompetitionMedalRow(
                    student_id=int(sid) if sid is not None else 0,
                    student_name=(sname or "").strip() or f"Student {sid}",
                    student_name_kh=(sname_kh or "").strip(),
                    student_name_en=(sname_en or "").strip(),
                    gender=(gender or "").strip(),
                    grade_name=gname or "Unknown",
                    grade_type_name=(gtype or "").strip(),
                    medal_type=mtype or "Unknown",
                    program_name=pname or "Unknown",
                    total_gold=int(gold or 0),
                    total_silver=int(silver or 0),
                    total_bronze=int(bronze or 0),
                    total_diamond=int(diamond or 0),
                    total_medals=int(total or 0),
                )
            )
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/admin/medals/report/summary", response_model=OverallMedalSummary)
def get_medal_report_summary(
    db: Session = Depends(get_db),
    academic_id: Optional[int] = Query(None, description="Filter by academic year"),
    branch_id: Optional[int] = Query(None, description="Filter by branch"),
    enrollment_program_id: Optional[int] = Query(
        None,
        description="Curriculum program id (learning.programid); same semantics as main report.",
    ),
):
    """
    Get overall medal summary statistics.
    
    Returns aggregated totals across all grades and programs.
    """
    # Resolve academic_id if not provided
    if academic_id is None:
        academic_id = _get_active_academic_id(db)
    
    learning_join, medal_academic_sql, branch_scope_sql = _learning_join_one_row_per_student_sql(
        academic_id, branch_id, enrollment_program_id
    )

    sql = text(f"""
        SELECT 
            SUM(CASE WHEN mp.name_kh = 'មាស' THEN 1 ELSE 0 END) as total_gold,
            SUM(CASE WHEN mp.name_kh = 'ប្រាក់' THEN 1 ELSE 0 END) as total_silver,
            SUM(CASE WHEN mp.name_kh = 'សំរិទ្ធ' THEN 1 ELSE 0 END) as total_bronze,
            SUM(CASE WHEN mp.name_kh = 'ពេជ្រ' THEN 1 ELSE 0 END) as total_diamond,
            COUNT(m.id) as total_medals,
            COUNT(DISTINCT g.grade_name) as total_grades,
            COUNT(DISTINCT m.medal_name) as total_programs
        FROM medals m
        JOIN students s ON m.student_id = s.id
        JOIN medal_price mp ON m.medal_price_id = mp.id
        {learning_join}
        JOIN grade g ON l.gradeid = g.id
        LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
        WHERE 1=1 {medal_academic_sql}{branch_scope_sql}
    """)
    
    params = {}
    if academic_id is not None:
        params["academic_id"] = academic_id
    params.update(_branch_params(branch_id))
    params.update(_enrollment_program_params(enrollment_program_id))
    
    try:
        row = db.execute(sql, params).fetchone()
        
        if row:
            total_gold, total_silver, total_bronze, total_diamond, total_medals, total_grades, total_programs = row
            return OverallMedalSummary(
                total_gold=total_gold or 0,
                total_silver=total_silver or 0,
                total_bronze=total_bronze or 0,
                total_diamond=total_diamond or 0,
                total_medals=total_medals or 0,
                total_grades=total_grades or 0,
                total_programs=total_programs or 0,
            )
        else:
            return OverallMedalSummary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/admin/medals/report/grade-options", response_model=List[str])
def get_medal_report_grade_options(
    db: Session = Depends(get_db),
    academic_id: Optional[int] = Query(None, description="Filter by academic year"),
    branch_id: Optional[int] = Query(None, description="Filter by branch"),
    enrollment_program_id: Optional[int] = Query(
        None, description="Curriculum program id (learning.programid)"
    ),
):
    """
    Get list of unique grade names that have medals for the filter dropdown.
    This helps build the grade filter options dynamically.
    """
    # Resolve academic_id if not provided
    if academic_id is None:
        academic_id = _get_active_academic_id(db)
    
    learning_join, medal_academic_sql, branch_scope_sql = _learning_join_one_row_per_student_sql(
        academic_id, branch_id, enrollment_program_id
    )

    sql = text(f"""
        SELECT DISTINCT g.grade_name
        FROM medals m
        JOIN students s ON m.student_id = s.id
        {learning_join}
        JOIN grade g ON l.gradeid = g.id
        LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
        WHERE g.grade_name IS NOT NULL AND g.grade_name != ''
        {medal_academic_sql}{branch_scope_sql}
        ORDER BY g.grade_name
    """)
    
    params = {}
    if academic_id is not None:
        params["academic_id"] = academic_id
    params.update(_branch_params(branch_id))
    params.update(_enrollment_program_params(enrollment_program_id))
    
    try:
        rows = db.execute(sql, params).fetchall()
        grade_names = [row[0] for row in rows if row[0]]
        return grade_names
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/admin/medals/report/program-options", response_model=List[str])
def get_medal_report_program_options(
    db: Session = Depends(get_db),
    academic_id: Optional[int] = Query(None, description="Filter by academic year"),
    branch_id: Optional[int] = Query(None, description="Filter by branch"),
    enrollment_program_id: Optional[int] = Query(
        None, description="Curriculum program id (learning.programid)"
    ),
):
    """
    Get list of unique program names that have medals for the filter dropdown.
    This helps build the program filter options dynamically.
    """
    # Resolve academic_id if not provided
    if academic_id is None:
        academic_id = _get_active_academic_id(db)
    
    learning_join, medal_academic_sql, branch_scope_sql = _learning_join_one_row_per_student_sql(
        academic_id, branch_id, enrollment_program_id
    )

    sql = text(f"""
        SELECT DISTINCT m.medal_name
        FROM medals m
        JOIN students s ON m.student_id = s.id
        {learning_join}
        WHERE m.medal_name IS NOT NULL AND m.medal_name != ''
        {medal_academic_sql}{branch_scope_sql}
        ORDER BY m.medal_name
    """)
    
    params = {}
    if academic_id is not None:
        params["academic_id"] = academic_id
    params.update(_branch_params(branch_id))
    params.update(_enrollment_program_params(enrollment_program_id))
    
    try:
        rows = db.execute(sql, params).fetchall()
        program_names = [row[0] for row in rows if row[0]]
        return program_names
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/admin/medals/report/enrollment-programs", response_model=List[EnrollmentProgramOption])
def get_medal_report_enrollment_programs(
    db: Session = Depends(get_db),
    academic_id: Optional[int] = Query(None, description="Filter by academic year"),
    branch_id: Optional[int] = Query(None, description="Filter by branch"),
):
    """
    Curriculum programs that have at least one learning row in the given academic year
    (and optional branch), for the medal report filter dropdown.
    """
    if academic_id is None:
        academic_id = _get_active_academic_id(db)
    if academic_id is None:
        return []

    branch_sql = ""
    if branch_id is not None:
        branch_sql = (
            " AND (l.branch_id = :branch_id OR (l.branch_id IS NULL "
            "AND TRIM(CAST(s.branch AS CHAR)) = TRIM(:branch_id_str)))"
        )

    sql = text(f"""
        SELECT DISTINCT p.id, p.program_name
        FROM program p
        INNER JOIN learning l ON l.programid = p.id
        LEFT JOIN students s ON s.id = l.studentid
        WHERE l.academicid = :academic_id{branch_sql}
        ORDER BY p.program_name
    """)

    params: dict = {"academic_id": academic_id}
    params.update(_branch_params(branch_id))

    try:
        rows = db.execute(sql, params).fetchall()
        return [
            EnrollmentProgramOption(id=int(r[0]), program_name=r[1] or "")
            for r in rows
            if r[0] is not None
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
