from decimal import Decimal
from sqlalchemy import text
from ...utils.results_utils import safe_decimal, is_fail_grade
import logging

logger = logging.getLogger(__name__)

def generate_iep_yearly_report(
    db, 
    student_id: int, 
    academic_id: int, 
    program_id: int, 
    grade_group_id: int, 
    grade_id: int, 
    shift_id: int, 
    result_name: str,
    sign_code: str,
    divide_by: Decimal,
    grade_type_id: int | None = None,
    branch_id: int | None = None
):
    """
    Generates the yearly report for IEP programs.
    - Breakdown by Semester Results (RSEM1, RSEM2)
    - Overall Yearly Summary (from marks_yearly)
    """
    # Logic identical to KH Yearly for now, but broken out for explicit structure matching
    # and future divergence if needed (e.g. detailed subject yearly average).
    
    details = {
        "items": [],
        "summary": {},
        "comment": ""
    }

    # 1. Fetch RSEM1 and RSEM2 results
    sem_configs_q = text("""
        SELECT id, sign_code, result_name 
        FROM exam_calculate_sign 
        WHERE academic_id = :aid AND program_id = :pid AND grade_group_id = :ggid AND sign_code IN ('RSEM1', 'RSEM2')
    """)
    sem_configs = db.execute(sem_configs_q, {
        "aid": academic_id,
        "pid": program_id,
        "ggid": grade_group_id
    }).fetchall()
    
    sign_codes = [r[1] for r in sem_configs]
    
    if sign_codes:
        sem_q = text("""
            SELECT ms.exam_name, ms.total, ms.average, gs.us_grade, gs.kh_grade, ecs.sign_code
            FROM marks_semester ms
            LEFT JOIN grade_scale gs ON ms.grade_scale_id = gs.id
            INNER JOIN exam_calculate_sign ecs ON ecs.result_name = ms.exam_name 
                AND ecs.academic_id = :aid 
                AND ecs.program_id = :pid 
                AND ecs.grade_group_id = :ggid 
                AND ecs.sign_code IN :scodes
            WHERE ms.student_id = :sid 
                AND ms.academic_id = :aid 
                AND ms.program_id = :pid 
                AND ms.grade_group_id = :ggid
        """)
        
        sem_res = db.execute(sem_q, {
            "aid": academic_id,
            "pid": program_id,
            "ggid": grade_group_id,
            "scodes": tuple(sign_codes),
            "sid": student_id
        }).fetchall()
        
        sem_map = {r[5]: r for r in sem_res}
        
        term_order = ['RSEM1', 'RSEM2']
        if not any(sc in sign_codes for sc in term_order):
             term_order = sorted(sign_codes)
             
        for code in term_order:
            if code not in sign_codes: continue
            
            row = sem_map.get(code)
            
            label = code
            if code == 'RSEM1': label = "Semester 1"
            elif code == 'RSEM2': label = "Semester 2"
            
            if row:
                total = safe_decimal(row[1], Decimal('0'))
                avg = safe_decimal(row[2], Decimal('0'))
                grade = row[3] or '-'
                kh_grade = row[4] or ''
                
                # Calculate Rank for Semester (Scoped)
                rank_q = text("""
                    SELECT COUNT(*) + 1
                    FROM marks_semester ms
                    JOIN learning l ON ms.student_id = l.studentid
                    JOIN students st ON l.studentid = st.id
                    WHERE ms.academic_id = :aid 
                      AND ms.program_id = :pid 
                      AND ms.grade_id = :gid
                      AND ms.exam_name = :ename
                      AND l.programid = :pid
                      AND l.gradeid = :gid
                      AND l.shiftid = :shift_id
                      AND l.academicid = :aid
                      AND (:branch_id IS NULL OR l.branch_id = :branch_id)
                      AND (:grade_type_id IS NULL OR l.grade_type_id = :grade_type_id)
                      AND st.status = 1
                      AND ms.average > :my_avg
                """)
                rank = db.execute(rank_q, {
                    "aid": academic_id,
                    "pid": program_id,
                    "gid": grade_id,
                    "shift_id": shift_id,
                    "branch_id": branch_id,
                    "grade_type_id": grade_type_id,
                    "ename": row[0],
                    "my_avg": avg
                }).scalar()
                
                details["items"].append({
                    "type": "semester",
                    "label": row[0] or label,
                    "score": float(total),
                    "average": float(avg),
                    "grade": grade,
                    "us_grade": grade,
                    "kh_grade": kh_grade,
                    "rank": str(rank) if rank else "-",
                    "is_highlight": False,
                    "is_failed": is_fail_grade(grade)
                })
            else:
                 details["items"].append({
                    "type": "semester",
                    "label": label,
                    "score": 0.0,
                    "average": 0.0,
                    "grade": "-",
                    "us_grade": "-",
                    "kh_grade": "",
                    "rank": "-",
                    "is_highlight": False,
                    "is_failed": False
                })

    # 2. Overall Yearly Summary
    y_q = text("""
        SELECT total, average, teacher_comment, gs.us_grade, gs.kh_grade
        FROM marks_yearly my
        LEFT JOIN grade_scale gs ON my.grade_scale_id = gs.id
        WHERE my.student_id = :sid AND my.academic_id = :aid AND my.exam_name = :name
    """)
    y_res = db.execute(y_q, {
        "sid": student_id,
        "aid": academic_id,
        "name": result_name
    }).fetchone()
    
    if y_res:
         # Calculate Rank for Yearly (Scoped)
         y_avg = safe_decimal(y_res[1], Decimal('0'))
         y_rank_q = text("""
            SELECT COUNT(*) + 1
            FROM marks_yearly my
            JOIN learning l ON my.student_id = l.studentid
            JOIN students st ON l.studentid = st.id
            WHERE my.academic_id = :aid 
              AND my.program_id = :pid 
              AND my.grade_id = :gid
              AND my.exam_name = :name
              AND l.programid = :pid
              AND l.gradeid = :gid
              AND l.shiftid = :shift_id
              AND l.academicid = :aid
              AND (:branch_id IS NULL OR l.branch_id = :branch_id)
              AND (:grade_type_id IS NULL OR l.grade_type_id = :grade_type_id)
              AND st.status = 1
              AND my.average > :my_avg
         """)
         y_rank = db.execute(y_rank_q, {
            "aid": academic_id,
            "pid": program_id,
            "gid": grade_id,
            "shift_id": shift_id,
            "branch_id": branch_id,
            "grade_type_id": grade_type_id,
            "name": result_name,
            "my_avg": y_avg
         }).scalar()

         details["summary"] = {
            "total": float(y_res[0]) if y_res[0] is not None else None,
            "average": float(y_res[1]) if y_res[1] is not None else None,
            "grade": y_res[3] or "-",
            "us_grade": y_res[3] or "-",
            "kh_grade": y_res[4] or "-",
            "rank": str(y_rank) if y_rank else "-",
            "is_failed": is_fail_grade(y_res[3] or "-")
        }
         details["comment"] = y_res[2] or ""
    
    return details
