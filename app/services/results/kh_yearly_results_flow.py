from decimal import Decimal
from sqlalchemy import text
from ...utils.results_utils import (
    safe_decimal,
    is_fail_grade,
    get_grade_from_score_raw,
    learning_class_scope_sql_suffix,
)
from .kh_monthly_results_flow import generate_kh_monthly_report
import logging

logger = logging.getLogger(__name__)


def _normalize_subject_mark(raw: Decimal, full_m: Decimal, calc_m: Decimal) -> Decimal:
    if full_m > 0:
        return (raw / full_m) * calc_m
    return raw


def _ecs_label_to_subject_id(
    db,
    sem1_ecs,
    sem2_ecs,
) -> dict[str, int]:
    """Map subject label -> id using ECS lists (same source as SEM detail sheets)."""
    label_to_sub_id: dict[str, int] = {}
    for ecs in (sem1_ecs, sem2_ecs):
        if not ecs:
            continue
        rows = db.execute(
            text("""
                SELECT s.id, s.subject_name
                FROM exam_calculate_sign_subjects ecss
                JOIN subjects s ON s.id = ecss.subject_id
                WHERE ecss.exam_calculate_sign_id = :ecs_id
            """),
            {"ecs_id": int(ecs[0])},
        ).fetchall()
        for sid, name in rows:
            label = (name or "").strip()
            if label:
                label_to_sub_id[label] = int(sid)
    return label_to_sub_id


def _resolve_subject_mark_rules(
    sub_id: int | None,
    subj_rules: dict[int, dict],
    sem1_item: dict | None,
    sem2_item: dict | None,
) -> tuple[Decimal, Decimal]:
    if sub_id is not None and sub_id in subj_rules:
        rule = subj_rules[sub_id]
        return rule["full_marks"], rule["calculate_marks"]

    for item in (sem1_item, sem2_item):
        if not item:
            continue
        max_score = item.get("max_score")
        if max_score is None:
            continue
        full_m = safe_decimal(max_score, Decimal("0"))
        if full_m > 0:
            return full_m, Decimal("100")

    return Decimal("10"), Decimal("100")


def _yearly_subject_grade_from_sem_items(
    db,
    *,
    academic_id: int,
    grade_group_id: int,
    sem1_item: dict | None,
    sem2_item: dict | None,
    yearly_avg: Decimal,
    full_m: Decimal,
    calc_m: Decimal,
) -> tuple[str, str]:
    """
    Grade on the same scale as KH SEM subject rows:
    normalize each semester mark, average, then map to grade_scale.
    """
    normalized_parts: list[Decimal] = []
    for item in (sem1_item, sem2_item):
        if not item or item.get("score") is None:
            continue
        raw = safe_decimal(item["score"], Decimal("0"))
        item_full = safe_decimal(item.get("max_score"), full_m)
        if item_full <= 0:
            item_full = full_m
        if item_full > 0:
            normalized_parts.append((raw / item_full) * calc_m)

    if normalized_parts:
        grade_input = sum(normalized_parts) / Decimal(len(normalized_parts))
    else:
        grade_input = _normalize_subject_mark(yearly_avg, full_m, calc_m)

    return get_grade_from_score_raw(
        grade_input, db, academic_id, grade_group_id, calc_m
    )


def _competition_rank(student_id: int, ranked: list[tuple[int, Decimal]]) -> str:
    """Return rank string for student_id from sorted (sid, score) desc list."""
    if not ranked:
        return "-"
    current_rank = 0
    last_score = Decimal("-1")
    for idx, (sid, score) in enumerate(ranked):
        if idx == 0:
            current_rank = 1
        elif score < last_score:
            current_rank = idx + 1
        last_score = score
        if sid == student_id:
            return str(current_rank)
    return "-"


def _resolve_marks_system_id(
    db,
    academic_id: int,
    program_id: int,
    grade_group_id: int,
    marks_system_id,
    sign_code: str,
    result_name: str,
) -> int | None:
    if marks_system_id and int(marks_system_id) > 0:
        return int(marks_system_id)
    code = (sign_code or "").strip()
    if code:
        found = db.execute(
            text("""
                SELECT id FROM marks_system
                WHERE academic_id = :aid AND program_id = :pid AND grade_group_id = :ggid
                  AND marks_code = :code
                LIMIT 1
            """),
            {
                "aid": academic_id,
                "pid": program_id,
                "ggid": grade_group_id,
                "code": code,
            },
        ).fetchone()
        if found:
            return int(found[0])
    name = (result_name or "").strip()
    if name:
        found_name = db.execute(
            text("""
                SELECT id FROM marks_system
                WHERE academic_id = :aid AND program_id = :pid AND grade_group_id = :ggid
                  AND marks_name = :name
                LIMIT 1
            """),
            {
                "aid": academic_id,
                "pid": program_id,
                "ggid": grade_group_id,
                "name": name,
            },
        ).fetchone()
        if found_name:
            return int(found_name[0])
    return None


def _fetch_sem_ecs_row(
    db,
    academic_id: int,
    program_id: int,
    grade_group_id: int,
    sign_code: str,
):
    return db.execute(
        text("""
            SELECT id, marks_system_id, sign_code, result_name, exam_type,
                   formula_expression, divide_by_multiplier
            FROM exam_calculate_sign
            WHERE academic_id = :aid
              AND program_id = :pid
              AND grade_group_id = :ggid
              AND sign_code = :sign
              AND is_active = 1
            ORDER BY id DESC
            LIMIT 1
        """),
        {
            "aid": academic_id,
            "pid": program_id,
            "ggid": grade_group_id,
            "sign": sign_code,
        },
    ).fetchone()


def _subject_items_by_label_from_sem_ecs(
    db,
    student_id: int,
    sem_ecs_row,
    *,
    academic_id: int,
    program_id: int,
    grade_group_id: int,
    grade_id: int,
    shift_id: int,
    grade_type_id: int | None,
    branch_id: int | None,
) -> dict[str, dict]:
    """Same subject marks as KH SEM1/SEM2 detail (generate_kh_monthly_report)."""
    if not sem_ecs_row:
        return {}

    ecs_id = int(sem_ecs_row[0])
    ms_id = _resolve_marks_system_id(
        db,
        academic_id,
        program_id,
        grade_group_id,
        sem_ecs_row[1],
        str(sem_ecs_row[2] or ""),
        str(sem_ecs_row[3] or ""),
    )
    if not ms_id:
        return {}

    report = generate_kh_monthly_report(
        db,
        student_id,
        academic_id,
        program_id,
        grade_group_id,
        grade_id,
        shift_id,
        marks_system_id=ms_id,
        ecs_id=ecs_id,
        formula=str(sem_ecs_row[5] or ""),
        divide_by=safe_decimal(sem_ecs_row[6], Decimal("1")),
        exam_type=str(sem_ecs_row[4] or "input"),
        grade_type_id=grade_type_id,
        sign_code=str(sem_ecs_row[2] or "").upper(),
        branch_id=branch_id,
    )

    by_label: dict[str, dict] = {}
    for item in report.get("items") or []:
        if item.get("type") != "subject":
            continue
        label = (item.get("label") or "").strip()
        if label:
            by_label[label] = item
    return by_label


def _list_class_student_ids(
    db,
    *,
    academic_id: int,
    program_id: int,
    grade_id: int,
    shift_id: int,
    grade_type_id: int | None,
    branch_id: int | None,
) -> list[int]:
    scope_sql, scope_params = learning_class_scope_sql_suffix(
        grade_type_id, branch_id
    )
    rows = db.execute(
        text(f"""
            SELECT DISTINCT l.studentid
            FROM learning l
            JOIN students st ON l.studentid = st.id
            WHERE l.programid = :pid
              AND l.gradeid = :gid
              AND l.shiftid = :shift_id
              AND l.academicid = :aid
              AND st.status = 1
              {scope_sql}
        """),
        {
            "aid": academic_id,
            "pid": program_id,
            "gid": grade_id,
            "shift_id": shift_id,
            **scope_params,
        },
    ).fetchall()
    return [int(r[0]) for r in rows]


def _yearly_subject_metrics_from_sem_items(
    sem1_item: dict | None,
    sem2_item: dict | None,
    subj_rules: dict,
    sub_id: int,
) -> tuple[Decimal | None, Decimal | None]:
    """
  Yearly per-subject metrics on the raw mark scale (e.g. out of 10).

  Subject A yearly average = mean(SEM1 subject A raw, SEM2 subject A raw).
  Total = sum of those raw marks (SEM1 + SEM2 when both exist).
    """
    raw_marks: list[Decimal] = []

    for item in (sem1_item, sem2_item):
        if not item or item.get("score") is None:
            continue
        raw_marks.append(safe_decimal(item["score"], Decimal("0")))

    if not raw_marks:
        return None, None

    raw_total = sum(raw_marks)
    yearly_avg = raw_total / Decimal(len(raw_marks))
    return raw_total, yearly_avg

def _append_kh_yearly_subject_items(
    db,
    details: dict,
    *,
    student_id: int,
    academic_id: int,
    program_id: int,
    grade_group_id: int,
    grade_id: int,
    shift_id: int,
    grade_type_id: int | None,
    branch_id: int | None,
) -> None:
    """Per-subject yearly rows: average of SEM1 + SEM2 (same source as SEM detail sheets)."""
    sem1_ecs = _fetch_sem_ecs_row(
        db, academic_id, program_id, grade_group_id, "SEM1"
    )
    sem2_ecs = _fetch_sem_ecs_row(
        db, academic_id, program_id, grade_group_id, "SEM2"
    )
    if not sem1_ecs and not sem2_ecs:
        return

    sem_ctx = {
        "academic_id": academic_id,
        "program_id": program_id,
        "grade_group_id": grade_group_id,
        "grade_id": grade_id,
        "shift_id": shift_id,
        "grade_type_id": grade_type_id,
        "branch_id": branch_id,
    }
    class_ctx = {
        "academic_id": academic_id,
        "program_id": program_id,
        "grade_id": grade_id,
        "shift_id": shift_id,
        "grade_type_id": grade_type_id,
        "branch_id": branch_id,
    }

    sem1_by_label = (
        _subject_items_by_label_from_sem_ecs(db, student_id, sem1_ecs, **sem_ctx)
        if sem1_ecs
        else {}
    )
    sem2_by_label = (
        _subject_items_by_label_from_sem_ecs(db, student_id, sem2_ecs, **sem_ctx)
        if sem2_ecs
        else {}
    )

    all_labels = sorted(set(sem1_by_label) | set(sem2_by_label))
    if not all_labels:
        return

    label_to_sub_id = _ecs_label_to_subject_id(db, sem1_ecs, sem2_ecs)
    for label in all_labels:
        if label not in label_to_sub_id:
            row = db.execute(
                text(
                    "SELECT id FROM subjects WHERE subject_name = :name LIMIT 1"
                ),
                {"name": label},
            ).fetchone()
            if row:
                label_to_sub_id[label] = int(row[0])

    subject_ids = list(dict.fromkeys(label_to_sub_id.values()))

    subj_rules: dict[int, dict] = {}
    if subject_ids:
        rules_rows = db.execute(
            text("""
                SELECT subject_id, full_marks, calculate_marks
                FROM subjects_group
                WHERE academic_id = :aid
                  AND program_id = :pid
                  AND grade_group_id = :ggid
                  AND subject_id IN :subject_ids
            """),
            {
                "aid": academic_id,
                "pid": program_id,
                "ggid": grade_group_id,
                "subject_ids": tuple(subject_ids),
            },
        ).fetchall()
        for r in rules_rows:
            subj_rules[int(r[0])] = {
                "full_marks": safe_decimal(r[1], Decimal("100.0")),
                "calculate_marks": safe_decimal(r[2], Decimal("100.0")),
            }

    class_ids = _list_class_student_ids(db, **class_ctx)
    if student_id not in class_ids:
        class_ids.append(student_id)

    # Cache SEM subject maps per student for ranking (2 reports per student, not per subject)
    sem_maps_cache: dict[int, tuple[dict[str, dict], dict[str, dict]]] = {}

    def sem_maps_for(sid: int) -> tuple[dict[str, dict], dict[str, dict]]:
        if sid not in sem_maps_cache:
            s1 = (
                _subject_items_by_label_from_sem_ecs(db, sid, sem1_ecs, **sem_ctx)
                if sem1_ecs
                else {}
            )
            s2 = (
                _subject_items_by_label_from_sem_ecs(db, sid, sem2_ecs, **sem_ctx)
                if sem2_ecs
                else {}
            )
            sem_maps_cache[sid] = (s1, s2)
        return sem_maps_cache[sid]

    for sid in class_ids:
        sem_maps_for(sid)

    yearly_items = []
    for label in all_labels:
        sub_id = label_to_sub_id.get(label)
        if sub_id is None:
            continue

        s1_item = sem1_by_label.get(label)
        s2_item = sem2_by_label.get(label)
        raw_total, yearly_avg = _yearly_subject_metrics_from_sem_items(
            s1_item, s2_item, subj_rules, sub_id
        )
        if yearly_avg is None:
            continue

        full_m, calc_m = _resolve_subject_mark_rules(
            sub_id, subj_rules, s1_item, s2_item
        )
        us_grade, kh_grade = _yearly_subject_grade_from_sem_items(
            db,
            academic_id=academic_id,
            grade_group_id=grade_group_id,
            sem1_item=s1_item,
            sem2_item=s2_item,
            yearly_avg=yearly_avg,
            full_m=full_m,
            calc_m=calc_m,
        )

        ranked: list[tuple[int, Decimal]] = []
        for sid in class_ids:
            s1_map, s2_map = sem_maps_for(sid)
            _, avg = _yearly_subject_metrics_from_sem_items(
                s1_map.get(label), s2_map.get(label), subj_rules, sub_id
            )
            if avg is not None:
                ranked.append((sid, avg))
        ranked.sort(key=lambda x: x[1], reverse=True)
        my_rank = _competition_rank(student_id, ranked)

        code = (s1_item or s2_item or {}).get("code")
        yearly_items.append(
            {
                "type": "yearly_subject",
                "label": label,
                "code": code,
                "score": float(raw_total),
                "average": float(yearly_avg),
                "grade": us_grade,
                "us_grade": us_grade,
                "kh_grade": kh_grade,
                "rank": my_rank,
                "max_score": float(full_m),
                "is_highlight": False,
                "is_failed": is_fail_grade(us_grade),
            }
        )

    details["items"].extend(yearly_items)

def generate_kh_yearly_report(
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
    Generates the yearly report for KH programs.
    - Breakdown by Semester Results (RSEM1, RSEM2)
    - Overall Yearly Summary (from marks_yearly)
    """
    
    details = {
        "items": [],
        "summary": {},
        "comment": ""
    }

    # 1. Fetch RSEM1 and RSEM2 results
    sem_configs_q = text("""
        SELECT id, sign_code, result_name 
        FROM exam_calculate_sign 
        WHERE academic_id = :aid AND program_id = :pid AND grade_group_id = :ggid AND sign_code IN ('RSEM1', 'RSEM2')
    """)
    sem_configs = db.execute(sem_configs_q, {
        "aid": academic_id,
        "pid": program_id,
        "ggid": grade_group_id
    }).fetchall()
    
    
    sign_codes = [r[1] for r in sem_configs]
    
    # Fetch RSEM1 and RSEM2 results directly from marks_semester via sign_code
    sem_data_map = {}
    
    sem_q = text("""
        SELECT ms.exam_name, ms.total, ms.average, gs.us_grade, gs.kh_grade, ecs.sign_code
        FROM marks_semester ms
        LEFT JOIN grade_scale gs ON ms.grade_scale_id = gs.id
        INNER JOIN exam_calculate_sign ecs ON ecs.result_name = ms.exam_name 
            AND ecs.academic_id = :aid 
            AND ecs.program_id = :pid 
            AND ecs.grade_group_id = :ggid 
            AND ecs.sign_code IN ('RSEM1', 'RSEM2')
        WHERE ms.student_id = :sid 
            AND ms.academic_id = :aid 
    """)
    
    sem_res = db.execute(sem_q, {
        "aid": academic_id,
        "pid": program_id,
        "ggid": grade_group_id,
        "sid": student_id
    }).fetchall()
    
    # Map results by sign_code
    for r in sem_res:
        s_code = r[5]
        sem_data_map[s_code] = r

    scope_sql, scope_params = learning_class_scope_sql_suffix(
        grade_type_id, branch_id
    )
    
    # Build Items: Semesters
    # Always display RSEM1 and RSEM2 in order
    term_order = ['RSEM1', 'RSEM2']
          
    for code in term_order:
        row = sem_data_map.get(code)
        
        if row:
            total = safe_decimal(row[1], Decimal('0'))
            avg = safe_decimal(row[2], Decimal('0'))
            grade = row[3] or '-'
            kh_grade = row[4] or ''
            
            # Calculate Rank for Semester (Scoped)
            rank_q = text(f"""
                SELECT COUNT(*) + 1
                FROM marks_semester ms
                JOIN learning l ON ms.student_id = l.studentid
                JOIN students st ON l.studentid = st.id
                WHERE ms.academic_id = :aid 
                  AND ms.program_id = :pid 
                  AND ms.grade_id = :gid
                  AND ms.exam_name = :ename
                  AND l.programid = :pid
                  AND l.gradeid = :gid
                  AND l.shiftid = :shift_id
                  AND l.academicid = :aid
                  {scope_sql}
                  AND st.status = 1
                  AND ms.average > :my_avg
            """)
            rank = db.execute(rank_q, {
                "aid": academic_id,
                "pid": program_id,
                "gid": grade_id,
                "shift_id": shift_id,
                "ename": row[0],
                "my_avg": avg,
                **scope_params,
            }).scalar()
            
            details["items"].append({
                "type": "semester",
                "label": row[0],  # Use exam_name from database
                "score": float(total),
                "average": float(avg),
                "grade": grade,
                "us_grade": grade,
                "kh_grade": kh_grade,
                "rank": str(rank) if rank else "-",
                "is_highlight": False,
                "is_failed": is_fail_grade(grade),
                "is_unavailable": False
            })

    try:
        _append_kh_yearly_subject_items(
            db,
            details,
            student_id=student_id,
            academic_id=academic_id,
            program_id=program_id,
            grade_group_id=grade_group_id,
            grade_id=grade_id,
            shift_id=shift_id,
            grade_type_id=grade_type_id,
            branch_id=branch_id,
        )
    except Exception as e:
        logger.error("KH yearly subject breakdown failed: %s", e, exc_info=True)

    # 3. Overall Yearly Summary
    # Filter directly by table marks_yearly using sign_code JOIN
    y_q = text("""
        SELECT my.total, my.average, my.teacher_comment, gs.us_grade, gs.kh_grade, my.exam_name
        FROM marks_yearly my
        LEFT JOIN grade_scale gs ON my.grade_scale_id = gs.id
        INNER JOIN exam_calculate_sign ecs ON ecs.result_name = my.exam_name
            AND ecs.academic_id = :aid
            AND ecs.sign_code = :sign_code
        WHERE my.student_id = :sid 
            AND my.academic_id = :aid 
    """)
    y_res = db.execute(y_q, {
        "sid": student_id,
        "aid": academic_id,
        "sign_code": sign_code
    }).fetchone()
    
    # Fallback: Fetch directly from marks_yearly if Strict JOIN failed
    if not y_res:
         y_q_fallback = text("""
            SELECT my.total, my.average, my.teacher_comment, gs.us_grade, gs.kh_grade, my.exam_name
            FROM marks_yearly my
            LEFT JOIN grade_scale gs ON my.grade_scale_id = gs.id
            WHERE my.student_id = :sid 
                AND my.academic_id = :aid 
            LIMIT 1
        """)
         y_res = db.execute(y_q_fallback, {
            "sid": student_id,
            "aid": academic_id
        }).fetchone()
    
    if y_res:
         # Calculate Rank for Yearly (Scoped)
         y_avg = safe_decimal(y_res[1], Decimal('0'))
         y_rank_q = text(f"""
            SELECT COUNT(*) + 1
            FROM marks_yearly my
            JOIN learning l ON my.student_id = l.studentid
            JOIN students st ON l.studentid = st.id
            WHERE my.academic_id = :aid 
              AND my.program_id = :pid 
              AND my.grade_id = :gid
              AND my.exam_name = :ename
              AND l.programid = :pid
              AND l.gradeid = :gid
              AND l.shiftid = :shift_id
              AND l.academicid = :aid
              {scope_sql}
              AND st.status = 1
              AND my.average > :my_avg
         """)
         y_rank = db.execute(y_rank_q, {
            "aid": academic_id,
            "pid": program_id,
            "gid": grade_id,
            "shift_id": shift_id,
            "ename": y_res[5],
            "my_avg": y_avg,
            **scope_params,
         }).scalar()

         details["summary"] = {
            "label": y_res[5] or "Yearly Result",
            "total": float(y_res[0]) if y_res[0] is not None else None,
            "score": float(y_res[0]) if y_res[0] is not None else None,  # UI expects 'score' for total
            "average": float(y_res[1]) if y_res[1] is not None else None,
            "grade": y_res[3] or "-",
            "us_grade": y_res[3] or "-",
            "kh_grade": y_res[4] or "-",
            "rank": str(y_rank) if y_rank else "-",
            "is_failed": is_fail_grade(y_res[3] or "-")
         }
         details["comment"] = y_res[2] or ""
    
    return details
