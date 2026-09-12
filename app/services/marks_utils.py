import logging
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from sqlalchemy import text

logger = logging.getLogger(__name__)

INPUT_MONTHLY_SIGN_CODES = {"MON1", "MON2", "MON3", "MON4", "MON5", "MON6", "MON7", "MON8"}
INPUT_SUBJECTS_FORMULA_REFERENCE = "exam_calculate_sign_subjects"

# Exams that can use `exam_calculate_sign_subjects` as their subject source.
# This includes the monthly inputs plus semester exam inputs (SEM1/SEM2) when configured the same way.
SUBJECTS_REFERENCE_EXAM_CODES = set(INPUT_MONTHLY_SIGN_CODES) | {"SEM1", "SEM2"}

def safe_decimal(value, default=Decimal('0.0')):
    """Safely converts a value to Decimal."""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default

def round_decimal_to_2_places(value: Decimal) -> Decimal:
    """Rounds a Decimal to 2 decimal places using ROUND_HALF_UP."""
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def format_number(value: Decimal) -> str:
    """Formats a decimal number to a string, removing trailing zeros if it's an integer."""
    if value == value.to_integral_value():
        return f"{value:.0f}"
    return f"{value:.2f}"

def get_exam_calculate_sign_subject_ids(db, exam_calculate_sign_id: int) -> list[int]:
    """
    Return subject IDs from exam_calculate_sign_subjects for a given exam_calculate_sign_id.
    """
    try:
        if not exam_calculate_sign_id:
            return []
        
        query = text("SELECT subject_id FROM exam_calculate_sign_subjects WHERE exam_calculate_sign_id = :ecs_id")
        result = db.execute(query, {"ecs_id": exam_calculate_sign_id}).fetchall()
        
        return [int(r[0]) for r in result if r[0] is not None]
    except Exception:
        return []

def get_input_monthly_subject_ids(db, details: dict) -> list[int]:
    """
    For exam_type='input' and sign_code MON1..MON8, prefer per-exam subjects stored in
    exam_calculate_sign_subjects. Returns [] when not applicable or no rows found.
    """
    try:
        exam_type = str(details.get("exam_type", "")).strip().lower()
        sign_code = str(details.get("sign_code", "")).strip().upper()
        
        if exam_type != "input" or sign_code not in SUBJECTS_REFERENCE_EXAM_CODES:
            return []

        # Prefer provided ID if available
        ecs_id = details.get("exam_calculate_sign_id") or details.get("ecs_id") or details.get("id")
        if ecs_id:
            ids = get_exam_calculate_sign_subject_ids(db, int(ecs_id))
            if ids:
                return ids

        # Otherwise resolve the config row ID (latest)
        academic_id = details.get("academic_id")
        program_id = details.get("program_id")
        grade_group_id = details.get("grade_group_id")
        marks_system_id = details.get("marks_system_id")
        
        if not (academic_id and program_id and grade_group_id and marks_system_id):
            return []

        query = text("""
            SELECT id
            FROM exam_calculate_sign
            WHERE academic_id = :academic_id 
            AND program_id = :program_id 
            AND grade_group_id = :grade_group_id
            AND marks_system_id = :marks_system_id 
            AND UPPER(sign_code) = :sign_code
            AND is_active = 1
            ORDER BY id DESC
            LIMIT 1
        """)
        
        result = db.execute(query, {
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_group_id": grade_group_id,
            "marks_system_id": marks_system_id,
            "sign_code": sign_code
        }).fetchone()
        
        ecs_id = result[0] if result else None
        if not ecs_id:
            return []
            
        return get_exam_calculate_sign_subject_ids(db, int(ecs_id))
    except Exception:
        return []

def validate_grade_scale_ranges(db, academic_id: int, grade_group_id: int):
    """
    Validates grade scale ranges and returns normalized min/max values (always 0-100) plus all scales.
    Returns (is_valid, min_val, max_val, scales_list)
    """
    try:
        query = text("""
            SELECT id, min_marks, max_marks FROM grade_scale
            WHERE academic_id = :academic_id AND grade_group_id = :grade_group_id
            ORDER BY min_marks
        """)
        result = db.execute(query, {
            "academic_id": academic_id, 
            "grade_group_id": grade_group_id
        }).fetchall()
        
        scales = [{'id': r[0], 'min_marks': r[1], 'max_marks': r[2]} for r in result]
        
        if not scales:
            logger.warning(f"No grade scales found for academic_id={academic_id}, grade_group_id={grade_group_id}")
            return False, Decimal('0'), Decimal('100'), []
        
        # Always normalize to 0-100 range
        normalized_min = Decimal('0')
        normalized_max = Decimal('100')
        
        return True, normalized_min, normalized_max, scales
        
    except Exception as e:
        logger.error(f"Error validating grade scale ranges: {e}")
        return False, Decimal('0'), Decimal('100'), []

def get_grade_scale_id_raw(db, raw_score: Decimal, academic_id: int, program_id: int, grade_group_id: int, max_possible_score: Decimal = Decimal('100.0')) -> int | None:
    """
    Fetches the grade scale ID by normalizing the raw score to a percentage relative to max_possible_score.
    """
    try:
        # Convert input to Decimal
        raw_score = Decimal(str(raw_score))
        if max_possible_score <= Decimal('0'):
            logger.warning(f"Invalid max_possible_score {max_possible_score}, defaulting to 100.0")
            max_possible_score = Decimal('100.0')

        # 1. Calculate Percentage (0-100)
        percentage = (raw_score / max_possible_score) * Decimal('100.0')
        
        # Clamp percentage to 0-100
        if percentage < Decimal('0'): percentage = Decimal('0')
        if percentage > Decimal('100'): percentage = Decimal('100')
        
        # 2. Get Grade Scales and Determine Target Range
        query = text("""
            SELECT id, min_marks, max_marks FROM grade_scale
            WHERE academic_id = :academic_id AND grade_group_id = :grade_group_id
            ORDER BY min_marks
        """)
        result = db.execute(query, {
            "academic_id": academic_id,
            "grade_group_id": grade_group_id
        }).fetchall()
        
        all_scales = [{'id': r[0], 'min_marks': r[1], 'max_marks': r[2]} for r in result]
        
        if not all_scales:
            logger.warning(f"No grade scales found for academic_id={academic_id}, grade_group_id={grade_group_id}")
            return None
            
        min_scale = min(Decimal(str(s['min_marks'])) for s in all_scales)
        max_scale = max(Decimal(str(s['max_marks'])) for s in all_scales)
        
        # 3. Map Percentage to Target Scale Range
        # Formula: (Percent / 100) * (Max - Min) + Min
        mapped_score = (percentage / Decimal('100.0')) * (max_scale - min_scale) + min_scale
        mapped_score = round_decimal_to_2_places(mapped_score)
        
        # 4. Find the matching ID for the MAPPED score
        matching_scale = next((s for s in all_scales if Decimal(str(s['min_marks'])) <= mapped_score <= Decimal(str(s['max_marks']))), None)
        
        if matching_scale:
            return matching_scale['id']
            
        # Fallback: Find closest
        closest_scale = min(all_scales, 
                          key=lambda x: min(abs(mapped_score - Decimal(str(x['min_marks']))), 
                                           abs(mapped_score - Decimal(str(x['max_marks'])))))
        
        return closest_scale['id']

    except Exception as e:
        logger.error(f"Error fetching grade scale ID for raw score {raw_score}: {e}", exc_info=True)
        return None

def get_max_scale_score(db, academic_id: int, grade_group_id: int) -> Decimal:
    """Fetches the maximum possible score defined in the grade scales."""
    try:
        query = text("SELECT MAX(max_marks) as highest_mark FROM grade_scale WHERE academic_id = :academic_id AND grade_group_id = :grade_group_id")
        result = db.execute(query, {
            "academic_id": academic_id, 
            "grade_group_id": grade_group_id
        }).fetchone()
        
        if result and result[0] is not None:
             return Decimal(str(result[0]))
        return Decimal('100.0') # Default fallback
    except Exception as e:
        logger.error(f"Error fetching max scale score: {e}")
        return Decimal('100.0')
