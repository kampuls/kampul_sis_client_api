from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from sqlalchemy import text
import re
import logging


logger = logging.getLogger(__name__)

def is_fail_grade(grade: str) -> bool:
    """Check if the grade represents a failure (F or Failed)."""
    if not grade:
        return False
    g_upper = grade.upper().strip()
    return "F" in g_upper or "FAIL" in g_upper


def safe_decimal(value, default=Decimal('0')):
    """Safely convert value to Decimal."""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            value = value.replace(',', '').replace(' ', '').strip()
            if not value:
                return default
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default

def get_max_scale_score(db_session, academic_id, grade_group_id):
    """Fetches the maximum possible score defined in the grade scales (e.g. 100, 50, 10, 4.0)."""
    try:
        query = text("SELECT MAX(max_marks) as highest_mark FROM grade_scale WHERE academic_id = :academic_id AND grade_group_id = :grade_group_id")
        result = db_session.execute(query, {"academic_id": academic_id, "grade_group_id": grade_group_id}).fetchone()
        if result and result[0] is not None:
             return Decimal(str(result[0]))
        return Decimal('100.0') # Default fallback
    except Exception as e:
        logger.error(f"Error fetching max scale score: {e}")
        return Decimal('100.0')

def get_grade_from_scale(score, db_session, academic_id, grade_group_id):
    """
    Get grade from scale using percentage-based lookup. 
    Matches logic from kortra_env.
    Input 'score' is expected to be a percentage (0-100).
    Returns (us_grade, kh_grade).
    """
    try:
        score_decimal = safe_decimal(score)
        
        # 1. Fetch all grade scales
        query_scales = text("""
            SELECT id, min_marks, max_marks, us_grade, kh_grade 
            FROM grade_scale 
            WHERE academic_id = :academic_id 
            AND grade_group_id = :grade_group_id
            ORDER BY min_marks
        """)
        scales = db_session.execute(query_scales, {
            "academic_id": academic_id, 
            "grade_group_id": grade_group_id
        }).fetchall()
        
        if not scales:
            return "-", "-"
            
        # 2. Determine Scale Domain (Global Min/Max)
        original_min = min(safe_decimal(s[1]) for s in scales)
        original_max = max(safe_decimal(s[2]) for s in scales)
        
        # 3. Map Percentage (0-100) to Original Scale Domain
        # If score is > 100, cap at 100? Or assume it's valid? 
        # Kortra implementation clamps it.
        if score_decimal < Decimal('0'): score_decimal = Decimal('0')
        if score_decimal > Decimal('100'): score_decimal = Decimal('100')
        
        if original_max > original_min:
            mapped_score = (score_decimal / Decimal('100')) * (original_max - original_min) + original_min
        else:
            mapped_score = original_min
            
        # Round for matching
        mapped_score = mapped_score.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # 4. Find Match
        for scale in scales:
            s_min = safe_decimal(scale[1])
            s_max = safe_decimal(scale[2])
            if mapped_score >= s_min and mapped_score <= s_max:
                return scale[3], scale[4] # us_grade, kh_grade
        
        # 5. Fallback: Find closest if no exact match (rounding issues etc)
        # (Optional, but good for robustness)
        # For now, let's just return -,- if no match to avoid false positives, 
        # or implement closest match if requested. Kortra has closest match.
        closest_scale = min(scales, key=lambda x: min(abs(mapped_score - safe_decimal(x[1])), abs(mapped_score - safe_decimal(x[2]))))
        if closest_scale:
             return closest_scale[3], closest_scale[4]

    except Exception as e:
        logger.warning(f"Error getting grade: {e}")
        
    return "-", "-"

def get_grade_from_score_raw(raw_score, db_session, academic_id, grade_group_id, max_possible_score=None):
    """
    Get grade from scale handling raw scores (normalizing to percentage first).
    """
    try:
        score_decimal = safe_decimal(raw_score)
        
        if max_possible_score is None:
             max_possible_score = Decimal('100.0')
        else:
             max_possible_score = safe_decimal(max_possible_score, Decimal('100.0'))
             
        if max_possible_score <= Decimal('0'):
             max_possible_score = Decimal('100.0')

        # 1. Calculate Percentage (0-100)
        percentage = (score_decimal / max_possible_score) * Decimal('100.0')
        
        # Clamp
        if percentage < Decimal('0'): percentage = Decimal('0')
        if percentage > Decimal('100'): percentage = Decimal('100')
        
        # 2. Reuse get_grade_from_scale which expects percentage
        return get_grade_from_scale(percentage, db_session, academic_id, grade_group_id)

    except Exception as e:
        logger.warning(f"Error getting grade raw: {e}")
        
    return "-", "-"


def parse_formula_expression(details: dict, db_session) -> dict:
    """
    Parse formula expression to get calculation data.
    Supports both formats:
    1. Numeric IDs: (123+456+789) or 123+456+789
    2. Codes: (MON1+MON2+MON3) or MON1+MON2+MON3
    
    Returns a dict with 'monthly_system_ids', 'subject_ids', 'divide_by_multiplier'
    """
    final_formula = details.get('formula_expression', '').replace(" ", "").strip()
    if not final_formula:
        return {"monthly_system_ids": [], "subject_ids": [], "divide_by_multiplier": Decimal('1.0')}
    
    # Remove parentheses if present
    formula_clean = final_formula.strip('()').strip()
    
    # Extract tokens (numeric IDs or codes)
    tokens = re.findall(r'[A-Za-z]+[0-9]*|\b\d+\b', formula_clean)
    if not tokens:
        return {"monthly_system_ids": [], "subject_ids": [], "divide_by_multiplier": Decimal('1.0')}
    
    monthly_calc_ids = []
    monthly_codes = []
    
    # Separate numeric IDs from codes
    for token in tokens:
        if token.isdigit():
            monthly_calc_ids.append(int(token))
        else:
            monthly_codes.append(token.upper())  # Normalize to uppercase
    
    # If we have codes, resolve them to exam_calculate_sign IDs
    if monthly_codes:
        placeholders_codes = ','.join([':code_' + str(i) for i in range(len(monthly_codes))])
        params = {
            "academic_id": details['academic_id'],
            "program_id": details['program_id'], 
            "grade_group_id": details['grade_group_id']
        }
        for i, code in enumerate(monthly_codes):
            params[f"code_{i}"] = code

        # Construct AND IN clause manually or loop?
        # Safe way with list params in text() is tricky across drivers sometimes,
        # but SQLAlchemy text() handles tuple binding usually.
        # Let's use tuple binding if possible.
        
        query_codes = text("""
            SELECT id, marks_system_id, formula_expression, divide_by_multiplier, sign_code, result_name 
            FROM exam_calculate_sign 
            WHERE academic_id = :academic_id AND program_id = :program_id AND grade_group_id = :grade_group_id 
            AND sign_code IN :codes
        """)
        code_configs = db_session.execute(query_codes, {
            "academic_id": details['academic_id'],
            "program_id": details['program_id'],
            "grade_group_id": details['grade_group_id'],
            "codes": tuple(monthly_codes)
        }).fetchall()
        
        monthly_calc_ids.extend([row[0] for row in code_configs]) # row[0] is id
    
    if not monthly_calc_ids:
        # Fallback if no valid IDs resolved (maybe pure ID formula?)
        pass
    
    # Get all monthly configs by IDs
    if not monthly_calc_ids:
         return {"monthly_system_ids": [], "subject_ids": [], "divide_by_multiplier": Decimal('1.0')}

    query_configs = text("""
        SELECT id, marks_system_id, formula_expression, divide_by_multiplier, sign_code, result_name 
        FROM exam_calculate_sign 
        WHERE id IN :ids
    """)
    monthly_configs = db_session.execute(query_configs, {"ids": tuple(monthly_calc_ids)}).fetchall()
    
    # Dict access for rows might differ (tuple vs mappings), assuming tuple for fetchall
    # id=0, marks_system_id=1, formula=2, divisor=3, sign_code=4, result_name=5
    
    all_monthly_system_ids = []
    
    for mc in monthly_configs:
         ms_id = mc[1]
         sign_code = mc[4]
         result_name = mc[5]
         
         if not ms_id or ms_id == 0:
             # Resolve ID logic
             # Priority 1: Match by Code (Safest)
             q_ms_code = text("SELECT id FROM marks_system WHERE academic_id=:aid AND program_id=:pid AND grade_group_id=:ggid AND marks_code=:code LIMIT 1")
             found = db_session.execute(q_ms_code, {
                 "aid": details['academic_id'], "pid": details['program_id'], "ggid": details['grade_group_id'], "code": sign_code
             }).fetchone()
             
             if found:
                 ms_id = found[0]
             else:
                 # Priority 2: Match by Name
                 q_ms_name = text("SELECT id FROM marks_system WHERE academic_id=:aid AND program_id=:pid AND grade_group_id=:ggid AND marks_name=:name LIMIT 1")
                 found = db_session.execute(q_ms_name, {
                     "aid": details['academic_id'], "pid": details['program_id'], "ggid": details['grade_group_id'], "name": result_name
                 }).fetchone()
                 if found:
                     ms_id = found[0]
         
         if ms_id:
             all_monthly_system_ids.append(ms_id)

    all_subject_ids = set()
    divide_by_multiplier = Decimal('1.0')
    
    # For now, simplistic subject gathering (marks_system_subjects)
    if all_monthly_system_ids:
        q_mss = text("SELECT subject_id FROM marks_system_subjects WHERE marks_system_id IN :ms_ids")
        mss_rows = db_session.execute(q_mss, {"ms_ids": tuple(all_monthly_system_ids)}).fetchall()
        
        if mss_rows:
            for row in mss_rows:
                all_subject_ids.add(row[0])
                
            # Get divide_by_multiplier from the first config (they should all be the same)
            for mc in monthly_configs:
                if mc[3]: # divide_by_multiplier
                    divide_by_multiplier = safe_decimal(mc[3], Decimal('1.0'))
                    break 
        else:
             # Fallback: Parse formula expression if no subjects found in normalized table
             # Extract IDs from formula string in mc[2]
            for mc in monthly_configs:
                f_expr = mc[2] or ''
                # Simple extraction of numbers
                subject_ids = [int(s_id) for s_id in re.findall(r'\d+', f_expr)]
                all_subject_ids.update(subject_ids)
                if mc[3]:
                    divide_by_multiplier = safe_decimal(mc[3], Decimal('1.0'))
                    
    return {
        "monthly_system_ids": list(set(all_monthly_system_ids)),
        "subject_ids": list(all_subject_ids),
        "divide_by_multiplier": divide_by_multiplier
    }

from sqlalchemy import text
from decimal import Decimal

def calculate_exam_rank(db, exam_type: str, system_ids: list, student_id: int, academic_id: int, program_id: int, grade_id: int, grade_group_id: int, shift_id: int, current_score: float):
    """
    Calculate rank for a student in a specific exam (or aggregation of exams) within their class.
    Class context: Academic + Program + Grade + Grade Group + Shift (if available).
    
    Args:
        exam_type: 'monthly' (for single exam) or 'average' (for avg of months)
        system_ids: List of marks_system_id
        current_score: The score to compare against
    """
    try:
        current_score_dec = Decimal(str(current_score))
        
        # NOTE: We filter Program, Grade, GradeGroup from MarksMonthly (mm) table directly
        # as the Student (st) table apparently lacks these columns in some schemas.
        # We join Student only to check active status.
        # Shift ID filtering is temporarily removed if not found on MarksMonthly or Student.
        
        if exam_type == 'monthly':
            # Rank based on marks_monthly average for a specific exam
            query = text("""
                SELECT mm.student_id, mm.average
                FROM marks_monthly mm
                JOIN students st ON mm.student_id = st.id
                WHERE mm.academic_id = :aid
                AND mm.grade_group_id = :ggid
                AND mm.program_id = :pid 
                AND mm.grade_id = :gid
                AND mm.marks_system_id IN :sys_ids
                AND st.status = 1
            """)
            
            rows = db.execute(query, {
                "aid": academic_id,
                "ggid": grade_group_id,
                "sys_ids": tuple(system_ids),
                "pid": program_id,
                "gid": grade_id
            }).fetchall()
            
            scores = []
            for r in rows:
                if r[1] is not None:
                    scores.append(Decimal(str(r[1])))
            scores.sort(reverse=True)
            
            rank = 1
            for s in scores:
                if s > current_score_dec:
                    rank += 1
                else:
                    break
            return str(rank)

        elif exam_type == 'average':
            query = text("""
                SELECT mm.student_id, mm.average
                FROM marks_monthly mm
                JOIN students st ON mm.student_id = st.id
                WHERE mm.academic_id = :aid
                AND mm.grade_group_id = :ggid
                AND mm.program_id = :pid
                AND mm.grade_id = :gid
                AND mm.marks_system_id IN :sys_ids
                AND st.status = 1
            """)
            
            rows = db.execute(query, {
                "aid": academic_id,
                "ggid": grade_group_id,
                "sys_ids": tuple(system_ids),
                "pid": program_id,
                "gid": grade_id
            }).fetchall()
            
            student_totals = {}
            student_counts = {}
            
            for r in rows:
                sid = r[0]
                val = Decimal(str(r[1])) if r[1] is not None else Decimal('0')
                if sid not in student_totals:
                    student_totals[sid] = Decimal('0')
                    student_counts[sid] = 0
                student_totals[sid] += val
                student_counts[sid] += 1
            
            class_averages = []
            for sid, total in student_totals.items():
                count = student_counts[sid]
                if count > 0:
                    avg = total / Decimal(count)
                    class_averages.append(avg)
            class_averages.sort(reverse=True)
            
            rank = 1
            for avg in class_averages:
                if avg > current_score_dec + Decimal('0.0001'):
                    rank += 1
            return str(rank)

    except Exception as e:
        print(f"Rank Custom Calc Error: {e}")
        return "-"

    return "-"


def class_scope_rank_sql_suffix(
    grade_type_id: int | None,
    branch_id: int | None,
) -> tuple[str, dict]:
    """
    Extra JOIN/WHERE fragments so rank counts only students in the viewed class.
    Requires: JOIN grade g ON l.gradeid = g.id (alias l = learning).
    """
    clauses = []
    params: dict = {}
    if branch_id is not None:
        clauses.append("AND g.branch_id = :branch_id")
        params["branch_id"] = branch_id
    if grade_type_id is not None:
        clauses.append("AND l.grade_type_id = :grade_type_id")
        params["grade_type_id"] = grade_type_id
    else:
        clauses.append("AND l.grade_type_id IS NULL")
    return " ".join(clauses), params


def learning_class_scope_sql_suffix(
    grade_type_id: int | None,
    branch_id: int | None = None,
) -> tuple[str, dict]:
    """
    WHERE fragments on learning alias `l` for one class section.
    Same rules as the class results student list (results.py):
    - grade_type_id set  -> that section only
    - grade_type_id None -> l.grade_type_id IS NULL only
    """
    clauses = []
    params: dict = {}
    if grade_type_id is not None:
        clauses.append("AND l.grade_type_id = :grade_type_id")
        params["grade_type_id"] = grade_type_id
    else:
        clauses.append("AND l.grade_type_id IS NULL")
    if branch_id is not None:
        clauses.append("AND l.branch_id = :branch_id")
        params["branch_id"] = branch_id
    return " ".join(clauses), params


def get_term_date_range(db_session, academic_id, program_id, term_type):
    """
    Determine the start and end dates for a term (RSEM1, RSEM2, YEAR) based on academic table.
    
    Logic:
    - RSEM1: academic.semester_one_start to academic.semester_one_end
    - RSEM2: academic.semester_two_start to academic.semester_two_end
    - YEAR: academic.semester_one_start to academic.semester_two_end
    """
    try:
        # Fetch academic semester dates
        query = text("""
            SELECT semester_one_start, semester_one_end, semester_two_start, semester_two_end
            FROM academic 
            WHERE id = :academic_id 
        """)
        row = db_session.execute(query, {"academic_id": academic_id}).fetchone()
        
        if not row:
            return None, None
            
        sem1_start = row[0]
        sem1_end = row[1]
        sem2_start = row[2]
        sem2_end = row[3]
        
        start_date = None
        end_date = None
        
        if term_type == 'RSEM1':
            start_date = sem1_start
            end_date = sem1_end
            
        elif term_type == 'RSEM2':
            start_date = sem2_start
            end_date = sem2_end
                
        elif term_type == 'YEAR':
            start_date = sem1_start
            end_date = sem2_end
            
        return start_date, end_date

    except Exception as e:
        logger.error(f"Error determining term date range: {e}")
        return None, None

from datetime import timedelta

def calculate_working_days(db_session, start_date, end_date):
    """
    Calculate working days between start_date and end_date (inclusive).
    Excludes weekends (Saturday, Sunday) and holidays from 'holidays' table.
    """
    if not start_date or not end_date:
        return 0
        
    try:
        # Fetch holidays in range
        h_query = text("SELECT date FROM holidays WHERE date BETWEEN :start AND :end")
        holidays_res = db_session.execute(h_query, {"start": start_date, "end": end_date}).fetchall()
        holiday_dates = {h[0] for h in holidays_res}
        
        working_days = 0
        current_date = start_date
        while current_date <= end_date:
            # weekday(): 0=Monday, 6=Sunday
            # Exclude Sat(5) and Sun(6)
            if current_date.weekday() < 5:
                if current_date not in holiday_dates:
                    working_days += 1
            current_date += timedelta(days=1)
            
        return working_days

    except Exception as e:
        logger.error(f"Error calculating working days: {e}")
        return 0
