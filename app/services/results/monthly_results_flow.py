from decimal import Decimal
from sqlalchemy import text
from ...utils.results_utils import (
    safe_decimal, get_grade_from_scale, is_fail_grade, 
    calculate_exam_rank, get_max_scale_score, get_grade_from_score_raw
)
import re
import logging

logger = logging.getLogger(__name__)

def generate_monthly_report(
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
    exam_type: str
):
    """
    Generates the monthly/input result report.
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

        # 4. Fetch Class-Wide Subject Totals for Rankings
        class_rank_q = text("""
            SELECT mi.student_id, mi.subject_id, mi.marks
            FROM marks_input mi
            JOIN students st ON mi.student_id = st.id
            WHERE mi.academic_id = :aid
            AND mi.marks_system_id = :sid
            AND st.status = 1
            AND mi.subject_id IN :sub_ids
        """)
        
        c_rank_rows = db.execute(class_rank_q, {
            "aid": academic_id,
            "sid": marks_system_id,
            "sub_ids": tuple(subject_ids)
        }).fetchall()
        
        subject_rank_map = {}
        for r_row in c_rank_rows:
            r_sid = r_row[0]
            r_sub = r_row[1]
            r_val = safe_decimal(r_row[2], Decimal('0'))
            
            if r_sub not in subject_rank_map:
                subject_rank_map[r_sub] = []
            subject_rank_map[r_sub].append((r_sid, r_val))

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
            # normalized_mark is out of calc_m. 
            # get_grade_from_scale usually expects % or we use get_grade_from_score_raw with max_possible=calc_m
            
            sub_grade, sub_kh_grade = get_grade_from_score_raw(normalized_mark, db, academic_id, grade_group_id, calc_m)
            
            # Calculate Rank
            rank_list = subject_rank_map.get(sub_id, [])
            
            # We need to normalize rank scores too? Or just compare raw marks if everyone has same full_marks?
            # Assuming same full_marks for all students in same class/subject.
            # So raw marks comparison is fine.
            rank_list.sort(key=lambda x: x[1], reverse=True)
            
            my_rank = "-"
            current_rank = 0
            last_score = Decimal('-1')
            
            for idx, (rsid, rscore) in enumerate(rank_list):
                 if rscore < last_score:
                     current_rank = idx + 1
                 elif idx == 0:
                     current_rank = 1
                 
                 last_score = rscore
                 if rsid == student_id:
                     my_rank = str(current_rank)
                     break
            
            # For "Input" like result, we display subjects
            details["items"].append({
                "type": "subject",
                "label": s_name,
                "score": float(raw_mark), # Show raw mark or normalized? Usually raw mark entry is what student recognizes.
                # Use raw_mark for "score" as display, but maybe normalized for "total"? 
                # Kortra usually shows Normalized in separate column or just one.
                # Let's show Normalized as "total" if different?
                # Using standard ResultItem: score (required), total (optional).
                "score": None if is_missing else float(normalized_mark), # Normalized is usually what matters for total sum
                "average": None, 
                "max_score": float(calc_m),
                "grade": sub_grade,
                "us_grade": sub_grade,
                "kh_grade": sub_kh_grade,
                "rank": my_rank,
                "is_highlight": False,
                "is_failed": is_fail_grade(sub_grade),
                "total": None if is_missing else (float(raw_mark) if raw_mark != normalized_mark else None) # Hint raw if different
            })
            
        # Summary
        if student_subject_count > 0:
             # Calculate Average
             # Weighted average? or Simple sum / divide_by?
             # Formula usually: (SUB1+SUB2...) / Divider
             
             final_average = final_total / divide_by if divide_by > 0 else final_total
             all_missing = len(student_marks) == 0
             
             # Get Overall Grade
             # If exam_type is "monthly", get grade from monthly scale?
             # Or if it's "input" (like sub-exam), might not have overall grade.
             
             # Fetch monthly result if exists (for overall rank/grade)
             # Wait, if we are calculating dynamically, we might not have stored monthly result yet?
             # But usually we read FROM marks_monthly for summary if available.
             
             # Try fetch stored summary from marks_monthly
             mm_q = text("""
                SELECT total, average, gs.us_grade, gs.kh_grade 
                FROM marks_monthly mm
                LEFT JOIN grade_scale gs ON mm.grade_scale_id = gs.id
                WHERE student_id=:sid AND marks_system_id=:msid AND academic_id=:aid
             """)
             mm_row = db.execute(mm_q, {"sid": student_id, "msid": marks_system_id, "aid": academic_id}).fetchone()
             
             if mm_row:
                 details["summary"] = {
                     "total": None if all_missing else float(mm_row[0]),
                     "average": None if all_missing else float(mm_row[1]),
                     "grade": mm_row[2] or "-",
                     "us_grade": mm_row[2] or "-",
                     "kh_grade": mm_row[3] or "-",
                     "is_failed": is_fail_grade(mm_row[2] or "-")
                 }
             else:
                 # Calculate on fly
                 overall_grade, overall_kh = get_grade_from_score_raw(final_average, db, academic_id, grade_group_id, Decimal('100')) # Assumes avg is %
                 details["summary"] = {
                     "total": None if all_missing else float(final_total),
                     "average": None if all_missing else float(final_average),
                     "grade": overall_grade,
                     "us_grade": overall_grade,
                     "kh_grade": overall_kh,
                     "is_failed": is_fail_grade(overall_grade)
                 }

        if all_missing:
            details["summary"]["grade"] = "-"
            details["summary"]["us_grade"] = "-"
            details["summary"]["kh_grade"] = "-"
            if "rank" in details["summary"]:
                details["summary"]["rank"] = "-"
            details["summary"]["is_failed"] = False

    return details
