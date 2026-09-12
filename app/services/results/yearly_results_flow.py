from decimal import Decimal
from sqlalchemy import text
from ...utils.results_utils import safe_decimal, is_fail_grade
from ...services.results.consistency_utils import build_consistency_check
import logging

logger = logging.getLogger(__name__)

def generate_yearly_report(
    db, 
    student_id: int, 
    academic_id: int, 
    program_id: int, 
    grade_group_id: int, 
    grade_id: int, 
    shift_id: int, 
    result_name: str,
    sign_code: str,
    divide_by: Decimal
):
    """
    Generates the yearly report.
    - List of Semesters
    - Overall Yearly Summary
    - Consistency Check
    """
    
    details = {
        "items": [],
        "summary": {},
        "comment": ""
    }

    # 1. Fetch Semester Results
    sem_all_query = text("""
        SELECT ms.exam_name, ms.average, gs.us_grade, gs.kh_grade
        FROM marks_semester ms
        LEFT JOIN grade_scale gs ON ms.grade_scale_id = gs.id
        WHERE ms.student_id = :student_id AND ms.academic_id = :academic_id
        ORDER BY ms.exam_name
    """)
    
    sem_all_res = db.execute(sem_all_query, {
        "student_id": student_id,
        "academic_id": academic_id
    }).fetchall()
    
    for row in sem_all_res:
        details["items"].append({
            "label": row[0],
            "score": float(row[1]) if row[1] is not None else 0.0,
            "max_score": 100,
            "grade": row[2] or "-",
            "us_grade": row[2] or "-",
            "kh_grade": row[3] or "-"
        })
        
    # 2. Fetch Overall Yearly Result
    if not sign_code:
         # Basic heuristic if sign_code missing
         if result_name and "YEAR" in result_name.upper():
             sign_code = "YEAR"

    y_res = None
    if sign_code:
            y_query = text("""
            SELECT my.total, my.average, my.teacher_comment, gs.us_grade, gs.kh_grade
            FROM marks_yearly my
            LEFT JOIN grade_scale gs ON my.grade_scale_id = gs.id
            INNER JOIN exam_calculate_sign ecs ON ecs.result_name = my.exam_name 
                AND ecs.academic_id = :academic_id 
                AND ecs.program_id = :program_id 
                AND ecs.grade_group_id = :grade_group_id 
                AND ecs.sign_code = :sign_code
            WHERE my.student_id = :student_id
            AND my.academic_id = :academic_id 
        """)
            y_res = db.execute(y_query, {
            "student_id": student_id,
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_group_id": grade_group_id,
            "sign_code": sign_code
        }).fetchone()
    else:
        y_query = text("""
            SELECT total, average, teacher_comment, gs.us_grade, gs.kh_grade
            FROM marks_yearly my
            LEFT JOIN grade_scale gs ON my.grade_scale_id = gs.id
            WHERE student_id = :student_id AND my.academic_id = :academic_id AND exam_name = :result_name
        """)
        y_res = db.execute(y_query, {
            "student_id": student_id,
            "academic_id": academic_id,
            "result_name": result_name
        }).fetchone()
    
    if y_res:
        details["summary"] = {
            "total": float(y_res[0]) if y_res[0] is not None else None,
            "average": float(y_res[1]) if y_res[1] is not None else None,
            "grade": y_res[3] or "-",
            "us_grade": y_res[3] or "-",
            "kh_grade": y_res[4] or "-",
            "is_failed": is_fail_grade(y_res[3] or "-")
        }
        details["comment"] = y_res[2] or ""
        
        # 3. Consistency Check
        try:
            stored_avg = safe_decimal(y_res[1], None)
            stored_total = safe_decimal(y_res[0], None)
            
            calc_total = Decimal('0')
            for item in details["items"]:
                calc_total += safe_decimal(item['score'])
                
            calc_avg = calc_total / divide_by if divide_by and divide_by > 0 else Decimal('0')
            
            check_res = build_consistency_check(
                "Yearly",
                stored_avg,
                calc_avg,
                stored_total=stored_total,
                calc_total=calc_total
            )
            if check_res:
                details["consistency"] = check_res
        except Exception as e:
            logger.error(f"Yearly consistency check failed: {e}")

    return details
