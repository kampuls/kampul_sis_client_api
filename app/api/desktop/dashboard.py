"""Typed, permission-aware dashboard data for the always-online desktop client."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core import get_db
from ...models import User
from .data import get_current_desktop_user


router = APIRouter()


def _mapping(row: Any) -> Mapping[str, Any]:
    return row._mapping if hasattr(row, "_mapping") else row


def _json_number(value: Any) -> float:
    """Return monetary aggregates as JSON numbers for desktop decimal fields."""
    if value is None:
        return 0.0
    return float(Decimal(str(value)))


def _integer(value: Any) -> int:
    return int(value or 0)


def _has_permission(db: Session, role_id: int, permission_name: str) -> bool:
    result = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM role_permissions rp
            INNER JOIN permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = :role_id AND p.permission_name = :permission_name
            """
        ),
        {"role_id": role_id, "permission_name": permission_name},
    ).scalar()
    return _integer(result) > 0


def _resolve_period(
    db: Session,
    academic_id: int,
    period: str,
    today: date,
) -> Tuple[datetime, datetime, str]:
    if period == "30d":
        start = datetime.combine(today - timedelta(days=29), time.min)
        return start, datetime.combine(today + timedelta(days=1), time.min), "Last 30 days"

    if period == "academic":
        row = db.execute(
            text(
                """
                SELECT academic_start, academic_end
                FROM academic
                WHERE id = :academic_id
                """
            ),
            {"academic_id": academic_id},
        ).first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The selected academic year was not found.",
            )
        values = _mapping(row)
        academic_start = values.get("academic_start")
        academic_end = values.get("academic_end")
        if not academic_start or not academic_end:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The selected academic year has no start or end date.",
            )
        if isinstance(academic_start, datetime):
            academic_start = academic_start.date()
        if isinstance(academic_end, datetime):
            academic_end = academic_end.date()
        return (
            datetime.combine(academic_start, time.min),
            datetime.combine(academic_end + timedelta(days=1), time.min),
            "Academic year",
        )

    start = datetime(today.year, today.month, 1)
    if today.month == 12:
        end = datetime(today.year + 1, 1, 1)
    else:
        end = datetime(today.year, today.month + 1, 1)
    return start, end, "This month"


def _filters(rows: Iterable[Any], name_column: str) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for row in rows:
        values = _mapping(row)
        result.append({"id": _integer(values.get("id")), "name": values.get(name_column) or ""})
    return result


@router.get("/overview")
def get_dashboard_overview(
    academic_id: int = Query(0, ge=0),
    branch_id: int = Query(0, ge=0),
    program_id: int = Query(0, ge=0),
    period: str = Query("month", pattern="^(month|30d|academic)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    """Return one live dashboard snapshot with filter options and operational metrics."""

    role_id = _integer(current_user.role)
    if not _has_permission(db, role_id, "ViewDashboard"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view the dashboard.",
        )
    can_view_basic = _has_permission(db, role_id, "DashboardBasic")
    can_view_accounting = _has_permission(db, role_id, "DashboardAccounting")

    now = datetime.now()
    today = now.date()
    if academic_id > 0:
        academic = db.execute(
            text(
                """
                SELECT id, academic_name, academic_us_name
                FROM academic
                WHERE id = :academic_id
                """
            ),
            {"academic_id": academic_id},
        ).first()
    else:
        # A fresh desktop session may not have loaded GlobalSettings yet. Resolve
        # the current server-owned academic year, falling back to the newest one,
        # so the first dashboard response can populate the academic selector.
        academic = db.execute(
            text(
                """
                SELECT id, academic_name, academic_us_name
                FROM academic
                ORDER BY CASE
                    WHEN academic_start IS NOT NULL
                     AND academic_end IS NOT NULL
                     AND :today BETWEEN DATE(academic_start) AND DATE(academic_end)
                    THEN 0 ELSE 1
                END,
                id DESC
                LIMIT 1
                """
            ),
            {"today": today},
        ).first()
    if academic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No academic year is available for the dashboard.",
        )
    academic_id = _integer(_mapping(academic).get("id"))

    can_view_all_branches = _has_permission(db, role_id, "ViewAllBranches")
    user_branch_id = _integer(current_user.workplace)
    if not can_view_all_branches:
        if user_branch_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has no branch scope for dashboard data.",
            )
        if branch_id not in (0, user_branch_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view another branch.",
            )
        effective_branch_id = user_branch_id
    else:
        effective_branch_id = branch_id

    if effective_branch_id > 0:
        branch_exists = db.execute(
            text("SELECT COUNT(*) FROM branch WHERE id = :branch_id"),
            {"branch_id": effective_branch_id},
        ).scalar()
        if _integer(branch_exists) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The selected branch was not found.",
            )

    if program_id > 0:
        program_exists = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM program
                WHERE id = :program_id AND academic_id = :academic_id
                """
            ),
            {"program_id": program_id, "academic_id": academic_id},
        ).scalar()
        if _integer(program_exists) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The selected program is not available in this academic year.",
            )

    start_at, end_at, period_label = _resolve_period(db, academic_id, period, today)
    params: Dict[str, Any] = {
        "academic_id": academic_id,
        "branch_id": effective_branch_id,
        "program_id": program_id,
        "start_at": start_at,
        "end_at": end_at,
        "today": today,
        "due_soon": today + timedelta(days=7),
    }

    branch_student = " AND s.branch = :branch_id" if effective_branch_id > 0 else ""
    branch_invoice = " AND i.branch_id = :branch_id" if effective_branch_id > 0 else ""
    branch_user = " AND u.workplace = :branch_id" if effective_branch_id > 0 else ""
    branch_cash = (
        " AND (i.branch_id = :branch_id OR "
        "(i.id IS NULL AND account_scope.branch_id = :branch_id))"
        if effective_branch_id > 0
        else ""
    )
    program_learning = " AND l.programid = :program_id" if program_id > 0 else ""
    program_invoice = (
        " AND EXISTS (SELECT 1 FROM invoice_items selected_program "
        "WHERE selected_program.invoice_id = i.id "
        "AND selected_program.academic_id = :academic_id "
        "AND selected_program.table_name = 'program' "
        "AND selected_program.itemId = :program_id)"
        if program_id > 0
        else ""
    )

    academic_rows = db.execute(
        text(
            """
            SELECT id,
                   COALESCE(NULLIF(academic_us_name, ''), academic_name) AS display_name
            FROM academic
            ORDER BY id DESC
            """
        )
    ).all()
    if can_view_all_branches:
        branch_rows = db.execute(
            text("SELECT id, branch_name FROM branch ORDER BY branch_name")
        ).all()
    else:
        branch_rows = db.execute(
            text(
                "SELECT id, branch_name FROM branch WHERE id = :branch_id ORDER BY branch_name"
            ),
            {"branch_id": user_branch_id},
        ).all()
    program_rows = db.execute(
        text(
            """
            SELECT id, program_name
            FROM program
            WHERE academic_id = :academic_id
            ORDER BY program_name
            """
        ),
        {"academic_id": academic_id},
    ).all()

    student_row = _mapping(
        db.execute(
            text(
                f"""
                SELECT SUM(CASE WHEN s.status = 1 THEN 1 ELSE 0 END) AS active_students,
                       SUM(CASE WHEN s.status = 1 AND s.gender IN ('ស្រី', 'female', 'Female') THEN 1 ELSE 0 END) AS female_students,
                       SUM(CASE WHEN s.status = 1 AND s.created_at >= :start_at AND s.created_at < :end_at THEN 1 ELSE 0 END) AS new_students,
                       SUM(CASE WHEN s.status IN (3, 5) THEN 1 ELSE 0 END) AS stopped_students,
                       SUM(CASE WHEN s.status = 2 THEN 1 ELSE 0 END) AS inactive_students
                FROM students s
                WHERE 1 = 1
                  {branch_student}
                  AND (
                      (s.status = 1 AND EXISTS (
                          SELECT 1
                          FROM learning l
                          WHERE l.studentid = s.id
                            AND l.academicid = :academic_id
                            {program_learning}
                      ))
                      OR (s.status <> 1 AND (
                          s.academic = :academic_id
                          OR EXISTS (
                              SELECT 1
                              FROM learning l
                              WHERE l.studentid = s.id
                                AND l.academicid = :academic_id
                                {program_learning}
                          )
                      ))
                  )
                """
            ),
            params,
        ).first()
    )

    staff_row = _mapping(
        db.execute(
            text(
                f"""
                SELECT SUM(CASE WHEN u.status = 1 THEN 1 ELSE 0 END) AS active_staff,
                       SUM(CASE WHEN u.status <> 1 THEN 1 ELSE 0 END) AS inactive_staff
                FROM users u
                WHERE 1 = 1 {branch_user}
                """
            ),
            params,
        ).first()
    )

    invoice_row = _mapping(
        db.execute(
            text(
                f"""
                SELECT COUNT(*) AS invoice_count,
                       SUM(CASE WHEN COALESCE(i.remaining_amount, 0) <= 0 THEN 1 ELSE 0 END) AS paid_count,
                       SUM(CASE WHEN COALESCE(i.paid_amount, 0) > 0 AND COALESCE(i.remaining_amount, 0) > 0
                                AND (i.due_date IS NULL OR DATE(i.due_date) >= :today) THEN 1 ELSE 0 END) AS partial_count,
                       SUM(CASE WHEN COALESCE(i.paid_amount, 0) <= 0 AND COALESCE(i.remaining_amount, 0) > 0
                                AND (i.due_date IS NULL OR DATE(i.due_date) >= :today) THEN 1 ELSE 0 END) AS unpaid_count,
                       SUM(CASE WHEN COALESCE(i.remaining_amount, 0) > 0 AND DATE(i.due_date) < :today THEN 1 ELSE 0 END) AS overdue_count,
                       SUM(CASE WHEN COALESCE(i.remaining_amount, 0) > 0 AND DATE(i.due_date) < :today
                                THEN i.remaining_amount ELSE 0 END) AS overdue_amount,
                       SUM(CASE WHEN COALESCE(i.remaining_amount, 0) > 0
                                 AND DATE(COALESCE(i.next_payment, i.due_date)) BETWEEN :today AND :due_soon
                                THEN 1 ELSE 0 END) AS due_soon_count,
                       SUM(CASE WHEN COALESCE(i.remaining_amount, 0) > 0 THEN i.remaining_amount ELSE 0 END) AS outstanding_amount
                FROM invoice i
                WHERE i.academic_id = :academic_id
                  AND COALESCE(i.payment_status, '') <> 'Void'
                  {branch_invoice}
                  {program_invoice}
                """
            ),
            params,
        ).first()
    )

    cash_row = _mapping(
        db.execute(
            text(
                f"""
                SELECT SUM(CASE WHEN lt.currency = 'USD' AND lt.amount > 0 THEN lt.amount ELSE 0 END) AS collected_usd,
                       SUM(CASE WHEN lt.currency = 'KHR' AND lt.amount > 0 THEN lt.amount ELSE 0 END) AS collected_khr,
                       ABS(SUM(CASE WHEN lt.currency = 'USD' AND lt.amount < 0 THEN lt.amount ELSE 0 END)) AS expense_usd,
                       ABS(SUM(CASE WHEN lt.currency = 'KHR' AND lt.amount < 0 THEN lt.amount ELSE 0 END)) AS expense_khr
                FROM logtransaction lt
                LEFT JOIN invoice i ON i.ref = lt.ref
                LEFT JOIN accounts account_scope ON account_scope.id = lt.accounts_id
                WHERE lt.created_at >= :start_at AND lt.created_at < :end_at
                  AND (i.academic_id = :academic_id OR account_scope.academic_id = :academic_id)
                  {branch_cash}
                  {program_invoice}
                """
            ),
            params,
        ).first()
    )

    attendance_rows = db.execute(
        text(
            f"""
            SELECT da.status, COUNT(DISTINCT da.student_id) AS status_count
            FROM daily_attendance da
            INNER JOIN students s ON s.id = da.student_id
            WHERE DATE(da.attendance_date) = :today
              AND da.academic_id = :academic_id
              {branch_student}
              {"AND da.program_id = :program_id" if program_id > 0 else ""}
            GROUP BY da.status
            """
        ),
        params,
    ).all()
    attendance = {"present": 0, "late": 0, "permission": 0, "absent": 0}
    attendance_status_map = {
        "ispresent": "present",
        "islate": "late",
        "ispermission": "permission",
        "isabsent": "absent",
    }
    for row in attendance_rows:
        values = _mapping(row)
        key = attendance_status_map.get(str(values.get("status") or "").lower())
        if key:
            attendance[key] = _integer(values.get("status_count"))
    attendance_taken = sum(attendance.values())
    attendance["not_taken"] = max(_integer(student_row.get("active_students")) - attendance_taken, 0)
    attendance["rate"] = (
        round((attendance["present"] + attendance["late"]) * 100.0 / attendance_taken, 1)
        if attendance_taken
        else 0.0
    )

    span_days = max((end_at - start_at).days, 1)
    trend_format = "%Y-%m" if span_days > 90 else "%Y-%m-%d"
    trend_rows = db.execute(
        text(
            f"""
            SELECT DATE_FORMAT(lt.created_at, '{trend_format}') AS period_key,
                   SUM(CASE WHEN lt.currency = 'USD' AND lt.amount > 0 THEN lt.amount ELSE 0 END) AS collected_usd,
                   SUM(CASE WHEN lt.currency = 'USD' AND lt.amount < 0 THEN ABS(lt.amount) ELSE 0 END) AS expense_usd
            FROM logtransaction lt
            LEFT JOIN invoice i ON i.ref = lt.ref
            LEFT JOIN accounts account_scope ON account_scope.id = lt.accounts_id
            WHERE lt.created_at >= :start_at AND lt.created_at < :end_at
              AND (i.academic_id = :academic_id OR account_scope.academic_id = :academic_id)
              {branch_cash}
              {program_invoice}
            GROUP BY DATE_FORMAT(lt.created_at, '{trend_format}')
            ORDER BY period_key
            """
        ),
        params,
    ).all()
    trend = [
        {
            "label": str(_mapping(row).get("period_key") or ""),
            "collected_usd": _json_number(_mapping(row).get("collected_usd")),
            "expense_usd": _json_number(_mapping(row).get("expense_usd")),
        }
        for row in trend_rows
    ]

    comparison_branch_condition = "" if can_view_all_branches else "WHERE b.id = :user_branch_id"
    comparison_params = dict(params)
    comparison_params["user_branch_id"] = user_branch_id
    comparison_rows = db.execute(
        text(
            f"""
            SELECT b.id, b.branch_name,
                   (SELECT COUNT(*)
                    FROM students s
                    WHERE s.status = 1 AND s.branch = b.id
                      AND EXISTS (
                          SELECT 1 FROM learning l
                          WHERE l.studentid = s.id AND l.academicid = :academic_id
                          {program_learning}
                      )) AS active_students,
                   (SELECT COALESCE(SUM(i.remaining_amount), 0)
                    FROM invoice i
                    WHERE i.academic_id = :academic_id AND i.branch_id = b.id
                      AND COALESCE(i.payment_status, '') <> 'Void' AND COALESCE(i.remaining_amount, 0) > 0
                      {program_invoice}) AS outstanding_amount,
                   (SELECT COALESCE(SUM(lt.amount), 0)
                    FROM logtransaction lt
                    INNER JOIN invoice i ON i.ref = lt.ref
                    WHERE i.academic_id = :academic_id AND i.branch_id = b.id
                      AND lt.currency = 'USD' AND lt.amount > 0
                      AND lt.created_at >= :start_at AND lt.created_at < :end_at
                      {program_invoice}) AS collected_usd
            FROM branch b
            {comparison_branch_condition}
            ORDER BY collected_usd DESC, b.branch_name
            """
        ),
        comparison_params,
    ).all()
    branch_comparison = [
        {
            "branch_id": _integer(_mapping(row).get("id")),
            "branch_name": _mapping(row).get("branch_name") or "",
            "active_students": _integer(_mapping(row).get("active_students")),
            "collected_usd": _json_number(_mapping(row).get("collected_usd")),
            "outstanding_amount": _json_number(_mapping(row).get("outstanding_amount")),
        }
        for row in comparison_rows
    ]

    recent_rows = db.execute(
        text(
            f"""
            SELECT i.id, i.invoice_no, i.ref, i.paid_amount, i.remaining_amount,
                   CASE
                       WHEN COALESCE(i.remaining_amount, 0) <= 0 THEN 'Paid'
                       WHEN DATE(COALESCE(i.next_payment, i.due_date)) < :today THEN 'Overdue'
                       WHEN COALESCE(i.paid_amount, 0) > 0 THEN 'Partial'
                       ELSE 'Unpaid'
                   END AS payment_status,
                   i.payment_method, i.created_invoice_at,
                   s.kName, s.eName, s.is_foreigner, b.branch_name
            FROM invoice i
            LEFT JOIN students s ON s.id = i.student_id
            LEFT JOIN branch b ON b.id = i.branch_id
            WHERE i.academic_id = :academic_id
              AND i.created_invoice_at >= :start_at AND i.created_invoice_at < :end_at
              {branch_invoice}
              {program_invoice}
            ORDER BY i.created_invoice_at DESC, i.id DESC
            LIMIT 8
            """
        ),
        params,
    ).all()
    recent_payments: List[Dict[str, Any]] = []
    for row in recent_rows:
        values = _mapping(row)
        khmer_name = str(values.get("kName") or "").strip()
        english_name = str(values.get("eName") or "").strip()
        student_name = english_name if _integer(values.get("is_foreigner")) == 2 else khmer_name
        if not student_name:
            student_name = english_name or khmer_name
        payment_status = str(values.get("payment_status") or "")
        recent_payments.append(
            {
                "invoice_id": _integer(values.get("id")),
                "invoice_no": values.get("invoice_no") or values.get("ref") or "",
                "student_name": student_name,
                "branch_name": values.get("branch_name") or "",
                "paid_amount": _json_number(values.get("paid_amount")),
                "remaining_amount": _json_number(values.get("remaining_amount")),
                "status": payment_status,
                "payment_method": values.get("payment_method") or "",
                "created_at": values.get("created_invoice_at"),
            }
        )

    selected_academic = _mapping(academic)
    return {
        "generated_at": now,
        "scope": {
            "academic_id": academic_id,
            "academic_name": selected_academic.get("academic_us_name")
            or selected_academic.get("academic_name")
            or "",
            "branch_id": effective_branch_id,
            "program_id": program_id,
            "period": period,
            "period_label": period_label,
            "start_at": start_at,
            "end_at": end_at,
            "can_view_all_branches": can_view_all_branches,
        },
        "filters": {
            "academics": _filters(academic_rows, "display_name"),
            "branches": _filters(branch_rows, "branch_name"),
            "programs": _filters(program_rows, "program_name"),
        },
        "permissions": {
            "can_view_basic": can_view_basic,
            "can_view_accounting": can_view_accounting,
        },
        "summary": {
            "active_students": _integer(student_row.get("active_students")) if can_view_basic else 0,
            "female_students": _integer(student_row.get("female_students")) if can_view_basic else 0,
            "new_students": _integer(student_row.get("new_students")) if can_view_basic else 0,
            "stopped_students": _integer(student_row.get("stopped_students")) if can_view_basic else 0,
            "inactive_students": _integer(student_row.get("inactive_students")) if can_view_basic else 0,
            "active_staff": _integer(staff_row.get("active_staff")) if can_view_basic else 0,
            "inactive_staff": _integer(staff_row.get("inactive_staff")) if can_view_basic else 0,
            "collected_usd": _json_number(cash_row.get("collected_usd")) if can_view_accounting else 0.0,
            "collected_khr": _json_number(cash_row.get("collected_khr")) if can_view_accounting else 0.0,
            "expense_usd": _json_number(cash_row.get("expense_usd")) if can_view_accounting else 0.0,
            "expense_khr": _json_number(cash_row.get("expense_khr")) if can_view_accounting else 0.0,
            "outstanding_amount": _json_number(invoice_row.get("outstanding_amount")) if can_view_accounting else 0.0,
            "overdue_amount": _json_number(invoice_row.get("overdue_amount")) if can_view_accounting else 0.0,
            "overdue_count": _integer(invoice_row.get("overdue_count")) if can_view_accounting else 0,
            "due_soon_count": _integer(invoice_row.get("due_soon_count")) if can_view_accounting else 0,
        },
        "payment_status": {
            "paid": _integer(invoice_row.get("paid_count")) if can_view_accounting else 0,
            "partial": _integer(invoice_row.get("partial_count")) if can_view_accounting else 0,
            "unpaid": _integer(invoice_row.get("unpaid_count")) if can_view_accounting else 0,
            "overdue": _integer(invoice_row.get("overdue_count")) if can_view_accounting else 0,
        },
        "attendance": attendance if can_view_basic else {
            "present": 0,
            "late": 0,
            "permission": 0,
            "absent": 0,
            "not_taken": 0,
            "rate": 0.0,
        },
        "trend": trend if can_view_accounting else [],
        "branch_comparison": branch_comparison if can_view_accounting else [],
        "student_breakdown": [
            {"key": "active", "name": "សិស្សសកម្ម", "count": _integer(student_row.get("active_students"))},
            {"key": "new", "name": "ចុះឈ្មោះថ្មី", "count": _integer(student_row.get("new_students"))},
            {"key": "stopped", "name": "ឈប់រៀន", "count": _integer(student_row.get("stopped_students"))},
            {"key": "inactive", "name": "អសកម្ម", "count": _integer(student_row.get("inactive_students"))},
        ] if can_view_basic else [],
        "recent_payments": recent_payments if can_view_accounting else [],
    }
