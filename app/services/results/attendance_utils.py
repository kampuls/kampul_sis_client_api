from datetime import timedelta, datetime
from decimal import Decimal
from sqlalchemy import text
from ...utils.results_utils import calculate_working_days, get_term_date_range, safe_decimal

def calculate_pct(value, total_days):
    if not total_days or total_days <= 0:
        return 0.0
    pct_val = (safe_decimal(value) / safe_decimal(total_days)) * Decimal('100')
    return float(pct_val.quantize(Decimal("0.00"), rounding='ROUND_HALF_UP'))

def get_attendance_summary(db, student_id, academic_id, program_id, exam_type, marks_system_id=None, result_name=None, sign_code=None):
    """
    Calculates attendance summary for a student based on exam context.
    Determines date range based on exam type (Monthly/Semester/Yearly).
    """
    
    att_start_date = None
    att_end_date = None
    
    # Determine strict range for RSEM1/2/YEAR using sign_code or exam_type
    if exam_type in ('semester', 'yearly'):
        term_type = None
        if sign_code:
            if sign_code in ('RSEM1', 'SEM1'):
                    term_type = 'RSEM1'
            elif sign_code in ('RSEM2', 'SEM2'):
                    term_type = 'RSEM2'
            elif sign_code == 'YEAR' or exam_type == 'yearly':
                    term_type = 'YEAR'
        else:
            # Fallback to name ONLY if sign_code is missing (legacy/fallback)
            result_name_str = str(result_name) if result_name else ""
            if '1' in result_name_str or 'SEM1' in result_name_str or '១' in result_name_str:
                    term_type = 'RSEM1'
            elif '2' in result_name_str or 'SEM2' in result_name_str or '២' in result_name_str:
                    term_type = 'RSEM2'
            elif exam_type == 'yearly':
                    term_type = 'YEAR'
                    
        if term_type:
                att_start_date, att_end_date = get_term_date_range(db, academic_id, program_id, term_type)
    
    elif exam_type in ('input', 'monthly') and marks_system_id and marks_system_id > 0:
        # Fetch for_month from marks_system to determine range
        ms_q = text("SELECT for_month FROM marks_system WHERE id = :mid")
        ms_res = db.execute(ms_q, {"mid": marks_system_id}).fetchone()
        if ms_res and ms_res[0]:
            for_month_date = ms_res[0] # date object
            # Start of month
            att_start_date = for_month_date.replace(day=1)
            # End of month: (start + 32 days).replace(day=1) - 1 day
            next_month = (att_start_date + timedelta(days=32)).replace(day=1)
            att_end_date = next_month - timedelta(days=1)

    # Build Query — MUST scope to program_id to prevent cross-program attendance bleed
    att_query_str = """
        SELECT status, COUNT(*) as count 
        FROM daily_attendance 
        WHERE student_id = :student_id 
        AND academic_id = :academic_id
        AND program_id = :program_id
    """
    att_params = {"student_id": student_id, "academic_id": academic_id, "program_id": program_id}
    
    if att_start_date and att_end_date:
        att_query_str += " AND attendance_date BETWEEN :start AND :end"
        att_params["start"] = att_start_date
        att_params["end"] = att_end_date
        
    att_query_str += " GROUP BY status"
    
    att_results = db.execute(text(att_query_str), att_params).fetchall()
    att_summary = {row[0]: row[1] for row in att_results}
    
    student_marked_count = sum(att_summary.values())
    
    # Calculate Working Days
    if att_start_date and att_end_date:
            working_days = calculate_working_days(db, att_start_date, att_end_date)
    else:
            working_days = 0
    
    not_marked = working_days - student_marked_count
    if not_marked < 0: not_marked = 0 # Safety check

    return {
        "present": att_summary.get("IsPresent", 0),
        "late": att_summary.get("IsLate", 0),
        "permission": att_summary.get("IsPermission", 0),
        "absent": att_summary.get("IsAbsent", 0),
        "working_days": working_days,
        "not_marked": not_marked,
        # Percentages
        "percent_present": calculate_pct(att_summary.get("IsPresent", 0), working_days),
        "percent_late": calculate_pct(att_summary.get("IsLate", 0), working_days),
        "percent_permission": calculate_pct(att_summary.get("IsPermission", 0), working_days),
        "percent_absent": calculate_pct(att_summary.get("IsAbsent", 0), working_days),
        "percent_not_marked": calculate_pct(not_marked, working_days),
    }
