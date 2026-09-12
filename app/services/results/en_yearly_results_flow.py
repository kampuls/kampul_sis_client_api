from decimal import Decimal
from sqlalchemy import text
from ...utils.results_utils import safe_decimal, is_fail_grade
import logging
from ...services.results.iep_yearly_results_flow import generate_iep_yearly_report

logger = logging.getLogger(__name__)

def generate_en_yearly_report(
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
    Generates the yearly report for EN programs.
    Delegate to IEP implementation as logic is identical (Sem1 + Sem2 + Yearly).
    """
    return generate_iep_yearly_report(
        db, student_id, academic_id, program_id, grade_group_id, grade_id, shift_id, 
        result_name, sign_code, divide_by, grade_type_id, branch_id
    )
