from decimal import Decimal
from sqlalchemy import text
from ...utils.results_utils import safe_decimal, is_fail_grade, get_grade_from_scale, get_max_scale_score
import logging

logger = logging.getLogger(__name__)

def generate_kh_semester_report(
    db, 
    student_id: int, 
    academic_id: int, 
    program_id: int, 
    grade_group_id: int, 
    grade_id: int, 
    shift_id: int, 
    all_sys_ids: list,
    formula: str,
    result_name: str,
    sign_code: str,
    grade_type_id: int | None = None,
    branch_id: int | None = None
):
    """
    Generates the semester report for KH programs.
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
    # Join with exam_calculate_sign to get the sign_code (MON1, MON2, etc.)
    q_names = text("""
        SELECT ms.id, ms.marks_name, ecs.sign_code 
        FROM marks_system ms
        LEFT JOIN exam_calculate_sign ecs ON ms.id = ecs.marks_system_id AND ecs.is_active = 1
        WHERE ms.id IN :ids
    """)
    names_res = db.execute(q_names, {"ids": tuple(all_sys_ids)}).fetchall()
    
    # Map ID -> (Name, SignCode)
    system_info_map = {r[0]: {"name": r[1], "code": str(r[2] or "").upper()} for r in names_res}
    names_map = {r[0]: r[1] for r in names_res} # Keep for backward compatibility/display label
    
    # 2. Fetch current student's marks
    mm_q = text("""
        SELECT mm.marks_system_id, mm.total, mm.average, gs.us_grade, gs.kh_grade, mm.exam_name
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

    # 3. Fetch all students' marks for ranking (Month Average Only)
    # We only need this for calculation of the "Month Average" aggregation rank.
    # Individual exams will use direct SQL ranking.
    rank_sql = """
        SELECT mm.student_id, mm.marks_system_id, mm.total, mm.average
        FROM marks_monthly mm
        JOIN learning l ON mm.student_id = l.studentid
        JOIN students st ON l.studentid = st.id
        WHERE mm.academic_id = :aid
        AND mm.marks_system_id IN :sys_ids
        AND l.programid = :pid
        AND l.gradeid = :gid
        AND l.shiftid = :shift_id
        AND l.academicid = :aid
        AND (:branch_id IS NULL OR l.branch_id = :branch_id)
        AND st.status = 1
    """
    
    params = {
        "aid": academic_id,
        "sys_ids": tuple(all_sys_ids),
        "pid": program_id,
        "gid": grade_id,
        "shift_id": shift_id,
        "branch_id": branch_id
    }

    if grade_type_id:
        rank_sql += " AND l.grade_type_id = :gtid"
        params["gtid"] = grade_type_id
    else:
        rank_sql += " AND l.grade_type_id IS NULL"

    rank_q = text(rank_sql)
    rank_rows = db.execute(rank_q, params).fetchall()
    
    # Organize data for "Month Average" ranking: student_id -> list of averages
    student_avgs_map = {}

    for r_row in rank_rows:
        r_sid = r_row[0]
        r_sys = r_row[1]
        r_avg = safe_decimal(r_row[3], Decimal('0'))
        
        # Month Average Ranking Data
        if r_sid not in student_avgs_map:
            student_avgs_map[r_sid] = []
        if r_avg is not None:
             student_avgs_map[r_sid].append(r_avg)
    
    # Calculate "Month Average" Rank for all students
    # List of (student_id, mean_average)
    month_avg_rank_list = []
    for s_id, avgs in student_avgs_map.items():
        if avgs:
            s_sum = sum(avgs)
            s_mean = s_sum / Decimal(str(len(avgs)))
            month_avg_rank_list.append((s_id, s_mean))
    
    # Sort by Mean Average Descending
    month_avg_rank_list.sort(key=lambda x: x[1], reverse=True)

    # 4. Build items list with ranks
    for sys_id in all_sys_ids:
        # Get System Info
        sys_info = system_info_map.get(sys_id, {})
        sys_code = sys_info.get("code", "")
        name = names_map.get(sys_id, f"Exam {sys_id}")
        
        row = mm_map.get(sys_id)
        
        if row:
            total = safe_decimal(row[1], Decimal('0'))
            avg = safe_decimal(row[2], Decimal('0'))
            grade = row[3] or '-'
            kh_grade = row[4] or ''
            exam_name = row[5] or f"Exam {sys_id}"  # Use exam_name from marks_monthly
            
            # Calculate Rank for Exam (SQL)
            # Rank against marks_monthly for this marks_system
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
            
            # Determine Type (Regular Exam vs Semester Exam)
            item_type = "exam"
            if sys_code in ['SEM1', 'SEM2']:
                item_type = "semester_exam"
                
            details["items"].append({
                "type": item_type,
                "label": exam_name,  # Use exam_name from marks_monthly
                "score": float(total),
                "average": float(avg),
                "grade": grade,
                "us_grade": grade,
                "kh_grade": kh_grade,
                "rank": str(ex_rank) if ex_rank else "-",
                "sign_code": sys_code, # Helper for sorting
                "is_highlight": False,
                "is_failed": is_fail_grade(grade)
            })

    # 5. Calculate "Month Average"
    # ... (existing calculation logic) ...
    
    my_month_avgs = student_avgs_map.get(student_id, [])
    
    # Filter Monthly Averages based on Semester (RSEM1 vs RSEM2)
    target_month_codes = set()
    if sign_code == 'RSEM1':
        target_month_codes = {'MON1', 'MON2', 'MON3', 'MON4'}
    elif sign_code == 'RSEM2':
        target_month_codes = {'MON5', 'MON6', 'MON7', 'MON8'}
    
    # Re-collect Valid Averages for Student
    final_monthly_avgs = []
    # logger.info(f"Filtering Month Average Components for Student {student_id}. Target Codes: {target_month_codes}")

    for sys_id in all_sys_ids:
        sys_info = system_info_map.get(sys_id, {})
        sys_code = sys_info.get("code", "")
        
        if sys_code not in target_month_codes:
            continue
        
        if sys_id in mm_map:
             row = mm_map[sys_id]
             if row and row[2] is not None:
                 val = safe_decimal(row[2], Decimal('0'))
                 final_monthly_avgs.append(val)

    if final_monthly_avgs:
        sum_avg = sum(final_monthly_avgs)
        count_avg = len(final_monthly_avgs)
        mean_avg = sum_avg / Decimal(str(count_avg))
        
        # Recalculate Rank (Using Month Average List built in step 3)
        filtered_rank_list = []
        temp_student_avgs = {}
        for r_row in rank_rows:
            r_sid = r_row[0]
            r_sys = r_row[1]
            r_avg = safe_decimal(r_row[3], Decimal('0'))
            r_sys_code = system_info_map.get(r_sys, {}).get("code", "")
            if r_sys_code not in target_month_codes:
                continue
            if r_sid not in temp_student_avgs:
                temp_student_avgs[r_sid] = []
            if r_avg is not None:
                 temp_student_avgs[r_sid].append(r_avg)
                 
        for s_id, avgs in temp_student_avgs.items():
            if avgs:
                s_sum = sum(avgs)
                s_mean = s_sum / Decimal(str(len(avgs)))
                filtered_rank_list.append((s_id, s_mean))
        
        filtered_rank_list.sort(key=lambda x: x[1], reverse=True)
        
        my_agg_rank = "-"
        current_rank = 0
        last_score = Decimal('-1')
        for idx, (rsid, rscore) in enumerate(filtered_rank_list):
            if rscore < last_score:
                current_rank = idx + 1
            elif idx == 0:
                current_rank = 1
            last_score = rscore
            if rsid == student_id:
                my_agg_rank = str(current_rank)
                break

        # Normalize to Percentage for Grade Lookup
        max_scale_val = get_max_scale_score(db, academic_id, grade_group_id)
        if max_scale_val > Decimal('0'):
            avg_percentage = (mean_avg / max_scale_val) * Decimal('100.0')
        else:
            avg_percentage = Decimal('0')
            
        us_grade, kh_grade = get_grade_from_scale(avg_percentage, db, academic_id, grade_group_id)
        
        # Determine label based on semester
        if sign_code == "RSEM1":
            month_avg_label = "មធ្យមភាគខែក្នុងឆមាសទី១"
        elif sign_code == "RSEM2":
            month_avg_label = "មធ្យមភាគខែក្នុងឆមាសទី២"
        else:
            month_avg_label = "Month Average"  # Fallback
        
        # INSERT (Not prepend yet, we will sort)
        details["items"].append({
            "type": "month_aggregation",
            "label": month_avg_label,
            "score": float(sum_avg), 
            "average": float(mean_avg), 
            "grade": us_grade,
            "us_grade": us_grade,
            "kh_grade": kh_grade,
            "rank": my_agg_rank, 
            "sign_code": "MONTH_AVG", # Virtual Code for sorting
            "is_highlight": True, 
            "is_failed": is_fail_grade(us_grade)
        })

    # 6. Apply Sorting
    # Order: MON1-4 -> Month Avg -> SEM1 | MON5-8 -> Month Avg -> SEM2
    sort_order = {
        "MON1": 10, "MON2": 20, "MON3": 30, "MON4": 40,
        "MONTH_AVG": 45,
        "SEM1": 50,
        "MON5": 60, "MON6": 70, "MON7": 80, "MON8": 90,
        "SEM2": 95,
        # Fallback for others
        "RSEM1": 100, "RSEM2": 110, "YEAR": 120
    }
    
    details["items"].sort(key=lambda x: sort_order.get(x.get("sign_code", ""), 999))


    # --- Overall Semester Summary ---
    if not sign_code:
            if "1" in result_name or "១" in result_name or "I" in result_name or "one" in result_name.lower():
                sign_code = "RSEM1"
            elif "2" in result_name or "២" in result_name or "II" in result_name or "two" in result_name.lower():
                sign_code = "RSEM2"

    sem_res = None
    sem_res = None
    
    # Query using sign_code lookup (JOIN with exam_calculate_sign)
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
