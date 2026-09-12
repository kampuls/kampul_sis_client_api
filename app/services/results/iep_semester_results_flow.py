from decimal import Decimal
from sqlalchemy import text
from ...utils.results_utils import safe_decimal, get_grade_from_scale, is_fail_grade
import logging

logger = logging.getLogger(__name__)

def generate_iep_semester_report(
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
    Generates the semester report for IEP/EN students.
    - Breakdown by Subject (aggregated from monthlies)
    - Overall Semester Summary
    """
    
    details = {
        "items": [],
        "summary": {},
        "comment": ""
    }

    if not all_sys_ids:
        return details

    # 1. Fetch Marks aggregated by Subject for CURRENT Student
    marks_q = text("""
        SELECT mi.subject_id, mi.marks, s.subject_name, mi.marks_system_id
        FROM marks_input mi
        JOIN subjects s ON mi.subject_id = s.id
        WHERE mi.student_id = :sid 
        AND mi.academic_id = :aid 
        AND mi.marks_system_id IN :sys_ids
    """)
    
    marks_rows = db.execute(marks_q, {
        "sid": student_id,
        "aid": academic_id,
        "sys_ids": tuple(all_sys_ids)
    }).fetchall()

    subj_agg = {} 
    
    for row in marks_rows:
        sid_subj = row[0]
        mark_val = safe_decimal(row[1], Decimal('0'))
        subj_name = row[2]
        ms_id = row[3]
        
        if sid_subj not in subj_agg:
            subj_agg[sid_subj] = {
                'total': Decimal('0'),
                'months': set(),
                'name': subj_name
            }
        
        subj_agg[sid_subj]['total'] += mark_val
        subj_agg[sid_subj]['months'].add(ms_id)
    
    # 2. Fetch Class-Wide Subject Totals for RANKING
    # Group by student_id and subject_id
    # Note: Removed st.program_id/grade_id/shift_id as they don't exist on students table
    class_rank_q = text("""
        SELECT mi.student_id, mi.subject_id, SUM(mi.marks) as total_marks
        FROM marks_input mi
        JOIN students st ON mi.student_id = st.id
        JOIN learning l ON mi.student_id = l.studentid
        WHERE mi.academic_id = :aid
        AND mi.marks_system_id IN :sys_ids
        AND l.programid = :pid
        AND l.gradeid = :gid
        AND l.shiftid = :shift_id
        AND l.academicid = :aid
        AND (:branch_id IS NULL OR l.branch_id = :branch_id)
        AND (:grade_type_id IS NULL OR l.grade_type_id = :grade_type_id)
        AND st.status = 1  -- Only active students
        GROUP BY mi.student_id, mi.subject_id
    """)
    
    rank_rows = db.execute(class_rank_q, {
        "aid": academic_id,
        "sys_ids": tuple(all_sys_ids),
        "pid": program_id,
        "gid": grade_id,
        "shift_id": shift_id,
        "branch_id": branch_id,
        "grade_type_id": grade_type_id
    }).fetchall()
    
    # Organize rank data: subject_id -> list of (student_id, total)
    subject_rank_map = {}
    for r_row in rank_rows:
        r_sid = r_row[0]
        r_sub = r_row[1]
        r_tot = safe_decimal(r_row[2], Decimal('0'))
        
        if r_sub not in subject_rank_map:
            subject_rank_map[r_sub] = []
        subject_rank_map[r_sub].append((r_sid, r_tot))
            
    # Calculate Averages, Grades, and Ranks per Subject
    for sid_subj, data in subj_agg.items():
        total = data['total']
        months_count = len(data['months'])
        avg = total / Decimal(months_count) if months_count > 0 else Decimal('0')
        
        # Get Grade
        subj_grade_val, _ = get_grade_from_scale(avg, db, academic_id, grade_group_id)

        # Calculate Rank
        # Sort students for this subject by total descending
        rank_list = subject_rank_map.get(sid_subj, [])
        rank_list.sort(key=lambda x: x[1], reverse=True)
        
        my_rank = "-"
        current_rank = 0
        last_score = Decimal('-1')
        
        for idx, (rsid, rscore) in enumerate(rank_list):
            if rscore < last_score:
                current_rank = idx + 1
            elif idx == 0:
                current_rank = 1
            # If tied, current_rank stays same
            
            last_score = rscore
            
            if rsid == student_id:
                my_rank = str(current_rank)
                break

        details["items"].append({
            "type": "subject",
            "label": data['name'],
            "score": float(total),
            "average": float(avg),
            "grade": subj_grade_val,
            "us_grade": subj_grade_val,
            "kh_grade": "",
            "rank": my_rank,
            "total": float(total) if total is not None else None,
            "is_highlight": False,
            "is_failed": is_fail_grade(subj_grade_val)
        })
    
    # Sort subjects by name
    details["items"].sort(key=lambda x: x['label'])

    # --- Overall Semester Summary ---
    # Ideally fetch direct from database using sign_code
    if not sign_code:
            # Try to deduce sign_code
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
