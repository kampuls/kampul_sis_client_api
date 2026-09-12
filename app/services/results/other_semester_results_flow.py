from decimal import Decimal
from sqlalchemy import text
from ...utils.results_utils import safe_decimal, is_fail_grade
import logging

logger = logging.getLogger(__name__)

def generate_other_semester_report(
    db, 
    student_id: int, 
    academic_id: int, 
    program_id: int, 
    grade_group_id: int, 
    grade_id: int, 
    shift_id: int, 
    all_sys_ids: list,
    result_name: str,
    sign_code: str,
    grade_type_id: int | None = None,
    branch_id: int | None = None
):
    """
    Generates the semester report for Other programs.
    - Breakdown by Monthly Results (list of (ExamName, Total, Avg, Grade))
    - Overall Semester Summary (from marks_semester)
    """
    
    details = {
        "items": [],
        "summary": {},
        "comment": ""
    }

    if not all_sys_ids:
        return details

    # 1. Fetch Marks for all involved systems (Monthlies + Final if any)
    # We want to display them as "items".
    
    # We need exam names for these system IDs.
    q_names = text("SELECT id, marks_name FROM marks_system WHERE id IN :ids")
    names_res = db.execute(q_names, {"ids": tuple(all_sys_ids)}).fetchall()
    names_map = {r[0]: r[1] for r in names_res}
    
    # Fetch results from marks_monthly
    # Note: "Other" semester usually aggregates MONTHLY results, which are stored in marks_monthly.
    # If one of the IDs is for a Final Exam (which is also stored in marks_monthly?), we fetch it too.
    
    mm_q = text("""
        SELECT marks_system_id, total, average, gs.us_grade, gs.kh_grade
        FROM marks_monthly mm
        LEFT JOIN grade_scale gs ON mm.grade_scale_id = gs.id
        WHERE mm.student_id = :sid 
        AND mm.academic_id = :aid 
        AND mm.marks_system_id IN :sys_ids
    """)
    
    mm_rows = db.execute(mm_q, {
        "sid": student_id,
        "aid": academic_id,
        "sys_ids": tuple(all_sys_ids)
    }).fetchall()
    
    mm_map = {}
    for r in mm_rows:
        mm_map[r[0]] = r
        
    # Build items list based on all_sys_ids order
    for sys_id in all_sys_ids:
        name = names_map.get(sys_id, f"Exam {sys_id}")
        row = mm_map.get(sys_id)
        
        if row:
            total = safe_decimal(row[1], Decimal('0'))
            avg = safe_decimal(row[2], Decimal('0'))
            grade = row[3] or '-'
            kh_grade = row[4] or ''
            
            # Calculate Rank dynamically for this Monthly Exam (SQL)
            # We want to know: How many students have a higher Average for this marks_system_id?
            exam_rank_q = text("""
                SELECT COUNT(*) + 1
                FROM marks_monthly mm
                JOIN learning l ON mm.student_id = l.studentid
                JOIN students st ON l.studentid = st.id
                WHERE mm.academic_id = :aid
                  AND mm.marks_system_id = :msid
                  AND l.programid = :pid
                  AND l.gradeid = :gid
                  AND l.shiftid = :shift_id
                  AND l.academicid = :aid
                  AND (:branch_id IS NULL OR l.branch_id = :branch_id)
                  AND (:grade_type_id IS NULL OR l.grade_type_id = :grade_type_id)
                  AND st.status = 1
                  AND mm.average > :my_avg
            """)
            ex_rank = db.execute(exam_rank_q, {
                "aid": academic_id,
                "msid": sys_id,
                "pid": program_id,
                "gid": grade_id,
                "shift_id": shift_id,
                "branch_id": branch_id,
                "grade_type_id": grade_type_id,
                "my_avg": avg
            }).scalar()
            
            details["items"].append({
                "type": "exam", # Exam/Monthly result
                "label": name,
                "score": float(total),
                "average": float(avg),
                "grade": grade,
                "us_grade": grade,
                "kh_grade": kh_grade,
                "rank": str(ex_rank) if ex_rank else "-",
                "is_highlight": False,
                "is_failed": is_fail_grade(grade)
            })
        else:
            # Missing result
            details["items"].append({
                "type": "exam",
                "label": name,
                "score": 0.0,
                "average": 0.0,
                "grade": "-",
                "us_grade": "-",
                "kh_grade": "",
                "rank": "-", 
                "is_highlight": False,
                "is_failed": False
            })

    # --- Overall Semester Summary ---
    if not sign_code:
            if "1" in result_name or "១" in result_name or "I" in result_name or "one" in result_name.lower():
                sign_code = "RSEM1"
            elif "2" in result_name or "២" in result_name or "II" in result_name or "two" in result_name.lower():
                sign_code = "RSEM2"

    sem_res = None
    if sign_code:
        sem_query = text("""
            SELECT ms.total, ms.average, ms.teacher_comment, gs.us_grade, gs.kh_grade, ms.exam_name
            FROM marks_semester ms
            LEFT JOIN grade_scale gs ON ms.grade_scale_id = gs.id
            INNER JOIN exam_calculate_sign ecs ON ecs.result_name = ms.exam_name 
                AND ecs.academic_id = :academic_id 
                AND ecs.program_id = :program_id 
                AND ecs.grade_group_id = :grade_group_id 
                AND ecs.sign_code = :sign_code
            WHERE ms.student_id = :student_id
            AND ms.academic_id = :academic_id 
        """)
        sem_res = db.execute(sem_query, {
            "student_id": student_id,
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_group_id": grade_group_id,
            "sign_code": sign_code
        }).fetchone()
    else:
        # Fallback to name
        sem_query = text("""
            SELECT total, average, teacher_comment, gs.us_grade, gs.kh_grade, ms.exam_name
            FROM marks_semester ms
            LEFT JOIN grade_scale gs ON ms.grade_scale_id = gs.id
            WHERE student_id = :student_id AND ms.academic_id = :academic_id AND exam_name = :result_name
        """)
        sem_res = db.execute(sem_query, {
            "student_id": student_id,
            "academic_id": academic_id,
            "result_name": result_name
        }).fetchone()
    
    if sem_res:
        # Calculate Rank for Semester Summary (SQL)
        my_avg = safe_decimal(sem_res[1], Decimal('0'))
        
        sem_rank_q = text("""
            SELECT COUNT(*) + 1
            FROM marks_semester ms
            JOIN learning l ON ms.student_id = l.studentid
            JOIN students st ON l.studentid = st.id
            WHERE ms.academic_id = :aid
              AND l.programid = :pid
              AND l.gradeid = :gid
              AND l.shiftid = :shift_id
              AND l.academicid = :aid
              AND (:branch_id IS NULL OR l.branch_id = :branch_id)
              AND (:grade_type_id IS NULL OR l.grade_type_id = :grade_type_id)
              AND st.status = 1
              AND ms.exam_name = :ename
              AND ms.average > :my_avg
        """)
        
        summ_rank = db.execute(sem_rank_q, {
            "aid": academic_id,
            "pid": program_id,
            "gid": grade_id,
            "shift_id": shift_id,
            "branch_id": branch_id,
            "grade_type_id": grade_type_id,
            "ename": sem_res[5],
            "my_avg": my_avg
        }).scalar()

        details["summary"] = {
            "total": float(sem_res[0]) if sem_res[0] is not None else None,
            "average": float(sem_res[1]) if sem_res[1] is not None else None,
            "grade": sem_res[3] or "-",
            "us_grade": sem_res[3] or "-",
            "kh_grade": sem_res[4] or "-",
            "rank": str(summ_rank) if summ_rank else "-",
            "is_failed": is_fail_grade(sem_res[3] or "-")
        }
        details["comment"] = sem_res[2] or ""

    return details
