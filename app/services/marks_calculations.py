"""
Marks calculation functions for monthly, semester, and yearly results.
Exact implementation matching the Python Telegram bot.
"""

from sqlalchemy.orm import Session
from sqlalchemy import text
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List, Optional
import logging
import re
from .marks_utils import (
    safe_decimal,
    round_decimal_to_2_places,
    get_grade_scale_id_raw,
    get_max_scale_score,
    get_input_monthly_subject_ids,
    SUBJECTS_REFERENCE_EXAM_CODES,
    INPUT_SUBJECTS_FORMULA_REFERENCE
)

logger = logging.getLogger(__name__)


def calculate_and_store_monthly_marks(
    db: Session,
    student_id: int,
    program_id: int,
    grade_id: int,
    grade_group_id: int,
    academic_id: int,
    marks_system_id: int,
    auto_commit: bool = True
) -> List[int]:
    """
    Calculate and store monthly marks for a student.
    Exact implementation matching Telegram bot's monthly_flow.py.
    Returns list of marks_monthly exam_calculate_sign IDs that were created/updated.
    """
    updated_monthly_exam_ids = []
    try:
        # Note: Transaction is managed by the calling function
        
        # 1. Get marks_code for the current marks_system_id
        marks_code_query = text("SELECT marks_code FROM marks_system WHERE id = :marks_system_id")
        marks_code_result = db.execute(marks_code_query, {"marks_system_id": marks_system_id}).fetchone()
        marks_code = marks_code_result[0] if marks_code_result else None
        
        # 2. Get the LATEST active rule (ORDER BY id DESC LIMIT 1)
        # Match kortra: no exam_type filter - can have duplicates for same marks_system_id, take newest
        rules_query = text("""
            SELECT id, result_name, formula_expression, divide_by_multiplier 
            FROM exam_calculate_sign 
            WHERE academic_id = :academic_id 
            AND program_id = :program_id 
            AND grade_group_id = :grade_group_id 
            AND marks_system_id = :marks_system_id 
            AND is_active = 1
            ORDER BY id DESC
            LIMIT 1
        """)
        rule_row = db.execute(rules_query, {
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_group_id": grade_group_id,
            "marks_system_id": marks_system_id
        }).fetchone()
        
        if not rule_row:
            logger.info(f"DEBUG: No rules found for marks_system_id {marks_system_id} (Code: {marks_code})")
            return []
            
        rules = [rule_row]
        
        # Get divide_by_multiplier from the rule
        divide_by_multiplier = safe_decimal(rule_row[3], Decimal('1.0'))
        
        for rule in rules:
            rule_id = rule[0]
            exam_name = rule[1]
            formula_str = rule[2] or ""
            
            # updated_monthly_exam_ids.append(rule_id) # Consistent with bot, we don't return rule ID here?
            # Actually bot returns: updated_monthly_exam_ids.append(marks_monthly_id)
            
            subject_ids = []
            
            # 1. Try to get subjects from exam_calculate_sign_subjects (via reference)
            marks_code_upper = (marks_code or "").upper()
            if marks_code_upper in SUBJECTS_REFERENCE_EXAM_CODES and str(formula_str).strip().lower() == INPUT_SUBJECTS_FORMULA_REFERENCE:
                # Use our new utility to get subjects
                # We can call get_input_monthly_subject_ids but we already have rule_id, so let's use get_exam_calculate_sign_subject_ids direct
                query = text("SELECT subject_id FROM exam_calculate_sign_subjects WHERE exam_calculate_sign_id = :ecs_id")
                result = db.execute(query, {"ecs_id": rule_id}).fetchall()
                subject_ids = [int(r[0]) for r in result if r[0] is not None]
                
                if not subject_ids:
                    # Fallback 1: marks_system_subjects
                    try:
                        mss_query = text("SELECT subject_id FROM marks_system_subjects WHERE marks_system_id = :marks_system_id ORDER BY subject_id")
                        mss_result = db.execute(mss_query, {"marks_system_id": marks_system_id}).fetchall()
                        subject_ids = [int(r[0]) for r in mss_result if r[0] is not None]
                        if subject_ids:
                            logger.info(f"Monthly calc: No rows in exam_calculate_sign_subjects for rule={rule_id}. Using fallback marks_system_subjects.")
                        else:
                            # Fallback 2: subjects_group (ALL subjects)
                            sg_all_query = text("""
                                SELECT subject_id FROM subjects_group 
                                WHERE academic_id = :academic_id 
                                AND program_id = :program_id 
                                AND grade_group_id = :grade_group_id
                                ORDER BY subject_id
                            """)
                            sg_all_result = db.execute(sg_all_query, {
                                "academic_id": academic_id,
                                "program_id": program_id,
                                "grade_group_id": grade_group_id
                            }).fetchall()
                            subject_ids = [int(r[0]) for r in sg_all_result if r[0] is not None]
                            logger.warning(f"Monthly calc: No rows in exam_calculate_sign_subjects or marks_system_subjects. Falling back to all subjects.")
                    except Exception as e:
                        logger.warning(f"Monthly calc fallback failed: {e}")

            # 2. If no subjects found yet, try parsing formula
            if not subject_ids:
                subject_ids = [int(s_id) for s_id in re.findall(r'\d+', formula_str)]
                
            if not subject_ids:
                continue
                
            # Deduplicate preserving order
            subject_ids = list(dict.fromkeys(int(s) for s in subject_ids))
            
            # Get subject rules (full_marks, calculate_marks)
            placeholders = ','.join([':sid' + str(i) for i in range(len(subject_ids))])
            sg_query = text(f"""
                SELECT subject_id, full_marks, calculate_marks 
                FROM subjects_group 
                WHERE academic_id = :academic_id 
                AND program_id = :program_id 
                AND grade_group_id = :grade_group_id 
                AND subject_id IN ({placeholders})
            """)
            sg_params = {
                "academic_id": academic_id,
                "program_id": program_id,
                "grade_group_id": grade_group_id,
                **{f'sid{i}': sid for i, sid in enumerate(subject_ids)}
            }
            subject_rules_result = db.execute(sg_query, sg_params).fetchall()
            subject_rules = {row[0]: {'full_marks': row[1], 'calculate_marks': row[2]} for row in subject_rules_result}
            
            # Get student marks for these subjects
            # CRITICAL: Fetch timestamps and deduplicate - keep latest per subject (match kortra)
            # Sort by updated_at, created_at, id so first row = latest for ascending
            marks_query = text(f"""
                SELECT id, marks, subject_id, updated_at, created_at
                FROM marks_input 
                WHERE student_id = :student_id 
                AND academic_id = :academic_id 
                AND program_id = :program_id 
                AND grade_group_id = :grade_group_id 
                AND marks_system_id = :marks_system_id 
                AND subject_id IN ({placeholders})
                ORDER BY COALESCE(updated_at, created_at) ASC, created_at ASC, id ASC
            """)
            marks_params = {
                "student_id": student_id,
                "academic_id": academic_id,
                "program_id": program_id,
                "grade_group_id": grade_group_id,
                "marks_system_id": marks_system_id,
                **{f'sid{i}': sid for i, sid in enumerate(subject_ids)}
            }
            student_marks_result = db.execute(marks_query, marks_params).fetchall()
            
            # CRITICAL: IN-MEMORY DEDUPLICATION (match kortra monthly_flow)
            # Sorted ascending by updated_at/created_at/id - LAST occurrence per subject = latest
            unique_marks_by_subject = {}
            for row in student_marks_result:
                subj_id = row[2]
                unique_marks_by_subject[subj_id] = row  # overwrite = keep last = latest
            if len(student_marks_result) > len(unique_marks_by_subject):
                logger.warning(
                    f"DUPLICATE MARKS in Monthly Flow for student {student_id}, exam {exam_name}: "
                    f"{len(student_marks_result)} raw rows -> {len(unique_marks_by_subject)} unique"
                )

            # Calculate adjusted total marks (sum of all adjusted marks after calculate_marks deductions)
            adjusted_total_marks = Decimal('0')
            present_subject_ids = set()
            marks_input_ids = []
            
            for subj_id, mark_record in unique_marks_by_subject.items():
                mark_id = mark_record[0]
                raw_mark = safe_decimal(mark_record[1], Decimal('0'))
                # subj_id already known
                
                if subj_id is not None:
                    present_subject_ids.add(int(subj_id))
                    
                rule_data = subject_rules.get(subj_id)
                
                adjusted_mark = raw_mark
                if rule_data and safe_decimal(rule_data.get('calculate_marks'), Decimal('100')) != Decimal('100'):
                    full_marks = safe_decimal(rule_data.get('full_marks'), Decimal('0'))
                    if raw_mark < (full_marks / Decimal('2')):
                        adjusted_mark = Decimal('0')
                    else:
                        calculate_marks = safe_decimal(rule_data.get('calculate_marks'), Decimal('0'))
                        deduction_base = full_marks * (calculate_marks / Decimal('100'))
                        adjusted_mark = raw_mark - deduction_base
                        if adjusted_mark < Decimal('0'):
                            adjusted_mark = Decimal('0')
                
                adjusted_total_marks += adjusted_mark
                marks_input_ids.append(str(mark_id))
            
            student_subject_count = len(present_subject_ids)
            
            # Check if record exists in marks_monthly table
            check_query = text("""
                SELECT id FROM marks_monthly 
                WHERE student_id = :student_id 
                AND academic_id = :academic_id 
                AND program_id = :program_id 
                AND grade_group_id = :grade_group_id 
                AND marks_system_id = :marks_system_id 
                AND exam_name = :exam_name
            """)
            existing_record = db.execute(check_query, {
                "student_id": student_id,
                "academic_id": academic_id,
                "program_id": program_id,
                "grade_group_id": grade_group_id,
                "marks_system_id": marks_system_id,
                "exam_name": exam_name
            }).fetchone()
            
            # Check if we have any subjects present
            if student_subject_count == 0:
                logger.info(f"Student {student_id} has NO input marks for {exam_name}. Deleting monthly record if exists.")
                if existing_record:
                    # Delete existing record because all inputs were removed
                    marks_monthly_id = existing_record[0]
                    db.execute(text("DELETE FROM marks_monthly_items WHERE marks_monthly_id = :mid"), {"mid": marks_monthly_id})
                    db.execute(text("DELETE FROM marks_monthly WHERE id = :id"), {"id": marks_monthly_id})
                    
                    # Return distinct flag (e.g., -1) to indicate "Change happened (deletion), please cascade"
                    # If we return empty, cascade stops. We want cascade to run to update Semester.
                    updated_monthly_exam_ids.append(-1)
                
                # Do NOT insert/update a 0.00 record.
                # Continue to next rule (if any)
                continue

            # Calculate missing subjects count and adjust divide_by_multiplier
            # Use 'expected_subjects' (from logic above) instead of grade group total
            expected_subjects = len(subject_ids)
            missing_subjects_count = max(0, expected_subjects - int(student_subject_count))
            
            adjusted_divide_by_multiplier = divide_by_multiplier - Decimal(str(missing_subjects_count))
            if adjusted_divide_by_multiplier < Decimal('1'):
                adjusted_divide_by_multiplier = Decimal('1')  # Minimum of 1 to avoid division by zero
            
            # Calculate raw average (not percentage) - this is what we store in the database
            raw_average = adjusted_total_marks / adjusted_divide_by_multiplier if adjusted_divide_by_multiplier > Decimal('0') else Decimal('0')
            total_to_store = round_decimal_to_2_places(adjusted_total_marks)
            average_to_store = round_decimal_to_2_places(raw_average)
            
            # Use raw average with scale max for grade scale lookup (match kortra)
            target_scale_max = get_max_scale_score(db, academic_id, grade_group_id)
            grade_scale_id = get_grade_scale_id_raw(
                db, average_to_store, academic_id, program_id, grade_group_id, max_possible_score=target_scale_max
            )
            
            logger.info(f"Recalculated for student {student_id}, exam {exam_name}: total={total_to_store}, avg={average_to_store}")
            
            # Use marks_monthly_items junction table only (match kortra - no marks_input_ids legacy column)
            marks_monthly_id = None
            if existing_record:
                marks_monthly_id = existing_record[0]
                update_query = text("""
                    UPDATE marks_monthly 
                    SET total = :total, average = :average, grade_scale_id = :grade_scale_id, 
                        grade_id = :grade_id, updated_at = NOW() 
                    WHERE id = :id
                """)
                db.execute(update_query, {
                    "total": total_to_store,
                    "average": average_to_store,
                    "grade_scale_id": grade_scale_id,
                    "grade_id": grade_id,
                    "id": marks_monthly_id
                })
            else:
                insert_query = text("""
                    INSERT INTO marks_monthly 
                    (exam_name, student_id, program_id, grade_id, grade_group_id, academic_id, marks_system_id, total, average, grade_scale_id, created_at, updated_at) 
                    VALUES 
                    (:exam_name, :student_id, :program_id, :grade_id, :grade_group_id, :academic_id, :marks_system_id, :total, :average, :grade_scale_id, NOW(), NOW())
                """)
                db.execute(insert_query, {
                    "exam_name": exam_name,
                    "student_id": student_id,
                    "program_id": program_id,
                    "grade_id": grade_id,
                    "grade_group_id": grade_group_id,
                    "academic_id": academic_id,
                    "marks_system_id": marks_system_id,
                    "total": total_to_store,
                    "average": average_to_store,
                    "grade_scale_id": grade_scale_id
                })
                # Get last ID
                cursor = db.execute(text("SELECT LAST_INSERT_ID()")).fetchone()
                marks_monthly_id = cursor[0] if cursor else None

            if marks_monthly_id:
                updated_monthly_exam_ids.append(marks_monthly_id)
                
                # Manage marks_monthly_items
                db.execute(text("DELETE FROM marks_monthly_items WHERE marks_monthly_id = :mid"), {"mid": marks_monthly_id})
                if marks_input_ids:
                    # Bulk insert
                    values_list = []
                    params = {"mid": marks_monthly_id}
                    for i, input_id in enumerate(marks_input_ids):
                        values_list.append(f"(:mid, :input_id{i}, NOW(), NOW())")
                        params[f"input_id{i}"] = input_id
                    
                    if values_list:
                        items_query = text(f"INSERT INTO marks_monthly_items (marks_monthly_id, marks_input_id, created_at, updated_at) VALUES {', '.join(values_list)}")
                        db.execute(items_query, params)
            
            if auto_commit:
                db.commit()
    
    except Exception as e:
        if auto_commit:
            db.rollback()
        logger.error(f"Error in calculate_and_store_monthly_marks for student {student_id}: {e}", exc_info=True)
        raise
    
    return updated_monthly_exam_ids


def calculate_and_store_semester_marks(
    db: Session,
    student_id: int,
    program_id: int,
    grade_id: int,
    grade_group_id: int,
    academic_id: int,
    triggered_by_monthly_ids: Optional[List[int]] = None,
    auto_commit: bool = True
) -> List[int]:
    """
    Calculate and store semester marks for a student.
    Exact implementation matching Telegram bot's semester_flow.py logic.
    Returns list of marks_semester exam_calculate_sign IDs that were created/updated.
    """
    updated_semester_exam_ids = []
    try:
        # Note: Transaction is managed by the calling function
        
        # Get program mark_type header
        program_query = text("SELECT mark_type FROM program WHERE id = :program_id")
        program_result = db.execute(program_query, {"program_id": program_id}).fetchone()
        mark_type = program_result[0] if program_result else 'kh'
        
        # Check columns existence for backward compatibility (optional but safe)
        # SQLAlchemy inspection or Just Trying is customary, but let's assume valid schema for pama_api
        # or use try-catch if needed. For now assuming schema has columns.
        
        # Get ALL Semester Rules (RSEM1, RSEM2)
        # We also fetch marks_system_id. If it's 0 in the rule table, we'll try to resolve it.
        # Use simple IN clause for sign_code
        rules_query = text("""
            SELECT id, result_name, formula_expression, marks_system_id, sign_code, divide_by_multiplier 
            FROM exam_calculate_sign 
            WHERE academic_id = :academic_id 
            AND program_id = :program_id 
            AND grade_group_id = :grade_group_id 
            AND upper(sign_code) IN ('RSEM1', 'RSEM2') 
            AND is_active = 1
        """)
        rules_result = db.execute(rules_query, {
            "academic_id": academic_id, 
            "program_id": program_id, 
            "grade_group_id": grade_group_id
        }).fetchall()
        
        # Convert to dicts for easier handling
        all_rules = []
        for r in rules_result:
            all_rules.append({
                'id': r[0], 'result_name': r[1], 'formula_expression': r[2], 
                'marks_system_id': r[3], 'sign_code': r[4], 'divide_by_multiplier': r[5]
            })

        if not all_rules:
            return []

        # STRICT DUPLICATE PREVENTION & MARK SYSTEM ID FIX (Ported from kortra_env)
        seen_ms_ids = set()
        rules = []
        for r in all_rules:
            # Fix for marks_system_id=0: Try to resolve from marks_system table
            if not r['marks_system_id'] or r['marks_system_id'] == 0:
                # Priority 1: Match by Code
                ms_query = text("SELECT id FROM marks_system WHERE academic_id=:aid AND program_id=:pid AND grade_group_id=:ggid AND marks_code=:code LIMIT 1")
                found = db.execute(ms_query, {"aid": academic_id, "pid": program_id, "ggid": grade_group_id, "code": r['sign_code']}).fetchone()
                
                if found:
                    r['marks_system_id'] = found[0]
                else:
                    # Priority 2: Match by Name
                    ms_name_query = text("SELECT id FROM marks_system WHERE academic_id=:aid AND program_id=:pid AND grade_group_id=:ggid AND marks_name=:name LIMIT 1")
                    found_name = db.execute(ms_name_query, {"aid": academic_id, "pid": program_id, "ggid": grade_group_id, "name": r['result_name']}).fetchone()
                    if found_name:
                        r['marks_system_id'] = found_name[0]
            
            # Use a composite key for uniqueness if MS_ID is still 0 (fallback)
            unique_key = r['marks_system_id'] if r['marks_system_id'] else r['sign_code']
            
            if unique_key not in seen_ms_ids:
                seen_ms_ids.add(unique_key)
                rules.append(r)
        
        if not rules: return []

        # Extract all potential keys (Codes or IDs) from formulas
        all_exam_keys_codes = set()
        all_exam_keys_ids = set()
        
        for r in rules:
             formula = r['formula_expression'] or ""
             # Find alphanumeric codes
             codes = re.findall(r'[A-Za-z]+[0-9]*', formula)
             all_exam_keys_codes.update(codes)
             # Find standalone numbers
             ids = re.findall(r'\b\d+\b', formula)
             all_exam_keys_ids.update(int(i) for i in ids)

        if not all_exam_keys_codes and not all_exam_keys_ids: return []

        # Resolve Codes -> marks_system_id
        code_to_sys_id_map = {}
        if all_exam_keys_codes:
            placeholders_codes = ','.join([f':c{i}' for i in range(len(all_exam_keys_codes))])
            params_codes = {f'c{i}': c for i, c in enumerate(all_exam_keys_codes)}
            params_codes.update({"aid": academic_id, "pid": program_id, "ggid": grade_group_id})
            
            # Filter by program_id and grade_group_id to resolve duplicate codes correctly
            code_query = text(f"""
                SELECT id, marks_code FROM marks_system 
                WHERE marks_code IN ({placeholders_codes}) 
                AND academic_id = :aid AND program_id = :pid AND grade_group_id = :ggid
            """)
            code_result = db.execute(code_query, params_codes).fetchall()
            code_to_sys_id_map = {str(row[1]).upper(): row[0] for row in code_result if row[1]}
            # Fallback: resolve any missing codes via exam_calculate_sign (when marks_system.marks_code is null)
            missing_codes = [c for c in all_exam_keys_codes if str(c).upper() not in code_to_sys_id_map]
            if missing_codes:
                ph = ','.join([f':mc{i}' for i in range(len(missing_codes))])
                mc_params = {f'mc{i}': str(c).upper() for i, c in enumerate(missing_codes)}
                mc_params.update({"aid": academic_id, "pid": program_id, "ggid": grade_group_id})
                ecs_code_query = text(f"""
                    SELECT UPPER(sign_code), marks_system_id FROM exam_calculate_sign
                    WHERE UPPER(sign_code) IN ({ph})
                    AND academic_id = :aid AND program_id = :pid AND grade_group_id = :ggid
                    AND marks_system_id IS NOT NULL AND marks_system_id != 0
                """)
                ecs_result = db.execute(ecs_code_query, mc_params).fetchall()
                for row in ecs_result:
                    if row[0] and row[1]:
                        code_to_sys_id_map[str(row[0]).upper()] = row[1]
        
        # Resolve IDs (legacy exam_calculate_sign IDs) -> marks_system_id
        id_to_sys_id_map = {}
        if all_exam_keys_ids:
            placeholders_ids = ','.join([f':id{i}' for i in range(len(all_exam_keys_ids))])
            params_ids = {f'id{i}': i_val for i, i_val in enumerate(all_exam_keys_ids)}
            id_query = text(f"SELECT id, marks_system_id FROM exam_calculate_sign WHERE id IN ({placeholders_ids})")
            id_result = db.execute(id_query, params_ids).fetchall()
            id_to_sys_id_map = {row[0]: row[1] for row in id_result}

        # Collect all unique marks_system_ids needed
        all_system_ids = list(set(code_to_sys_id_map.values()) | set(id_to_sys_id_map.values()))
        if not all_system_ids:
            return []
        
        # Get Monthly Averages
        placeholders_sys = ','.join([f':sid{i}' for i in range(len(all_system_ids))])
        monthly_avg_params = {f'sid{i}': sid for i, sid in enumerate(all_system_ids)}
        monthly_avg_params.update({
            "student_id": student_id, "aid": academic_id, "pid": program_id, "ggid": grade_group_id
        })
        
        # ORDER BY id DESC so first occurrence per marks_system_id = latest (handles duplicates)
        monthly_avg_query = text(f"""
            SELECT exam_name, average, id, marks_system_id 
            FROM marks_monthly 
            WHERE student_id = :student_id 
            AND academic_id = :aid AND program_id = :pid AND grade_group_id = :ggid 
            AND marks_system_id IN ({placeholders_sys})
            ORDER BY id DESC
        """)
        monthly_avg_result = db.execute(monthly_avg_query, monthly_avg_params).fetchall()
        
        # Deduplicate by marks_system_id - keep LATEST (highest id, first after ORDER BY id DESC)
        monthly_data_by_sys_id = {}
        for row in monthly_avg_result:
            sys_id = row[3]
            if sys_id not in monthly_data_by_sys_id:
                monthly_data_by_sys_id[sys_id] = {
                    'average': safe_decimal(row[1], Decimal('0.0')),
                    'id': row[2],
                    'exam_name': row[0]
                }
        if len(monthly_avg_result) > len(monthly_data_by_sys_id):
            logger.warning(
                f"DUPLICATE marks_monthly in Semester Flow for student {student_id}: "
                f"{len(monthly_avg_result)} rows -> {len(monthly_data_by_sys_id)} unique (kept latest per marks_system_id)"
            )

        # Helper to get average by Key (Code or ID)
        def get_monthly_data_by_key(key):
            sys_id = code_to_sys_id_map.get(str(key).upper())
            if not sys_id:
                try:
                    sys_id = id_to_sys_id_map.get(int(key))
                except (ValueError, TypeError):
                    pass
            if sys_id and sys_id in monthly_data_by_sys_id:
                return monthly_data_by_sys_id[sys_id]
            return None

        # --- PROCESS EACH RULE ---
        for rule in rules:
            updated_semester_exam_ids.append(rule['id'])
            exam_name = rule['result_name']
            sign_code = rule['sign_code']
            divide_by_multiplier = safe_decimal(rule['divide_by_multiplier'], Decimal('1.0'))
            
            # Check existing record - ORDER BY id DESC to get latest if duplicates exist
            existing_query = text("""
                SELECT ms.id 
                FROM marks_semester ms
                JOIN exam_calculate_sign ecs ON ecs.result_name = ms.exam_name 
                    AND ecs.academic_id = ms.academic_id 
                    AND ecs.program_id = ms.program_id 
                    AND ecs.grade_group_id = ms.grade_group_id 
                    AND ecs.sign_code = :sign_code
                WHERE ms.student_id = :student_id 
                AND ms.academic_id = :aid 
                AND ms.program_id = :pid 
                AND ms.grade_group_id = :ggid
                ORDER BY ms.id DESC
                LIMIT 1
            """)
            existing_params = {
                "sign_code": sign_code, "student_id": student_id, 
                "aid": academic_id, "pid": program_id, "ggid": grade_group_id
            }
            existing_record = db.execute(existing_query, existing_params).fetchone()
            
            if not existing_record:
                # Fallback to name match (ORDER BY id DESC for duplicate safety)
                fallback_query = text("""
                    SELECT id FROM marks_semester 
                    WHERE student_id = :student_id AND academic_id = :aid 
                    AND program_id = :pid AND grade_group_id = :ggid 
                    AND exam_name = :exam_name
                    ORDER BY id DESC
                    LIMIT 1
                """)
                existing_record = db.execute(fallback_query, {**existing_params, "exam_name": exam_name}).fetchone()

            # Default max
            target_scale_max = get_max_scale_score(db, academic_id, grade_group_id)

            marks_monthly_ids_str = ""
            final_total = Decimal('0')
            final_average = Decimal('0')

            if mark_type in ['en', 'iep']:
                # EN/IEP Subject-Average Calculation Logic
                formula_str = rule['formula_expression'] or ""
                formula_str_clean = formula_str.replace('(', '').replace(')', '').strip()
                tokens = re.findall(r'[A-Za-z]+[0-9]*|\b\d+\b', formula_str_clean)
                
                if not tokens: continue

                month_system_ids = []
                for token in tokens:
                    # Resolve to marks_system_id
                    sys_id = code_to_sys_id_map.get(str(token).upper())
                    if not sys_id:
                        try:
                            sys_id = id_to_sys_id_map.get(int(token))
                        except: pass
                    if sys_id:
                        month_system_ids.append(int(sys_id))
                month_system_ids = list(dict.fromkeys(month_system_ids))

                if not month_system_ids: continue

                # Expected months
                try:
                    expected_months = int(divide_by_multiplier)
                except:
                    expected_months = 0
                if expected_months <= 0:
                    expected_months = len(month_system_ids)

                # Active months count
                placeholders_ms = ','.join([f':ms{i}' for i in range(len(month_system_ids))])
                ms_params = {f'ms{i}': ms for i, ms in enumerate(month_system_ids)}
                ms_params.update({"sid": student_id, "aid": academic_id})
                
                active_months_query = text(f"""
                    SELECT marks_system_id, COUNT(*) 
                    FROM marks_input 
                    WHERE student_id = :sid AND academic_id = :aid 
                    AND marks_system_id IN ({placeholders_ms}) 
                    GROUP BY marks_system_id
                """)
                active_months_result = db.execute(active_months_query, ms_params).fetchall()
                active_month_system_ids = {int(r[0]) for r in active_months_result}
                
                # Load subjects
                subjects_query = text("SELECT subject_id, full_marks FROM subjects_group WHERE academic_id=:aid AND program_id=:pid AND grade_group_id=:ggid")
                subjects_result = db.execute(subjects_query, {"aid": academic_id, "pid": program_id, "ggid": grade_group_id}).fetchall()
                subject_ids = [int(r[0]) for r in subjects_result]
                subject_full_marks = {int(r[0]): safe_decimal(r[1], Decimal('100.0')) for r in subjects_result}
                
                if not subject_ids: continue

                # Calculate per-subject averages
                placeholders_subj = ','.join([f':subj{i}' for i in range(len(subject_ids))])
                subj_params = {f'subj{i}': s for i, s in enumerate(subject_ids)}
                # Combine params (careful with name collisions - used distinct prefixes)
                # Re-using ms_params for month ids
                
                combined_params = {
                     **ms_params, 
                     **subj_params, 
                     "pid": program_id, 
                     "ggid": grade_group_id
                }
                
                # CRITICAL: Fetch Raw Marks for In-Memory Deduplication
                # Removing SUM(marks) to prevent inflation from duplicates
                per_subject_query = text(f"""
                    SELECT subject_id, marks, marks_system_id, id, updated_at
                    FROM marks_input
                    WHERE student_id = :sid 
                    AND academic_id = :aid AND program_id = :pid AND grade_group_id = :ggid 
                    AND marks_system_id IN ({placeholders_ms})
                    AND subject_id IN ({placeholders_subj})
                    ORDER BY id DESC
                """)
                per_subject_result = db.execute(per_subject_query, combined_params).fetchall()
                
                # Deduplicate: Key by (subject_id, marks_system_id) -> Keep Latest
                unique_inputs = {}
                for row in per_subject_result:
                    key = (row[0], row[2]) # (subject_id, marks_system_id)
                    if key not in unique_inputs:
                        unique_inputs[key] = row
                
                # Aggregate Deduplicated Data
                per_subject_data = {} # subject_id -> {total_marks, months_count}
                for (sub_id, ms_id), row in unique_inputs.items():
                    if sub_id not in per_subject_data:
                        per_subject_data[sub_id] = {'total': Decimal('0'), 'months': 0}
                    
                    per_subject_data[sub_id]['total'] += safe_decimal(row[1])
                    per_subject_data[sub_id]['months'] += 1

                subject_total = Decimal('0')
                missing_subjects = 0
                
                for sid in subject_ids:
                    # Get aggregated data for this subject
                    data = per_subject_data.get(sid)
                    
                    if not data:
                        missing_subjects += 1
                        continue
                    
                    subj_sum = data['total']
                    months_with_marks = data['months']
                    
                    if months_with_marks <= 0:
                        missing_subjects += 1
                        continue
                        
                    subj_missing_months = max(0, expected_months - months_with_marks)
                    
                    # SAFETY CLAMP REMOVED: User requested strict adherence to divide_by_multiplier logic
                    # calculated_divisor = expected_months - subj_missing_months
                    # Logic: divisor = expected - missing. Even if it is < months_with_marks, we use it.
                    subj_divisor = expected_months - subj_missing_months
                    
                    if subj_divisor < 1: subj_divisor = Decimal('1')
                    
                    subj_avg = subj_sum / subj_divisor
                    subject_total += subj_avg
                
                final_total = subject_total
                effective_subject_divisor = len(subject_ids) - missing_subjects
                if effective_subject_divisor < 1: effective_subject_divisor = 1
                
                final_average = final_total / Decimal(str(effective_subject_divisor))
                
                # Scaling
                total_full = sum(subject_full_marks.get(sid, Decimal('100.0')) for sid in subject_ids)
                max_possible_avg = total_full / Decimal(str(effective_subject_divisor)) if effective_subject_divisor > 0 else Decimal('100.0')
                
                if max_possible_avg > 0 and target_scale_max:
                    final_average = (final_average / max_possible_avg) * target_scale_max

                # Collect monthly IDs for junction
                monthly_ids_used = []
                for ms_id in active_month_system_ids:
                     # Find marks_monthly id
                     mm_query = text("SELECT id FROM marks_monthly WHERE student_id=:sid AND marks_system_id=:msid AND academic_id=:aid LIMIT 1")
                     mm_res = db.execute(mm_query, {"sid": student_id, "msid": ms_id, "aid": academic_id}).fetchone()
                     if mm_res: monthly_ids_used.append(str(mm_res[0]))
                marks_monthly_ids_str = ",".join(monthly_ids_used)
                
                # Logic for EN/IEP Deletion check
                if not monthly_ids_used and existing_record:
                     # Delete logic for EN/IEP if NO VALID MONTHS found
                     logger.info(f"Student {student_id} has NO valid months for Semester {exam_name} (EN/IEP). Deleting record.")
                     marks_semester_id = existing_record[0]
                     db.execute(text("DELETE FROM marks_semester_monthlies WHERE marks_semester_id = :sid"), {"sid": marks_semester_id})
                     db.execute(text("DELETE FROM marks_semester WHERE id = :id"), {"id": marks_semester_id})
                     updated_semester_exam_ids.append(-1)
                     continue

            elif mark_type == 'other':
                # 'OTHER' Logic: Sum(Monthly Averages) / (Expected - Missing)
                formula_str = rule['formula_expression'] or ""
                formula_str_clean = formula_str.replace('(', '').replace(')', '').strip()
                tokens = re.findall(r'[A-Za-z]+[0-9]*|\b\d+\b', formula_str_clean)
                
                if not tokens: continue
                
                total_monthly_sum = Decimal('0')
                missing_months_count = 0
                monthly_ids_used = []
                
                for token in tokens:
                    data = get_monthly_data_by_key(token)
                    if data and data.get('average') is not None:
                        total_monthly_sum += safe_decimal(data['average'])
                        monthly_ids_used.append(str(data['id']))
                    else:
                        missing_months_count += 1
                        
                # Dynamic divisor
                if divide_by_multiplier <= 0: divide_by_multiplier = Decimal(len(tokens))
                effective_divisor = divide_by_multiplier - Decimal(missing_months_count)
                if effective_divisor < 1: effective_divisor = Decimal('1')
                
                final_total = total_monthly_sum
                final_average = total_monthly_sum / effective_divisor
                marks_monthly_ids_str = ",".join(monthly_ids_used)

            else:
                # KHMER Logic with Nested Formula Fix
                # Formula Example: (MON1+MON2+MON3+MON4+MON5)+SEM1
                formula = rule['formula_expression'] or ""
                
                # Check for parenthesis group
                grouped_part = re.search(r'\((.*?)\)', formula)
                
                grouped_keys = []
                standalone_keys = []
                
                if grouped_part:
                    content = grouped_part.group(1)
                    # Extract keys inside ( ... )
                    grouped_keys = list(dict.fromkeys(
                        re.findall(r'[A-Za-z]+[0-9]*', content) + re.findall(r'\b\d+\b', content)
                    ))
                    
                    # Remove the group from formula to find standalone parts
                    standalone_str = formula.replace(grouped_part.group(0), '').replace('+', ' ').strip()
                    standalone_keys = list(dict.fromkeys(
                        re.findall(r'[A-Za-z]+[0-9]*', standalone_str) + re.findall(r'\b\d+\b', standalone_str)
                    ))
                else:
                    # No grouping, treat all as standalone/flat or handle as simple sum if needed.
                    # Standard KH usually has grouping for months. If not, fallback to treating all as linear.
                    grouped_keys = []
                    standalone_keys = list(dict.fromkeys(
                        re.findall(r'[A-Za-z]+[0-9]*', formula) + re.findall(r'\b\d+\b', formula)
                    ))
                
                # Filter out empty keys
                grouped_keys = [k for k in grouped_keys if k]
                standalone_keys = [k for k in standalone_keys if k]

                # Fetch Data
                grouped_data = [get_monthly_data_by_key(k) for k in grouped_keys]
                standalone_data = [get_monthly_data_by_key(k) for k in standalone_keys]
                
                # Calculate Group Average
                # Only include valid data points (average > 0) for the calculation.
                # A zero average means the month was either not entered or is a stale bad record.
                valid_grouped_avgs = [
                    safe_decimal(d['average']) 
                    for d in grouped_data 
                    if d and safe_decimal(d.get('average', 0)) > 0
                ]
                avg_of_group = sum(valid_grouped_avgs) / Decimal(len(valid_grouped_avgs)) if valid_grouped_avgs else Decimal('0')
                
                # Calculate Standalone Sum (usually just SEM1 exam)
                # Only include if average > 0 (a zero means no exam marks entered yet)
                valid_standalone_avgs = [
                    safe_decimal(d['average']) 
                    for d in standalone_data 
                    if d and safe_decimal(d.get('average', 0)) > 0
                ]
                standalone_total_sum = sum(valid_standalone_avgs)
                
                final_total = avg_of_group + standalone_total_sum
                
                # Divisor Logic (Standard KH = 2)
                base_divisor = divide_by_multiplier
                if base_divisor <= 0:
                    # Auto-detect divisor based on structure
                    if grouped_keys and standalone_keys: 
                        base_divisor = Decimal('2.0')
                    elif grouped_keys or standalone_keys:
                        base_divisor = Decimal('1.0')
                    else:
                        base_divisor = Decimal('1.0') 
                
                # Dynamic Divisor Adjustment
                # Reduce by 1 if the ENTIRE group has no valid (non-zero) marks
                missing_components = 0
                if grouped_keys and not valid_grouped_avgs: 
                    missing_components += 1
                
                # Reduce by 1 if the ENTIRE standalone marks are missing (e.g. SEM1 not entered yet)
                if standalone_keys and not valid_standalone_avgs: 
                    missing_components += 1
                
                effective_divisor = base_divisor - Decimal(missing_components)
                if effective_divisor < 1: effective_divisor = Decimal('1')
                
                final_average = final_total / effective_divisor
                
                # IDs — Only include monthly IDs where average > 0 (real data)
                all_keys = grouped_keys + standalone_keys
                monthly_ids_list = []
                for k in all_keys:
                    d = get_monthly_data_by_key(k)
                    if d and safe_decimal(d.get('average', 0)) > 0:
                        monthly_ids_list.append(str(d['id']))
                marks_monthly_ids_str = ",".join(monthly_ids_list)

            # Check if all components are missing
            if final_total == 0 and final_average == 0 and not marks_monthly_ids_str:
                # Assuming this means NO data was found (careful with legitimate 0s)
                # Better check: Are there any monthly IDs?
                # For KH: we relied on `get_monthly_data_by_key` usage.
                # Let's check if we actually found any valid monthly records
                 if not marks_monthly_ids_str and not existing_record:
                     # Nothing to save and nothing exists.
                     continue
                 
                 if not marks_monthly_ids_str and existing_record:
                     # WE HAVE AN EXISTING RECORD BUT NO SOURCES NOW (e.g. User deleted all months)
                     # DELETE IT
                     logger.info(f"Student {student_id} has NO source marks for Semester {exam_name}. Deleting record.")
                     marks_semester_id = existing_record[0]
                     db.execute(text("DELETE FROM marks_semester_monthlies WHERE marks_semester_id = :sid"), {"sid": marks_semester_id})
                     db.execute(text("DELETE FROM marks_semester WHERE id = :id"), {"id": marks_semester_id})
                     updated_semester_exam_ids.append(-1)
                     continue

            # Check if source data is missing
            if not marks_monthly_ids_str and not existing_record:
                continue
            
            if not marks_monthly_ids_str and existing_record:
                # DELETE Semester Record
                logger.info(f"Student {student_id} has NO source marks for Semester {exam_name}. Deleting record.")
                marks_semester_id = existing_record[0]
                db.execute(text("DELETE FROM marks_semester_monthlies WHERE marks_semester_id = :sid"), {"sid": marks_semester_id})
                db.execute(text("DELETE FROM marks_semester WHERE id = :id"), {"id": marks_semester_id})
                updated_semester_exam_ids.append(-1)
                continue

            # --- STORE RESULT ---
            # Rounding
            final_total = round_decimal_to_2_places(final_total)
            final_average = round_decimal_to_2_places(final_average)
            
            grade_scale_id = get_grade_scale_id_raw(
                db, final_average, academic_id, program_id, grade_group_id, max_possible_score=target_scale_max
            )
            
            marks_system_id_val = int(rule.get('marks_system_id') or 0)
            
            # Use marks_semester_monthlies junction table only (match kortra - no marks_imonthly_ids legacy column)
            marks_semester_id = None
            if existing_record:
                marks_semester_id = existing_record[0]
                update_q = text("""
                    UPDATE marks_semester 
                    SET marks_system_id=:msid, grade_id=:gid, total=:tot, average=:avg, grade_scale_id=:gsid, updated_at=NOW() 
                    WHERE id=:id
                """)
                db.execute(update_q, {
                    "msid": marks_system_id_val, "gid": grade_id, "tot": final_total, "avg": final_average, 
                    "gsid": grade_scale_id, "id": marks_semester_id
                })
            else:
                insert_q = text("""
                    INSERT INTO marks_semester 
                    (exam_name, student_id, program_id, grade_id, grade_group_id, academic_id, marks_system_id, total, average, grade_scale_id, created_at, updated_at)
                    VALUES 
                    (:exam, :sid, :pid, :gid, :ggid, :aid, :msid, :tot, :avg, :gsid, NOW(), NOW())
                """)
                db.execute(insert_q, {
                    "exam": exam_name, "sid": student_id, "pid": program_id, "gid": grade_id, "ggid": grade_group_id, "aid": academic_id,
                    "msid": marks_system_id_val, "tot": final_total, "avg": final_average, "gsid": grade_scale_id
                })
                # Get ID
                res = db.execute(text("SELECT LAST_INSERT_ID()")).fetchone()
                if res: marks_semester_id = res[0]
            
            # Update Junction Table (marks_semester_monthlies)
            if marks_semester_id and marks_monthly_ids_str:
                db.execute(text("DELETE FROM marks_semester_monthlies WHERE marks_semester_id = :sid"), {"sid": marks_semester_id})
                m_ids = [int(mid) for mid in marks_monthly_ids_str.split(',') if mid]
                if m_ids:
                    # Build parameterized query with unique placeholders for each value
                    vals = []
                    item_params = {}
                    for i, mid in enumerate(m_ids):
                        vals.append(f"(:marks_semester_id_{i}, :marks_monthly_id_{i}, NOW(), NOW())")
                        item_params[f"marks_semester_id_{i}"] = marks_semester_id
                        item_params[f"marks_monthly_id_{i}"] = mid

                    # Execute with parameterized query (prevents SQL injection)
                    db.execute(text(f"INSERT INTO marks_semester_monthlies (marks_semester_id, marks_monthly_id, created_at, updated_at) VALUES {','.join(vals)}"), item_params)

        if auto_commit:
            db.commit()
            
    except Exception as e:
        if auto_commit: db.rollback()
        logger.error(f"Error in calculate_and_store_semester_marks: {e}", exc_info=True)
        raise
        
    return updated_semester_exam_ids


def calculate_and_store_yearly_marks(
    db: Session,
    student_id: int,
    program_id: int,
    grade_id: int,
    grade_group_id: int,
    academic_id: int,
    triggered_by_semester_ids: Optional[List[int]] = None,
    auto_commit: bool = True
) -> List[int]:
    """
    Calculate and store yearly marks for a student.
    Exact implementation matching Telegram bot's yearly_flow.py.
    Returns list of marks_yearly IDs that were created/updated.
    """
    updated_yearly_ids = []
    try:
        # Note: Transaction is managed by the calling function
        
        # Get program mark_type
        program_query = text("SELECT mark_type FROM program WHERE id = :pid")
        program_result = db.execute(program_query, {"pid": program_id}).fetchone()
        mark_type = program_result[0] if program_result else 'kh'
        
        # English programs check
        if mark_type == 'en':
            yearly_count_q = text("""
                SELECT COUNT(*) FROM exam_calculate_sign 
                WHERE academic_id=:aid AND program_id=:pid AND grade_group_id=:ggid 
                AND sign_code='YEAR' AND is_active=1
            """)
            count_res = db.execute(yearly_count_q, {"aid": academic_id, "pid": program_id, "ggid": grade_group_id}).fetchone()
            if not count_res or count_res[0] == 0:
                logger.info(f"No yearly calculation rules for English program {program_id}, skipping.")
                return []
        
        # Get divide_by_multiplier
        div_q = text("""
            SELECT divide_by_multiplier FROM exam_calculate_sign 
            WHERE academic_id=:aid AND program_id=:pid AND grade_group_id=:ggid 
            AND sign_code='YEAR' AND is_active=1 LIMIT 1
        """)
        div_res = db.execute(div_q, {"aid": academic_id, "pid": program_id, "ggid": grade_group_id}).fetchone()
        
        if not div_res:
            logger.warning(f"No yearly calculation configuration found for {program_id}/{grade_group_id}/{academic_id}")
            return []
            
        divide_by_multiplier = safe_decimal(div_res[0], Decimal('1.0'))
        
        # Build rules query - always get ALL YEAR rules (no REGEXP filter)
        # This ensures yearly runs even when only RSEM1 or only RSEM2 has data
        rules_query = text("""
            SELECT id, result_name, formula_expression, marks_system_id 
            FROM exam_calculate_sign 
            WHERE academic_id = :aid AND program_id = :pid AND grade_group_id = :ggid 
            AND sign_code = 'YEAR' AND is_active = 1
        """)
        rules_params = {"aid": academic_id, "pid": program_id, "ggid": grade_group_id}
        rules_result = db.execute(rules_query, rules_params).fetchall()
        all_rules = []
        for r in rules_result:
            all_rules.append({
                'id': r[0], 'result_name': r[1], 'formula_expression': r[2], 'marks_system_id': r[3]
            })

        # STRICT DUPLICATE PREVENTION:
        seen_ms_ids = set()
        rules = []
        for r in all_rules:
            if r['marks_system_id'] not in seen_ms_ids:
                seen_ms_ids.add(r['marks_system_id'])
                rules.append(r)
        
        if not rules: return []

        # Extract all potential keys (Codes) from formulas
        all_sem_keys_codes = set()
        for r in rules:
             codes = re.findall(r'[A-Za-z]+[0-9]*', r['formula_expression'] or "")
             all_sem_keys_codes.update(codes)

        if not all_sem_keys_codes: return []

        # Resolve Sign Code (RSEM1) -> Result Name
        code_to_name_map = {}
        placeholders_codes = ','.join([f':c{i}' for i in range(len(all_sem_keys_codes))])
        params_codes = {f'c{i}': c for i, c in enumerate(all_sem_keys_codes)}
        params_codes.update({"aid": academic_id, "pid": program_id, "ggid": grade_group_id})
        
        name_query = text(f"""
            SELECT sign_code, result_name FROM exam_calculate_sign 
            WHERE sign_code IN ({placeholders_codes}) 
            AND academic_id=:aid AND program_id=:pid AND grade_group_id=:ggid
        """)
        name_res = db.execute(name_query, params_codes).fetchall()
        code_to_name_map = {str(row[0]).upper(): row[1] for row in name_res}

        # Retrieve Semester Results - ORDER BY id DESC to keep latest if duplicates exist
        semester_avg_query = text(f"""
            SELECT ms.exam_name, ms.average, ms.id 
            FROM marks_semester ms
            JOIN exam_calculate_sign ecs ON ecs.result_name = ms.exam_name 
                AND ecs.academic_id = ms.academic_id 
                AND ecs.program_id = ms.program_id 
                AND ecs.grade_group_id = ms.grade_group_id 
                AND ecs.sign_code IN ({placeholders_codes})
            WHERE ms.student_id = :sid 
            AND ms.academic_id = :aid AND ms.program_id = :pid AND ms.grade_group_id = :ggid
            ORDER BY ms.id DESC
        """)
        sem_params = params_codes.copy()
        sem_params.update({"sid": student_id})
        
        sem_res = db.execute(semester_avg_query, sem_params).fetchall()
        # Deduplicate by exam_name - keep latest (first after ORDER BY id DESC)
        semester_data_by_name = {}
        for row in sem_res:
            if row[0] not in semester_data_by_name:
                avg_val = safe_decimal(row[1], Decimal('0.0'))
                # Treat null/zero averages as missing (do not count towards divisor)
                if avg_val > 0:
                    semester_data_by_name[row[0]] = {'average': avg_val, 'id': row[2]}

        def get_semester_data_by_key(key):
            target_name = code_to_name_map.get(str(key).upper())
            if target_name and target_name in semester_data_by_name:
                return semester_data_by_name[target_name]
            return None

        for rule in rules:
            exam_name = rule['result_name']
            formula = rule['formula_expression'] or ""
            marks_system_id_value = int(rule.get('marks_system_id') or 0)
            
            semester_keys = re.findall(r'[A-Za-z]+[0-9]*', formula) + re.findall(r'\b\d+\b', formula)
            
            results_found = []
            for key in semester_keys:
                d = get_semester_data_by_key(key)
                if d: results_found.append(d)
                
            # Dynamic Divisor Logic (UNIVERSAL)
            # For YEAR, use divide_by_multiplier as the expected number of semesters.
            # Missing semesters = expected (divide_by_multiplier) - actually found (with avg > 0).
            found_count = len(results_found)
            try:
                expected_semesters = int(divide_by_multiplier) if divide_by_multiplier > 0 else len(semester_keys)
            except (InvalidOperation, ValueError, TypeError):
                expected_semesters = len(semester_keys)
            if expected_semesters < 0:
                expected_semesters = 0
            missing_count = max(0, expected_semesters - found_count)
            
            final_total = sum(r['average'] for r in results_found) if results_found else Decimal('0')
            
            # SAFETY CLAMP REMOVED: User requested strict adherence to divide_by_multiplier logic
            # Use divide_by_multiplier as base, subtract missing.
            # Even if result < found_count, we use it (allows inflation if configured).
            adjusted_div = divide_by_multiplier - Decimal(missing_count)
            if adjusted_div < 1: adjusted_div = Decimal('1')
            
            final_average = final_total / adjusted_div if adjusted_div > 0 else Decimal('0')
            
            # Check existing record (YEAR) - ORDER BY id DESC for duplicate safety
            existing_query = text("""
                SELECT my.id 
                FROM marks_yearly my
                JOIN exam_calculate_sign ecs ON ecs.result_name = my.exam_name 
                    AND ecs.academic_id = my.academic_id 
                    AND ecs.program_id = my.program_id 
                    AND ecs.grade_group_id = my.grade_group_id 
                    AND ecs.sign_code = 'YEAR'
                WHERE my.student_id = :sid 
                AND my.academic_id = :aid AND my.program_id = :pid AND my.grade_group_id = :ggid
                ORDER BY my.id DESC
                LIMIT 1
            """)
            ex_params = {"sid": student_id, "aid": academic_id, "pid": program_id, "ggid": grade_group_id}
            existing_record = db.execute(existing_query, ex_params).fetchone()
            
            if not existing_record:
                fallback_query = text("""
                    SELECT id FROM marks_yearly 
                    WHERE student_id=:sid AND academic_id=:aid AND program_id=:pid AND grade_group_id=:ggid 
                    AND exam_name=:name
                    ORDER BY id DESC
                    LIMIT 1
                """)
                existing_record = db.execute(fallback_query, {**ex_params, "name": exam_name}).fetchone()

            # Max Possible Average
            max_possible_grading = get_max_scale_score(db, academic_id, grade_group_id)
            
            if mark_type in ['en', 'iep']:
                # For IEP/EN, avg of full_marks of all subjects
                max_score_q = text("""
                    SELECT AVG(sg.full_marks)
                    FROM marks_input mi
                    JOIN subjects_group sg ON mi.subject_id = sg.subject_id
                    WHERE mi.student_id = :sid AND mi.academic_id = :aid
                    AND sg.academic_id = :aid AND sg.program_id = :pid AND sg.grade_group_id = :ggid
                """)
                max_res = db.execute(max_score_q, {"sid": student_id, "aid": academic_id, "pid": program_id, "ggid": grade_group_id}).fetchone()
                if max_res and max_res[0]:
                    max_possible_grading = safe_decimal(max_res[0], Decimal('100.0'))

            # Scaling
            target_scale_max = get_max_scale_score(db, academic_id, grade_group_id)
            if max_possible_grading > 0:
                final_average = (final_average / max_possible_grading) * target_scale_max
            
            # Rounding
            final_total = round_decimal_to_2_places(final_total)
            final_average = round_decimal_to_2_places(final_average)
            
            grade_scale_id = get_grade_scale_id_raw(
                db, final_average, academic_id, program_id, grade_group_id, max_possible_score=target_scale_max
            )
            
            marks_yearly_id = None
            if existing_record:
                marks_yearly_id = existing_record[0]
                update_q = text("""
                    UPDATE marks_yearly 
                    SET marks_system_id=:msid, total=:tot, average=:avg, grade_scale_id=:gsid, grade_id=:gid, updated_at=NOW() 
                    WHERE id=:id
                """)
                db.execute(update_q, {
                    "msid": marks_system_id_value, "tot": final_total, "avg": final_average, 
                    "gsid": grade_scale_id, "gid": grade_id, "id": marks_yearly_id
                })
            else:
                insert_q = text("""
                    INSERT INTO marks_yearly 
                    (exam_name, student_id, program_id, grade_id, grade_group_id, academic_id, marks_system_id, total, average, grade_scale_id) 
                    VALUES 
                    (:name, :sid, :pid, :gid, :ggid, :aid, :msid, :tot, :avg, :gsid)
                """)
                db.execute(insert_q, {
                    "name": exam_name, "sid": student_id, "pid": program_id, "gid": grade_id, "ggid": grade_group_id, "aid": academic_id,
                    "msid": marks_system_id_value, "tot": final_total, "avg": final_average, "gsid": grade_scale_id
                })
                res = db.execute(text("SELECT LAST_INSERT_ID()")).fetchone()
                if res: marks_yearly_id = res[0]
            
            updated_yearly_ids.append(rule['id']) # Or marks_yearly_id? Original code appended rule ID (legacy quirk). Let's stick to it.
            
            # Junction Logic: marks_yearly_semesters (Smart Sync)
            if marks_yearly_id:
                new_sem_ids = {r['id'] for r in results_found}
                
                # Get Existing
                ex_links_q = text("SELECT marks_semester_id FROM marks_yearly_semesters WHERE marks_yearly_id = :mid")
                ex_links_res = db.execute(ex_links_q, {"mid": marks_yearly_id}).fetchall()
                existing_sem_ids = {r[0] for r in ex_links_res}
                
                to_insert = new_sem_ids - existing_sem_ids
                to_delete = existing_sem_ids - new_sem_ids
                
                if to_delete:
                    # Build parameterized DELETE with unique placeholders (prevents SQL injection)
                    del_ph = ','.join([f':delete_id_{i}' for i in range(len(to_delete))])
                    del_p = {f'delete_id_{i}': d for i, d in enumerate(to_delete)}
                    del_p['marks_yearly_id'] = marks_yearly_id
                    db.execute(text(f"DELETE FROM marks_yearly_semesters WHERE marks_yearly_id = :marks_yearly_id AND marks_semester_id IN ({del_ph})"), del_p)

                if to_insert:
                    # Build parameterized INSERT with unique placeholders (prevents SQL injection)
                    ins_vals = []
                    ins_p = {'marks_yearly_id': marks_yearly_id}
                    for i, ins in enumerate(to_insert):
                        ins_vals.append(f"(:marks_yearly_id, :insert_id_{i})")
                        ins_p[f'insert_id_{i}'] = ins
                    if ins_vals:
                        db.execute(text(f"INSERT INTO marks_yearly_semesters (marks_yearly_id, marks_semester_id) VALUES {','.join(ins_vals)}"), ins_p)

        if auto_commit:
            db.commit()
            
    except Exception as e:
        if auto_commit: db.rollback()
        logger.error(f"Error in calculate_and_store_yearly_marks for student {student_id}: {e}", exc_info=True)
        raise
    
    return updated_yearly_ids
