from decimal import Decimal
from sqlalchemy import text
from ...utils.results_utils import (
    safe_decimal, get_grade_from_score_raw, is_fail_grade, class_scope_rank_sql_suffix
)
import re
import logging

logger = logging.getLogger(__name__)

def generate_en_monthly_report(
    db, 
    student_id: int, 
    academic_id: int, 
    program_id: int, 
    grade_group_id: int, 
    grade_id: int, 
    shift_id: int, 
    marks_system_id: int,
    ecs_id: int,
    formula: str,
    divide_by: Decimal, 
    exam_type: str,
    grade_type_id: int | None = None,
    branch_id: int | None = None
):
    """
    Generates the EN monthly/input result report.
    - Breakdown by Subject
    - Overall Summary (Total/Avg)
    """
    
    details = {
        "items": [],
        "summary": {},
        "comment": ""
    }

    # 1. Get List of Subjects
    # Support full priority: 
    # 1. exam_calculate_sign_subjects (if ecs_id available)
    # 2. marks_system_subjects (if marks_system_id available)
    # 3. Formula parsing (fallback)

    subject_ids = []

    # Priority 1: exam_calculate_sign_subjects
    if ecs_id:
        q_ecs_sub = text("SELECT subject_id FROM exam_calculate_sign_subjects WHERE exam_calculate_sign_id = :ecs_id")
        rows = db.execute(q_ecs_sub, {"ecs_id": ecs_id}).fetchall()
        if rows:
            subject_ids = [r[0] for r in rows]

    # Priority 2: marks_system_subjects
    if not subject_ids and marks_system_id:
        q_mss = text("SELECT subject_id FROM marks_system_subjects WHERE marks_system_id = :marks_system_id")
        rows = db.execute(q_mss, {"marks_system_id": marks_system_id}).fetchall()
        if rows:
            subject_ids = [r[0] for r in rows]

    # Priority 3: Parse formula as Subject IDs (integers)
    if not subject_ids:
        subject_ids = [int(s) for s in re.findall(r'\d+', formula)]
    
    # Ensure unique IDs
    subject_ids = list(set(subject_ids))

    # 2. Get Subject Names and Rules
    if subject_ids:
        sub_query = text("SELECT id, subject_name FROM subjects WHERE id IN :ids")
        sub_res = db.execute(sub_query, {"ids": tuple(subject_ids)}).fetchall()
        sub_map = {row[0]: row[1] for row in sub_res}

        # Get subject rules for calculations
        subj_rules_query = text("""
            SELECT subject_id, full_marks, calculate_marks
            FROM subjects_group
            WHERE academic_id = :academic_id
            AND program_id = :program_id
            AND grade_group_id = :grade_group_id
            AND subject_id IN :subject_ids
        """)
        subj_rules_result = db.execute(subj_rules_query, {
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_group_id": grade_group_id,
            "subject_ids": tuple(subject_ids)
        }).fetchall()
        
        subj_rules = {}
        for r in subj_rules_result:
            subj_rules[r[0]] = {
                "full_marks": safe_decimal(r[1], Decimal('100.0')),
                "calculate_marks": safe_decimal(r[2], Decimal('100.0'))
            }

        # 3. Get Student Marks
        marks_query = text("""
            SELECT subject_id, marks 
            FROM marks_input 
            WHERE student_id = :student_id 
            AND academic_id = :academic_id 
            AND marks_system_id = :marks_system_id
            AND subject_id IN :subject_ids
        """)
        marks_rows = db.execute(marks_query, {
            "student_id": student_id,
            "academic_id": academic_id,
            "marks_system_id": marks_system_id,
            "subject_ids": tuple(subject_ids)
        }).fetchall()
        
        student_marks = {row[0]: safe_decimal(row[1], Decimal('0')) for row in marks_rows}

        # 5. Build Items List
        final_total = Decimal('0')
        student_subject_count = 0
        
        for sub_id in subject_ids:
            s_name = sub_map.get(sub_id, f"Subject {sub_id}")
            is_missing = sub_id not in student_marks
            raw_mark = student_marks.get(sub_id, Decimal('0'))
            
            rule = subj_rules.get(sub_id, {"full_marks": Decimal('100'), "calculate_marks": Decimal('100')})
            full_m = rule['full_marks']
            calc_m = rule['calculate_marks']
            
            # Normalize to Calculate Marks (e.g. 50)
            if full_m > 0:
                normalized_mark = (raw_mark / full_m) * calc_m
            else:
                normalized_mark = raw_mark # Fallback
                
            # Accumulate Total
            final_total += normalized_mark
            student_subject_count += 1
            
            # Get Grade (using Percentage)
            sub_grade, sub_kh_grade = get_grade_from_score_raw(normalized_mark, db, academic_id, grade_group_id, calc_m)
            
            # Calculate Rank for Subject (SQL) - SCOPED TO CLASS
            sub_rank_q = text("""
                SELECT COUNT(*) + 1
                FROM marks_input mi
                JOIN learning l ON mi.student_id = l.studentid
                JOIN students st ON l.studentid = st.id
                WHERE mi.academic_id = :aid
                  AND mi.marks_system_id = :msid
                  AND mi.subject_id = :sub_id
                  AND mi.marks > :my_mark
                  AND l.programid = :pid
                  AND l.gradeid = :gid
                  AND l.shiftid = :shift_id
                  AND l.academicid = :aid
                  AND (:branch_id IS NULL OR l.branch_id = :branch_id)
                  AND (:grade_type_id IS NULL OR l.grade_type_id = :grade_type_id)
                  AND st.status = 1
            """)
            s_rank = db.execute(sub_rank_q, {
                "aid": academic_id,
                "msid": marks_system_id,
                "sub_id": sub_id,
                "my_mark": raw_mark,
                "pid": program_id,
                "gid": grade_id,
                "shift_id": shift_id,
                "branch_id": branch_id,
                "grade_type_id": grade_type_id
            }).scalar()
            
            # For "Input" like result, we display subjects
            details["items"].append({
                "type": "subject",
                "label": s_name,
                "score": None if is_missing else float(raw_mark),  # Return None if missing
                "average": None, 
                "max_score": float(full_m),  # Changed: show full marks
                "grade": sub_grade,
                "us_grade": sub_grade,
                "kh_grade": sub_kh_grade,
                "rank": str(s_rank) if s_rank else "-",
                "is_highlight": False,
                "is_failed": is_fail_grade(sub_grade),
                "total": None  # No longer needed
            })
            
        # Summary
        if student_subject_count > 0:
             final_average = final_total / divide_by if divide_by > 0 else final_total
             all_missing = len(student_marks) == 0
             
             # Try fetch stored summary from marks_monthly
             mm_q = text("""
                SELECT total, average, gs.us_grade, gs.kh_grade, teacher_comment 
                FROM marks_monthly mm
                LEFT JOIN grade_scale gs ON mm.grade_scale_id = gs.id
                WHERE mm.student_id=:sid AND mm.marks_system_id=:msid AND mm.academic_id=:aid
             """)
             mm_row = db.execute(mm_q, {"sid": student_id, "msid": marks_system_id, "aid": academic_id}).fetchone()
             
             if mm_row:
                 # Calculate Rank for Overall Summary (SQL)
                 my_avg = safe_decimal(mm_row[1], Decimal('0'))
                 
                 scope_sql, scope_params = class_scope_rank_sql_suffix(
                     grade_type_id, branch_id
                 )
                 summ_rank_q = text(f"""
                    SELECT COUNT(*) + 1
                    FROM marks_monthly mm
                    JOIN learning l ON mm.student_id = l.studentid
                    JOIN grade g ON l.gradeid = g.id
                    JOIN students st ON l.studentid = st.id
                    WHERE mm.academic_id = :aid
                      AND mm.marks_system_id = :msid
                      AND l.programid = :pid
                      AND l.gradeid = :gid
                      AND l.shiftid = :shift_id
                      AND l.academicid = :aid
                      AND st.status = 1
                      {scope_sql}
                      AND mm.average > :my_avg
                 """)
                 summ_rank = db.execute(summ_rank_q, {
                    "aid": academic_id,
                    "msid": marks_system_id,
                    "pid": program_id,
                    "gid": grade_id,
                    "shift_id": shift_id,
                    "my_avg": my_avg,
                    **scope_params,
                 }).scalar()

                 details["summary"] = {
                     "total": None if all_missing else float(mm_row[0]),
                     "average": None if all_missing else float(mm_row[1]),
                     "grade": mm_row[2] or "-",
                     "us_grade": mm_row[2] or "-",
                     "kh_grade": mm_row[3] or "-",
                     "rank": str(summ_rank) if summ_rank else "-",
                     "is_failed": is_fail_grade(mm_row[2] or "-")
                 }
                 details["comment"] = mm_row[4] or ""
             else:
                 # Calculate on fly
                 overall_grade, overall_kh = get_grade_from_score_raw(final_average, db, academic_id, grade_group_id, Decimal('100'))
                 
                 # Best-effort rank against others
                 scope_sql, scope_params = class_scope_rank_sql_suffix(
                     grade_type_id, branch_id
                 )
                 summ_rank_q = text(f"""
                    SELECT COUNT(*) + 1
                    FROM marks_monthly mm
                    JOIN learning l ON mm.student_id = l.studentid
                    JOIN grade g ON l.gradeid = g.id
                    JOIN students st ON l.studentid = st.id
                    WHERE mm.academic_id = :aid
                      AND mm.marks_system_id = :msid
                      AND l.programid = :pid
                      AND l.gradeid = :gid
                      AND l.shiftid = :shift_id
                      AND l.academicid = :aid
                      AND st.status = 1
                      {scope_sql}
                      AND mm.average > :my_avg
                 """)
                 summ_rank = db.execute(summ_rank_q, {
                    "aid": academic_id,
                    "msid": marks_system_id,
                    "pid": program_id,
                    "gid": grade_id,
                    "shift_id": shift_id,
                    "my_avg": final_average,
                    **scope_params,
                 }).scalar()

                 details["summary"] = {
                     "total": None if all_missing else float(final_total),
                     "average": None if all_missing else float(final_average),
                     "grade": overall_grade,
                     "us_grade": overall_grade,
                     "kh_grade": overall_kh,
                     "rank": str(summ_rank) if summ_rank else "-",
                     "is_failed": is_fail_grade(overall_grade)
                 }

        if all_missing:
            details["summary"]["grade"] = "-"
            details["summary"]["us_grade"] = "-"
            details["summary"]["kh_grade"] = "-"
            details["summary"]["rank"] = "-"
            details["summary"]["is_failed"] = False

    return details
