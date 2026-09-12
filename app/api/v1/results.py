"""
Results API endpoints for viewing student results.
Based on the Python Telegram bot implementation.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import Optional, List, Dict, Any
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
from collections import defaultdict
import calendar
import re
from datetime import datetime, timedelta
from uuid import uuid4
from pydantic import BaseModel, Field

from ...utils.academic_year import is_historical_academic_year

from ...core import get_db
from ...auth import get_current_active_user
from ...models.marks import GradeScale
from ...utils.attendance_utils import enrich_attendance_summary
from ...utils.consistency_utils import build_consistency_check
from ...utils.results_utils import (
    parse_formula_expression, get_grade_from_scale, safe_decimal,
    get_grade_from_score_raw, get_max_scale_score, calculate_exam_rank,
    is_fail_grade, get_term_date_range, calculate_working_days
)
from ...services.results.results_handler import get_student_result_detail_service
from ...services.results.teacher_comment import (
    TEACHER_COMMENT_MAX_LENGTH,
    can_user_comment_on_result,
    save_teacher_comment,
)
from ...models.results_top_student import ResultTopStudent
from datetime import date

router = APIRouter()
logger = logging.getLogger(__name__)


def _class_subject_cell_value(item: Dict[str, Any]) -> Optional[float]:
    """Pick a single numeric display value for class/PDF columns from a detail item."""
    t = item.get("type")
    if t in ("exam", "semester_exam", "month_aggregation", "semester"):
        if item.get("average") is not None:
            return float(item["average"])
    if item.get("score") is not None:
        return float(item["score"])
    return None


def _merge_student_detail_into_class_subjects(
    stu_details: Dict[str, Any],
    sem_stu_details: Optional[Dict[str, Any]],
    *,
    skip_month_aggregation: bool,
    append_rsem_summary_column: bool,
) -> tuple[Dict[str, float], List[Dict[str, Any]]]:
    """
    Build per-student subjects map and ordered subjects_meta for class PDF/detail parity.
    KH semester/RSEM rows use types exam / semester_exam / month_aggregation (not subject).
    """
    columns: List[Dict[str, Any]] = []
    seen: set = set()
    sub_dict: Dict[str, float] = {}

    def _add_column(meta: Dict[str, Any]) -> None:
        cid = meta.get("id")
        if not cid or cid in seen:
            return
        seen.add(cid)
        columns.append(meta)

    # 1) Companion semester exam (SEM1 for RSEM1, SEM2 for RSEM2) — subject marks for KH
    if sem_stu_details:
        for item in sem_stu_details.get("items") or []:
            if item.get("type") != "subject":
                continue
            sub_label = (item.get("label") or "").strip() or "Subject"
            meta = {
                "id": sub_label,
                "name": sub_label,
                "name_us": sub_label,
                "code": item.get("code"),
            }
            if item.get("max_score") is not None:
                meta["max_score"] = float(item["max_score"])
            _add_column(meta)
            val = _class_subject_cell_value(item)
            if val is not None:
                sub_dict[sub_label] = val

    items = stu_details.get("items") or []
    for i, item in enumerate(items):
        t = item.get("type")
        if t == "subject":
            sub_label = (item.get("label") or "").strip() or "Subject"
            meta = {
                "id": sub_label,
                "name": sub_label,
                "name_us": sub_label,
                "code": item.get("code"),
            }
            if item.get("max_score") is not None:
                meta["max_score"] = float(item["max_score"])
            _add_column(meta)
            val = _class_subject_cell_value(item)
            if val is not None:
                sub_dict[sub_label] = val
        elif t in ("exam", "semester_exam", "month_aggregation", "semester"):
            if skip_month_aggregation and t == "month_aggregation":
                continue
            sign = (item.get("sign_code") or "").strip().upper()
            cid = sign if sign else f"{t}:{(item.get('label') or '')}:{i}"
            label = (item.get("label") or "").strip() or cid
            _add_column(
                {
                    "id": cid,
                    "name": label,
                    "name_us": label,
                    "code": sign or None,
                }
            )
            val = _class_subject_cell_value(item)
            if val is not None:
                sub_dict[cid] = val

    if append_rsem_summary_column:
        sc = (stu_details.get("sign_code") or "").strip().upper()
        if sc in ("RSEM1", "RSEM2"):
            summ = stu_details.get("summary") or {}
            res_nm = (stu_details.get("result_name") or sc).strip()
            _add_column(
                {
                    "id": sc,
                    "name": res_nm,
                    "name_us": sc,
                    "code": sc,
                }
            )
            if summ.get("average") is not None:
                sub_dict[sc] = float(summ["average"])
            elif summ.get("total") is not None:
                sub_dict[sc] = float(summ["total"])

    return sub_dict, columns


class FeatureTopStudentItem(BaseModel):
    student_id: int
    rank: int = Field(..., ge=1)
    average: Optional[float] = None
    grade: Optional[str] = None


class FeatureTopStudentsPayload(BaseModel):
    academic_id: int
    program_id: int
    grade_id: int
    shift_id: int
    grade_type_id: Optional[int] = None
    marks_system_id: Optional[int] = None
    result_name: Optional[str] = None
    exam_name: Optional[str] = None
    exam_type: Optional[str] = None
    period: Optional[str] = None
    students: List[FeatureTopStudentItem]


@router.get("/definitions")
def get_result_definitions(
    program_id: int = Query(...),
    grade_id: int = Query(...),
    academic_id: int = Query(...),
    grade_group_id: Optional[int] = Query(None, description="Optional grade group ID (use when available from class info)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get available result definitions (Exams) for a class."""
    try:
        # Use grade_group_id if provided; otherwise look up from grade table
        if grade_group_id is None:
            grade_query = text("SELECT group_id FROM grade WHERE id = :grade_id")
            grade_result = db.execute(grade_query, {"grade_id": grade_id}).fetchone()
            if not grade_result:
                raise HTTPException(status_code=404, detail="Grade not found")
            grade_group_id = grade_result[0]
        
        # If grade_group_id is still None (e.g. grade.group_id is NULL), return empty
        if grade_group_id is None:
            return {"success": True, "definitions": []}
        
        # Get result definitions
        # Join with marks_system to get for_month for ordering
        query = text("""
            SELECT ecs.result_name, ecs.exam_type, ecs.marks_system_id, ms.for_month, ms.marks_name, ecs.formula_expression, ecs.sign_code
            FROM exam_calculate_sign ecs
            LEFT JOIN marks_system ms ON ecs.marks_system_id = ms.id
            WHERE ecs.academic_id = :academic_id 
            AND ecs.program_id = :program_id 
            AND ecs.grade_group_id = :grade_group_id 
            AND ecs.is_active = 1
        """)
        
        results = db.execute(query, {
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_group_id": grade_group_id
        }).fetchall()
        
        # Define sort order mapping
        # MON1..MON4 -> 1..4
        # SEM1, RSEM1 -> 4.5, 4.6
        # MON5..MON8 -> 5..8
        # SEM2, RSEM2 -> 8.5, 8.6
        # YEAR -> 9
        
        def get_sort_key(row):
            sign_code = row[6] # Now fetching sign_code
            for_month = row[3]
            marks_name = row[4]
            result_name = row[0]
            
            # Priority 1: Sign Code
            if sign_code:
                if sign_code == 'MON1': return 10
                if sign_code == 'MON2': return 20
                if sign_code == 'MON3': return 30
                if sign_code == 'MON4': return 40
                if sign_code == 'SEM1': return 45
                if sign_code == 'RSEM1': return 46
                if sign_code == 'MON5': return 50
                if sign_code == 'MON6': return 60
                if sign_code == 'MON7': return 70
                if sign_code == 'MON8': return 80
                if sign_code == 'SEM2': return 85
                if sign_code == 'RSEM2': return 86
                if sign_code == 'YEAR': return 90
            
            # Fallback 2: for_month
            if for_month:
                # Convert date to comparable integer (YYYYMM)
                return 100 + int(for_month.strftime('%Y%m'))
                
            return 999
            
        # Sort in memory (convert to list - fetchall returns Sequence)
        results = sorted(results, key=get_sort_key)
        
        definitions = []
        for row in results:
            definitions.append({
                "result_name": row[0],
                "exam_type": row[1],
                "marks_system_id": row[2],
                "for_month": row[3].isoformat() if row[3] else None,
                "exam_name": row[4],
                "formula_expression": row[5] if len(row) > 5 else None,
                "sign_code": row[6]
            })
            
        return {"success": True, "definitions": definitions}
        
    except Exception as e:
        logger.error(f"Error fetching result definitions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/class")
def get_class_results(
    program_id: int = Query(...),
    grade_id: int = Query(...),
    shift_id: int = Query(...),
    academic_id: int = Query(...),
    marks_system_id: int = Query(...),
    grade_type_id: Optional[int] = Query(None),
    result_name: Optional[str] = Query(None),  # REQUIRED for semester/yearly to filter correctly
    exam_name: Optional[str] = Query(None),
    exam_type: Optional[str] = Query(None),
    include_subjects: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get calculated results for a class. If include_subjects is True, injects subject names and marks into response."""
    try:
        # 1. Get Grade Group ID
        grade_query = text("SELECT group_id FROM grade WHERE id = :grade_id")
        grade_result = db.execute(grade_query, {"grade_id": grade_id}).fetchone()
        if not grade_result:
            raise HTTPException(status_code=404, detail="Grade not found")
        grade_group_id = grade_result[0]

        # 1.1 Get Program Info (mark_type)
        program_query = text("SELECT mark_type FROM program WHERE id = :program_id")
        program_result = db.execute(program_query, {"program_id": program_id}).fetchone()
        mark_type = program_result[0] if program_result else 'kh'

        # 1.2 Fetch Grade Scale Meanings for all grades in this group (kh_grade + us_grade)
        grade_meaning_map = {}  # us_grade -> (kh_grade, us_grade)
        gm_query = text("SELECT us_grade, kh_grade FROM grade_scale WHERE academic_id = :aid AND grade_group_id = :ggid")
        gm_res = db.execute(gm_query, {"aid": academic_id, "ggid": grade_group_id}).fetchall()
        for gs in gm_res:
            if gs[0]:
                grade_meaning_map[gs[0]] = {"kh": gs[1] or "-", "en": gs[0] or "-"}

        # 2. Get Exam Type & Info
        # CRITICAL: For semester/yearly, if result_name is provided, use it to get the exact exam
        # This ensures we filter to the specific semester/yearly the user selected
        ecs_sign_code = ""
        if result_name and result_name.strip():
            # Use result_name to get the exact exam definition (matching Telegram bot logic)
            ecs_query = text("""
                SELECT exam_type, result_name, formula_expression, divide_by_multiplier, sign_code
                FROM exam_calculate_sign
                WHERE result_name = :result_name
                AND academic_id = :academic_id
                AND program_id = :program_id
                AND grade_group_id = :grade_group_id
                AND is_active = 1
                LIMIT 1
            """)
            ecs_result = db.execute(ecs_query, {
                "result_name": result_name,
                "academic_id": academic_id,
                "program_id": program_id,
                "grade_group_id": grade_group_id
            }).fetchone()
        else:
            # Fallback to marks_system_id lookup (for monthly/input exams)
            ecs_query = text("""
                SELECT exam_type, result_name, formula_expression, divide_by_multiplier, sign_code
                FROM exam_calculate_sign
                WHERE marks_system_id = :marks_system_id
                AND academic_id = :academic_id
                AND program_id = :program_id
                AND grade_group_id = :grade_group_id
                LIMIT 1
            """)
            ecs_result = db.execute(ecs_query, {
                "marks_system_id": marks_system_id,
                "academic_id": academic_id,
                "program_id": program_id,
                "grade_group_id": grade_group_id
            }).fetchone()

        # Process the exam definition result
        if ecs_result:
            exam_type = ecs_result[0]
            # Use result_name from query parameter if provided, otherwise use from database
            result_name = result_name if result_name and result_name.strip() else ecs_result[1]
            formula = ecs_result[2] if ecs_result[2] else ''
            divide_by_multiplier = safe_decimal(ecs_result[3] if ecs_result[3] else None, Decimal('1.0'))
            ecs_sign_code = (ecs_result[4] or "").strip().upper() if len(ecs_result) > 4 else ""
        else:
            # If no exam definition found, try to determine from exam_type parameter
            if exam_type and exam_type in ['semester', 'yearly'] and result_name:
                # We have exam_type and result_name from parameters, use them
                formula = ''
                divide_by_multiplier = Decimal('1.0')
            else:
                # Fallback: assume input type
                exam_type = exam_type or 'input'
                result_name = result_name or ''
                formula = ''
                divide_by_multiplier = Decimal('1.0')


        subject_ids = []
        # Pre-parse formula for subject IDs (ONLY for monthly input type exams)
        # For calculated exams (semester/en_final), formula contains IDs that are NOT subject IDs.
        if formula and exam_type not in ['semester', 'yearly']:
             subject_ids = [int(s_id) for s_id in re.findall(r'\d+', formula)]

        # Fetch Subject Rules & Marks only if we might need them (Monthly/Input)
        subject_rules = {}
        scores_by_student = defaultdict(dict)
        subjects_meta = []

        if include_subjects and subject_ids:
            meta_q = text("SELECT id, subject_name, subject_name_us, short_code FROM subjects WHERE id IN :sids ORDER BY id ASC")
            meta_res = db.execute(meta_q, {"sids": tuple(subject_ids)}).fetchall()
            for r in meta_res:
                subjects_meta.append({
                    "id": r[0],
                    "name": r[1] if r[1] else '',
                    "name_us": r[2] if r[2] else '',
                    "code": r[3] if r[3] else ''
                })

        if subject_ids:
             # Subject Rules
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
            
            for row in subj_rules_result:
                subject_rules[row[0]] = {
                    "full_marks": safe_decimal(row[1], Decimal('100')),
                    "calculate_marks": safe_decimal(row[2], Decimal('100'))
                }

        # 3. Get Student List (DISTINCT to avoid duplicates from multiple learning rows per student)
        student_query_str = """
            SELECT DISTINCT s.id, s.studentid, s.kName, s.eName, s.gender, ur.avatar
            FROM learning l
            JOIN students s ON l.studentid = s.id
            LEFT JOIN users_resource ur ON ur.user_id = s.id AND ur.user_type = 'student'
            WHERE l.programid = :program_id
            AND l.gradeid = :grade_id
            AND l.shiftid = :shift_id
            AND l.academicid = :academic_id
            AND (s.status = 1 OR :historical = 1)
        """
        params = {
            "program_id": program_id,
            "grade_id": grade_id,
            "shift_id": shift_id,
            "academic_id": academic_id,
            "historical": 1 if is_historical_academic_year(db, academic_id) else 0
        }
        
        if grade_type_id:
            student_query_str += " AND l.grade_type_id = :grade_type_id"
            params["grade_type_id"] = grade_type_id
        else:
            student_query_str += " AND l.grade_type_id IS NULL"
            
        student_query_str += " ORDER BY s.eName, s.kName"
        
        students = db.execute(text(student_query_str), params).fetchall()
        
        if not students:
            return {"success": True, "results": []}

        student_ids = [s[0] for s in students]
        student_map = {s[0]: s for s in students}

        results_list = []

        
        # Pre-fetch marks if needed for fallback (Monthly/Input)
        if exam_type not in ('semester', 'yearly') and student_ids and subject_ids:
            marks_query = text("""
                SELECT student_id, subject_id, marks 
                FROM marks_input 
                WHERE student_id IN :student_ids 
                AND subject_id IN :subject_ids 
                AND academic_id = :academic_id 
                AND marks_system_id = :marks_system_id
            """)
            marks_result = db.execute(marks_query, {
                "student_ids": tuple(student_ids),
                "subject_ids": tuple(subject_ids),
                "academic_id": academic_id,
                "marks_system_id": marks_system_id
            }).fetchall()
            
            for row in marks_result:
                scores_by_student[row[0]][row[1]] = safe_decimal(row[2])

        # --- STRATEGY SWITCH BASED ON EXAM TYPE ---
        
        if exam_type == 'semester':
            # Try to fetch stored result first (Standard Semester Logic)
            # Use marks_semester table
            sem_query = text("""
                SELECT ms.student_id, ms.total, ms.average, gs.us_grade
                FROM marks_semester ms
                LEFT JOIN grade_scale gs ON ms.grade_scale_id = gs.id
                WHERE ms.student_id IN :student_ids
                AND ms.academic_id = :academic_id
                AND ms.exam_name = :result_name
            """)
            
            sem_results = db.execute(sem_query, {
                "student_ids": tuple(student_ids),
                "academic_id": academic_id,
                "result_name": result_name
            }).fetchall()
            
            sem_map = {row[0]: row for row in sem_results}
            
            # Check if we have results for most students (heuristic)
            has_stored_results = len(sem_results) > 0

            # Special handling for English/IEP Semester if NO stored results found
            if mark_type in ['en', 'iep'] and not has_stored_results:
                 # English Final Fallback: Calculate from scratch by aggregating marks_input across months
                 # This is a fallback for legacy support or if calculations haven't run yet
                 
                 # Parse Formula: (1+2+3+4)+5 -> Monthly IDs + Final ID
                 monthly_calc_ids = []
                 all_calc_ids = []
                 
                 match = re.search(r'\((\d+(?:\+\d+)*)\)\+(\d+)', formula.replace(' ', ''))
                 if match:
                    monthly_calc_ids = [int(x) for x in match.group(1).split('+')]
                    all_calc_ids = monthly_calc_ids + [int(match.group(2))]
                    
                    # Get map of calc_id -> marks_system_id
                    map_query = text("SELECT id, marks_system_id FROM exam_calculate_sign WHERE id IN :ids")
                    map_res = db.execute(map_query, {"ids": tuple(all_calc_ids)}).fetchall()
                    sys_id_map = {row[0]: row[1] for row in map_res}
                    
                    all_sys_ids = [sys_id_map[i] for i in all_calc_ids if i in sys_id_map]
                    
                    if all_sys_ids:
                        # Fetch ALL marks for relevant system IDs and students
                        all_marks_query = text("""
                            SELECT student_id, subject_id, marks
                            FROM marks_input
                            WHERE student_id IN :student_ids
                            AND academic_id = :academic_id
                            AND marks_system_id IN :sys_ids
                        """)
                        all_marks = db.execute(all_marks_query, {
                            "student_ids": tuple(student_ids),
                            "academic_id": academic_id,
                            "sys_ids": tuple(all_sys_ids)
                        }).fetchall()
                        
                        # Group by student -> subject -> sum
                        stu_marks = defaultdict(lambda: defaultdict(Decimal))
                        for row in all_marks:
                            stu_marks[row[0]][row[1]] += safe_decimal(row[2])
                            
                        # Calculate per student
                        for s_id in student_ids:
                            student = student_map[s_id]
                            subj_totals = stu_marks.get(s_id, {})
                            
                            grand_total = sum(subj_totals.values())
                            subject_count = len(subj_totals)
                            
                            # Overall Average = Grand Total / Subject Count
                            final_average = grand_total / subject_count if subject_count > 0 else Decimal('0')
                            
                            grade, _ = get_grade_from_scale(final_average, db, academic_id, grade_group_id)
                            
                            results_list.append({
                                "student_id": s_id,
                                "studentid": student[1],
                                "kName": student[2],
                                "eName": student[3],
                                "gender": student[4],
                                "avatar": student[5],
                                "total": float(grand_total),
                                "average": float(final_average),
                                "grade": grade
                            })
            else:
                 # Standard Semester Logic (Stored) OR English with Stored Results
                 for s_id in student_ids:
                    row = sem_map.get(s_id)
                    student = student_map[s_id]
                    
                    y_total = float(row[1]) if row else 0.0
                    y_avg = float(row[2]) if row else 0.0
                    y_grade = row[3] if row and row[3] else "-"
                    
                    is_failed = is_fail_grade(y_grade) if y_grade != "-" else False
                    
                    # Force None if grade is missing
                    final_total = y_total if (row and row[1] is not None and y_grade != "-") else None
                    final_average = y_avg if (row and row[2] is not None and y_grade != "-") else None

                    res_dict = {
                        "student_id": s_id,
                        "studentid": student[1],
                        "kName": student[2],
                        "eName": student[3],
                        "gender": student[4],
                        "avatar": student[5],
                        "total": final_total,
                        "average": final_average,
                        "grade": y_grade,
                        "meaning_kh": grade_meaning_map.get(y_grade, {}).get("kh", "-"),
                        "meaning_en": grade_meaning_map.get(y_grade, {}).get("en", "-"),
                        "is_failed": is_failed
                    }
                    if include_subjects:
                        res_dict["subjects"] = {}
                    results_list.append(res_dict)
                
        elif exam_type == 'yearly':
            # Use marks_yearly table
            yearly_query = text("""
                SELECT my.student_id, my.total, my.average, gs.us_grade
                FROM marks_yearly my
                LEFT JOIN grade_scale gs ON my.grade_scale_id = gs.id
                WHERE my.student_id IN :student_ids
                AND my.academic_id = :academic_id
                AND my.exam_name = :result_name
            """)
            
            yearly_results = db.execute(yearly_query, {
                "student_ids": tuple(student_ids),
                "academic_id": academic_id,
                "result_name": result_name
            }).fetchall()

            yearly_map = {row[0]: row for row in yearly_results}

            for s_id in student_ids:
                row = yearly_map.get(s_id)
                student = student_map[s_id]
                
                # Check indices:
                # 0: student_id
                # 1: total
                # 2: average
                # 3: us_grade
                
                y_total = float(row[1]) if row else 0.0
                y_avg = float(row[2]) if row else 0.0
                y_grade = row[3] if row and row[3] else "-"
                
                is_failed = is_fail_grade(y_grade) if y_grade != "-" else False

                # Force None if grade is missing
                # Note: safe_decimal not strictly needed if we cast float, but good for safety if DB returns None for total/avg even if row exists.
                # Here row[1] and row[2] are usually Decimals from DB.
                
                final_total = y_total if (row and row[1] is not None and y_grade != "-") else None
                final_average = y_avg if (row and row[2] is not None and y_grade != "-") else None

                res_dict = {
                    "student_id": s_id,
                    "studentid": student[1],
                    "kName": student[2],
                    "eName": student[3],
                    "gender": student[4],
                    "avatar": student[5],
                    "total": final_total,
                    "average": final_average,
                    "grade": y_grade,
                    "meaning_kh": grade_meaning_map.get(y_grade, {}).get("kh", "-"),
                    "meaning_en": grade_meaning_map.get(y_grade, {}).get("en", "-"),
                    "rank": 0, # Will be re-calculated by sort below
                    "is_failed": is_failed
                }
                if include_subjects:
                    res_dict["subjects"] = {}
                results_list.append(res_dict)
                
        else:
            # Monthly / Input / Default
            # Use precalculated marks_monthly or calculate from marks_input
            
            # Fetch precalculated marks_monthly
            monthly_query = text("""
                SELECT student_id, total, average, grade_scale_id 
                FROM marks_monthly 
                WHERE student_id IN :student_ids 
                AND academic_id = :academic_id 
                AND marks_system_id = :marks_system_id
            """)
            monthly_result = db.execute(monthly_query, {
                "student_ids": tuple(student_ids),
                "academic_id": academic_id,
                "marks_system_id": marks_system_id
            }).fetchall()
            
            monthly_map = {
                row[0]: {
                    "total": safe_decimal(row[1]),
                    "average": safe_decimal(row[2]),
                    "grade_scale_id": row[3]
                } for row in monthly_result
            }

            grade_scale_ids = sorted(
                {
                    prec["grade_scale_id"]
                    for prec in monthly_map.values()
                    if prec and prec.get("grade_scale_id")
                }
            )
            grade_scale_map: Dict[Any, Any] = {}
            if grade_scale_ids:
                gs_rows = db.execute(
                    text("SELECT id, us_grade FROM grade_scale WHERE id IN :ids"),
                    {"ids": tuple(grade_scale_ids)},
                ).fetchall()
                grade_scale_map = {r[0]: r[1] for r in gs_rows}
            
            # If monthly record exists, use it. Otherwise 0. (Assuming calculation happens on save)
            for s_id in student_ids:
                student = student_map[s_id]
                prec = monthly_map.get(s_id)
                
                final_total = Decimal('0')
                final_average = Decimal('0')
                grade = "-"
                
                if prec:
                    # Use stored monthly row even when total/average are 0
                    final_total = prec['total']
                    final_average = prec['average']
                    if prec['grade_scale_id']:
                        gsv = grade_scale_map.get(prec['grade_scale_id'])
                        if gsv is not None:
                            grade = gsv
                    elif prec['average'] is not None:
                        grade, _ = get_grade_from_scale(
                            prec['average'], db, academic_id, grade_group_id
                        )
                else:
                    # FALLBACK: Calculate from marks_input (only subjects with saved marks)
                    adjusted_total_marks = Decimal('0')
                    student_subject_count = 0
                    student_scores = scores_by_student.get(s_id, {})

                    for subj_id in subject_ids:
                        if subj_id not in student_scores:
                            continue
                        raw_mark = safe_decimal(student_scores[subj_id], Decimal('0'))
                        student_subject_count += 1

                        rule = subject_rules.get(subj_id)
                        adjusted_mark = raw_mark
                        if rule and safe_decimal(rule.get('calculate_marks'), Decimal('100')) != Decimal('100'):
                            full_marks = safe_decimal(rule.get('full_marks'), Decimal('0'))
                            if raw_mark < (full_marks / Decimal('2')):
                                adjusted_mark = Decimal('0')
                            else:
                                calculate_marks = safe_decimal(rule.get('calculate_marks'), Decimal('0'))
                                deduction_base = full_marks * (calculate_marks / Decimal('100'))
                                adjusted_mark = raw_mark - deduction_base
                                if adjusted_mark < Decimal('0'):
                                    adjusted_mark = Decimal('0')
                        adjusted_total_marks += adjusted_mark

                    final_total = adjusted_total_marks
                    final_average = (
                        adjusted_total_marks / divide_by_multiplier
                        if divide_by_multiplier > Decimal('0')
                        else Decimal('0')
                    )

                    if student_subject_count > 0:
                        grade, _ = get_grade_from_scale(
                            final_average, db, academic_id, grade_group_id
                        )

                # Force None if grade is missing (Monthly/Input)
                # Note: final_total/average here are calculated Decimals.
                # If grade is "-", we should hide them.
                display_total = float(final_total) if grade != "-" else None
                display_average = float(final_average) if grade != "-" else None

                res_dict = {
                    "student_id": s_id,
                    "studentid": student[1],
                    "kName": student[2],
                    "eName": student[3],
                    "gender": student[4],
                    "avatar": student[5],
                    "total": display_total,
                    "average": display_average,
                    "grade": grade,
                    "meaning_kh": grade_meaning_map.get(grade, {}).get("kh", "-"),
                    "meaning_en": grade_meaning_map.get(grade, {}).get("en", "-"),
                    "is_failed": is_fail_grade(grade)
                }

                if include_subjects:
                    res_dict["subjects"] = {
                        str(k): float(v) for k, v in scores_by_student.get(s_id, {}).items()
                    }
                
                results_list.append(res_dict)

        # Sort by displayed average (2 decimals) so visual ties stay tied.
        results_list.sort(
            key=lambda x: round(float(x["average"]), 2) if x["average"] is not None else -1.0,
            reverse=True
        )

        # Competition ranking (1,1,3...) for equal averages.
        prev_score = None
        prev_rank = 0
        for idx, res in enumerate(results_list, start=1):
            score = round(float(res["average"]), 2) if res["average"] is not None else None
            if idx == 1:
                rank = 1
            elif score is not None and prev_score is not None and score == prev_score:
                rank = prev_rank
            else:
                rank = idx

            res['rank'] = rank
            prev_score = score
            prev_rank = rank

        # Include exam_name so frontend can display which exam results are shown
        exam_display_name = result_name or (exam_name if exam_name else None)
        response = {"success": True, "exam_name": exam_display_name, "results": results_list}
        
        # ---------------------------------------------------------------------
        # NEW INSTRUCTION FROM USER: Instead of attempting to parse formulas,
        # we will fetch the 1-to-1 individual bottom-sheet view for everyone, 
        # extract their internal subject dictionary directly, and merge it here.
        # This mathematical overlay ensures 100% data and logic consistency!
        # ---------------------------------------------------------------------
        if include_subjects:
            from ...services.results.results_handler import get_student_result_detail_service

            mt_lower = (mark_type or "kh").lower()
            is_kh_rsem_class = (
                exam_type == "semester"
                and mt_lower == "kh"
                and ecs_sign_code in ("RSEM1", "RSEM2")
            )
            sem_ecs_row = None
            if is_kh_rsem_class:
                sem_sign = "SEM1" if ecs_sign_code == "RSEM1" else "SEM2"
                sem_ecs_row = db.execute(
                    text("""
                        SELECT marks_system_id, result_name, exam_type
                        FROM exam_calculate_sign
                        WHERE academic_id = :academic_id
                          AND program_id = :program_id
                          AND grade_group_id = :grade_group_id
                          AND sign_code = :sem_sign
                          AND is_active = 1
                        LIMIT 1
                    """),
                    {
                        "academic_id": academic_id,
                        "program_id": program_id,
                        "grade_group_id": grade_group_id,
                        "sem_sign": sem_sign,
                    },
                ).fetchone()

            subjects_meta_columns: Optional[List[Dict[str, Any]]] = None

            for res_dict in response["results"]:
                s_id = res_dict["student_id"]
                stu_details = get_student_result_detail_service(
                    db=db,
                    student_id=s_id,
                    program_id=program_id,
                    grade_id=grade_id,
                    academic_id=academic_id,
                    marks_system_id=marks_system_id,
                    grade_type_id=grade_type_id,
                    shift_id=shift_id,
                    result_name=result_name,
                    exam_name=exam_name,
                    exam_type=exam_type,
                )

                summary = stu_details.get("summary", {})
                if summary.get("total") is not None:
                    res_dict["total"] = float(summary["total"])
                if summary.get("average") is not None:
                    res_dict["average"] = float(summary["average"])
                if summary.get("grade") is not None:
                    res_dict["grade"] = summary["grade"]

                sem_stu_details = None
                if sem_ecs_row and sem_ecs_row[0] is not None:
                    sem_stu_details = get_student_result_detail_service(
                        db=db,
                        student_id=s_id,
                        program_id=program_id,
                        grade_id=grade_id,
                        academic_id=academic_id,
                        marks_system_id=int(sem_ecs_row[0]),
                        grade_type_id=grade_type_id,
                        shift_id=shift_id,
                        result_name=sem_ecs_row[1],
                        exam_name=None,
                        exam_type=sem_ecs_row[2],
                    )

                sub_dict, ordered_columns = _merge_student_detail_into_class_subjects(
                    stu_details,
                    sem_stu_details,
                    skip_month_aggregation=is_kh_rsem_class,
                    append_rsem_summary_column=is_kh_rsem_class,
                )

                if subjects_meta_columns is None:
                    subjects_meta_columns = ordered_columns
                elif ordered_columns:
                    known = {c.get("id") for c in (subjects_meta_columns or []) if c.get("id")}
                    for c in ordered_columns:
                        cid = c.get("id")
                        if cid and cid not in known:
                            known.add(cid)
                            subjects_meta_columns.append(c)

                aligned: Dict[str, float] = {}
                for col in subjects_meta_columns or []:
                    cid = col.get("id")
                    if not cid:
                        continue
                    if cid in sub_dict:
                        aligned[cid] = sub_dict[cid]
                res_dict["subjects"] = aligned

            if subjects_meta_columns:
                label_set = []
                for c in subjects_meta_columns:
                    nm = c.get("name")
                    if not nm:
                        continue
                    code = (c.get("code") or "").upper()
                    if code in (
                        "MON1", "MON2", "MON3", "MON4", "MON5", "MON6", "MON7", "MON8",
                        "SEM1", "SEM2", "RSEM1", "RSEM2", "MONTH_AVG",
                    ):
                        continue
                    if nm in ("RSEM1", "RSEM2"):
                        continue
                    label_set.append(nm)
                if label_set:
                    name_us_query = text(
                        "SELECT DISTINCT subject_name, subject_name_us FROM subjects WHERE subject_name IN :labels"
                    )
                    name_us_res = db.execute(
                        name_us_query, {"labels": tuple(set(label_set))}
                    ).fetchall()
                    name_us_map = {r[0]: r[1] for r in name_us_res if r[1]}
                    for c in subjects_meta_columns:
                        nm = c.get("name")
                        if nm and nm in name_us_map:
                            c["name_us"] = name_us_map[nm]

            response["subjects_meta"] = subjects_meta_columns or []
            
        return response

    except Exception as e:
        logger.error(f"Error getting class results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/student")
def get_student_result_detail(
    student_id: int = Query(...),
    program_id: int = Query(...),
    grade_id: int = Query(...),
    academic_id: int = Query(...),
    marks_system_id: int = Query(...),
    grade_type_id: Optional[int] = Query(None),
    shift_id: Optional[int] = Query(None),
    result_name: Optional[str] = Query(None),
    exam_name: Optional[str] = Query(None),
    exam_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get detailed result breakdown for a specific student."""
    try:
        details = get_student_result_detail_service(
            db=db,
            student_id=student_id,
            program_id=program_id,
            grade_id=grade_id,
            academic_id=academic_id,
            marks_system_id=marks_system_id,
            grade_type_id=grade_type_id,
            shift_id=shift_id,
            result_name=result_name,
            exam_name=exam_name,
            exam_type=exam_type
        )
        can_comment = False
        if shift_id is not None:
            can_comment = can_user_comment_on_result(
                db,
                current_user,
                program_id,
                grade_id,
                int(shift_id),
                academic_id,
                grade_type_id,
            )
        details["can_comment"] = can_comment
        details["comment_max_length"] = TEACHER_COMMENT_MAX_LENGTH
        return {"success": True, "details": details}

    except Exception as e:
        logger.error(f"Error getting student detail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class SaveTeacherCommentPayload(BaseModel):
    student_id: int
    program_id: int
    grade_id: int
    shift_id: int
    academic_id: int
    marks_system_id: int
    comment: str = ""
    grade_type_id: Optional[int] = None
    result_name: Optional[str] = None
    exam_name: Optional[str] = None
    exam_type: Optional[str] = None


@router.post("/comment")
def save_student_result_comment(
    payload: SaveTeacherCommentPayload,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Save homeroom teacher comment on monthly/semester/yearly result row."""
    try:
        return save_teacher_comment(
            db=db,
            current_user=current_user,
            student_id=payload.student_id,
            program_id=payload.program_id,
            grade_id=payload.grade_id,
            shift_id=payload.shift_id,
            academic_id=payload.academic_id,
            marks_system_id=payload.marks_system_id,
            comment=payload.comment,
            grade_type_id=payload.grade_type_id,
            result_name=payload.result_name or payload.exam_name,
            exam_type=payload.exam_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving teacher comment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/top-students/feature")
def feature_top_students(
    payload: FeatureTopStudentsPayload,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Publish top students for one class context.

    Behavior:
    - Deactivates old active records of the same class context.
    - Inserts new top rows as active.
    - Keeps old rows in history.
    """
    if not payload.students:
        raise HTTPException(status_code=400, detail="students payload is empty")
    if len(payload.students) > 3:
        raise HTTPException(status_code=400, detail="Only top 3 students are allowed")

    role_id = getattr(current_user, "role", None)
    if role_id == 3:
        raise HTTPException(status_code=403, detail="Parents cannot feature top students")

    try:
        batch_id = str(uuid4())

        # Replace active snapshot for this class context
        query = db.query(ResultTopStudent).filter(
            ResultTopStudent.academic_id == payload.academic_id,
            ResultTopStudent.program_id == payload.program_id,
            ResultTopStudent.grade_id == payload.grade_id,
            ResultTopStudent.shift_id == payload.shift_id,
            ResultTopStudent.is_active == 1,
        )
        if payload.grade_type_id is None:
            query = query.filter(ResultTopStudent.grade_type_id.is_(None))
        else:
            query = query.filter(ResultTopStudent.grade_type_id == payload.grade_type_id)

        query.update({"is_active": 0}, synchronize_session=False)

        created_rows = 0
        for row in sorted(payload.students, key=lambda x: x.rank):
            item = ResultTopStudent(
                featured_batch_id=batch_id,
                academic_id=payload.academic_id,
                program_id=payload.program_id,
                grade_id=payload.grade_id,
                shift_id=payload.shift_id,
                grade_type_id=payload.grade_type_id,
                student_id=row.student_id,
                rank=row.rank,
                average=row.average,
                grade=row.grade,
                marks_system_id=payload.marks_system_id,
                result_name=payload.result_name,
                exam_name=payload.exam_name,
                exam_type=payload.exam_type,
                period=payload.period,
                is_active=1,
                featured_by=getattr(current_user, "id", None),
            )
            db.add(item)
            created_rows += 1

        db.commit()

        return {
            "success": True,
            "message": "Top students featured successfully",
            "featured_batch_id": batch_id,
            "count": created_rows,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error featuring top students: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-students/featured")
def get_featured_top_students(
    limit_classes: int = Query(20, ge=1, le=100),
    academic_id: Optional[int] = Query(None, description="Only snapshots of this academic year"),
    db: Session = Depends(get_db),
):
    """
    Get active featured top students snapshots for home screen.
    Returns grouped class snapshots, each containing up to 3 students.
    When academic_id is omitted, behavior is unchanged (all active snapshots).
    """
    try:
        year_filter = "AND rts.academic_id = :academic_id" if academic_id is not None else ""
        year_params = {"academic_id": academic_id} if academic_id is not None else {}
        rows = db.execute(
            text(
                f"""
                SELECT
                    rts.id,
                    rts.featured_batch_id,
                    rts.academic_id,
                    rts.program_id,
                    rts.grade_id,
                    rts.shift_id,
                    rts.grade_type_id,
                    rts.student_id,
                    rts.rank,
                    rts.average,
                    rts.grade,
                    rts.result_name,
                    rts.exam_name,
                    rts.exam_type,
                    rts.period,
                    rts.created_at,
                    s.kName,
                    s.eName,
                    s.gender,
                    ur.avatar,
                    p.program_name,
                    g.grade_name,
                    sh.shift_name,
                    gt.type_name AS grade_type_name,
                    b.branch_name,
                    COALESCE(ay.academic_us_name, ay.academic_name) AS academic_name
                FROM results_top_students rts
                LEFT JOIN students s ON s.id = rts.student_id
                LEFT JOIN users_resource ur ON ur.user_id = s.id AND ur.user_type = 'student'
                LEFT JOIN program p ON p.id = rts.program_id
                LEFT JOIN grade g ON g.id = rts.grade_id
                LEFT JOIN shift sh ON sh.id = rts.shift_id
                LEFT JOIN grade_type gt ON gt.id = rts.grade_type_id
                LEFT JOIN branch b ON b.id = g.branch_id
                LEFT JOIN academic ay ON ay.id = rts.academic_id
                WHERE rts.is_active = 1
                {year_filter}
                ORDER BY rts.created_at DESC, rts.rank ASC
                """
            ),
            year_params,
        ).fetchall()

        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            group_key = f"{row[2]}:{row[3]}:{row[4]}:{row[5]}:{row[6]}"
            if group_key not in grouped:
                grouped[group_key] = {
                    "featured_batch_id": row[1],
                    "academic_id": row[2],
                    "program_id": row[3],
                    "grade_id": row[4],
                    "shift_id": row[5],
                    "grade_type_id": row[6],
                    "program_name": row[20],
                    "grade_name": row[21],
                    "shift_name": row[22],
                    "grade_type_name": row[23],
                    "branch_name": row[24],
                    "academic_name": row[25],
                    "result_name": row[11],
                    "exam_name": row[12],
                    "exam_type": row[13],
                    "period": row[14],
                    "featured_at": row[15].isoformat() if row[15] else None,
                    "students": [],
                }

            grouped[group_key]["students"].append(
                {
                    "id": row[7],
                    "rank": row[8],
                    "average": float(row[9]) if row[9] is not None else None,
                    "grade": row[10],
                    "kName": row[16],
                    "eName": row[17],
                    "gender": row[18],
                    "avatar": row[19],
                }
            )

        # Same ordering as before: newest featured_at first, then cap class count (stable for equal timestamps).
        groups = list(grouped.values())
        groups.sort(key=lambda x: x.get("featured_at") or "", reverse=True)
        groups = groups[:limit_classes]

        for group in groups:
            group["students"] = sorted(group["students"], key=lambda x: x["rank"])[:3]

        return {"success": True, "groups": groups}
    except Exception as e:
        logger.error(f"Error fetching featured top students: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-students/student-extra")
def get_featured_top_student_extra(
    student_id: int = Query(..., description="Student ID"),
    academic_id: Optional[int] = Query(None, description="Academic year ID"),
    db: Session = Depends(get_db),
):
    """
    Get extra details for featured-top-student bottom sheet.
    Includes parent names + branch + academic name.
    """
    try:
        student_row = db.execute(
            text(
                """
                SELECT
                    s.fatherName,
                    s.motherName,
                    b.branch_name
                FROM students s
                LEFT JOIN branch b ON b.id = s.branch
                WHERE s.id = :student_id
                LIMIT 1
                """
            ),
            {"student_id": student_id},
        ).fetchone()

        if not student_row:
            raise HTTPException(status_code=404, detail="Student not found")

        academic_name = None
        if academic_id is not None:
            acad_row = db.execute(
                text(
                    """
                    SELECT COALESCE(academic_us_name, academic_name) AS academic_name
                    FROM academic
                    WHERE id = :academic_id
                    LIMIT 1
                    """
                ),
                {"academic_id": academic_id},
            ).fetchone()
            if acad_row:
                academic_name = acad_row[0]

        parents_rows = db.execute(
            text(
                """
                SELECT fatherName, motherName
                FROM parents
                WHERE FIND_IN_SET(:student_id, myChilds) > 0
                LIMIT 5
                """
            ),
            {"student_id": str(student_id)},
        ).fetchall()

        parent_names: List[str] = []
        for p_row in parents_rows:
            father = (p_row[0] or "").strip()
            mother = (p_row[1] or "").strip()
            if father:
                parent_names.append(father)
            if mother:
                parent_names.append(mother)

        # Fallback from student row if parents table has no match
        if not parent_names:
            fallback_father = (student_row[0] or "").strip()
            fallback_mother = (student_row[1] or "").strip()
            if fallback_father:
                parent_names.append(fallback_father)
            if fallback_mother:
                parent_names.append(fallback_mother)

        # Unique + keep order
        seen = set()
        deduped = []
        for n in parent_names:
            if n and n not in seen:
                seen.add(n)
                deduped.append(n)

        return {
            "success": True,
            "branch_name": student_row[2],
            "academic_name": academic_name,
            "parent_names": deduped,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching top-student extra: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
