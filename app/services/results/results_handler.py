from sqlalchemy import text
from sqlalchemy.orm import Session
from decimal import Decimal
import logging
from fastapi import HTTPException
from ...utils.results_utils import (
    safe_decimal, get_grade_from_scale, parse_formula_expression,
    get_term_date_range
)
from ...services.results.attendance_utils import get_attendance_summary

# Import Specific Flow Modules
from ...services.results.kh_monthly_results_flow import generate_kh_monthly_report
from ...services.results.en_monthly_results_flow import generate_en_monthly_report
from ...services.results.iep_monthly_results_flow import generate_iep_monthly_report
from ...services.results.other_monthly_results_flow import generate_other_monthly_report

from ...services.results.kh_semester_results_flow import generate_kh_semester_report
from ...services.results.en_semester_results_flow import generate_en_semester_report
from ...services.results.iep_semester_results_flow import generate_iep_semester_report
from ...services.results.other_semester_results_flow import generate_other_semester_report

from ...services.results.kh_yearly_results_flow import generate_kh_yearly_report
from ...services.results.en_yearly_results_flow import generate_en_yearly_report
from ...services.results.iep_yearly_results_flow import generate_iep_yearly_report
from ...services.results.other_yearly_results_flow import generate_other_yearly_report

logger = logging.getLogger(__name__)

def get_student_result_detail_service(
    db: Session,
    student_id: int,
    program_id: int,
    grade_id: int,
    academic_id: int,
    marks_system_id: int,
    grade_type_id: int | None = None,
    shift_id: int | None = None,
    result_name: str | None = None,
    exam_name: str | None = None,
    exam_type: str | None = None
):
    """
    Service function to get detailed result breakdown.
    Refactored from monolithic results.py to use specific flow modules.
    """
    
    # 1. Get Grade Group ID
    grade_query = text("SELECT group_id FROM grade WHERE id = :grade_id")
    grade_result = db.execute(grade_query, {"grade_id": grade_id}).fetchone()
    if not grade_result:
        raise HTTPException(status_code=404, detail="Grade not found")
    grade_group_id = grade_result[0]

    # 1.5 Fetch Branch ID (Needed for scoped ranking)
    # We must also filter by shift and grade_type to retrieve the EXACT learning record
    # for this specific class context.
    branch_q = text("""
        SELECT branch_id 
        FROM learning 
        WHERE studentid = :sid 
        AND academicid = :aid
        AND programid = :pid
        AND gradeid = :gid
        AND (:shift_id IS NULL OR shiftid = :shift_id)
        AND (:grade_type_id IS NULL OR grade_type_id = :grade_type_id)
        LIMIT 1
    """)
    branch_res = db.execute(branch_q, {
        "sid": student_id,
        "aid": academic_id,
        "pid": program_id,
        "gid": grade_id,
        "shift_id": shift_id,
        "grade_type_id": grade_type_id
    }).fetchone()
    branch_id = branch_res[0] if branch_res else None

    # 2. Resolve Exam Definition (ECS)
    ecs_result = None
    
    # Query builder helper
    ecs_base_query = """
        SELECT exam_type, result_name, formula_expression, divide_by_multiplier, sign_code, id
        FROM exam_calculate_sign 
        WHERE academic_id = :academic_id 
        AND program_id = :program_id 
        AND grade_group_id = :grade_group_id
    """
    
    if result_name and result_name.strip():
        # Look up by result_name
        q = text(f"{ecs_base_query} AND result_name = :result_name AND is_active = 1 LIMIT 1")
        ecs_result = db.execute(q, {
            "result_name": result_name,
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_group_id": grade_group_id
        }).fetchone()
        
        # Fallback to exam_name
        if not ecs_result and exam_name and exam_name != result_name:
             ecs_result = db.execute(q, {
                "result_name": exam_name,
                "academic_id": academic_id,
                "program_id": program_id,
                "grade_group_id": grade_group_id
            }).fetchone()
            
    else:
        # Look up by marks_system_id
        q = text(f"{ecs_base_query} AND marks_system_id = :marks_system_id LIMIT 1")
        ecs_result = db.execute(q, {
            "marks_system_id": marks_system_id,
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_group_id": grade_group_id
        }).fetchone()
        
    # Process fetched ECS
    if not ecs_result:
        # If not found, try fallback lookup if we know it's Semester/Yearly (often has ms_id=0)
        if exam_type and exam_type in ['semester', 'yearly'] and result_name:
             q_lookup = text(f"{ecs_base_query} AND result_name = :result_name LIMIT 1")
             ecs_lookup = db.execute(q_lookup, {
                "result_name": result_name,
                "academic_id": academic_id,
                "program_id": program_id,
                "grade_group_id": grade_group_id
            }).fetchone()
             
             if ecs_lookup:
                 exam_type = ecs_lookup[0]
                 formula = ecs_lookup[2] if ecs_lookup[2] else ''
                 divide_by = safe_decimal(ecs_lookup[3] if ecs_lookup[3] else None, Decimal('1.0'))
                 sign_code = ecs_lookup[4] if len(ecs_lookup) > 4 else None
                 ecs_id = ecs_lookup[5] if len(ecs_lookup) > 5 else None
             else:
                 # Minimal fallback
                 formula = ''
                 divide_by = Decimal('1.0')
                 sign_code = None
                 ecs_id = None
        else:
             raise HTTPException(status_code=404, detail="Exam definition not found")
    else:
        exam_type = ecs_result[0]
        result_name = result_name if result_name and result_name.strip() else ecs_result[1]
        formula = ecs_result[2] if ecs_result[2] else ''
        divide_by = safe_decimal(ecs_result[3] if ecs_result[3] else None, Decimal('1.0'))
        sign_code = ecs_result[4] if len(ecs_result) > 4 else None
        ecs_id = ecs_result[5] if len(ecs_result) > 5 else None

    # 3. Calculate Attendance
    att_summary = get_attendance_summary(
        db, student_id, academic_id, program_id, exam_type, marks_system_id, result_name, sign_code
    )
    
    # 4. Dispatch to Specific Logic
    details = {
        "exam_type": exam_type,
        "result_name": result_name,
        "sign_code": sign_code,
        "ecs_id": ecs_id,
        "items": [],
        "summary": {},
        "attendance": att_summary,
        "comment": ""
    }
    
    report_data = {}
    
    # Determine Program Type (mark_type)
    prog_q = text("SELECT mark_type FROM program WHERE id = :pid")
    prog_res = db.execute(prog_q, {"pid": program_id}).fetchone()
    mark_type = prog_res[0].lower() if prog_res and prog_res[0] else 'kh'
    
    if exam_type == 'semester':
        # Parse Formula
        parsed_data = parse_formula_expression({
            'formula_expression': formula,
            'academic_id': academic_id,
            'program_id': program_id,
            'grade_group_id': grade_group_id
        }, db)
        all_sys_ids = parsed_data.get('monthly_system_ids', [])
        
        if mark_type == 'en':
            report_data = generate_en_semester_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                all_sys_ids, result_name, sign_code, grade_type_id, branch_id
            )
        elif mark_type == 'iep':
            report_data = generate_iep_semester_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                all_sys_ids, result_name, sign_code, grade_type_id, branch_id
            )
        elif mark_type == 'other':
            report_data = generate_other_semester_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                all_sys_ids, result_name, sign_code, grade_type_id, branch_id
            )
        else: # Default/KH
            report_data = generate_kh_semester_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                all_sys_ids, formula, result_name, sign_code, grade_type_id, branch_id
            )
            
    elif exam_type == 'yearly':
        if mark_type == 'en':
            report_data = generate_en_yearly_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                result_name, sign_code, divide_by, grade_type_id, branch_id
            )
        elif mark_type == 'iep':
             report_data = generate_iep_yearly_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                result_name, sign_code, divide_by, grade_type_id, branch_id
            )
        elif mark_type == 'other':
             report_data = generate_other_yearly_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                result_name, sign_code, divide_by, grade_type_id, branch_id
            )
        else: # Default/KH
            report_data = generate_kh_yearly_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                result_name, sign_code, divide_by, grade_type_id, branch_id
            )
        
    else:
        # Monthly / Input
        if mark_type == 'en':
            report_data = generate_en_monthly_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                marks_system_id, ecs_id, formula, divide_by, exam_type, grade_type_id, branch_id
            )
        elif mark_type == 'iep':
            report_data = generate_iep_monthly_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                marks_system_id, ecs_id, formula, divide_by, exam_type, grade_type_id, branch_id
            )
        elif mark_type == 'other':
            report_data = generate_other_monthly_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                marks_system_id, ecs_id, formula, divide_by, exam_type, grade_type_id, branch_id
            )
        else: # Default/KH
             report_data = generate_kh_monthly_report(
                db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
                marks_system_id, ecs_id, formula, divide_by, exam_type, grade_type_id,
                sign_code=sign_code, branch_id=branch_id
            )
        
    # Merge result
    details.update(report_data)
    
    return details
