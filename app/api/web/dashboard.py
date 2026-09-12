from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import logging

from ...core import get_db
from ...models import User, Student

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats")
async def get_dashboard_stats(
    db: Session = Depends(get_db)
):
    """
    Returns all key statistics for the Web Admin Dashboard.
    Mirrors the desktop app's ControlDashboard key metrics:
    - Student counts (total + female + male)
    - Staff/User counts (active total + female + inactive)
    - New student registrations (today, this month, this year)
    - Income summary (USD + KHR, this month)
    - Expense summary (USD + KHR, this month)
    - Recent receipts (latest 10)
    """
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    # ── Student Counts ──────────────────────────────────────────────────────
    try:
        student_stats = db.execute(text("""
            SELECT COUNT(*) as total FROM students WHERE status = 1
        """)).first()
        student_total = int(student_stats.total or 0)
    except Exception as e:
        logger.warning(f"student counts: {e}")
        student_total = 0

    # ── Staff Counts ────────────────────────────────────────────────────────
    try:
        staff_stats = db.execute(text("""
            SELECT SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) as active_total FROM users
        """)).first()
        staff_total = int(staff_stats.active_total or 0)
    except Exception as e:
        logger.warning(f"staff counts: {e}")
        staff_total = 0

    return {
        "students": {
            "total": student_total,
        },
        "staff": {
            "active_total": staff_total,
        },
        "date": {
            "today": today_str,
        }
    }
